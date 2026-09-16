-- schema.sql
--
-- Paste this whole file into the Supabase SQL Editor (Project ->
-- SQL Editor -> New query) and click Run.

create table if not exists player_season_summary (
    batter_name text not null,
    season int not null,
    batted_balls_considered int not null default 0,
    actual_home_runs int not null default 0,
    primary key (batter_name, season)
);

create table if not exists player_park_season_summary (
    batter_name text not null,
    season int not null,
    park_key text not null,
    would_be_hrs_all int not null default 0,
    would_be_hrs_actual_only int not null default 0,
    primary key (batter_name, season, park_key)
);

-- Tracks which calendar dates have already been ingested, so
-- ingest.py can run repeatedly (e.g. nightly) without double-counting.
create table if not exists ingest_log (
    game_date date primary key,
    batted_balls_count int not null default 0,
    loaded_at timestamptz not null default now()
);

create index if not exists idx_pss_batter on player_season_summary (batter_name);
create index if not exists idx_ppss_batter on player_park_season_summary (batter_name);
create index if not exists idx_ppss_park_season on player_park_season_summary (park_key, season);

-- Public read access for the two summary tables (the website reads
-- these directly via the public anon key -- safe, since it's
-- read-only and holds no personal data beyond public HR counts).
alter table player_season_summary enable row level security;
alter table player_park_season_summary enable row level security;

drop policy if exists "public read" on player_season_summary;
create policy "public read" on player_season_summary
    for select using (true);

drop policy if exists "public read" on player_park_season_summary;
create policy "public read" on player_park_season_summary
    for select using (true);

-- ingest_log has RLS enabled with NO policies -- fully private.
-- It's only ever written to via the direct database connection
-- string (which bypasses RLS), never via the public anon key.
alter table ingest_log enable row level security;
