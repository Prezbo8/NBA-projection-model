"""Checks the saved Action Network files (data/odds) against nba.com and SBR.

  1. final scores == nba.com's (date + teams)
  2. consensus close vs SBR close where both exist (Oct 2022 - Jan 2023): spread / total agreement
  3. props: share of prop players matched to an nba.com player who played that day for that team
     (by normalized name), per season; lists the most common unmatched names

  python src/check_odds.py
"""
import os
import sys

import pandas as pd

from gameday import code
from names import norm, read_all

ROOT = os.path.join(os.path.dirname(__file__), "..")
fails = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg, flush=True)
    if not ok:
        fails.append(msg)


def read(pattern):
    return read_all(os.path.join(ROOT, pattern))


games = read("data/odds/*/*_games.csv.gz")
props = read("data/odds/*/*_props.csv.gz")
teams = read("data/nbacom/team_games_*.csv.gz")
players = read("data/nbacom/player_games_*.csv.gz")
for df in (games, props):
    for c in ("away", "home", "team"):
        if c in df:
            df[c] = df[c].map(code)   # Action Network codes -> nba.com codes
teams["date"] = pd.to_datetime(teams.GAME_DATE).dt.strftime("%Y-%m-%d")
players["date"] = pd.to_datetime(players.GAME_DATE).dt.strftime("%Y-%m-%d")
print(f"{games.date.nunique()} days of game lines ({games.date.min()} to {games.date.max()}), "
      f"{len(props):,} prop rows over {props.date.nunique()} days\n")

# 1. scores
cons = games[games.book == "consensus"].drop_duplicates("an_game_id")
home = teams[teams.MATCHUP.str.contains(" vs. ")][["date", "TEAM_ABBREVIATION", "PTS"]].rename(
    columns={"TEAM_ABBREVIATION": "home", "PTS": "nba_home_pts"})
m = cons.merge(home, on=["date", "home"], how="left")
found = m.nba_home_pts.notna()
same = (m.home_pts == m.nba_home_pts)[found]
check(found.mean() > 0.98 and same.mean() > 0.995,
      f"scores: {found.mean():.1%} of games found in nba.com, home score equal in {same.mean():.2%}")
for _, r in m[~found].head(5).iterrows():
    print(f"     not in nba.com: {r.date} {r.away} @ {r.home}")

# 2. vs SBR
sbr = pd.read_csv(os.path.join(ROOT, "data", "lines", "sbr_nba.csv"))
both = cons.merge(sbr, on=["date", "away", "home"], suffixes=("", "_sbr"))
if len(both):
    dt = (both.total - both.close_total).abs()
    ds = (both.spread_home - both.close_spread_home).abs()
    check(dt.median() <= 1 and ds.median() <= 1,
          f"vs SBR close ({len(both)} games): total within 1 pt {(dt <= 1).mean():.0%} (median gap {dt.median():.1f}), "
          f"spread within 1 pt {(ds <= 1).mean():.0%} (median gap {ds.median():.1f}), same favorite "
          f"{(both.spread_home.lt(0) == both.close_spread_home.lt(0)).mean():.0%}")

# 3. props -> nba.com players
if len(props):
    played = set(zip(players.date, players.TEAM_ABBREVIATION, players.PLAYER_NAME.map(norm)))
    pl = props.drop_duplicates(["date", "an_player_id"]).copy()
    pl["key"] = list(zip(pl.date, pl.team, pl.player.map(norm)))
    pl["hit"] = pl.key.isin(played)
    pl["season"] = pl.date.str[:4].astype(int) - (pl.date.str[5:7].astype(int) < 8)
    for y, d in pl.groupby("season"):
        check(d.hit.mean() > 0.95, f"props {y}-{str(y + 1)[2:]}: {len(d):,} player-days, "
              f"{d.hit.mean():.1%} matched to an nba.com player who played that day")
    miss = pl[~pl.hit].player.value_counts().head(12)
    print("     most common unmatched:", dict(miss))

print(f"\n{len(fails)} check(s) failed" if fails else "\nall checks passed")
sys.exit(1 if fails else 0)
