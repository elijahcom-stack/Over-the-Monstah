"""
park_data.py

Approximate geometry for all 30 current MLB ballparks.

For each park we store three fence distances (down the left-field line,
straightaway center, down the right-field line) and a single
representative fence height. Real ballparks have fences that vary in
height segment-by-segment (e.g. Fenway's 37-foot Green Monster in left
vs. its much shorter bullpen wall in right-center) -- we deliberately
simplify this to one average height per park. See README.md for the
full list of known limitations.

Distances are in feet, measured from home plate.
Heights are in feet.

Spray angle convention used throughout this project:
    -45 deg = left-field line
      0 deg = straightaway center field
    +45 deg = right-field line

Sources: publicly available ballpark dimension figures (rounded to the
nearest few feet). These are approximations for modeling purposes, not
official surveyed distances.
"""

# key -> { name, team, lf_line, cf, rf_line, fence_height }
PARKS = {
    "ARI": {"name": "Chase Field",               "team": "Arizona Diamondbacks",  "lf_line": 330, "cf": 407, "rf_line": 334, "fence_height": 8},
    "ATL": {"name": "Truist Park",                "team": "Atlanta Braves",        "lf_line": 335, "cf": 400, "rf_line": 325, "fence_height": 8},
    "BAL": {"name": "Oriole Park at Camden Yards", "team": "Baltimore Orioles",    "lf_line": 333, "cf": 400, "rf_line": 318, "fence_height": 10},
    "BOS": {"name": "Fenway Park",                "team": "Boston Red Sox",        "lf_line": 310, "cf": 390, "rf_line": 302, "fence_height": 15},
    "CHC": {"name": "Wrigley Field",               "team": "Chicago Cubs",          "lf_line": 355, "cf": 400, "rf_line": 353, "fence_height": 11.5},
    "CWS": {"name": "Rate Field",                  "team": "Chicago White Sox",     "lf_line": 330, "cf": 400, "rf_line": 335, "fence_height": 8},
    "CIN": {"name": "Great American Ball Park",    "team": "Cincinnati Reds",       "lf_line": 328, "cf": 404, "rf_line": 325, "fence_height": 8},
    "CLE": {"name": "Progressive Field",           "team": "Cleveland Guardians",   "lf_line": 325, "cf": 405, "rf_line": 325, "fence_height": 12},
    "COL": {"name": "Coors Field",                 "team": "Colorado Rockies",      "lf_line": 347, "cf": 415, "rf_line": 350, "fence_height": 8},
    "DET": {"name": "Comerica Park",               "team": "Detroit Tigers",        "lf_line": 345, "cf": 412, "rf_line": 330, "fence_height": 8},
    "HOU": {"name": "Minute Maid Park",            "team": "Houston Astros",        "lf_line": 315, "cf": 409, "rf_line": 326, "fence_height": 14},
    "KC":  {"name": "Kauffman Stadium",            "team": "Kansas City Royals",    "lf_line": 330, "cf": 410, "rf_line": 330, "fence_height": 9},
    "LAA": {"name": "Angel Stadium",               "team": "Los Angeles Angels",    "lf_line": 330, "cf": 396, "rf_line": 330, "fence_height": 8},
    "LAD": {"name": "Dodger Stadium",              "team": "Los Angeles Dodgers",   "lf_line": 330, "cf": 395, "rf_line": 330, "fence_height": 8},
    "MIA": {"name": "loanDepot park",              "team": "Miami Marlins",         "lf_line": 344, "cf": 400, "rf_line": 335, "fence_height": 8},
    "MIL": {"name": "American Family Field",       "team": "Milwaukee Brewers",     "lf_line": 344, "cf": 400, "rf_line": 345, "fence_height": 8},
    "MIN": {"name": "Target Field",                "team": "Minnesota Twins",       "lf_line": 339, "cf": 404, "rf_line": 328, "fence_height": 8},
    "NYM": {"name": "Citi Field",                  "team": "New York Mets",         "lf_line": 330, "cf": 408, "rf_line": 330, "fence_height": 8},
    "NYY": {"name": "Yankee Stadium",               "team": "New York Yankees",      "lf_line": 318, "cf": 408, "rf_line": 314, "fence_height": 8},
    "OAK": {"name": "Oakland Coliseum",             "team": "Athletics",             "lf_line": 330, "cf": 400, "rf_line": 330, "fence_height": 8},
    "PHI": {"name": "Citizens Bank Park",          "team": "Philadelphia Phillies", "lf_line": 329, "cf": 401, "rf_line": 330, "fence_height": 10},
    "PIT": {"name": "PNC Park",                     "team": "Pittsburgh Pirates",    "lf_line": 325, "cf": 399, "rf_line": 320, "fence_height": 10},
    "SD":  {"name": "Petco Park",                   "team": "San Diego Padres",      "lf_line": 336, "cf": 396, "rf_line": 322, "fence_height": 9},
    "SEA": {"name": "T-Mobile Park",                "team": "Seattle Mariners",      "lf_line": 331, "cf": 401, "rf_line": 326, "fence_height": 8},
    "SF":  {"name": "Oracle Park",                  "team": "San Francisco Giants",  "lf_line": 339, "cf": 399, "rf_line": 309, "fence_height": 12},
    "STL": {"name": "Busch Stadium",                "team": "St. Louis Cardinals",   "lf_line": 336, "cf": 400, "rf_line": 335, "fence_height": 8},
    "TB":  {"name": "Tropicana Field",              "team": "Tampa Bay Rays",        "lf_line": 315, "cf": 404, "rf_line": 322, "fence_height": 8},
    "TEX": {"name": "Globe Life Field",             "team": "Texas Rangers",         "lf_line": 329, "cf": 407, "rf_line": 326, "fence_height": 8},
    "TOR": {"name": "Rogers Centre",                "team": "Toronto Blue Jays",     "lf_line": 328, "cf": 400, "rf_line": 328, "fence_height": 10},
    "WSH": {"name": "Nationals Park",               "team": "Washington Nationals",  "lf_line": 336, "cf": 402, "rf_line": 335, "fence_height": 8},
}

# Baseball Savant's `home_team` abbreviations differ slightly from the
# keys above in a couple of cases; map anything that needs it here.
SAVANT_TEAM_ALIASES = {
    "CHW": "CWS",
    "KCR": "KC",
    "SDP": "SD",
    "SFG": "SF",
    "TBR": "TB",
    "WSN": "WSH",
    "ATH": "OAK",
}


def normalize_team_code(code: str) -> str:
    """Map a Statcast home_team code onto a PARKS key."""
    code = code.upper()
    return SAVANT_TEAM_ALIASES.get(code, code)


def fence_distance_at_spray_angle(park_key: str, spray_angle_deg: float) -> float:
    """
    Linearly interpolate a park's fence distance at a given spray angle.

    spray_angle_deg: -45 (LF line) .. 0 (CF) .. +45 (RF line)
    Angles outside [-45, 45] are clamped (foul territory / not a fair
    batted ball in play at the fence).
    """
    park = PARKS[park_key]
    angle = max(-45.0, min(45.0, spray_angle_deg))

    if angle <= 0:
        # interpolate between LF line (-45) and CF (0)
        frac = (angle - (-45.0)) / 45.0  # 0 at LF line, 1 at CF
        return park["lf_line"] + frac * (park["cf"] - park["lf_line"])
    else:
        # interpolate between CF (0) and RF line (45)
        frac = angle / 45.0  # 0 at CF, 1 at RF line
        return park["cf"] + frac * (park["rf_line"] - park["cf"])


def fence_height(park_key: str) -> float:
    return PARKS[park_key]["fence_height"]


ALL_PARK_KEYS = list(PARKS.keys())
