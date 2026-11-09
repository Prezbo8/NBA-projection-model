"""Study: totals by pace matchup (user request, Nov 8 2026): top/mid/trash pace team vs top/mid/trash.

Pace tier (no look-ahead): a team's average possessions over its previous 20 games (before this game, can
reach into last season), split into thirds within each season: top / mid / trash. Both teams need 10+ games
of history. Regular season only. Lines: Action Network consensus (close) + open from 2022-23, SBR before.

  python research/pace_matchups.py 2021-22 2026-27
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import team_model as tm  # noqa: E402
from gameday import code  # noqa: E402
from names import read_all  # noqa: E402

a, b = int(sys.argv[1][:4]), int(sys.argv[2][:4])
seasons = [f"{y}-{str(y + 1)[2:]}" for y in range(a, b + 1)]
g = tm.load().sort_values(["TEAM_ID", "date"])
roll = g.groupby("TEAM_ID").poss
g["pace20"] = roll.transform(lambda x: x.shift(1).rolling(20, min_periods=10).mean())
g = g[g.SEASON.isin(seasons) & (g.SEASON_TYPE == "Regular Season")].copy()
g["tier"] = g.groupby("SEASON").pace20.transform(
    lambda x: pd.qcut(x, 3, labels=["trash", "mid", "top"]).astype(str).where(x.notna()))
opp = g[["GAME_ID", "TEAM_ID", "tier", "pace20"]].rename(columns={"TEAM_ID": "OPP_ID", "tier": "opp_tier",
                                                                   "pace20": "opp_pace20"})
h = g[g.is_home | (g.neutral & (g.TEAM_ID < g.OPP_ID))].merge(opp, on=["GAME_ID", "OPP_ID"])
h = h.dropna(subset=["pace20", "opp_pace20"])
h = h[h.tier.isin(["top", "mid", "trash"]) & h.opp_tier.isin(["top", "mid", "trash"])].copy()
rank = {"top": 0, "mid": 1, "trash": 2}
h["matchup"] = [" vs ".join(sorted((x, y), key=rank.get)) for x, y in zip(h.tier, h.opp_tier)]
h["actual"] = h.PTS + h.OPP_PTS
h["date_s"] = h.date.dt.strftime("%Y-%m-%d")
h["home"], h["away"] = h.TEAM_ABBREVIATION, h.OPP

o = read_all(os.path.join(ROOT, "data", "odds", "*", "*_games.csv.gz"))
o = o[o.book.isin(["consensus", "open"])].copy()
o["home"], o["away"] = o.home.map(code), o.away.map(code)
o = o.pivot_table(index=["date", "away", "home"], columns="book", values="total", aggfunc="first").reset_index()
o = o.rename(columns={"date": "date_s", "consensus": "close"})
h = h.merge(o, on=["date_s", "away", "home"], how="left")
sbr = pd.read_csv(os.path.join(ROOT, "data", "lines", "sbr_nba.csv"), dtype={"game_id": str})
sbr = sbr.dropna(subset=["game_id"]).drop_duplicates("game_id").set_index("game_id")
h["close"] = h.close.fillna(h.GAME_ID.map(sbr.close_total))
h["open"] = h.open.fillna(h.GAME_ID.map(sbr.open_total))


def table(d, title):
    print(f"\n{title}")
    print(f"{'matchup':<16} | {'games':>5} | {'pace':>5} | {'total':>6} | {'close':>6} | {'act-close':>9} | "
          f"{'over% close':>11} | {'open':>6} | {'over% open':>10} | {'close-open':>10} | {'|move|':>6}")
    order = ["top vs top", "top vs mid", "mid vs mid", "top vs trash", "mid vs trash", "trash vs trash"]
    for mu in order + ["ALL"]:
        x = d if mu == "ALL" else d[d.matchup == mu]
        if not len(x):
            continue
        c = x.dropna(subset=["close"])
        c = c[c.actual != c.close]
        op = x.dropna(subset=["open"])
        op = op[op.actual != op.open]
        mv = x.dropna(subset=["open", "close"])
        print(f"{mu:<16} | {len(x):>5} | {x.poss.mean():5.1f} | {x.actual.mean():6.1f} | {x.close.mean():6.1f} | "
              f"{(x.actual - x.close).mean():+9.1f} | {(c.actual > c.close).mean():11.1%} | {x.open.mean():6.1f} | "
              f"{(op.actual > op.open).mean() if len(op) else np.nan:10.1%} | "
              f"{(mv.close - mv.open).mean() if len(mv) else np.nan:+10.2f} | "
              f"{(mv.close - mv.open).abs().mean() if len(mv) else np.nan:6.2f}")


print(f"TOTALS BY PACE MATCHUP, regular season {seasons[0]} .. {seasons[-1]}: {len(h):,} games "
      f"({h.close.notna().sum():,} with a closing total, {h.open.notna().sum():,} with an opening total)")
print("pace = actual possessions per team; act-close = actual total minus closing total; close-open = how the line "
      "moved (+ = up); |move| = average size of the move")
table(h, "ALL SEASONS")
for s, d in h.groupby("SEASON"):
    table(d, s)
