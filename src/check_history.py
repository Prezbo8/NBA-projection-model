"""Checks the nba.com season files in data/nbacom before they are committed / loaded.

Fails (exit 1) if any check fails. Checks:
  1. every game has exactly 2 team rows (one home, one away)
  2. player points summed per team-game == the team's points (catches missing players)
  3. regular-season games per team match the schedule length (82; 66 in 2011-12; 72 in 2020-21;
     2012-13 BOS-IND was cancelled -> 81; 2019-20 bubble season varied 63-75)
  4. LeBron's regular-season GP / PTS per season == nba.com's career page (a separate endpoint)

  python src/check_history.py
"""
import glob
import os
import sys

import pandas as pd

D = os.path.join(os.path.dirname(__file__), "..", "data", "nbacom")
GAMES = {"2011-12": {66}, "2012-13": {81, 82}, "2020-21": {72}, "2019-20": set(range(63, 76))}
fails = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg, flush=True)
    if not ok:
        fails.append(msg)


players = pd.concat([pd.read_csv(f, dtype={"GAME_ID": str}) for f in sorted(glob.glob(f"{D}/player_games_*.csv.gz"))])
teams = pd.concat([pd.read_csv(f, dtype={"GAME_ID": str}) for f in sorted(glob.glob(f"{D}/team_games_*.csv.gz"))])
print(f"{len(players):,} player rows, {len(teams):,} team rows, seasons {teams.SEASON.min()} to {teams.SEASON.max()}\n")

for season, t in teams.groupby("SEASON"):
    p = players[players.SEASON == season]
    per_game = t.groupby("GAME_ID").size()
    home = t.MATCHUP.str.contains(" vs. ").groupby(t.GAME_ID).sum()
    sums = p.groupby(["GAME_ID", "TEAM_ID"]).PTS.sum()
    tp = t.set_index(["GAME_ID", "TEAM_ID"]).PTS
    gap = sums.reindex(tp.index).fillna(-1) != tp
    bad_pts = int(gap.sum())
    for (gid, tid) in tp[gap].index:
        row = t[(t.GAME_ID == gid) & (t.TEAM_ID == tid)].iloc[0]
        print(f"     pts mismatch {season} game {gid} {row.MATCHUP} {row.GAME_DATE}: team {row.PTS}, "
              f"players {int(sums.get((gid, tid), 0))} ({int(((p.GAME_ID == gid) & (p.TEAM_ID == tid)).sum())} player rows)")
    rs = t[t.SEASON_TYPE == "Regular Season"].groupby("TEAM_ABBREVIATION").size()
    want = GAMES.get(season, {82})
    by_type = t.groupby("SEASON_TYPE").GAME_ID.nunique().to_dict()
    check((per_game == 2).all() and (home == 1).all() and bad_pts == 0 and set(rs.unique()) <= want and len(rs) == 30,
          f"{season}: {len(p):>6,} player rows | games {by_type} | teams {len(rs)} | "
          f"RS games/team {sorted(int(x) for x in rs.unique())} | team-games where player pts != team pts: {bad_pts}")

lbj = pd.read_csv(f"{D}/check_lebron_career.csv.gz")
lbj = lbj[lbj.TEAM_ABBREVIATION != "TOT"].groupby("SEASON_ID")[["GP", "PTS"]].sum()
mine = players[(players.PLAYER_ID == 2544) & (players.SEASON_TYPE == "Regular Season")]
mine = mine.groupby("SEASON").agg(GP=("GAME_ID", "nunique"), PTS=("PTS", "sum"))
both = lbj.join(mine, rsuffix="_logs", how="inner")
diff = both[(both.GP != both.GP_logs) | (both.PTS != both.PTS_logs)]
check(len(both) > 0 and diff.empty,
      f"LeBron: {len(both)} seasons compared, career RS points {int(both.PTS_logs.sum()):,} (logs) vs "
      f"{int(both.PTS.sum()):,} (career page), mismatched seasons: {list(diff.index)}")

print(f"\n{len(fails)} check(s) failed" if fails else "\nall checks passed")
sys.exit(1 if fails else 0)
