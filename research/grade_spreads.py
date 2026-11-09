"""Report card for v1 SPREADS (no availability = no look-ahead) vs the opening and closing spread.

Regular season, play = |v1 margin + home spread| >= K (edge > 0 = home covers by that much in the model).
Lines: Action Network consensus (close) / open with prices from 2022-23; SBR close / open before (priced -110).

  python research/grade_spreads.py 2021-22 2025-26
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
p = p[p.season_type == "Regular Season"].copy()

o = read_all(os.path.join(ROOT, "data", "odds", "*", "*_games.csv.gz"))
o = o[o.book.isin(["consensus", "open"])].copy()
o["home"], o["away"] = o.home.map(code), o.away.map(code)
o = o.pivot_table(index=["date", "away", "home"], columns="book",
                  values=["spread_home", "spread_home_line", "spread_away_line"], aggfunc="first")
o.columns = [f"{v}_{bk}" for v, bk in o.columns]
m = p.merge(o.reset_index(), on=["date", "away", "home"], how="left")
sbr = pd.read_csv(os.path.join(ROOT, "data", "lines", "sbr_nba.csv"), dtype={"game_id": str})
sbr = sbr.dropna(subset=["game_id"]).drop_duplicates("game_id").set_index("game_id")
for line, col in (("consensus", "close_spread_home"), ("open", "open_spread_home")):
    if f"spread_home_{line}" not in m:
        m[f"spread_home_{line}"] = np.nan
    m[f"spread_home_{line}"] = m[f"spread_home_{line}"].fillna(m.game_id.map(sbr[col]))
m["margin"] = m.home_pts - m.away_pts
m["month"] = m.date.str[:7]
print(f"v1 spreads, {', '.join(seasons)} regular season: {len(p)} games, "
      f"{m.spread_home_consensus.notna().sum()} with a closing spread, {m.spread_home_open.notna().sum()} with an opening spread\n")


def payout(odds):
    odds = odds.fillna(-110)
    return np.where(odds > 0, odds / 100, 100 / odds.abs())


def plays(d, line):
    d = d.dropna(subset=[f"spread_home_{line}"]).copy()
    d["edge"] = d.pred_margin + d[f"spread_home_{line}"]        # > 0: model has home covering
    d = d[d.edge.abs() >= K].copy()
    d["home_side"] = d.edge > 0
    res = d.margin + d[f"spread_home_{line}"]                   # > 0: home covered
    d = d[res != 0].copy()
    d["won"] = (d.edge * res[res != 0]) > 0
    d["u110"] = np.where(d.won, 100 / 110, -1.0)
    hl, al = f"spread_home_line_{line}", f"spread_away_line_{line}"
    price = np.where(d.home_side, d[hl] if hl in d else np.nan, d[al] if al in d else np.nan)
    d["u_px"] = np.where(d.won, payout(pd.Series(price, index=d.index, dtype=float)), -1.0)
    return d


def row(name, d):
    n, w = len(d), int(d.won.sum()) if len(d) else 0
    if not n:
        return f"{name:<22} |     - |"
    z = (w / n - 0.5238) / np.sqrt(0.25 / n)
    return (f"{name:<22} | {n:>5} | {w}-{n - w:<5} | {w / n:6.1%} | {d.u110.sum():+7.1f} | {d.u110.mean():+6.1%} | "
            f"{d.u_px.sum():+7.1f} | {z:+5.1f}")


HDR = f"{'':<22} | {'bets':>5} | {'W-L':<10} | {'win%':>6} | {'u -110':>7} | {'ROI':>6} | {'u price':>7} | z vs 52.4%"
print("ACCURACY (avg miss on the margin, pts): v1 / opening spread / closing spread")
for s, d in m.groupby("season"):
    print(f"  {s}: {(d.pred_margin - d.margin).abs().mean():.2f} / {(-d.spread_home_open - d.margin).abs().mean():.2f} / "
          f"{(-d.spread_home_consensus - d.margin).abs().mean():.2f}")
for line, label in (("open", "OPENING"), ("consensus", "CLOSING")):
    d = plays(m, line)
    print(f"\nPLAYS vs {label} spread (edge >= {K:g}); 'u price' = at the real price (AN seasons; SBR = -110)")
    print(HDR)
    print(row("ALL", d))
    for s, x in d.groupby("season"):
        print(row(f"  {s}", x))
    print(row("  home", d[d.home_side]))
    print(row("  away", d[~d.home_side]))
    print(row("  favorite", d[(d.home_side & (d[f"spread_home_{line}"] < 0)) | (~d.home_side & (d[f"spread_home_{line}"] > 0))]))
    print(row("  underdog", d[(d.home_side & (d[f"spread_home_{line}"] > 0)) | (~d.home_side & (d[f"spread_home_{line}"] < 0))]))
    for lo, hi in ((3, 4), (4, 6), (6, 99)):
        print(row(f"  edge {lo}-{hi if hi < 99 else '+'}", d[d.edge.abs().between(lo, hi, inclusive="left")]))
    if line == "open":
        x = d.dropna(subset=["spread_home_consensus"])
        mv = (x.spread_home_consensus - x.spread_home_open) * np.where(x.home_side, -1, 1)   # > 0: close moved toward us
        print(f"\n  CLOSING-LINE VALUE of opening plays: close moved toward the model {(mv > 0).mean():.0%}, "
              f"away {(mv < 0).mean():.0%}, unchanged {(mv == 0).mean():.0%}; average {mv.mean():+.2f} pts")
        cum = d.sort_values("date").u110.cumsum()
        print(f"  units path: max drawdown {(cum.cummax() - cum).max():.1f} u; "
              f"winning months {(d.groupby('month').u110.sum() > 0).sum()}/{d.month.nunique()}")
