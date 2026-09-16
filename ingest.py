"""
ingest.py

Pulls Statcast batted-ball data for a date range, computes would-be-HR
outcomes across all 30 parks, and pushes the results straight to
Supabase -- no local database file needed. Safe to run repeatedly:
each calendar date is only ever counted once (tracked in the
`ingest_log` table), so re-running over an overlapping range just
skips dates already loaded.

This one script covers two situations:
    1. One-time historical backfill (wide date range, run locally --
       this can take hours for multiple seasons, so it's best run on
       your own machine rather than in a GitHub Actions job with a
       time limit).
    2. Nightly automatic updates (a single day's games, run by the
       GitHub Actions workflow in .github/workflows/daily-update.yml).

Usage:
    # Historical backfill (run locally):
    python ingest.py --start-date 2015-03-01 --end-date 2024-11-01

    # Daily update (what the GitHub Action runs automatically):
    python ingest.py   # defaults to "yesterday" if no dates given
"""

import argparse
import datetime as dt
import math
import os
import sys

import numpy as np
import pandas as pd
import psycopg2
import psycopg2.extras

import park_data
import trajectory

HC_X_ORIGIN = 125.42
HC_Y_ORIGIN = 198.27

CHUNK_DAYS = 10  # how many days per Statcast request while backfilling


def spray_angle_deg(hc_x: float, hc_y: float) -> float:
    return math.degrees(math.atan2(hc_x - HC_X_ORIGIN, HC_Y_ORIGIN - hc_y))


def _clean(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, np.generic):
        return val.item()
    return val


# Statcast's raw `player_name` column is the PITCHER on that pitch, not
# the batter. Batter names are looked up separately by MLBAM id.
_BATTER_NAME_CACHE = {}


def _format_name(last, first) -> str:
    last = str(last).strip().title() if last else ""
    first = str(first).strip().title() if first else ""
    if last and first:
        return f"{last}, {first}"
    return last or first or None


def ensure_batter_names_cached(batter_ids):
    to_fetch = sorted({
        int(bid) for bid in batter_ids
        if bid is not None and not pd.isna(bid) and int(bid) not in _BATTER_NAME_CACHE
    })
    if not to_fetch:
        return
    from pybaseball import playerid_reverse_lookup
    try:
        result = playerid_reverse_lookup(to_fetch, key_type="mlbam")
    except Exception as exc:  # noqa: BLE001
        print(f"  warning: name lookup failed for {len(to_fetch)} ids: {exc}", file=sys.stderr)
        return
    for _, row in result.iterrows():
        mlbam_id = int(row["key_mlbam"])
        _BATTER_NAME_CACHE[mlbam_id] = _format_name(row.get("name_last"), row.get("name_first"))
    for bid in to_fetch:
        _BATTER_NAME_CACHE.setdefault(bid, None)


def batter_name_for_id(batter_id):
    if batter_id is None or pd.isna(batter_id):
        return None
    return _BATTER_NAME_CACHE.get(int(batter_id))


def fetch_statcast_range(start: str, end: str) -> pd.DataFrame:
    from pybaseball import statcast
    return statcast(start_dt=start, end_dt=end, verbose=False)


def filter_batted_balls(df: pd.DataFrame) -> pd.DataFrame:
    needed = ["hc_x", "hc_y", "launch_speed", "launch_angle"]
    df = df.dropna(subset=needed)
    if "type" in df.columns:
        df = df[df["type"] == "X"]
    return df


def already_ingested_dates(pg_conn, start: dt.date, end: dt.date):
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT game_date FROM ingest_log WHERE game_date BETWEEN %s AND %s",
            (start, end),
        )
        return {row[0] for row in cur.fetchall()}


def compute_aggregates(df: pd.DataFrame):
    """
    Returns:
        season_totals: {(batter_name, season): [batted_balls, actual_hrs]}
        park_totals: {(batter_name, season, park_key): [would_all, would_actual]}
        dates_seen: {(date, batted_ball_count), ...} as a dict date -> count
    """
    if "batter" in df.columns:
        ensure_batter_names_cached(df["batter"].tolist())

    season_totals = {}
    park_totals = {}
    date_counts = {}

    for _, row in df.iterrows():
        game_date = pd.to_datetime(row.get("game_date")).date()
        season = game_date.year
        date_counts[game_date] = date_counts.get(game_date, 0) + 1

        hc_x = float(row["hc_x"])
        hc_y = float(row["hc_y"])
        launch_speed = float(row["launch_speed"])
        launch_angle = float(row["launch_angle"])
        spray = spray_angle_deg(hc_x, hc_y)

        batter_id = _clean(row.get("batter"))
        batter_name = batter_name_for_id(batter_id) or (f"MLBAM {batter_id}" if batter_id else None)
        if not batter_name:
            continue

        events = _clean(row.get("events"))
        was_hr = 1 if events == "home_run" else 0

        key = (batter_name, season)
        if key not in season_totals:
            season_totals[key] = [0, 0]
        season_totals[key][0] += 1
        season_totals[key][1] += was_hr

        points, _carry = trajectory.simulate_trajectory(launch_speed, launch_angle)
        for park_key in park_data.ALL_PARK_KEYS:
            fence_dist = park_data.fence_distance_at_spray_angle(park_key, spray)
            fence_h = park_data.fence_height(park_key)
            would_hr = int(trajectory.would_clear_fence(
                launch_speed, launch_angle, fence_dist, fence_h, points=points
            ))
            pkey = (batter_name, season, park_key)
            if pkey not in park_totals:
                park_totals[pkey] = [0, 0]
            park_totals[pkey][0] += would_hr
            if was_hr:
                park_totals[pkey][1] += would_hr

    return season_totals, park_totals, date_counts


def push_increment(pg_conn, season_totals, park_totals, date_counts, batch_size=2000):
    season_rows = [
        (name, season, counts[0], counts[1])
        for (name, season), counts in season_totals.items()
    ]
    park_rows = [
        (name, season, park_key, counts[0], counts[1])
        for (name, season, park_key), counts in park_totals.items()
    ]

    with pg_conn.cursor() as cur:
        for i in range(0, len(season_rows), batch_size):
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO player_season_summary
                    (batter_name, season, batted_balls_considered, actual_home_runs)
                VALUES %s
                ON CONFLICT (batter_name, season) DO UPDATE SET
                    batted_balls_considered = player_season_summary.batted_balls_considered
                        + EXCLUDED.batted_balls_considered,
                    actual_home_runs = player_season_summary.actual_home_runs
                        + EXCLUDED.actual_home_runs
                """,
                season_rows[i:i + batch_size],
            )

        for i in range(0, len(park_rows), batch_size):
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO player_park_season_summary
                    (batter_name, season, park_key, would_be_hrs_all, would_be_hrs_actual_only)
                VALUES %s
                ON CONFLICT (batter_name, season, park_key) DO UPDATE SET
                    would_be_hrs_all = player_park_season_summary.would_be_hrs_all
                        + EXCLUDED.would_be_hrs_all,
                    would_be_hrs_actual_only = player_park_season_summary.would_be_hrs_actual_only
                        + EXCLUDED.would_be_hrs_actual_only
                """,
                park_rows[i:i + batch_size],
            )

        date_rows = [(d, c) for d, c in date_counts.items()]
        if date_rows:
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO ingest_log (game_date, batted_balls_count)
                VALUES %s
                ON CONFLICT (game_date) DO NOTHING
                """,
                date_rows,
            )

    pg_conn.commit()


def chunk_date_range(start: dt.date, end: dt.date, chunk_days: int = CHUNK_DAYS):
    cur = start
    step = dt.timedelta(days=chunk_days)
    while cur <= end:
        chunk_end = min(cur + step - dt.timedelta(days=1), end)
        yield cur, chunk_end
        cur = chunk_end + dt.timedelta(days=1)


def run(conn_string: str, start_date: str, end_date: str):
    if not start_date and not end_date:
        yesterday = dt.date.today() - dt.timedelta(days=1)
        start = end = yesterday
    else:
        start = dt.date.fromisoformat(start_date) if start_date else dt.date.fromisoformat(end_date)
        end = dt.date.fromisoformat(end_date) if end_date else dt.date.fromisoformat(start_date)

    pg_conn = psycopg2.connect(conn_string)

    total_rows_ingested = 0
    for chunk_start, chunk_end in chunk_date_range(start, end):
        already = already_ingested_dates(pg_conn, chunk_start, chunk_end)
        print(f"pulling {chunk_start} .. {chunk_end} "
              f"({len(already)} date(s) already loaded, will skip)...", file=sys.stderr)

        try:
            df = fetch_statcast_range(chunk_start.isoformat(), chunk_end.isoformat())
        except Exception as exc:  # noqa: BLE001
            print(f"  fetch failed: {exc}", file=sys.stderr)
            continue

        if df is None or df.empty:
            print("  no rows returned", file=sys.stderr)
            continue

        df = filter_batted_balls(df)
        if df.empty:
            print("  no batted balls in range", file=sys.stderr)
            continue

        df["_game_date"] = pd.to_datetime(df["game_date"]).dt.date
        df = df[~df["_game_date"].isin(already)]
        if df.empty:
            print("  everything in this chunk was already loaded", file=sys.stderr)
            continue

        season_totals, park_totals, date_counts = compute_aggregates(df)
        push_increment(pg_conn, season_totals, park_totals, date_counts)

        n = sum(date_counts.values())
        total_rows_ingested += n
        print(f"  ingested {n} batted balls across {len(date_counts)} date(s)", file=sys.stderr)

    pg_conn.close()
    print(f"Done. {total_rows_ingested} new batted balls ingested.")


def main():
    parser = argparse.ArgumentParser(description="Ingest Statcast data into Supabase")
    parser.add_argument("--start-date", type=str, default=None, help="YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--end-date", type=str, default=None, help="YYYY-MM-DD (default: yesterday)")
    parser.add_argument(
        "--conn-string", type=str, default=os.environ.get("SUPABASE_DB_URL"),
        help="Supabase Postgres connection string (or set SUPABASE_DB_URL env var)",
    )
    args = parser.parse_args()

    if not args.conn_string:
        print("Missing connection string. Pass --conn-string or set SUPABASE_DB_URL.", file=sys.stderr)
        sys.exit(1)

    run(args.conn_string, args.start_date, args.end_date)


if __name__ == "__main__":
    main()
