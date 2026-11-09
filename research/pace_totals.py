"""Study: how pace relates to game totals (user request, Nov 8 2026). Regular season only.

  1. Actual games: how much of a game's total is pace (possessions) vs efficiency (points per possession)
  2. Before the game: how predictable pace is (v1's pre-game pace from a fit on earlier games only), and how
     well pre-game pace alone predicts the total
  3. Market: is pace already in the line? Over rate vs the close / open by pre-game pace quintile, and a
     regression of (actual - close) on pre-game pace and v1's ppp-only edge

  python research/pace_totals.py 2021-22 2025-26
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
g = tm.load()
p = tm.per_game(g, *tm.run(g, tm.Fitter(g), seasons, tm.HALF_LIFE, tm.LAM))   # v1, no look-ahead
p = p[p.season_type == "Regular Season"].copy()
act = g.drop_duplicates("GAME_ID").set_index("GAME_ID").poss
p["poss"] = p.game_id.map(act)
p["actual"] = p.home_pts + p.away_pts
p["ppp"] = p.actual / p.poss / 2          # points per possession per team
p["pred_ppp"] = p.pred_total / p.pred_pace / 2


def corr(x, y):
    return np.corrcoef(x, y)[0, 1]


print(f"PACE vs TOTALS, regular season {', '.join(seasons)}: {len(p):,} games\n")
print("1. ACTUAL GAMES (possessions per team per game; total = 2 x pace x ppp)")
print(f"{'season':<8} | {'games':>5} | {'avg pace':>8} | {'avg ppp':>7} | {'avg total':>9} | {'r pace~total':>12} | "
      f"{'r ppp~total':>11} | {'pace share':>10} | {'pts per +1 poss':>15}")
for s, d in list(p.groupby("season")) + [("ALL", p)]:
    lt, lp, le = np.log(d.actual), np.log(d.poss), np.log(d.ppp)
    share = (np.var(lp) + np.cov(lp, le)[0, 1]) / np.var(lt)   # log total = log pace + log ppp (+ const)
    slope = np.polyfit(d.poss, d.actual, 1)[0]
    print(f"{s:<8} | {len(d):>5} | {d.poss.mean():8.1f} | {d.ppp.mean():7.3f} | {d.actual.mean():9.1f} | "
          f"{corr(d.poss, d.actual):12.2f} | {corr(d.ppp, d.actual):11.2f} | {share:10.0%} | {slope:15.2f}")
print("   pace share = part of the variance in (log) totals explained by possessions; the rest is efficiency.\n")

print("2. BEFORE THE GAME (v1's pre-game projections, fit on earlier games only)")
print(f"{'season':<8} | {'r pred pace~actual pace':>23} | {'r pred pace~total':>17} | {'r pred ppp~total':>16} | "
      f"{'r v1 total~total':>16}")
for s, d in list(p.groupby("season")) + [("ALL", p)]:
    print(f"{s:<8} | {corr(d.pred_pace, d.poss):23.2f} | {corr(d.pred_pace, d.actual):17.2f} | "
          f"{corr(d.pred_ppp, d.actual):16.2f} | {corr(d.pred_total, d.actual):16.2f}")

# lines: Action Network consensus (close) + open, 2022-23 on; SBR close/open before that
o = read_all(os.path.join(ROOT, "data", "odds", "*", "*_games.csv.gz"))
o = o[o.book.isin(["consensus", "open"])].copy()
o["home"], o["away"] = o.home.map(code), o.away.map(code)
o = o.pivot_table(index=["date", "away", "home"], columns="book", values="total", aggfunc="first").reset_index()
o = o.rename(columns={"consensus": "close", "open": "open"})
m = p.merge(o, on=["date", "away", "home"], how="left")
sbr = pd.read_csv(os.path.join(ROOT, "data", "lines", "sbr_nba.csv"), dtype={"game_id": str})
sbr = sbr.set_index("game_id")
m["close"] = m.close.fillna(m.game_id.map(sbr.close_total))
m["open"] = m.open.fillna(m.game_id.map(sbr.open_total))
m = m.dropna(subset=["close"])
m["res"] = m.actual - m.close
print(f"\n3. MARKET ({len(m):,} games with a closing total, {m.open.notna().sum():,} with an opening total)")
print(f"   r(pre-game pace, closing total) = {corr(m.pred_pace, m.close):.2f}  "
      f"(how much the line already moves with pace)")
print(f"   r(actual pace, actual - close)  = {corr(m.poss, m.res):.2f}  "
      f"(games that ran faster than expected went over: the in-game effect)")
print(f"   r(pre-game pace, actual - close) = {corr(m.pred_pace, m.res):.3f}  (pre-game pace the line missed)")
m["pq"] = m.groupby("season").pred_pace.transform(lambda x: pd.qcut(x, 5, labels=False)) + 1
print("\n   Over rate by pre-game pace quintile (within each season; 1 = slowest), pushes dropped")
print(f"   {'quintile':<8} | {'games':>5} | {'pred pace':>9} | {'actual pace':>11} | {'close':>6} | {'actual':>6} | "
      f"{'over% close':>11} | {'over% open':>10}")
for q, d in m.groupby("pq"):
    oc = d[d.res != 0]
    do = d.dropna(subset=["open"])
    do = do[do.actual != do.open]
    print(f"   {int(q):<8} | {len(d):>5} | {d.pred_pace.mean():9.1f} | {d.poss.mean():11.1f} | {d.close.mean():6.1f} | "
          f"{d.actual.mean():6.1f} | {(oc.res > 0).mean():11.1%} | "
          f"{((do.actual > do.open).mean() if len(do) else np.nan):10.1%}")
# does pace carry information beyond the line? actual - close ~ pace z + ppp-only edge
z = (m.pred_pace - m.groupby("season").pred_pace.transform("mean")) / m.pred_pace.std()
X = np.column_stack([np.ones(len(m)), z, m.pred_total - m.close])
beta, *_ = np.linalg.lstsq(X, m.res, rcond=None)
resid = m.res - X @ beta
se = np.sqrt(np.diag(np.linalg.inv(X.T @ X)) * resid.var())
print(f"\n   regression: actual - close = {beta[0]:+.2f} + {beta[1]:+.2f} x (pre-game pace, sd units; t {beta[1] / se[1]:+.1f})"
      f" + {beta[2]:+.2f} x (v1 total - close; t {beta[2] / se[2]:+.1f})")
print("   (a pace coefficient near 0 = the closing line already prices pace)")
