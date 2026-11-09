"""Do nba.com tracking stats improve the v3 totals model? (protocol: research/README.md)

Each team-game gets the team's tracking stats as of the day BEFORE the game (data/tracking, one row per team per
game day), weighted by recency with the model's half-life, so there is no look-ahead. Each group of terms is added
to v3 (with_v3) on its own and judged on MAE total over TUNE_SEASONS.

  TUNE_SEASONS=2021-22,2022-23,2023-24 python research/tracking_totals.py           # all groups
  CONFIGS="v3,B open-3 luck" TUNE_SEASONS=2024-25,2025-26 python research/tracking_totals.py   # one look at test
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import team_model as tm  # noqa: E402

WINDOW = tm.WINDOW
_ridge = tm.ridge


def ridge_safe(X, y, w, penalized, lam):
    """Same ridge, but drops columns that are all zero in this fit (a tracking term before its data starts,
    Oct 2021) instead of failing on a singular matrix. Their coefficient is 0 = no effect."""
    live = np.any(X != 0, axis=0)
    if live.all():
        return _ridge(X, y, w, penalized, lam)
    b = np.zeros(X.shape[1])
    b[live] = _ridge(X[:, live], y, w, penalized[live], lam)
    return b


tm.ridge = ridge_safe   # research only; the live model is unchanged


def load_tracking(g):
    """Tracking rows + that day's box score (FGA, opponent FGA) for the share denominators."""
    tr = pd.concat([pd.read_csv(p) for p in glob.glob(os.path.join(tm.ROOT, "data", "tracking", "tracking_*.csv.gz"))])
    tr["date"] = pd.to_datetime(tr.date)
    box = g[["TEAM_ID", "date", "GAME_ID", "FGA"]].copy()
    box["opp_FGA"] = g.groupby("GAME_ID").FGA.transform("sum") - g.FGA
    return tr.merge(box, on=["TEAM_ID", "date"], how="inner")   # regular-season days that have a box score


FEATS = ["owo_share", "dwo_share", "owo_luck", "dwo_luck", "dfg_diff", "contests", "deflections", "drives", "drive_ppd"]
SUMS = {  # name: column summed over earlier days (weighted)
    "fga": "FGA", "opp_fga": "opp_FGA", "games": None,
    "owo_fga": "owo_FGA", "owo_3a": "owo_FG3A", "owo_3m": "owo_FG3M",
    "dwo_fga": "dwo_FGA", "dwo_3a": "dwo_FG3A", "dwo_3m": "dwo_FG3M",
    "d_fgm": "dfg_D_FGM", "d_fga": "dfg_D_FGA", "d_exp": None,
    "contests": "hus_CONTESTED_SHOTS", "deflections": "hus_DEFLECTIONS",
    "drives": "drv_DRIVES", "drive_pts": "drv_DRIVE_PTS",
}


def asof_features(g, tr, half_life=tm.HALF_LIFE):
    """Per team-game row of g: recency-weighted tracking rates from days before the game, centered on the
    league (same weights), 0 when the team has no earlier tracking data (= league average)."""
    tr = tr.assign(games=1.0, d_exp=tr.dfg_NORMAL_FG_PCT * tr.dfg_D_FGA)
    cols = list(SUMS)
    vals = np.column_stack([tr[c if SUMS[c] is None else SUMS[c]].to_numpy(float) for c in cols])
    vals = np.nan_to_num(vals)
    tday = (tr.date - pd.Timestamp("2000-01-01")).dt.days.to_numpy()
    tteam = tr.TEAM_ID.to_numpy()
    gday = (g.date - pd.Timestamp("2000-01-01")).dt.days.to_numpy()
    out = {k: np.full(len(g), np.nan) for k in FEATS}
    for day in np.unique(gday):
        m = (tday < day) & (tday >= day - WINDOW)
        if not m.any():
            continue
        w = 0.5 ** ((day - tday[m]) / half_life)
        S = vals[m] * w[:, None]
        lg = dict(zip(cols, S.sum(0)))
        lg3 = (lg["owo_3m"] + lg["dwo_3m"]) / max(lg["owo_3a"] + lg["dwo_3a"], 1e-9)   # league wide-open 3P%
        teams = pd.DataFrame(S, columns=cols).groupby(tteam[m]).sum()
        rows = np.flatnonzero(gday == day)
        for r in rows:
            tid = g.TEAM_ID.iat[r]
            if tid not in teams.index:
                continue
            t = teams.loc[tid]
            gm = max(t.games, 1e-9)
            out["owo_share"][r] = t.owo_fga / max(t.fga, 1e-9) - lg["owo_fga"] / lg["fga"]
            out["dwo_share"][r] = t.dwo_fga / max(t.opp_fga, 1e-9) - lg["dwo_fga"] / lg["opp_fga"]
            out["owo_luck"][r] = 3 * (t.owo_3m - lg3 * t.owo_3a) / gm          # points per game above league on open 3s
            out["dwo_luck"][r] = 3 * (t.dwo_3m - lg3 * t.dwo_3a) / gm          # ... allowed (positive = opponents lucky)
            out["dfg_diff"][r] = (t.d_fgm - t.d_exp) / max(t.d_fga, 1e-9) - (lg["d_fgm"] - lg["d_exp"]) / lg["d_fga"]
            out["contests"][r] = t.contests / gm - lg["contests"] / lg["games"]
            out["deflections"][r] = t.deflections / gm - lg["deflections"] / lg["games"]
            out["drives"][r] = t.drives / gm - lg["drives"] / lg["games"]
            out["drive_ppd"][r] = t.drive_pts / max(t.drives, 1e-9) - lg["drive_pts"] / lg["drives"]
    return {k: np.nan_to_num(v) for k, v in out.items()}


def add_columns(g, f, feats):
    """Own (offense) and opponent (defense) versions of every feature, plus game sums for pace."""
    for k, v in feats.items():
        g[k] = v
        g[f"opp_{k}"] = f.opp_of(v)
        g[f"sum_{k}"] = g[k] + g[f"opp_{k}"]


# name: (extra ppp terms, extra pace terms). Offense terms use the team's own value, defense terms the opponent's.
GROUPS = {
    "v3": ([], []),
    "A open-shot share": (["owo_share", "opp_dwo_share"], []),
    "B open-3 luck": (["owo_luck", "opp_dwo_luck"], []),
    "C defended FG% vs normal": (["opp_dfg_diff"], []),
    "D hustle": (["opp_contests", "opp_deflections"], ["sum_deflections"]),
    "E drives": (["drives", "drive_ppd"], ["sum_drives"]),
}
GROUPS["F all"] = (sorted({c for p, _ in GROUPS.values() for c in p}), sorted({c for _, q in GROUPS.values() for c in q}))


if __name__ == "__main__":
    g = tm.load()
    f = tm.Fitter(g)
    tm.with_v3(g, f)
    tr = load_tracking(g)
    print(f"tracking: {tr.date.min().date()} .. {tr.date.max().date()}, {len(tr):,} team-days", flush=True)
    add_columns(g, f, asof_features(g, tr))
    in_tune = g.SEASON.isin(tm.TUNE_SEASONS) & g.SEASON_TYPE.eq("Regular Season")
    print("feature means / sd on the tune rows:\n"
          + g.loc[in_tune, FEATS].describe().loc[["mean", "std"]].round(4).to_string(), flush=True)
    only = os.environ.get("CONFIGS")
    groups = {k: v for k, v in GROUPS.items() if not only or k in only.split(",")}
    print(f"config | MAE total | MAE margin | extra coefs (ppp..., pace...)  ({', '.join(tm.TUNE_SEASONS)})")
    for name, (ppp, pace) in groups.items():
        f.set_features(tm.V3_PPP + ppp)
        f.set_pace_features(tm.V3_PACE + pace)
        pg = tm.per_game(g, *tm.run(g, f, tm.TUNE_SEASONS, tm.HALF_LIFE, tm.LAM))
        mt, mm = tm.score(pg)
        by = " ".join(f"{s} {tm.score(d)[0]:.3f}" for s, d in pg.groupby("season"))
        n_ppp = 3 + len(tm.V3_PPP)   # home, b2b, opp b2b, v3 terms come first
        coefs = list(f.last_extras[n_ppp:n_ppp + len(ppp)]) + list(f.last_extras[-len(pace):] if pace else [])
        print(f"{name:<26} | {mt:9.3f} | {mm:10.3f} | " + ", ".join(f"{c}={x:+.3f}" for c, x in zip(ppp + pace, coefs)))
        print(f"    [{by}]", flush=True)
