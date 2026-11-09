"""Who's missing, and how much they matter: one 'missing value' number per team per game.

For a team's game on date d (using only games before d):
  pool    = players who played for the team in the last `away_days` days AND whose most recent game
            (any team) was for this team (a traded player stops counting for his old team)
  minutes = his average minutes over his last 10 appearances for the team
  value   = Game Score per minute over the past 365 days (any team), shrunk toward the league rate
            with 100 pseudo-minutes, minus replacement level `repl`
  missing = sum over pool players NOT in tonight's box score of minutes * value
Game Score (Hollinger) = PTS + .4 FGM - .7 FGA - .4 (FTA - FTM) + .7 OREB + .3 DREB + STL + .7 AST
                         + .7 BLK - .4 PF - TOV

  python src/availability.py      # prints a few big-absence games as a sanity check
"""
import bisect
import glob
import os
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
REPL, AWAY_DAYS = 0.30, 90  # tuned Nov 8 2026 on 2015-21 (team_model tune_avail: MAE margin 10.08 -> 9.98)
SHRINK_MIN, VALUE_DAYS, LAST_N = 100, 365, 10


def load_players():
    p = pd.concat([pd.read_csv(f, dtype={"GAME_ID": str},
                               usecols=["GAME_ID", "GAME_DATE", "PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "MIN", "PTS",
                                        "FGM", "FGA", "FTM", "FTA", "OREB", "DREB", "STL", "AST", "BLK", "PF", "TOV"])
                   for f in glob.glob(os.path.join(ROOT, "data", "nbacom", "player_games_*.csv.gz"))])
    p["day"] = (pd.to_datetime(p.GAME_DATE) - pd.Timestamp("2000-01-01")).dt.days
    p["gmsc"] = (p.PTS + 0.4 * p.FGM - 0.7 * p.FGA - 0.4 * (p.FTA - p.FTM) + 0.7 * p.OREB + 0.3 * p.DREB + p.STL
                 + 0.7 * p.AST + 0.7 * p.BLK - 0.4 * p.PF - p.TOV)
    return p[p.MIN > 0].sort_values(["day", "GAME_ID"]).reset_index(drop=True)


class Availability:
    def __init__(self, p, stat="gmsc"):
        """stat: per-game column that measures a player's value (gmsc = Game Score; PTS = points only)."""
        p = p.assign(gmsc=p[stat])
        self.league_rate = p.gmsc.sum() / p.MIN.sum()
        # per player: appearance days, teams, cumulative minutes / game score (for 365-day value windows)
        self.days, self.teams, self.cmin, self.cgs = {}, {}, {}, {}
        for pid, d in p.groupby("PLAYER_ID", sort=False):
            self.days[pid] = d.day.to_numpy()
            self.teams[pid] = d.TEAM_ID.to_numpy()
            self.cmin[pid] = np.r_[0, d.MIN.cumsum().to_numpy()]
            self.cgs[pid] = np.r_[0, d.gmsc.cumsum().to_numpy()]
        # per team: chronological (day, player, minutes) appearances, and who played in each game
        self.team_apps = defaultdict(list)
        for r in p[["TEAM_ID", "day", "PLAYER_ID", "MIN"]].itertuples(index=False):
            self.team_apps[r.TEAM_ID].append((r.day, r.PLAYER_ID, r.MIN))
        self.team_days = {t: [a[0] for a in apps] for t, apps in self.team_apps.items()}
        self.played = p.groupby(["GAME_ID", "TEAM_ID"]).PLAYER_ID.apply(set).to_dict()

    def value(self, pid, day):
        """Game Score per minute over the past VALUE_DAYS, shrunk toward the league rate."""
        d = self.days[pid]
        i, j = np.searchsorted(d, day - VALUE_DAYS), np.searchsorted(d, day)
        mins = self.cmin[pid][j] - self.cmin[pid][i]
        gs = self.cgs[pid][j] - self.cgs[pid][i]
        return (gs + SHRINK_MIN * self.league_rate) / (mins + SHRINK_MIN)

    def pool(self, team, day, away_days):
        """{player: expected minutes} for players who count as this team's regulars before `day`."""
        apps, days = self.team_apps[team], self.team_days[team]
        lo, hi = bisect.bisect_left(days, day - away_days), bisect.bisect_left(days, day)
        recent = defaultdict(list)
        for k in range(lo, hi):
            recent[apps[k][1]].append(apps[k][2])
        out = {}
        for pid, mins in recent.items():
            j = np.searchsorted(self.days[pid], day) - 1   # his most recent game before `day`
            if j >= 0 and self.teams[pid][j] == team:
                out[pid] = float(np.mean(mins[-LAST_N:]))
        return out

    def missing(self, game_id, team, day, repl=REPL, away_days=AWAY_DAYS, detail=False):
        here = self.played.get((game_id, team), set())
        out = [(pid, m, self.value(pid, day) - repl) for pid, m in self.pool(team, day, away_days).items()
               if pid not in here]
        total = sum(m * v for _, m, v in out)
        return (total, out) if detail else total


def team_missing_parts(g, av, away_days=AWAY_DAYS):
    """For every row of team_model's game table: (sum of minutes x value, sum of minutes) over missing
    players, with value before subtracting replacement. missing(repl) = A - repl * B, so tuning `repl`
    needs no recomputation."""
    day = (g.date - pd.Timestamp("2000-01-01")).dt.days
    A, B = np.zeros(len(g)), np.zeros(len(g))
    for i, (gid, t, d) in enumerate(zip(g.GAME_ID, g.TEAM_ID, day)):
        _, det = av.missing(gid, t, d, 0.0, away_days, detail=True)
        A[i] = sum(m * v for _, m, v in det)
        B[i] = sum(m for _, m, _ in det)
    return A, B


if __name__ == "__main__":
    p = load_players()
    av = Availability(p)
    names = p.drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID").PLAYER_NAME
    print(f"league Game Score per minute: {av.league_rate:.3f}")
    games = p[p.GAME_DATE >= "2024-10-22"].drop_duplicates(["GAME_ID", "TEAM_ID"])
    rows = []
    for r in games.itertuples(index=False):
        tot, det = av.missing(r.GAME_ID, r.TEAM_ID, r.day, detail=True)
        rows.append((tot, r.GAME_DATE, r.TEAM_ID, det))
    rows.sort(key=lambda x: -x[0])
    for tot, date, team, det in rows[:8]:
        who = ", ".join(f"{names.get(pid, pid)} {m:.0f}min x {v:+.2f}" for pid, m, v in sorted(det, key=lambda x: -x[1] * x[2])[:4])
        print(f"{date} team {team}: missing {tot:5.1f} | {who}")
    vals = np.array([x[0] for x in rows])
    print(f"2024-26 team-games: missing value mean {vals.mean():.2f}, median {np.median(vals):.2f}, "
          f"90th pct {np.percentile(vals, 90):.2f}, share with 0: {(vals == 0).mean():.0%}")
