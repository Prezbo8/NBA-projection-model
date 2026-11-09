"""Paper trading: log bets from docs/today.json, grade them when final. No real money.

Strategies (thresholds from the backtests, Nov 8 2026):
  v1_total   |v1 projected total - consensus total| >= 3    (v1 beat OPENING lines ~53-54%; lost to closing)
  v2_spread  |v2 spread edge| >= 3                          (v2's injury signal: untestable on past data)
  v3_total   |v3 projected total - consensus total| >= 3    (v3 = v1 + availability for totals, from Nov 8 2026;
                                                              beats v1 on MAE, but its line test has look-ahead)
  v3_spread  |v3 spread edge| >= 3                          (v3's margin error 10.83 vs v2 10.90; paper only)

Every game on the slate is graded too (slate.csv: final score + closing total / spread), not just the bets.

A bet is logged ONCE per game and strategy: the line and price at the first run that flags it (later runs
never change it, so the record reflects a line you could actually have bet then). Only games that haven't
started. Grading uses final scores from the morning odds files (data/odds/<season>/<date>_games.csv.gz),
at the logged American odds: win = odds/100 or 100/|odds|, loss = -1, push = 0.

Also keeps data/paper/slate.csv: every game's first-seen line + projections, for later threshold studies.

  python src/paper.py          # log from docs/today.json (+ docs/tomorrow.json if there), then grade
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
SLATES = [os.path.join(ROOT, "docs", f) for f in ("today.json", "tomorrow.json")]  # tomorrow: evening runs, near the open
K = {"v1_total": 3.0, "v2_spread": 3.0, "v3_total": 3.0, "v3_spread": 3.0}
SLATE_RESULT = ["away_pts", "home_pts", "close_total", "close_spread_home"]
COLS = ["date", "an_game_id", "start_utc", "away", "home", "strategy", "side", "line", "odds", "proj", "edge",
        "logged_et", "open_line", "close_line", "clv", "away_pts", "home_pts", "result", "units"]
# open_line: the opening line, in the bet's terms (how far it had moved when logged)
# close_line / clv: the final consensus line (from the morning odds file) and how much better the logged line was
#   (> 0 = the bet beat the close; the quickest sign of a real edge, long before 100 graded bets)


def load(path, cols=None):
    return pd.read_csv(path, dtype={"an_game_id": str}) if os.path.exists(path) else pd.DataFrame(columns=cols)


def log(path):
    t = json.load(open(path))
    now = datetime.now(timezone.utc)
    stamp = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")
    trades, slate = load(LOG, COLS), load(SLATE)
    trades = trades.reindex(columns=COLS)   # older logs lack the newer columns
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
                              "away_missing": g["away_missing"], "v3_total": g.get("v3_total"),
                              "v3_spread_home": g.get("v3_spread_home"), "v1_spread_home": g.get("v1_spread_home")})
        # v1 and v3 totals
        for s in ("v1_total", "v3_total"):
            e = g.get(s.replace("_total", "_edge_total"))
            if e is not None and abs(e) >= K[s] and (gid, s) not in have:
                over = e > 0
                new.append({**base, "strategy": s, "side": "over" if over else "under", "line": c["total"],
                            "odds": c["over"] if over else c["under"], "proj": g[s], "edge": e,
                            "open_line": g.get("open_total")})
        # v2 / v3 spreads (edge > 0 = model likes home vs the line)
        for s, ek, pk in (("v2_spread", "edge_spread", "proj_spread_home"), ("v3_spread", "v3_edge_spread", "v3_spread_home")):
            e = g.get(ek)
            if e is not None and abs(e) >= K[s] and (gid, s) not in have and c.get("spread_home") is not None:
                home = e > 0
                new.append({**base, "strategy": s, "side": g["home"] if home else g["away"],
                            "line": c["spread_home"] if home else -c["spread_home"],
                            "odds": c["spread_home_line"] if home else c["spread_away_line"],
                            "proj": g[pk] if home else -g[pk], "edge": e,
                            "open_line": None if g.get("open_spread_home") is None else
                            (g["open_spread_home"] if home else -g["open_spread_home"])})
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if new:
        trades = pd.concat([trades, pd.DataFrame(new)], ignore_index=True)
    trades[COLS].to_csv(LOG, index=False)
    if new_slate:
        pd.concat([slate, pd.DataFrame(new_slate)], ignore_index=True).to_csv(SLATE, index=False)
    print(f"paper ({t['date']}): {len(new)} new bets logged, {len(new_slate)} games added to the slate log")


def grade():
    trades = load(LOG, COLS).reindex(columns=COLS)
    open_ = trades.result.isna()
    finals = read_all(os.path.join(ROOT, "data", "odds", "*", "*_games.csv.gz"))
    if not len(finals):
        return
    finals = finals[(finals.status == "complete") & (finals.book == "consensus")].drop_duplicates("an_game_id")
    score = {str(r.an_game_id): (r.away_pts, r.home_pts) for r in finals.itertuples()}
    close = {str(r.an_game_id): (r.total, r.spread_home) for r in finals.itertuples()}
    done = 0
    for i in trades.index[open_]:
        r = trades.loc[i]
        if str(r.an_game_id) not in score:
            continue
        a, h = score[str(r.an_game_id)]
        if r.strategy.endswith("_total"):
            diff = (a + h) - r.line
            res = 0 if diff == 0 else (1 if (diff > 0) == (r.side == "over") else -1)
        else:
            margin = (h - a) if r.side == r.home else (a - h)    # side's own margin
            diff = margin + r.line
            res = 0 if diff == 0 else (1 if diff > 0 else -1)
        o = float(r.odds) if pd.notna(r.odds) else -110.0
        units = 0.0 if res == 0 else ((o / 100 if o > 0 else 100 / -o) if res > 0 else -1.0)
        trades.loc[i, ["away_pts", "home_pts", "result", "units"]] = [a, h, {1: "W", -1: "L", 0: "P"}[res], round(units, 3)]
        ct, cs = close[str(r.an_game_id)]
        if r.strategy.endswith("_total") and pd.notna(ct):
            trades.loc[i, ["close_line", "clv"]] = [ct, (ct - r.line) if r.side == "over" else (r.line - ct)]
        elif r.strategy.endswith("_spread") and pd.notna(cs):
            c_side = cs if r.side == r.home else -cs
            trades.loc[i, ["close_line", "clv"]] = [c_side, r.line - c_side]
        done += 1
    trades[COLS].to_csv(LOG, index=False)
    print(f"paper: {done} bets graded")
    # every game on the slate: final score + closing lines (the model's projections are already in each row)
    slate = load(SLATE)
    if len(slate):
        slate = slate.reindex(columns=list(dict.fromkeys(list(slate.columns) + SLATE_RESULT)))
        todo = slate.home_pts.isna() & slate.an_game_id.astype(str).isin(score)
        for i in slate.index[todo]:
            gid = str(slate.at[i, "an_game_id"])
            slate.loc[i, SLATE_RESULT] = [*score[gid], *close[gid]]
        slate.to_csv(SLATE, index=False)
        print(f"paper: {int(todo.sum())} slate games graded")


if __name__ == "__main__":
    for path in SLATES:
        if os.path.exists(path):
            log(path)
    grade()
    t = load(LOG, COLS)
    for s, d in t.groupby("strategy"):
        g = d[d.result.notna()]
        print(f"  {s}: {len(d)} logged, {len(g)} graded, {(g.result == 'W').sum()}-{(g.result == 'L').sum()}-"
              f"{(g.result == 'P').sum()}, {g.units.sum():+.2f} u, avg CLV {g.clv.mean():+.2f}")
