"""Could pbpstats replace the nba.com game logs (the Mac job)? Compare one season stat by stat.

usage: python research/pbpstats_compare.py [season] [max_players]
Downloads pbpstats game logs for all 30 teams and every player in data/nbacom/player_games_<season>.csv.gz,
then reports, per stat, how often pbpstats equals nba.com exactly. Nothing is written to the repo.
"""
import json
import os
import sys
import time
import urllib.request

import pandas as pd

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SEASON = sys.argv[1] if len(sys.argv) > 1 else "2024-25"
MAX_PLAYERS = int(sys.argv[2]) if len(sys.argv) > 2 else 0
URL = ("https://api.pbpstats.com/get-game-logs/nba?Season={s}&SeasonType=Regular%2BSeason"
       "&EntityType={t}&EntityId={i}")
STATS = ["PTS", "MIN", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB",
         "AST", "STL", "BLK", "TOV", "PF", "PLUS_MINUS"]


def get(entity, eid):
    for i in range(4):
        try:
            req = urllib.request.Request(URL.format(s=SEASON, t=entity, i=eid),
                                         headers={"User-Agent": "nba-projection-model research"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r).get("multi_row_table_data", [])
        except Exception as e:
            print(f"  retry {entity} {eid}: {type(e).__name__} {e}", flush=True)
            time.sleep(5 * (i + 1))
    return None


def minutes(s):
    m, sec = str(s or "0:00").split(":")
    return int(m) + int(sec) / 60


def to_nbacom(rows, eid):
    """pbpstats rows -> nba.com column names. pbpstats leaves a key out when it is 0."""
    out = []
    for r in rows:
        g = lambda k: r.get(k, 0) or 0
        out.append({"ID": int(eid), "GAME_ID": int(r["GameId"]), "PTS": g("Points"), "MIN": minutes(r.get("Minutes")),
                    "FGM": g("FG2M") + g("FG3M"), "FGA": g("FG2A") + g("FG3A"), "FG3M": g("FG3M"), "FG3A": g("FG3A"),
                    "FTM": g("FtPoints"), "FTA": g("FTA"), "OREB": g("Rebounds") - g("DefRebounds"),
                    "DREB": g("DefRebounds"), "REB": g("Rebounds"), "AST": g("Assists"), "STL": g("Steals"),
                    "BLK": g("Blocks"), "TOV": g("Turnovers"), "PF": g("Fouls"), "PLUS_MINUS": g("PlusMinus")})
    return out


def compare(kind, nba, ids, entity):
    t0, rows, failed = time.time(), [], []
    for n, eid in enumerate(ids, 1):
        got = get(entity, eid)
        if got is None:
            failed.append(eid)
        else:
            rows += to_nbacom(got, eid)
        if n % 50 == 0:
            print(f"  {kind}: {n}/{len(ids)} fetched, {time.time() - t0:.0f}s", flush=True)
        time.sleep(1)   # pbpstats answered 503 once at 0.5 s
    pbp = pd.DataFrame(rows)
    if kind == "team":   # nba.com team MIN = player-minutes (240 per game)
        pbp["MIN"] *= 5
    nba = nba.rename(columns={"PLAYER_ID" if kind == "player" else "TEAM_ID": "ID"})
    nba = nba[nba.ID.isin(ids) & (nba.SEASON_TYPE == "Regular Season")]   # pbpstats call is regular season only
    m = nba.merge(pbp, on=["ID", "GAME_ID"], how="outer", suffixes=("_nba", "_pbp"), indicator=True)
    both = m[m._merge == "both"]
    print(f"\n=== {kind.upper()} {SEASON}: {len(ids)} ids, {len(failed)} failed downloads, {time.time() - t0:.0f}s")
    print(f"rows: nba.com {len(nba):,} | pbpstats {len(pbp):,} | matched {len(both):,} | "
          f"only nba.com {int((m._merge == 'left_only').sum()):,} | only pbpstats {int((m._merge == 'right_only').sum()):,}")
    print(f"{'stat':<11}{'exact %':>9}{'within 1 %':>12}{'nba total':>12}{'pbp total':>12}")
    for s in STATS:
        if s == "PLUS_MINUS" and kind == "team":   # pbpstats team logs have no PlusMinus
            continue
        a, b = both[f"{s}_nba"].astype(float), both[f"{s}_pbp"].astype(float)
        if s == "MIN":   # nba.com rounds minutes to whole numbers
            b = b.round()
        d = (a - b).abs()
        print(f"{s:<11}{(d < 0.01).mean() * 100:>8.2f}%{(d <= 1).mean() * 100:>11.2f}%{a.sum():>12,.0f}{b.sum():>12,.0f}")
    worst = both.assign(dpts=(both.PTS_nba - both.PTS_pbp).abs(), dmin=(both.MIN_nba - both.MIN_pbp.round()).abs())
    bad = worst[(worst.dpts > 0) | (worst.dmin > 1)].sort_values(["dpts", "dmin"], ascending=False)
    if len(bad):
        cols = ["ID", "GAME_ID", "PTS_nba", "PTS_pbp", "MIN_nba", "MIN_pbp"]
        print(f"largest PTS/MIN differences ({len(bad)} rows):\n{bad[cols].head(10).round(1).to_string(index=False)}")
    only = m[m._merge == "left_only"]
    if len(only):
        print(f"sample rows only on nba.com:\n{only[['ID', 'GAME_ID', 'MIN_nba', 'PTS_nba']].head(5).to_string(index=False)}")
    return pbp


team = pd.read_csv(os.path.join(ROOT, "data", "nbacom", f"team_games_{SEASON}.csv.gz"))
player = pd.read_csv(os.path.join(ROOT, "data", "nbacom", f"player_games_{SEASON}.csv.gz"))
compare("team", team, sorted(team.TEAM_ID.unique()), "Team")
ids = sorted(player.PLAYER_ID.unique())
compare("player", player, ids[:MAX_PLAYERS] if MAX_PLAYERS else ids, "Player")
