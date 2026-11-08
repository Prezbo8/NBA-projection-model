"""Report card for v1 totals (the paper-traded model) on given seasons, vs Action Network open and close.

Runs a fresh v1 backtest (no availability = no look-ahead), regular season only, play = |v1 - line| >= 3.

  python research/grade_totals.py 2023-24 2025-26
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

K = 3.0
a, b = int(sys.argv[1][:4]), int(sys.argv[2][:4])
seasons = [f"{y}-{str(y + 1)[2:]}" for y in range(a, b + 1)]
g = tm.load()
p = tm.per_game(g, *tm.run(g, tm.Fitter(g), seasons, tm.HALF_LIFE, tm.LAM))   # v1: no set_missing
p = p[p.season_type == "Regular Season"]

o = read_all(os.path.join(ROOT, "data", "odds", "*", "*_games.csv.gz"))
o = o[o.book.isin(["consensus", "open"])].copy()
o["home"], o["away"] = o.home.map(code), o.away.map(code)
o = o.pivot_table(index=["date", "away", "home"], columns="book", values=["total", "over", "under"], aggfunc="first")
o.columns = [f"{v}_{bk}" for v, bk in o.columns]
m = p.merge(o.reset_index(), on=["date", "away", "home"])
m["actual"] = m.home_pts + m.away_pts
m["month"] = m.date.str[:7]
print(f"v1 totals, {', '.join(seasons)} regular season: {len(p)} games, {len(m)} with lines "
      f"({m.total_open.notna().sum()} with an opening total)\n")


def payout(odds):
    odds = odds.fillna(-110)
    return np.where(odds > 0, odds / 100, 100 / odds.abs())


def plays(d, line):
    d = d.dropna(subset=[f"total_{line}"]).copy()
    d["edge"] = d.pred_total - d[f"total_{line}"]
    d = d[d.edge.abs() >= K].copy()
    d["over"] = d.edge > 0
    res = d.actual - d[f"total_{line}"]
    d = d[res != 0].copy()
    d["won"] = (d.edge * res[res != 0]) > 0
    d["u110"] = np.where(d.won, 100 / 110, -1.0)
    price = np.where(d.over, d[f"over_{line}"], d[f"under_{line}"])
    d["u_px"] = np.where(d.won, payout(pd.Series(price, index=d.index)), -1.0)
    return d


def row(name, d):
    n, w = len(d), int(d.won.sum())
    if not n:
        return f"{name:<22} |     - |"
    z = (w / n - 0.5238) / np.sqrt(0.25 / n)
    return (f"{name:<22} | {n:>5} | {w}-{n - w:<5} | {w / n:6.1%} | {d.u110.sum():+7.1f} | {d.u110.mean():+6.1%} | "
            f"{d.u_px.sum():+7.1f} | {z:+5.1f}")


HDR = f"{'':<22} | {'bets':>5} | {'W-L':<10} | {'win%':>6} | {'u -110':>7} | {'ROI':>6} | {'u price':>7} | z vs 52.4%"
print("ACCURACY (avg miss, pts): v1 / opening line / closing line")
for s, d in m.groupby("season"):
    print(f"  {s}: {(d.pred_total - d.actual).abs().mean():.2f} / "
          f"{(d.total_open - d.actual).abs().mean():.2f} / {(d.total_consensus - d.actual).abs().mean():.2f}")

for line, label in (("open", "OPENING"), ("consensus", "CLOSING")):
    d = plays(m, line)
    print(f"\nPLAYS vs {label} total (edge >= {K:g}); 'u price' = graded at the real over/under price")
    print(HDR)
    print(row("ALL", d))
    for s, x in d.groupby("season"):
        print(row(f"  {s}", x))
    print(row("  overs", d[d.over]))
    print(row("  unders", d[~d.over]))
    for lo, hi in ((3, 4), (4, 6), (6, 99)):
        print(row(f"  edge {lo}-{hi if hi < 99 else '+'}", d[d.edge.abs().between(lo, hi, inclusive="left")]))
    for part, months in (("  Oct-Dec", ("10", "11", "12")), ("  Jan-Feb", ("01", "02")), ("  Mar-Apr", ("03", "04"))):
        print(row(part, d[d.month.str[5:].isin(months)]))
    if line == "open":
        # backtest CLV: did the line move toward the model between the open and the close?
        mv = (d.total_consensus - d.total_open) * np.where(d.over, 1, -1)
        mv = mv.dropna()
        print(f"\n  CLOSING-LINE VALUE of opening plays: close moved toward the model {(mv > 0).mean():.0%}, "
              f"away {(mv < 0).mean():.0%}, unchanged {(mv == 0).mean():.0%}; average {mv.mean():+.2f} pts")
        cum = d.sort_values("date").u110.cumsum()
        print(f"  units path: max drawdown {(cum.cummax() - cum).max():.1f} u; "
              f"worst month {d.groupby('month').u110.sum().min():+.1f} u; "
              f"winning months {(d.groupby('month').u110.sum() > 0).sum()}/{d.month.nunique()}")
