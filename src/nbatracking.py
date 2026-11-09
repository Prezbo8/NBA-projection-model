"""Team tracking stats for each game day (nba.com player tracking / hustle), offense and defense.

One request per measure per game day (DateFrom = DateTo = that day, PerMode Totals), so the totals model can
use only the days BEFORE each game (no look-ahead). Synergy play types are not here: that endpoint has no
date filter (season only), so it can't be used without look-ahead.

Only works from the self-hosted Mac runner (see nbacom.py). Resumable: days already in
data/tracking/tracking_<season>.csv.gz are skipped, and the file is rewritten every 10 days.

  python src/nbatracking.py 2021-22 2025-26 [--limit N]   # fetch missing days (Mac runner)
  python src/nbatracking.py --check                        # check the saved files (any machine)
"""
import glob
import os
import sys
import time

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "data", "tracking")
PAUSE = 2  # seconds between requests (same as the referee backfill)
B = "https://stats.nba.com/stats/"
BASE = {"LeagueID": "00", "SeasonType": "Regular Season", "PerMode": "Totals", "GameSegment": "",
        "LastNGames": "0", "Location": "", "Month": "0", "OpponentTeamID": "0", "Outcome": "", "PORound": "0",
        "Period": "0", "SeasonSegment": "", "TeamID": "0", "VsConference": "", "VsDivision": "", "Conference": "",
        "Division": "", "GameScope": "", "PlayerExperience": "", "PlayerPosition": "", "StarterBench": "",
        "DraftPick": "", "DraftYear": "", "College": "", "Country": "", "Height": "", "Weight": "", "ISTRound": ""}
SHOT = {"DribbleRange": "", "GeneralRange": "", "ShotClockRange": "", "ShotDistRange": "", "TouchTimeRange": ""}
# prefix: (endpoint, extra params). Every endpoint returns one row per team that played that day.
MEASURES = {
    "owo": ("leaguedashteamptshot", {**SHOT, "CloseDefDistRange": "6+ Feet - Wide Open"}),   # own wide-open shots
    "dwo": ("leaguedashoppptshot", {**SHOT, "CloseDefDistRange": "6+ Feet - Wide Open"}),    # wide-open shots allowed
    "dfg": ("leaguedashptteamdefend", {"DefenseCategory": "Overall"}),                     # FG% allowed vs normal
    "hus": ("leaguehustlestatsteam", {}),                                                  # contests, deflections...
    "drv": ("leaguedashptstats", {"PlayerOrTeam": "Team", "PtMeasureType": "Drives"}),
}
DROP = {"TEAM_NAME", "TEAM_ABBREVIATION", "GP", "G", "W", "L"}


def game_days(season):
    t = pd.read_csv(os.path.join(ROOT, "data", "nbacom", f"team_games_{season}.csv.gz"))
    t = t[t.SEASON_TYPE == "Regular Season"]
    return sorted(pd.to_datetime(t.GAME_DATE).dt.date.unique())


def fetch_day(season, day):
    """One row per team that played on `day`, columns '<prefix>_<NBA COLUMN>'."""
    from nbacom import get_json
    d = day.strftime("%m/%d/%Y")
    out = None
    for prefix, (ep, extra) in MEASURES.items():
        js = get_json(B + ep, {**BASE, **extra, "Season": season, "DateFrom": d, "DateTo": d})
        rs = js["resultSets"][0] if isinstance(js["resultSets"], list) else js["resultSets"]
        df = pd.DataFrame(rs["rowSet"], columns=rs["headers"])
        df = df[[c for c in df.columns if c not in DROP]].rename(
            columns=lambda c: c if c == "TEAM_ID" else f"{prefix}_{c}")
        out = df if out is None else out.merge(df, on="TEAM_ID", how="outer")
        time.sleep(PAUSE)
    out.insert(0, "date", day.isoformat())
    out.insert(0, "season", season)
    return out


def path(season):
    return os.path.join(OUT, f"tracking_{season}.csv.gz")


def fetch(first, last, limit=None):
    from nbacom import seasons
    os.makedirs(OUT, exist_ok=True)
    for season in seasons(first, last):
        p = path(season)
        have = pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
        done = set(have.date) if len(have) else set()
        todo = [d for d in game_days(season) if d.isoformat() not in done][:limit]
        print(f"{season}: {len(done)} days saved, {len(todo)} to fetch", flush=True)
        parts, t0 = [have], time.time()
        for i, day in enumerate(todo, 1):
            try:
                parts.append(fetch_day(season, day))
            except Exception as e:   # get_json already retried 3 times: skip the day, the next run retries it
                print(f"  {day} skipped: {type(e).__name__}: {str(e)[:120]}", flush=True)
            if i % 10 == 0 or i == len(todo):
                save(p, parts)
                print(f"  {i}/{len(todo)} days, {(time.time() - t0) / 60:.0f} min", flush=True)


def save(p, parts):
    df = pd.concat([x for x in parts if len(x)]).sort_values(["date", "TEAM_ID"])
    df.to_csv(p, index=False, compression={"method": "gzip", "mtime": 0})


def check():
    """Every saved day: 2 teams per game played that day, and the measures agree with each other."""
    bad = 0
    for p in sorted(glob.glob(os.path.join(OUT, "tracking_*.csv.gz"))):
        df = pd.read_csv(p)
        season = df.season.iloc[0]
        t = pd.read_csv(os.path.join(ROOT, "data", "nbacom", f"team_games_{season}.csv.gz"))
        t = t[t.SEASON_TYPE == "Regular Season"]
        played = t.groupby("GAME_DATE").TEAM_ID.nunique()
        got = df.groupby("date").TEAM_ID.nunique()
        short = (got - played.reindex(got.index)).ne(0)
        missing = {c: int(df[c].isna().sum()) for c in ["owo_FGA", "dwo_FGA", "dfg_D_FGA", "hus_DEFLECTIONS", "drv_DRIVES"]}
        print(f"{season}: {len(got)}/{len(played)} days, {len(df):,} team-days, "
              f"days with a team count != nba.com: {int(short.sum())}, empty cells per measure: {missing}")
        bad += int(short.sum()) + sum(missing.values())
    return bad


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if sys.argv[1] == "--check":
        sys.exit(1 if check() else 0)
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    fetch(sys.argv[1], sys.argv[2], lim)
