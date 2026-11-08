"""Does the team model beat the betting lines? (data/backtest/team_preds.csv vs SBR + Action Network)

Lines per game: Action Network consensus close / open when saved (2022-23 on), else SBR close / open.
For each season and edge threshold k: bet the over when model total - line >= k, the under when <= -k;
bet the home side when model margin + home spread >= k, the away side when <= -k. Pushes don't count.
Win% vs 52.4% (break-even at -110) and units at -110. Regular season only.

  python research/team_vs_lines.py
"""
import glob
import os
import sys

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from gameday import code  # noqa: E402  (team names -> nba.com codes)

TUNE = {"2015-16", "2016-17", "2017-18", "2018-19", "2019-20", "2020-21"}
KS = [0, 1, 2, 3, 4, 5, 6, 8]

p = pd.read_csv(os.path.join(ROOT, "data", "backtest", "team_preds.csv"), dtype={"game_id": str})
p = p[p.season_type == "Regular Season"]

sbr = pd.read_csv(os.path.join(ROOT, "data", "lines", "sbr_nba.csv"), dtype={"game_id": str}).dropna(subset=["game_id"])
sbr = sbr.rename(columns={"close_total": "c_total", "open_total": "o_total",
                          "close_spread_home": "c_spread", "open_spread_home": "o_spread",
                          "home": "l_home"})[["game_id", "l_home", "c_total", "o_total", "c_spread", "o_spread"]]
sbr["src"] = "SBR"

an = []
for f in glob.glob(os.path.join(ROOT, "data", "odds", "*", "*_games.csv.gz")):
    d = pd.read_csv(f)
    if len(d):
        an.append(d[d.book.isin(["consensus", "open"])])
if an:
    a = pd.concat(an)
    a["home"], a["away"] = a.home.map(code), a.away.map(code)
    a = a.pivot_table(index=["date", "away", "home"], columns="book", values=["total", "spread_home"], aggfunc="first")
    a.columns = [f"{v}_{b}" for v, b in a.columns]
    a = a.reset_index().rename(columns={"total_consensus": "c_total", "total_open": "o_total",
                                        "spread_home_consensus": "c_spread", "spread_home_open": "o_spread"})
    a = a.merge(p[["game_id", "date", "away", "home"]], on=["date", "away", "home"])
    a["l_home"], a["src"] = a.home, "ActionNetwork"
    lines = pd.concat([a[sbr.columns], sbr[~sbr.game_id.isin(a.game_id)]])
else:
    lines = sbr
m = p.merge(lines, on="game_id")
# a line's 'home' must be the model's home (neutral games can be listed either way): flip if not
flip = m.l_home != m.home
for c in ("c_spread", "o_spread"):
    m.loc[flip, c] = -m.loc[flip, c]
m["total"] = m.home_pts + m.away_pts
m["margin"] = m.home_pts - m.away_pts
print(f"{len(m):,} regular-season games with lines ({(m.src == 'ActionNetwork').sum():,} Action Network, "
      f"{(m.src == 'SBR').sum():,} SBR), {m.season.min()} to {m.season.max()}\n")

print("season  | games | MAE total: model / close | MAE margin: model / close | source")
for s, d in m.groupby("season"):
    print(f"{s} | {len(d):>5} | {(d.pred_total - d.total).abs().mean():5.2f} / {(d.c_total - d.total).abs().mean():5.2f}"
          f"            | {(d.pred_margin - d.margin).abs().mean():5.2f} / {(d.c_spread + d.margin).abs().mean():5.2f}"
          f"             | {d.src.mode()[0]}")


def bets(d, kind, when, k):
    if kind == "total":
        edge = d.pred_total - d[f"{when}_total"]
        res = d.total - d[f"{when}_total"]           # >0 over won
    else:
        edge = d.pred_margin + d[f"{when}_spread"]
        res = d.margin + d[f"{when}_spread"]          # >0 home covered
    pick = edge.where(edge.abs() >= max(k, 1e-9))
    won = (pick * res > 0)[pick.notna() & (res != 0)]
    n, w = len(won), int(won.sum())
    return n, w, (w * 100 / 110 - (n - w)) if n else 0.0


for kind in ("total", "spread"):
    for when, label in (("c", "CLOSE"), ("o", "OPEN")):
        print(f"\n{kind.upper()} vs {label} line: bets / win% / units at -110, by edge >= k")
        print("period          | " + " | ".join(f"k={k:<14}" for k in KS))
        for name, d in (("tune 2015-21", m[m.season.isin(TUNE)]), ("test 2021-now", m[m.season >= "2021-22"])):
            cells = []
            for k in KS:
                n, w, u = bets(d.dropna(subset=[f"{when}_{kind}"]), kind, when, k)
                cells.append(f"{n:>5} {w / n:5.1%} {u:+6.1f}" if n else f"{'-':>16}")
            print(f"{name:<15} | " + " | ".join(cells))
