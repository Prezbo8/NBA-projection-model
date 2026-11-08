"""Player props model v1: projected PTS / REB / AST / 3PM / STL / BLK (+ combos) for every player-game.

For a player's game on date d, using only games before d:
  minutes  = recency-weighted average of his minutes (half-life MIN_HL games)
             + BOOST x his share of the minutes of missing teammates (availability.py's pool)
  rate[s]  = per-minute stat over the past 365 days, weights 0.5**(age_days/RATE_HL),
             shrunk toward the league per-minute rate with K pseudo-minutes
  pace     = team model's projected possessions (data/backtest/team_preds.csv) / team's recent average
  opp[s]   = stat s the opponent allows per possession / league, recency-weighted, shrunk
  proj[s]  = minutes x rate[s] x pace x opp[s]; combos are sums
Scored only on players who played (props on players who sit are void).

  python src/player_model.py tune                       # grid on 2021-22 + 2022-23 (MAE vs actual)
  python src/player_model.py backtest 2021-22 2026-27   # writes data/backtest/player_preds.csv.gz
"""
import glob
import itertools
import os
import sys

import numpy as np
import pandas as pd

import availability
import team_model

ROOT = os.path.join(os.path.dirname(__file__), "..")
PREDS = os.path.join(ROOT, "data", "backtest", "player_preds.csv.gz")
STATS = ["PTS", "REB", "AST", "FG3M", "STL", "BLK"]
COMBOS = {"PRA": ["PTS", "REB", "AST"], "PR": ["PTS", "REB"], "PA": ["PTS", "AST"], "RA": ["REB", "AST"],
          "STOCKS": ["STL", "BLK"]}
MIN_HL, RATE_HL, K, BOOST = 4, 60, 25, 0.0    # tuned Nov 8 2026 on 2021-23 (fixed eval set; any minutes boost hurt)
OPP_HL, OPP_K = 90, 15                        # opponent allowed-rate half-life (days) / pseudo-games
TUNE_SEASONS = ["2021-22", "2022-23"]
DAY0 = pd.Timestamp("2000-01-01")


def load():
    p = availability.load_players()
    full = pd.concat([pd.read_csv(f, dtype={"GAME_ID": str}, usecols=["GAME_ID", "PLAYER_ID", "REB", "FG3M", "SEASON",
                                                                       "SEASON_TYPE", "TEAM_ABBREVIATION", "MATCHUP"])
                      for f in glob.glob(os.path.join(ROOT, "data", "nbacom", "player_games_*.csv.gz"))])
    p = p.merge(full, on=["GAME_ID", "PLAYER_ID"])
    p["OPP"] = p.MATCHUP.str[-3:]
    return p.sort_values(["day", "GAME_ID", "PLAYER_ID"]).reset_index(drop=True)


def player_asof(days, mins, vals, j, day, min_hl, rate_hl, k, league):
    """Expected minutes (before teammate boost) and per-minute rates from a player's games [0, j)
    (sorted by day) as of `day`. Shared by the backtest and today.py."""
    if j == 0:
        return np.nan, dict(league)                # no history: minutes get a rookie prior later
    lo = np.searchsorted(days, day - 365)
    # minutes: last games, weighted by games-ago
    ga = np.arange(j - 1, lo - 1, -1) if j > lo else np.array([j - 1])
    wm = 0.5 ** ((j - 1 - ga) / min_hl)
    exp_min = (wm * mins[ga]).sum() / wm.sum()
    # rates: weighted by days-ago, shrunk toward league
    seg = slice(lo, j)
    wd = 0.5 ** ((day - days[seg]) / rate_hl)
    wmin = (wd * mins[seg]).sum()
    return exp_min, {s: ((wd * vals[s][seg]).sum() + k * league[s]) / (wmin + k) for s in STATS}


def league_rates(p):
    return {s: p[s].sum() / p.MIN.sum() for s in STATS}


def player_features(p, targets, min_hl, rate_hl, k):
    """Expected minutes (before teammate boost) and per-minute rates for target rows."""
    exp_min = np.full(len(p), np.nan)
    rates = {s: np.full(len(p), np.nan) for s in STATS}
    league = league_rates(p)
    tmask = np.zeros(len(p), bool)
    tmask[targets] = True
    for _, idx in p.groupby("PLAYER_ID", sort=False).indices.items():
        idx = np.sort(idx)
        t = idx[tmask[idx]]
        if not len(t):
            continue
        days = p.day.to_numpy()[idx]
        mins = p.MIN.to_numpy()[idx]
        vals = {s: p[s].to_numpy()[idx] for s in STATS}
        pos = np.searchsorted(idx, t)            # position of each target within this player's games
        for i, j in zip(t, pos):
            exp_min[i], r = player_asof(days, mins, vals, j, days[j], min_hl, rate_hl, k, league)
            for s in STATS:
                rates[s][i] = r[s]
    return exp_min, rates


def weighted_asof(days, poss, vals, j, day, half_life, league=None, k_poss=0.0):
    """Recency-weighted per-possession averages from rows [0, j) as of `day` (365-day window).
    With `league`: rate relative to league, shrunk with k_poss pseudo-possessions. Without: mean of poss."""
    lo = np.searchsorted(days, day - 365)
    w = 0.5 ** ((day - days[lo:j]) / half_life)
    if league is None:
        return (w * poss[lo:j]).sum() / w.sum() if j > lo else np.nan
    wp = (w * poss[lo:j]).sum()
    return {s: ((w * vals[s][lo:j]).sum() + k_poss * league[s]) / (wp + k_poss) / league[s] for s in league}


ALLOWED = ["PTS", "REB", "AST", "FG3M", "STL", "BLK"]


def opp_tables(g):
    """Per defense team: sorted arrays of the stats scored against it (for allowed-rate lookups)."""
    t = g.assign(day=(g.date - DAY0).dt.days)
    league = {s: t[s].sum() / t.poss.sum() for s in ALLOWED}
    tabs = {}
    for d_id, d in t.groupby("OPP_ID"):
        d = d.sort_values("day")
        tabs[d_id] = (d.GAME_ID.to_numpy(), d.day.to_numpy(), d.poss.to_numpy(), {s: d[s].to_numpy() for s in ALLOWED})
    return tabs, league


def opp_allowed(g):
    """Per team-game: what the opponent allows per possession for each stat, relative to league,
    from the opponent's earlier games (recency-weighted, shrunk). Keyed by (GAME_ID, OPP_ID)."""
    tabs, league = opp_tables(g)
    out = {}
    for d_id, (gids, days, poss, vals) in tabs.items():
        for j, (gid, day) in enumerate(zip(gids, days)):
            out[(gid, d_id)] = weighted_asof(days, poss, vals, j, day, OPP_HL, league, OPP_K * 100.0)
    return out


def team_pace(g):
    """Team's recency-weighted average game possessions before each game, keyed by (GAME_ID, TEAM_ID)."""
    out = {}
    t = g.assign(day=(g.date - DAY0).dt.days)
    for tid, d in t.groupby("TEAM_ID"):
        d = d.sort_values("day")
        days, poss = d.day.to_numpy(), d.poss.to_numpy()
        for j, (gid, day) in enumerate(zip(d.GAME_ID, days)):
            out[(gid, tid)] = weighted_asof(days, poss, None, j, day, 60)
    return out


class Context:
    """Everything that doesn't depend on the tuned settings, computed once."""

    def __init__(self, seasons):
        self.p = load()
        self.targets = np.flatnonzero(self.p.SEASON.isin(seasons).to_numpy())
        g = team_model.load()
        self.opp_of = dict(zip(zip(g.GAME_ID, g.TEAM_ID), g.OPP_ID))   # (game, team) -> opponent TEAM_ID
        self.opp = opp_allowed(g)
        self.pace = team_pace(g)
        tp = pd.read_csv(team_model.PREDS, dtype={"game_id": str})
        self.pred_pace = dict(zip(tp.game_id, tp.pred_pace))
        self.av = availability.Availability(availability.load_players())
        # missing teammates' minutes per (game, team), and each present regular's expected minutes
        self.missing_min, self.pool_min = {}, {}
        tg = self.p.iloc[self.targets].drop_duplicates(["GAME_ID", "TEAM_ID"])
        for gid, tid, day in zip(tg.GAME_ID, tg.TEAM_ID, tg.day):
            pool = self.av.pool(tid, day, availability.AWAY_DAYS)
            here = self.av.played.get((gid, tid), set())
            self.missing_min[(gid, tid)] = sum(m for pid, m in pool.items() if pid not in here)
            self.pool_min[(gid, tid)] = sum(m for pid, m in pool.items() if pid in here)
        self.cache = {}
        # fixed evaluation set for tuning: players at >= 20 expected minutes under a fixed baseline
        # (min_hl 6, no boost), so every config is graded on the same player-games
        base, _ = player_features(self.p, self.targets, 6, 120, 150)
        self.eval_ids = set(self.p.index[self.targets][np.nan_to_num(base[self.targets]) >= 20])


def project(ctx, min_hl=MIN_HL, rate_hl=RATE_HL, k=K, boost=BOOST):
    key = (min_hl, rate_hl, k)
    if key not in ctx.cache:
        ctx.cache[key] = player_features(ctx.p, ctx.targets, min_hl, rate_hl, k)
    exp_min, rates = ctx.cache[key]
    p = ctx.p.iloc[ctx.targets]
    em = pd.Series(exp_min[ctx.targets], index=p.index).fillna(12.0)   # rookie / no-history prior
    gt = list(zip(p.GAME_ID, p.TEAM_ID))
    miss = np.array([ctx.missing_min.get(x, 0.0) for x in gt])
    pool = np.array([ctx.pool_min.get(x, 0.0) for x in gt])
    share = np.where(pool > 0, em / np.maximum(pool, 1), 0)
    minutes = np.minimum(em + boost * miss * share, 42.0)
    pace = np.array([ctx.pred_pace.get(gid, np.nan) / ctx.pace.get((gid, tid), np.nan) for gid, tid in gt])
    pace = np.nan_to_num(pace, nan=1.0)
    out = pd.DataFrame({"row": p.index.values, "game_id": p.GAME_ID.values, "date": p.GAME_DATE.values, "season": p.SEASON.values,
                        "season_type": p.SEASON_TYPE.values, "player_id": p.PLAYER_ID.values,
                        "player": p.PLAYER_NAME.values, "team": p.TEAM_ABBREVIATION.values, "opp": p.OPP.values,
                        "exp_min": minutes.round(1), "min": p.MIN.values})
    opp_team = [ctx.opp_of.get(x) for x in gt]
    for s in STATS:
        o = np.array([ctx.opp.get((gid, oteam), {}).get(s, 1.0) for (gid, _), oteam in zip(gt, opp_team)])
        out[f"proj_{s}"] = (minutes * rates[s][ctx.targets] * pace * o).round(2)
        out[s] = p[s].values
    for c, parts in COMBOS.items():
        out[f"proj_{c}"] = out[[f"proj_{s}" for s in parts]].sum(axis=1).round(2)
        out[c] = out[parts].sum(axis=1)
    return out


def score(out, seasons, eval_ids=None):
    d = out[out.season.isin(seasons) & (out.season_type == "Regular Season")]
    d = d[d.row.isin(eval_ids)] if eval_ids is not None else d[d.exp_min >= 20]
    return {s: (d[f"proj_{s}"] - d[s]).abs().mean() for s in STATS + ["PRA"]}


if __name__ == "__main__":
    if sys.argv[1] == "tune":
        ctx = Context(TUNE_SEASONS)
        print(f"min_hl | rate_hl | K | boost | MAE on {len(ctx.eval_ids):,} fixed player-games: " + " ".join(STATS + ["PRA"]))
        for mh, rh, k, b in itertools.product([2, 3, 4], [30, 45, 60], [10, 25, 50], [0.0, 0.1, 0.25]):
            m = score(project(ctx, mh, rh, k, b), TUNE_SEASONS, ctx.eval_ids)
            print(f"{mh:>6} | {rh:>7} | {k:>3} | {b:5.2f} | " + " ".join(f"{m[s]:.3f}" for s in STATS + ["PRA"]),
                  flush=True)
    elif sys.argv[1] == "backtest":
        a, b = int(sys.argv[2][:4]), int(sys.argv[3][:4])
        seasons = [f"{y}-{str(y + 1)[2:]}" for y in range(a, b + 1)]
        out = project(Context(seasons))
        out.to_csv(PREDS, index=False)
        for s, d in out.groupby("season"):
            m = score(d, [s])
            print(f"{s}: {len(d):,} player-games | MAE " + " ".join(f"{k} {v:.2f}" for k, v in m.items()))
        print(f"wrote {len(out):,} rows to {PREDS}")
