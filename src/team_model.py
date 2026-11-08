"""Team model v2: projected points for both teams in every game -> total, spread, team totals.

Before each game day, two weighted ridge regressions are refit on earlier games only (no look-ahead):
  pace:  game possessions        = mu_p + pace[team] + pace[opp]
  ppp:   team points / possession = mu + off[team] + def[opp] + home*(home, not neutral)
                                     + b2b_own*(team on a back-to-back) + b2b_opp*(opp on a back-to-back)
                                     + miss_own*(team's missing value) + miss_opp*(opp's missing value)
Missing value (src/availability.py) = expected minutes x (Game Score/min - replacement) of regulars who
aren't playing. Fitted jointly with the ratings, so team ratings mean "at full strength" (v1 had no
availability terms; `--v1` reproduces it).
Recent games weigh more (0.5 ** (age_days / half_life)); team terms are shrunk toward 0 by `lam`.
Projected points = pace * ppp. Teams are nba.com TEAM_IDs (stable through Seattle->OKC, NJ->BKN).

  python src/team_model.py tune                       # grid of half_life x lam on 2015-16 .. 2020-21
  python src/team_model.py tune_avail                 # grid of replacement x away_days on 2015-16 .. 2020-21
  python src/team_model.py backtest 2007-08 2026-27   # writes data/backtest/team_preds.csv (add --v1 for v1)
"""
import glob
import itertools
import os
import sys

import numpy as np
import pandas as pd

import availability

ROOT = os.path.join(os.path.dirname(__file__), "..")
PREDS = os.path.join(ROOT, "data", "backtest", "team_preds.csv")
HALF_LIFE, LAM = 90, 5    # tuned Nov 8 2026 on 2015-21 (MAE total 14.67, margin 10.08)
WINDOW = 400              # days of history in each fit (older games have ~0 weight anyway)
REPL, AWAY_DAYS = availability.REPL, availability.AWAY_DAYS
TUNE_SEASONS = ["2015-16", "2016-17", "2017-18", "2018-19", "2019-20", "2020-21"]


def load():
    """One row per team per game, with the opponent's stats, possessions, home/neutral and rest."""
    t = pd.concat([pd.read_csv(f, dtype={"GAME_ID": str})
                   for f in glob.glob(os.path.join(ROOT, "data", "nbacom", "team_games_*.csv.gz"))])
    t["date"] = pd.to_datetime(t.GAME_DATE)
    t["poss_est"] = t.FGA + 0.44 * t.FTA - t.OREB + t.TOV
    o = t[["GAME_ID", "TEAM_ID", "TEAM_ABBREVIATION", "PTS", "poss_est"]].rename(
        columns={"TEAM_ID": "OPP_ID", "TEAM_ABBREVIATION": "OPP", "PTS": "OPP_PTS", "poss_est": "opp_poss_est"})
    g = t.merge(o, on="GAME_ID")
    g = g[g.TEAM_ID != g.OPP_ID].copy()
    g["poss"] = (g.poss_est + g.opp_poss_est) / 2          # both teams' estimates averaged
    g["ppp"] = g.PTS / g.poss
    g["is_home"] = g.MATCHUP.str.contains(" vs. ")
    g["neutral"] = ~g.is_home.groupby(g.GAME_ID).transform("any")  # both listed '@'
    g = g.sort_values(["TEAM_ID", "date"])
    g["rest"] = g.groupby("TEAM_ID").date.diff().dt.days     # NaN for a team's first game in the data
    g["b2b"] = g.rest.eq(1)
    # experimental features (v3 candidates; v1/v2 don't use them)
    g["rested"] = g.rest.ge(3) & g.rest.le(10)                 # 2+ days off (not the season's first game)
    day = (g.date - pd.Timestamp("2000-01-01")).dt.days
    prev2 = g.groupby("TEAM_ID").date.shift(2)
    g["three4"] = ((g.date - prev2).dt.days <= 3).fillna(False)  # 3rd game in 4 nights
    loc = g.apply(lambda r: r.TEAM_ABBREVIATION if r.is_home or r.neutral else r.OPP, axis=1)  # where it's played
    lat, lon = loc.map(lambda t: ARENA.get(t, (np.nan, np.nan))[0]), loc.map(lambda t: ARENA.get(t, (np.nan, np.nan))[1])
    plat, plon = lat.groupby(g.TEAM_ID).shift(1), lon.groupby(g.TEAM_ID).shift(1)
    g["travel"] = (km(plat, plon, lat, lon) / 1000).where(g.rest.le(10), 0).fillna(0)  # 1000s of km since last game
    del day
    feats = ["b2b", "rested", "three4", "travel"]
    opp = g[["GAME_ID", "TEAM_ID"] + feats].rename(columns={"TEAM_ID": "OPP_ID", **{c: f"opp_{c}" for c in feats}})
    g = g.merge(opp, on=["GAME_ID", "OPP_ID"])
    return g.sort_values(["date", "GAME_ID", "TEAM_ID"]).reset_index(drop=True)


def km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371 * 2 * np.arcsin(np.sqrt(a))


# arena locations (city level) by nba.com abbreviation, incl. old franchises
ARENA = {"ATL": (33.76, -84.39), "BOS": (42.37, -71.06), "BKN": (40.68, -73.97), "NJN": (40.73, -74.17),
         "CHA": (35.23, -80.84), "CHI": (41.88, -87.67), "CLE": (41.50, -81.69), "DAL": (32.79, -96.81),
         "DEN": (39.75, -105.0), "DET": (42.34, -83.06), "GSW": (37.77, -122.39), "HOU": (29.75, -95.36),
         "IND": (39.76, -86.16), "LAC": (34.04, -118.27), "LAL": (34.04, -118.27), "MEM": (35.14, -90.05),
         "MIA": (25.78, -80.19), "MIL": (43.04, -87.92), "MIN": (44.98, -93.28), "NOP": (29.95, -90.08),
         "NOH": (29.95, -90.08), "NOK": (35.46, -97.52), "NYK": (40.75, -73.99), "OKC": (35.46, -97.52),
         "SEA": (47.62, -122.35), "ORL": (28.54, -81.38), "PHI": (39.90, -75.17), "PHX": (33.45, -112.07),
         "POR": (45.53, -122.67), "SAC": (38.58, -121.50), "SAS": (29.43, -98.44), "TOR": (43.64, -79.38),
         "UTA": (40.77, -111.90), "WAS": (38.90, -77.02)}


def ridge(X, y, w, penalized, lam):
    """Weighted ridge: (X'WX + lam*P) b = X'Wy, P = 1 on penalized columns."""
    Xw = X * w[:, None]
    A = X.T @ Xw + lam * np.diag(penalized.astype(float))
    return np.linalg.solve(A, Xw.T @ y)


class Fitter:
    """Holds the game table as arrays so each per-date fit is fast."""

    def __init__(self, g):
        self.g = g
        ids = sorted(set(g.TEAM_ID) | set(g.OPP_ID))
        self.idx = {t: i for i, t in enumerate(ids)}
        self.n = len(ids)
        self.team = g.TEAM_ID.map(self.idx).to_numpy()
        self.opp = g.OPP_ID.map(self.idx).to_numpy()
        self.day = (g.date - pd.Timestamp("2000-01-01")).dt.days.to_numpy()
        self.home = (g.is_home & ~g.neutral).to_numpy(float)
        self.b2b = g.b2b.to_numpy(float)
        self.opp_b2b = g.opp_b2b.to_numpy(float)
        self.poss = g.poss.to_numpy()
        self.ppp = g.ppp.to_numpy()
        self.miss = self.opp_miss = None   # set_missing() turns on the v2 availability terms
        self.feat = np.zeros((len(g), 0))  # set_features() adds experimental terms (v3 candidates)
        self.pace_hl = None                # None: pace uses the same half-life as ppp

    def set_features(self, cols):
        """Extra unpenalized ppp terms, e.g. ['rested', 'opp_rested', 'three4', 'opp_three4', 'travel', 'opp_travel']."""
        self.feat_cols = list(cols)
        self.feat = self.g[self.feat_cols].to_numpy(float) if cols else np.zeros((len(self.g), 0))

    def set_missing(self, own):
        """own: missing value per row. The opponent's value comes from the other row of the same game."""
        key = dict(zip(zip(self.g.GAME_ID, self.g.TEAM_ID), own))
        self.miss = np.asarray(own, float)
        self.opp_miss = np.array([key[(gid, o)] for gid, o in zip(self.g.GAME_ID, self.g.OPP_ID)])

    def fit(self, day, half_life, lam):
        """Ratings from games before `day` (days since 2000-01-01)."""
        m = (self.day < day) & (self.day >= day - WINDOW)
        n, rows = self.n, np.flatnonzero(m)
        w = 0.5 ** ((day - self.day[rows]) / half_life)
        wp = w if self.pace_hl is None else 0.5 ** ((day - self.day[rows]) / self.pace_hl)
        k = len(rows)
        # pace: intercept + one 'pace' vector used for both team and opponent
        Xp = np.zeros((k, 1 + n))
        Xp[:, 0] = 1
        Xp[np.arange(k), 1 + self.team[rows]] += 1
        Xp[np.arange(k), 1 + self.opp[rows]] += 1
        bp = ridge(Xp, self.poss[rows], wp, np.r_[0, np.ones(n)], lam)
        # ppp: intercept + off[team] + def[opp] + home + b2b_own + b2b_opp
        extra = self.extras(rows)
        Xo = np.zeros((k, 1 + 2 * n))
        Xo[:, 0] = 1
        Xo[np.arange(k), 1 + self.team[rows]] = 1
        Xo[np.arange(k), 1 + n + self.opp[rows]] = 1
        Xo = np.hstack([Xo, extra])
        # lam works like `lam` (weighted) pseudo-games at league average: unit-free, same for both fits
        bo = ridge(Xo, self.ppp[rows], w, np.r_[0, np.ones(2 * n), np.zeros(extra.shape[1])], lam)
        return bp, bo

    def extras(self, rows):
        """Unpenalized terms: home, b2b own/opp, and (v2) missing own/opp."""
        cols = [self.home[rows], self.b2b[rows], self.opp_b2b[rows]]
        if self.miss is not None:
            cols += [self.miss[rows], self.opp_miss[rows]]
        return np.column_stack(cols + [self.feat[rows, i] for i in range(self.feat.shape[1])])

    def predict(self, rows, bp, bo):
        n = self.n
        pace = bp[0] + bp[1 + self.team[rows]] + bp[1 + self.opp[rows]]
        ppp = bo[0] + bo[1 + self.team[rows]] + bo[1 + n + self.opp[rows]] + self.extras(rows) @ bo[1 + 2 * n:]
        return pace, ppp


def run(g, f, seasons, half_life, lam):
    """Projected points for every team-game in `seasons`, each from a fit on earlier days only."""
    out = np.full(len(g), np.nan)
    pace_out = np.full(len(g), np.nan)
    target = np.flatnonzero(g.SEASON.isin(seasons).to_numpy())
    for day in np.unique(f.day[target]):
        rows = target[f.day[target] == day]
        bp, bo = f.fit(day, half_life, lam)
        pace, ppp = f.predict(rows, bp, bo)
        out[rows], pace_out[rows] = pace * ppp, pace
    f.last_extras = bo[1 + 2 * f.n:]  # home, b2b own/opp, (miss own/opp) from the last fit
    return out, pace_out


def per_game(g, pts, pace):
    """Team rows -> one row per game (home side; for neutral games the row nba.com lists first)."""
    g = g.assign(pred_pts=pts, pred_pace=pace)
    opp = g[["GAME_ID", "TEAM_ID", "pred_pts"]].rename(columns={"TEAM_ID": "OPP_ID", "pred_pts": "pred_opp"})
    g = g.merge(opp, on=["GAME_ID", "OPP_ID"])
    h = g[g.is_home | (g.neutral & (g.TEAM_ID < g.OPP_ID))].dropna(subset=["pred_pts"])
    return pd.DataFrame({
        "game_id": h.GAME_ID, "date": h.date.dt.strftime("%Y-%m-%d"), "season": h.SEASON,
        "season_type": h.SEASON_TYPE, "home": h.TEAM_ABBREVIATION, "away": h.OPP, "neutral": h.neutral,
        "home_b2b": h.b2b, "away_b2b": h.opp_b2b,
        "pred_home": h.pred_pts.round(2), "pred_away": h.pred_opp.round(2),
        "pred_total": (h.pred_pts + h.pred_opp).round(2), "pred_margin": (h.pred_pts - h.pred_opp).round(2),
        "pred_pace": h.pred_pace.round(2), "home_pts": h.PTS, "away_pts": h.OPP_PTS,
    }).sort_values(["date", "game_id"])


def score(p):
    p = p[p.season_type == "Regular Season"]
    return ((p.pred_total - (p.home_pts + p.away_pts)).abs().mean(),
            (p.pred_margin - (p.home_pts - p.away_pts)).abs().mean())


def with_missing(g, f, repl=REPL, away_days=AWAY_DAYS):
    av = availability.Availability(availability.load_players())
    A, B = availability.team_missing_parts(g, av, away_days)
    f.set_missing(A - repl * B)
    return av


if __name__ == "__main__":
    g = load()
    f = Fitter(g)
    v1 = "--v1" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--v1"]
    if args[0] == "tune_avail":
        av = availability.Availability(availability.load_players())
        print(f"(half_life {HALF_LIFE}, lam {LAM}) | v1 baseline: MAE total / margin "
              + "%.3f / %.3f" % score(per_game(g, *run(g, f, TUNE_SEASONS, HALF_LIFE, LAM))), flush=True)
        print("away_days | repl | MAE total | MAE margin | last fit: home, b2b own, b2b opp, miss own, miss opp")
        for away in (90, 150):
            A, B = availability.team_missing_parts(g, av, away)
            for repl in (0.3, 0.35, 0.4, 0.5):
                f.set_missing(A - repl * B)
                mt, mm = score(per_game(g, *run(g, f, TUNE_SEASONS, HALF_LIFE, LAM)))
                print(f"{away:>9} | {repl:4.1f} | {mt:9.3f} | {mm:10.3f} | "
                      + ", ".join(f"{x:+.4f}" for x in f.last_extras), flush=True)
        sys.exit()
    if args[0] == "ablate":
        # each idea alone and together, on v1 (no availability) and v2; scored on the tune seasons only
        rest = ["rested", "opp_rested", "three4", "opp_three4"]
        trav = ["travel", "opp_travel"]
        # Nov 8 2026 round 1 (rejected, all worse on 2015-21): +rest, +travel, pace_hl 180 / 365, combos
        configs = [("base", [], None), ("+pace_hl 30", [], 30), ("+pace_hl 45", [], 45), ("+pace_hl 60", [], 60)]
        del rest, trav
        print("version | config | MAE total | MAE margin | last fit extras (home, b2b, b2b opp, [miss], features...)")
        for ver in ("v1", "v2"):
            if ver == "v2":
                with_missing(g, f)
            for name, cols, phl in configs:
                f.set_features(cols)
                f.pace_hl = phl
                mt, mm = score(per_game(g, *run(g, f, TUNE_SEASONS, HALF_LIFE, LAM)))
                print(f"{ver} | {name:<26} | {mt:9.3f} | {mm:10.3f} | " + ", ".join(f"{x:+.4f}" for x in f.last_extras),
                      flush=True)
        sys.exit()
    if not v1 and args[0] in ("tune", "backtest"):
        with_missing(g, f)
    sys.argv = [sys.argv[0]] + args
    if sys.argv[1] == "tune":
        print("half_life | lam | MAE total | MAE margin   (regular season, " + ", ".join(TUNE_SEASONS) + ")")
        for hl, lam in itertools.product([45, 60, 90, 120], [0.5, 1, 2, 5]):
            mt, mm = score(per_game(g, *run(g, f, TUNE_SEASONS, hl, lam)))
            print(f"{hl:>9} | {lam:>3} | {mt:9.3f} | {mm:10.3f}", flush=True)
    elif sys.argv[1] == "backtest":
        a, b = int(sys.argv[2][:4]), int(sys.argv[3][:4])
        seasons = [f"{y}-{str(y + 1)[2:]}" for y in range(a, b + 1)]
        hl = float(sys.argv[4]) if len(sys.argv) > 4 else HALF_LIFE
        lam = float(sys.argv[5]) if len(sys.argv) > 5 else LAM
        p = per_game(g, *run(g, f, seasons, hl, lam))
        os.makedirs(os.path.dirname(PREDS), exist_ok=True)
        p.to_csv(PREDS, index=False)
        for s, d in p.groupby("season"):
            mt, mm = score(d)
            print(f"{s}: {len(d)} games | MAE total {mt:.2f} | MAE margin {mm:.2f}")
        print(f"wrote {len(p):,} games to {PREDS} ({'v1' if v1 else f'v2: repl {REPL}, away_days {AWAY_DAYS}'}, "
              f"half_life {hl}, lam {lam}) | last fit: home, b2b own, b2b opp(, miss own, miss opp) = "
              + ", ".join(f"{x:+.4f}" for x in f.last_extras))
