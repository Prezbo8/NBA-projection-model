"""Paper trading: log bets from docs/today.json, grade them when final. No real money.

Strategies (thresholds from the backtests, Nov 8 2026):
  v1_total   |v1 projected total - consensus total| >= 3    (v1 beat OPENING lines ~53-54%; lost to closing)
  v2_spread  |v2 spread edge| >= 3                          (v2's injury signal: untestable on past data)

A bet is logged ONCE per game and strategy: the line and price at the first run that flags it (later runs
never change it, so the record reflects a line you could actually have bet then). Only games that haven't
started. Grading uses final scores from the morning odds files (data/odds/<season>/<date>_games.csv.gz),
at the logged American odds: win = odds/100 or 100/|odds|, loss = -1, push = 0.

Also keeps data/paper/slate.csv: every game's first-seen line + projections, for later threshold studies.

  python src/paper.py          # log from docs/today.json, then grade
"""
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from names import read_all

ROOT = os.path.join(os.path.dirname(__file__), "..")
LOG = os.path.join(ROOT, "data", "paper", "paper_trades.csv")
SLATE = os.path.join(ROOT, "data", "paper", "slate.csv")
TODAY = os.path.join(ROOT, "docs", "today.json")
K = {"v1_total": 3.0, "v2_spread": 3.0}
COLS = ["date", "an_game_id", "start_utc", "away", "home", "strategy", "side", "line", "odds", "proj", "edge",
        "logged_et", "away_pts", "home_pts", "result", "units"]


def load(path, cols=None):
    return pd.read_csv(path, dtype={"an_game_id": str}) if os.path.exists(path) else pd.DataFrame(columns=cols)


def log():
    t = json.load(open(TODAY))
    now = datetime.now(timezone.utc)
    stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")
    trades, slate = load(LOG, COLS), load(SLATE)
    have = set(zip(trades.an_game_id.astype(str), trades.strategy))
    seen = set(slate.an_game_id.astype(str)) if len(slate) else set()
    new, new_slate = [], []
    for g in t["games"]:
        gid = str(g["an_game_id"])
        if datetime.fromisoformat(g["start_utc"].replace("Z", "+00:00")) <= now:
            continue                                   # started: nothing can be logged any more
        c = g.get("cons") or {}
        base = {"date": t["date"], "an_game_id": gid, "start_utc": g["start_utc"], "away": g["away"],
                "home": g["home"], "logged_et": stamp}
        if gid not in seen and c.get("total") is not None:
            new_slate.append({**base, "total": c["total"], "over": c["over"], "under": c["under"],
                              "spread_home": c["spread_home"], "v1_total": g["v1_total"], "v2_total": g["proj_total"],
                              "v2_spread_home": g["proj_spread_home"], "home_missing": g["home_missing"],
                              "away_missing": g["away_missing"]})
        # v1 totals
        e = g.get("v1_edge_total")
        if e is not None and abs(e) >= K["v1_total"] and (gid, "v1_total") not in have:
            over = e > 0
            new.append({**base, "strategy": "v1_total", "side": "over" if over else "under", "line": c["total"],
                        "odds": c["over"] if over else c["under"], "proj": g["v1_total"], "edge": e})
        # v2 spreads (edge > 0 = model likes home vs the line)
        e = g.get("edge_spread")
        if e is not None and abs(e) >= K["v2_spread"] and (gid, "v2_spread") not in have and c.get("spread_home") is not None:
            home = e > 0
            new.append({**base, "strategy": "v2_spread", "side": g["home"] if home else g["away"],
                        "line": c["spread_home"] if home else -c["spread_home"],
                        "odds": c["spread_home_line"] if home else c["spread_away_line"],
                        "proj": g["proj_spread_home"] if home else -g["proj_spread_home"], "edge": e})
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if new:
        trades = pd.concat([trades, pd.DataFrame(new)], ignore_index=True)
    trades[COLS].to_csv(LOG, index=False)
    if new_slate:
        pd.concat([slate, pd.DataFrame(new_slate)], ignore_index=True).to_csv(SLATE, index=False)
    print(f"paper: {len(new)} new bets logged, {len(new_slate)} games added to the slate log")


def grade():
    trades = load(LOG, COLS)
    open_ = trades.result.isna()
    if not open_.any():
        return
    finals = read_all(os.path.join(ROOT, "data", "odds", "*", "*_games.csv.gz"))
    if not len(finals):
        return
    finals = finals[(finals.status == "complete")].drop_duplicates("an_game_id")
    score = {str(r.an_game_id): (r.away_pts, r.home_pts) for r in finals.itertuples()}
    done = 0
    for i in trades.index[open_]:
        r = trades.loc[i]
        if str(r.an_game_id) not in score:
            continue
        a, h = score[str(r.an_game_id)]
        if r.strategy == "v1_total":
            diff = (a + h) - r.line
            res = 0 if diff == 0 else (1 if (diff > 0) == (r.side == "over") else -1)
        else:
            margin = (h - a) if r.side == r.home else (a - h)    # side's own margin
            diff = margin + r.line
            res = 0 if diff == 0 else (1 if diff > 0 else -1)
        o = float(r.odds) if pd.notna(r.odds) else -110.0
        units = 0.0 if res == 0 else ((o / 100 if o > 0 else 100 / -o) if res > 0 else -1.0)
        trades.loc[i, ["away_pts", "home_pts", "result", "units"]] = [a, h, {1: "W", -1: "L", 0: "P"}[res], round(units, 3)]
        done += 1
    trades[COLS].to_csv(LOG, index=False)
    print(f"paper: {done} bets graded")


if __name__ == "__main__":
    log()
    grade()
    t = load(LOG, COLS)
    for s, d in t.groupby("strategy"):
        g = d[d.result.notna()]
        print(f"  {s}: {len(d)} logged, {len(g)} graded, {(g.result == 'W').sum()}-{(g.result == 'L').sum()}-"
              f"{(g.result == 'P').sum()}, {g.units.sum():+.2f} u")
