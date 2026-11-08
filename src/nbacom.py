"""nba.com stats API: full-season player and team game logs (one request per season / type / P-or-T).

Only works from the self-hosted Mac runner, and only with a Chrome-like connection (curl_cffi):
stats.nba.com never answers GitHub's cloud runners, and rejects plain `requests` even from a home IP.
Endpoint and parameter names follow swar/nba_api (LeagueGameLog).

  python src/nbacom.py 2003-04 2025-26     # writes data/nbacom/{player,team}_games_<season>.csv.gz
"""
import csv
import gzip
import io
import os
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from curl_cffi import requests as cr

URL = "https://stats.nba.com/stats/leaguegamelog"
HEADERS = {
    "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com",
    "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
    "x-nba-stats-origin": "stats", "x-nba-stats-token": "true",
}
TYPES = ["Regular Season", "PlayIn", "Playoffs"]  # PlayIn exists from 2019-20; earlier seasons return 0 rows
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "nbacom")
PAUSE = 4  # seconds between requests: ~140 requests for 2003-26, keep it gentle on the home IP


def seasons(first, last):
    """'2003-04', '2005-06' -> ['2003-04', '2004-05', '2005-06']"""
    a, b = int(first[:4]), int(last[:4])
    return [f"{y}-{str(y + 1)[2:]}" for y in range(a, b + 1)]


def get(params, tries=3, url=URL):
    for i in range(tries):
        try:
            r = cr.get(url, params=params, headers=HEADERS, impersonate="chrome", timeout=60)
            r.raise_for_status()
            rs = r.json()["resultSets"][0]
            return rs["headers"], rs["rowSet"]
        except Exception as e:
            print(f"  try {i + 1} failed: {type(e).__name__}: {str(e)[:120]}", flush=True)
            time.sleep(15 * (i + 1))
    raise RuntimeError(f"nba.com failed 3 times: {params}")


def season_log(season, who):
    """All games of one season (every season type) for players (who='P') or teams (who='T')."""
    cols, rows = None, []
    for st in TYPES:
        h, rs = get({"Counter": 0, "Direction": "ASC", "LeagueID": "00", "PlayerOrTeam": who,
                     "Season": season, "SeasonType": st, "Sorter": "DATE"})
        cols = ["SEASON", "SEASON_TYPE"] + h
        if who == "T":  # games never played (2012-13 BOS-IND, cancelled) are listed as 0-0: drop them
            unplayed = [r for r in rs if r[h.index("PTS")] == 0]
            for r in unplayed:
                print(f"  dropped unplayed game {r[h.index('GAME_ID')]} {r[h.index('MATCHUP')]} {r[h.index('GAME_DATE')]}")
            rs = [r for r in rs if r not in unplayed]
        today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        rs = [r for r in rs if r[h.index("GAME_DATE")] < today]  # only finished days: today's games can be live
        rows += [[season, st] + r for r in rs]
        print(f"  {season} {who} {st}: {len(rs)} rows", flush=True)
        time.sleep(PAUSE)
    return cols, rows


def write(path, cols, rows):
    # mtime=0: same data -> same bytes, so git only sees a change when the data changes
    with gzip.GzipFile(path, "wb", mtime=0) as gz, io.TextIOWrapper(gz, newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    # LeBron's season-by-season career totals: a separate nba.com endpoint, used only to check the logs
    h, rs = get({"PlayerID": 2544, "PerMode": "Totals", "LeagueID": "00"},
                url="https://stats.nba.com/stats/playercareerstats")
    write(os.path.join(OUT, "check_lebron_career.csv.gz"), h, rs)
    time.sleep(PAUSE)
    for s in seasons(sys.argv[1], sys.argv[2]):
        for who, name in (("P", "player"), ("T", "team")):
            cols, rows = season_log(s, who)
            write(os.path.join(OUT, f"{name}_games_{s}.csv.gz"), cols, rows)
