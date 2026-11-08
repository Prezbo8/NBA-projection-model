"""Does the props model beat the prop lines? (data/backtest/player_preds.csv.gz vs Action Network props)

Prop rows are matched to nba.com player-games by date + team + normalized name. For each market and
line (consensus = close, open), bet the over when (projection - line) / line >= k, the under when <= -k.
Each bet is scored at that line's own over/under price (prop juice varies a lot). Pushes don't count.
Regular season only.

  python research/props_vs_lines.py
"""
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
from gameday import code  # noqa: E402
from names import norm, read_all  # noqa: E402

MARKETS = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M", "stl": "STL", "blk": "BLK",
           "pra": "PRA", "pr": "PR", "pa": "PA", "ra": "RA", "stocks": "STOCKS"}
KS = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]


def payout(odds):
    """Profit per 1 unit staked at American odds."""
    return np.where(odds > 0, odds / 100, 100 / np.abs(odds))


pr = pd.read_csv(os.path.join(ROOT, "data", "backtest", "player_preds.csv.gz"), dtype={"game_id": str})
pr = pr[pr.season_type == "Regular Season"]
pr["key"] = pr.player.map(norm)

props = read_all(os.path.join(ROOT, "data", "odds", "*", "*_props.csv.gz"))
props = props[props.book.isin(["consensus", "open"]) & props.over.notna() & props.under.notna()]
# Action Network tags players with their CURRENT team (Jaylen Brown = PHI even in 2023 BOS games), so
# match on date + name, and require the nba.com team to be one of the two teams in that game
for c in ("away", "home"):
    props[c] = props[c].map(code)
props["key"] = props.player.map(norm)
props["stat"] = props.market.map(MARKETS)

m = props.drop(columns=["team"]).merge(pr, on=["date", "key"])
m = m[(m.team == m.away) | (m.team == m.home)]
matched = m.drop_duplicates(["date", "an_player_id"]).shape[0] / props.drop_duplicates(["date", "an_player_id"]).shape[0]
print(f"{len(props):,} consensus/open prop lines; {matched:.1%} of player-days matched to a player who played "
      f"(the rest mostly didn't play: void bets)\n")
m["proj"] = m.apply(lambda r: r[f"proj_{r.stat}"], axis=1)
m["actual"] = m.apply(lambda r: r[r.stat], axis=1)
m["edge"] = (m.proj - m.line) / m.line.clip(lower=0.5)

for book in ("consensus", "open"):
    d0 = m[m.book == book]
    print(f"=== vs {'CLOSE (consensus)' if book == 'consensus' else 'OPEN'}: bets / win% / ROI at the line's own price, "
          f"by edge >= k (share of the line)")
    print(f"{'market':<7}| {'MAE proj / line':<16}| " + " | ".join(f"k={k:<17.0%}" for k in KS))
    for mk, st in MARKETS.items():
        d = d0[d0.market == mk]
        if not len(d):
            continue
        cells = []
        for k in KS:
            b = d[d.edge.abs() >= max(k, 1e-9)]
            over = b.edge > 0
            res = np.sign(b.actual - b.line)
            won = np.where(over, res > 0, res < 0)
            push = res == 0
            price = np.where(over, b.over, b.under)
            pnl = np.where(push, 0, np.where(won, payout(price), -1.0))
            n = int((~push).sum())
            cells.append(f"{n:>6} {won[~push].mean():5.1%} {pnl.sum() / max(n, 1):+6.1%}" if n else f"{'-':>19}")
        mae = f"{(d.proj - d.actual).abs().mean():5.2f} / {(d.line - d.actual).abs().mean():5.2f}"
        print(f"{mk:<7}| {mae:<16}| " + " | ".join(cells))
    print()
