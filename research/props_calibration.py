"""How wide are real outcomes around the props projection? Fits variance = a*proj + b*proj^2 per market
(Poisson-like + overdispersion) from 2021-22 .. 2022-23 player-games (no prop lines needed), then checks
calibration on 2023-24+ against the actual prop lines: model P(over) bucket vs real over rate.

  python research/props_calibration.py
"""
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from gameday import code  # noqa: E402
from names import norm, read_all  # noqa: E402

STATS = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M", "stl": "STL", "blk": "BLK",
         "pra": "PRA", "pr": "PR", "pa": "PA", "ra": "RA", "stocks": "STOCKS"}

pr = pd.read_csv(os.path.join(ROOT, "data", "backtest", "player_preds.csv.gz"), dtype={"game_id": str})
pr = pr[(pr.season_type == "Regular Season") & (pr.exp_min >= 12)]
fit_rows = pr[pr.season.isin(["2021-22", "2022-23"])]

VAR = {}
print("market | a (x proj) | b (x proj^2) | sd at proj=5 / 25 | old sd guess at 5 / 25")
for mk, st in STATS.items():
    x, y = fit_rows[f"proj_{st}"].to_numpy(), fit_rows[st].to_numpy()
    r2 = (y - x) ** 2
    A = np.column_stack([x, x ** 2])
    a, b = np.linalg.lstsq(A, r2, rcond=None)[0]
    VAR[mk] = (max(a, 0.05), max(b, 0.0))
    sd = lambda p: math.sqrt(VAR[mk][0] * p + VAR[mk][1] * p * p)  # noqa: E731
    print(f"{mk:<6} | {VAR[mk][0]:10.3f} | {VAR[mk][1]:12.4f} | {sd(5):5.2f} / {sd(25):5.2f} | "
          f"{1.1 * math.sqrt(5):5.2f} / {1.1 * math.sqrt(25):5.2f}")


def p_over(mk, proj, line):
    a, b = VAR[mk]
    sd = math.sqrt(max(a * proj + b * proj * proj, 1e-6))
    return 0.5 * math.erfc((math.floor(line) + 0.5 - proj) / (sd * math.sqrt(2)))  # over x.5 = at least floor+1


props = read_all(os.path.join(ROOT, "data", "odds", "*", "*_props.csv.gz"))
props = props[(props.book == "consensus") & props.over.notna() & props.under.notna()]
for c in ("away", "home"):
    props[c] = props[c].map(code)
props["key"] = props.player.map(norm)
pr["key"] = pr.player.map(norm)
m = props.drop(columns=["team"]).merge(pr, on=["date", "key"])
m = m[(m.team == m.away) | (m.team == m.home)]
m["stat"] = m.market.map(STATS)
m["proj"] = m.apply(lambda r: r[f"proj_{r.stat}"], axis=1)
m["actual"] = m.apply(lambda r: r[r.stat], axis=1)
m = m[m.actual != m.line]
m["p"] = [p_over(mk, p, ln) for mk, p, ln in zip(m.market, m.proj, m.line)]
imp = lambda o: np.where(o > 0, 100 / (o + 100), -o / (-o + 100))  # noqa: E731
m["mkt"] = imp(m.over) / (imp(m.over) + imp(m.under))
m["hit"] = m.actual > m.line
print(f"\nCALIBRATION vs consensus lines, 2023-24+ ({len(m):,} props, pushes dropped)")
print("model P(over) bucket | props | model avg | market avg (no vig) | actual over rate")
for lo in np.arange(0, 1, 0.1):
    d = m[(m.p >= lo) & (m.p < lo + 0.1)]
    if len(d):
        print(f"  {lo:.1f}-{lo + 0.1:.1f}          | {len(d):>6} | {d.p.mean():8.1%} | {d.mkt.mean():18.1%} | {d.hit.mean():8.1%}")
print("\nBrier score (lower = better): model", round(((m.p - m.hit) ** 2).mean(), 4),
      "| market", round(((m.mkt - m.hit) ** 2).mean(), 4))
print("\nVAR =", {k: (round(a, 4), round(b, 5)) for k, (a, b) in VAR.items()})
