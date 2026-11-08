"""Referees of every past game, from nba.com's box score summary (one request per game).

Only works from the self-hosted Mac runner (see nbacom.py). Resumable: games already in
data/refs/refs_<season>.csv.gz are skipped, and the file is rewritten every 50 games, so a stopped
run keeps what it got and the next run carries on.

  python src/nbarefs.py 2015-16 2025-26 [--limit N]   # fetch missing games (Mac runner)
  python src/nbarefs.py --check                        # check the saved files (any machine)
"""
import glob
import gzip
import os
import sys
import time

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "data", "refs")
COLS = ["season", "game_id", "date", "official_id", "name", "jersey", "source"]
PAUSE = 2  # seconds between requests: ~1,300 a season, gentle on the home IP


def officials(gid):
    """[(official_id, name, jersey)] and which endpoint answered. v3 first (v2 stopped updating in 2025)."""
    from nbacom import get_json
    try:
        j = get_json("https://stats.nba.com/stats/boxscoresummaryv3", {"GameID": gid})
        o = j["boxScoreSummary"].get("officials") or []
        if o:
            return [(x["personId"], f"{x['firstName']} {x['familyName']}".strip(), x.get("jerseyNum")) for x in o], "v3"
    except Exception as e:
        print(f"  {gid} v3: {type(e).__name__}: {str(e)[:100]}", flush=True)
    j = get_json("https://stats.nba.com/stats/boxscoresummaryv2", {"GameID": gid})
    rs = next(r for r in j["resultSets"] if r["name"] == "Officials")
    h = rs["headers"]
    return [(r[h.index("OFFICIAL_ID")], f"{r[h.index('FIRST_NAME')]} {r[h.index('LAST_NAME')]}".strip(),
             r[h.index("JERSEY_NUM")]) for r in rs["rowSet"]], "v2"


def path(season):
    return os.path.join(OUT, f"refs_{season}.csv.gz")


def save(season, rows):
    df = pd.DataFrame(rows, columns=COLS).sort_values(["date", "game_id", "name"])
    with gzip.GzipFile(path(season), "wb", mtime=0) as f:   # mtime=0: same data -> same bytes
        df.to_csv(f, index=False)


def fetch(season, limit=None):
    games = pd.read_csv(os.path.join(ROOT, "data", "nbacom", f"team_games_{season}.csv.gz"),
                        dtype={"GAME_ID": str}, usecols=["GAME_ID", "GAME_DATE"]).drop_duplicates("GAME_ID")
    games["GAME_ID"] = games.GAME_ID.str.zfill(10)
    old = pd.read_csv(path(season), dtype={"game_id": str}) if os.path.exists(path(season)) else pd.DataFrame(columns=COLS)
    rows = old.values.tolist()
    todo = games[~games.GAME_ID.isin(set(old.game_id))].sort_values("GAME_DATE")
    todo = todo.head(limit) if limit else todo
    print(f"{season}: {len(games)} games, {old.game_id.nunique()} saved, fetching {len(todo)}", flush=True)
    for i, (gid, date) in enumerate(zip(todo.GAME_ID, todo.GAME_DATE), 1):
        try:
            got, src = officials(gid)
        except Exception as e:   # one bad game must not stop the season; it is retried next run
            print(f"  {gid} failed: {type(e).__name__}: {str(e)[:100]}", flush=True)
            got, src = [], None
        rows += [[season, gid, date, oid, name, jersey, src] for oid, name, jersey in got]
        if not got:
            print(f"  {gid} {date}: no officials", flush=True)
        if i % 50 == 0 or i == len(todo):
            save(season, rows)
            print(f"  {season}: {i}/{len(todo)} done", flush=True)
        time.sleep(PAUSE)


def check():
    fails = 0
    for f in sorted(glob.glob(os.path.join(OUT, "refs_*.csv.gz"))):
        r = pd.read_csv(f, dtype={"game_id": str})
        s = os.path.basename(f)[5:12]
        g = pd.read_csv(os.path.join(ROOT, "data", "nbacom", f"team_games_{s}.csv.gz"), dtype={"GAME_ID": str})
        n = r.groupby("game_id").size()
        cover = n.size / g.GAME_ID.nunique()
        three = (n == 3).mean()
        ok = three > 0.95 and r.official_id.notna().all()
        fails += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {s}: {n.size}/{g.GAME_ID.nunique()} games ({cover:.0%}), "
              f"{three:.1%} with 3 officials, {r.official_id.nunique()} officials, source {dict(r.source.value_counts())}")
    return fails


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if sys.argv[1] == "--check":
        sys.exit(1 if check() else 0)
    sys.path.insert(0, os.path.dirname(__file__))
    from nbacom import seasons
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    for s in seasons(sys.argv[1], sys.argv[2]):
        fetch(s, lim)
