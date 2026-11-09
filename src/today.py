"""Today's slate: team + player projections vs current Action Network lines -> docs/today.json.

Uses the exact backtest code (team_model Fitter, availability pool/values, player_model as-of helpers),
fitted on every game before today. Who's out: Rotowire's play-probability (pct_play) per listed player,
ESPN 'Out' as a fallback. Expected missing value = sum of P(out) x minutes x (value - replacement).
Props are projected for pool players with P(out) < 0.5 (a prop on a player who sits is void).

  python src/today.py           # writes docs/today.json
  python src/today.py --tomorrow    # tomorrow's slate, totals only -> docs/tomorrow.json (evening runs: NBA totals
                                    # open the night before and move a lot, so paper bets log near the opener)
"""
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import math

import numpy as np
import pandas as pd

import actionnet
import availability
import gameday
import player_model as pm
import team_model as tm
from names import norm

ROOT = os.path.join(os.path.dirname(__file__), "..")
import sys
from datetime import timedelta
TOMORROW = "--tomorrow" in sys.argv
OUT = os.path.join(ROOT, "docs", "tomorrow.json" if TOMORROW else "today.json")
NOW = datetime.now(ZoneInfo("America/New_York"))
TODAY = NOW.date() + timedelta(days=1 if TOMORROW else 0)   # the slate's date
DAY = (pd.Timestamp(TODAY) - pm.DAY0).days
MARKET_STAT = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M", "stl": "STL", "blk": "BLK",
               "pra": "PRA", "pr": "PR", "pa": "PA", "ra": "RA", "stocks": "STOCKS"}


# Outcome variance around the projection = a*proj + b*proj^2, fitted Nov 8 2026 on 2021-23 player-games
# (research/props_calibration.py). Backtest 2023-26 vs 513k consensus lines: even with these spreads the
# model's P(over) is overconfident and the market's no-vig price is better calibrated (Brier .243 vs .255).
VAR = {"pts": (3.891, 0.0), "reb": (1.542, 0.0), "ast": (1.394, 0.0), "fg3m": (1.066, 0.0124), "stl": (1.280, 0.0),
       "blk": (1.125, 0.0), "pra": (4.597, 0.0), "pr": (4.330, 0.0), "pa": (4.071, 0.0), "ra": (1.966, 0.0),
       "stocks": (1.265, 0.0)}


def p_over(market, proj, line):
    """Model's chance of going over `line`: normal with the fitted variance (over x.5 = at least floor+1)."""
    a, b = VAR[market]
    sd = math.sqrt(max(a * proj + b * proj * proj, 1e-6))
    return 0.5 * math.erfc((math.floor(line) + 0.5 - proj) / (sd * math.sqrt(2)))


def no_vig(over, under):
    """Market's over chance with the vig removed (American odds)."""
    imp = lambda o: 100 / (o + 100) if o > 0 else -o / (-o + 100)  # noqa: E731
    a, b = imp(over), imp(under)
    return a / (a + b)


# ESPN 'Day-To-Day' players: chance of sitting from the note's wording (Rotowire's play % wins when it lists him;
# Rotowire only covers today's games, so tomorrow's slate depends on these)
DTD = (("doubtful", 0.75), ("questionable", 0.5), ("probable", 0.15))


def out_probs():
    """{(team, normalized name): P(out)} from Rotowire, with ESPN as a fallback (Out = 1, Day-To-Day by its note)."""
    probs = {}
    try:
        for r in gameday.injuries():
            st, note = (r.get("status") or "").lower(), (r.get("comment") or "").lower()
            p = 1.0 if st == "out" else next((v for k, v in DTD if k in note), None) if st == "day-to-day" else None
            if p is not None:
                probs[(r["team"], norm(r["player"]))] = p
    except Exception as e:
        print("ESPN injuries failed:", e)
    try:
        for r in gameday.lineups():
            if r["pct_play"] is not None and r["player"]:
                probs[(r["team"], norm(r["player"]))] = 1 - r["pct_play"] / 100   # Rotowire wins when both list him
    except Exception as e:
        print("Rotowire lineups failed:", e)
    return probs


def lines_for(rows, home, away):
    """Consensus (current) and open lines + every book's line for one game."""
    by = {r["book"]: r for r in rows if r["home"] == home and r["away"] == away}
    pick = lambda b, k: by.get(b, {}).get(k)  # noqa: E731
    books = {b: {k: r.get(k) for k in ("spread_home", "spread_home_line", "spread_away_line", "total", "over", "under",
                                       "ml_home", "ml_away")}
             for b, r in by.items() if b not in ("consensus", "open")}
    return {"total": pick("consensus", "total"), "open_total": pick("open", "total"),
            "spread_home": pick("consensus", "spread_home"), "open_spread_home": pick("open", "spread_home"),
            "books": books}


def main():
    raw, teams_of = actionnet.games(TODAY)
    for r in raw:
        r["home"], r["away"] = gameday.code(r["home"]), gameday.code(r["away"])
    slate = {}
    for r in raw:
        slate.setdefault(r["an_game_id"], {"an_game_id": r["an_game_id"], "start_utc": r["start_utc"],
                                           "status": r["status"], "away": r["away"], "home": r["home"]})
    print(f"{TODAY}: {len(slate)} games")
    # tomorrow's slate: tonight's games aren't in the nba.com logs until the morning, so take tonight's
    # schedule from Action Network for back-to-backs
    tonight = set()
    if TOMORROW:
        tonight = {gameday.code(t) for at in actionnet.games(TODAY - timedelta(days=1))[1].values() for t in at}
    if not slate:
        json.dump({"generated_et": NOW.strftime("%Y-%m-%d %H:%M"), "date": str(TODAY), "games": [], "props": []},
                  open(OUT, "w"), indent=1)
        return

    # ---- team model, fitted on everything before today
    g = tm.load()
    f1 = tm.Fitter(g)                      # v1: no availability terms (the version paper-traded on totals)
    bp1, bo1 = f1.fit(DAY, tm.HALF_LIFE, tm.LAM)
    f = tm.Fitter(g)
    av = tm.with_missing(g, f)
    bp, bo = f.fit(DAY, tm.HALF_LIFE, tm.LAM)
    f3 = tm.Fitter(g)                      # v3: points-based availability in ppp and pace (totals)
    avp = tm.with_v3(g, f3)
    bp3, bo3 = f3.fit(DAY, tm.HALF_LIFE, tm.LAM)
    latest = g.sort_values("date").drop_duplicates("TEAM_ABBREVIATION", keep="last")
    tid_of = dict(zip(latest.TEAM_ABBREVIATION, latest.TEAM_ID))
    last_day = g.groupby("TEAM_ID").date.max().map(lambda d: (d - pm.DAY0).days)
    p = pm.load()
    names = p.drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID").PLAYER_NAME
    probs = out_probs()
    n = f.n

    def team_side(abbr):
        tid = tid_of[abbr]
        pool = av.pool(tid, DAY, availability.AWAY_DAYS)
        players, miss, mpts, mmin = [], 0.0, 0.0, 0.0
        for pid, m in pool.items():
            p_out = probs.get((abbr, norm(names.get(pid, ""))), 0.0)
            v = av.value(pid, DAY) - availability.REPL
            ppm = avp.value(pid, DAY)
            miss += p_out * m * v
            mpts += p_out * m * ppm        # v3: expected missing points and minutes
            mmin += p_out * m
            players.append({"player_id": int(pid), "player": names.get(pid, str(pid)), "min": round(m, 1),
                            "value": round(v, 3), "pts_min": round(ppm, 3), "p_out": round(p_out, 2)})
        return tid, miss, players, bool(last_day.get(tid, -9) == DAY - 1 or abbr in tonight), mpts, mmin

    games = []
    for gm in slate.values():
        ht, hmiss, hpl, hb2b, hpa, hpb = team_side(gm["home"])
        at, amiss, apl, ab2b, apa, apb = team_side(gm["away"])
        ih, ia = f.idx[ht], f.idx[at]
        pace = bp[0] + bp[1 + ih] + bp[1 + ia]
        ex = bo[1 + 2 * n:]   # home, b2b own, b2b opp, miss own, miss opp
        ppp_h = bo[0] + bo[1 + ih] + bo[1 + n + ia] + ex @ np.array([1, hb2b, ab2b, hmiss, amiss])
        ppp_a = bo[0] + bo[1 + ia] + bo[1 + n + ih] + ex @ np.array([0, ab2b, hb2b, amiss, hmiss])
        ph, pa = pace * ppp_h, pace * ppp_a
        # v1 (same fit without missing-player terms: extras are home, b2b own, b2b opp)
        pace1 = bp1[0] + bp1[1 + ih] + bp1[1 + ia]
        ex1 = bo1[1 + 2 * n:]
        v1h = pace1 * (bo1[0] + bo1[1 + ih] + bo1[1 + n + ia] + ex1 @ np.array([1, hb2b, ab2b]))
        v1a = pace1 * (bo1[0] + bo1[1 + ia] + bo1[1 + n + ih] + ex1 @ np.array([0, ab2b, hb2b]))
        # v3 (extras: home, b2b own, b2b opp, missing pts own, missing min own, missing pts opp, missing min opp)
        pace3 = bp3[0] + bp3[1 + ih] + bp3[1 + ia] + bp3[1 + n:] @ np.array([hpa + apa, hpb + apb])
        ex3 = bo3[1 + 2 * n:]
        v3h = pace3 * (bo3[0] + bo3[1 + ih] + bo3[1 + n + ia] + ex3 @ np.array([1, hb2b, ab2b, hpa, hpb, apa, apb]))
        v3a = pace3 * (bo3[0] + bo3[1 + ia] + bo3[1 + n + ih] + ex3 @ np.array([0, ab2b, hb2b, apa, apb, hpa, hpb]))
        ln = lines_for(raw, gm["home"], gm["away"])
        games.append({**gm, "proj_home": round(ph, 1), "proj_away": round(pa, 1), "proj_total": round(ph + pa, 1),
                      "proj_spread_home": round(pa - ph, 1), "proj_pace": round(pace, 1),
                      "home_b2b": hb2b, "away_b2b": ab2b, "home_missing": round(hmiss, 1),
                      "away_missing": round(amiss, 1), **{k: v for k, v in ln.items()},
                      "edge_total": None if ln["total"] is None else round(ph + pa - ln["total"], 1),
                      "v1_home": round(v1h, 1), "v1_away": round(v1a, 1), "v1_total": round(v1h + v1a, 1),
                      "v1_edge_total": None if ln["total"] is None else round(v1h + v1a - ln["total"], 1),
                      "v3_home": round(v3h, 1), "v3_away": round(v3a, 1), "v3_total": round(v3h + v3a, 1),
                      "v3_pace": round(pace3, 1), "home_missing_pts": round(hpa, 1), "away_missing_pts": round(apa, 1),
                      "v3_edge_total": None if ln["total"] is None else round(v3h + v3a - ln["total"], 1),
                      # spreads: home spread in betting terms (-5 = home favored by 5); edge > 0 = model likes home
                      "v3_spread_home": round(v3a - v3h, 1), "v1_spread_home": round(v1a - v1h, 1),
                      "v3_edge_spread": None if ln["spread_home"] is None else round(ln["spread_home"] - (v3a - v3h), 1),
                      "v1_edge_spread": None if ln["spread_home"] is None else round(ln["spread_home"] - (v1a - v1h), 1),
                      "cons": {k: next((r.get(k) for r in raw if r["home"] == gm["home"] and r["away"] == gm["away"]
                                        and r["book"] == "consensus"), None)
                               for k in ("total", "over", "under", "spread_home", "spread_home_line", "spread_away_line")},
                      # > 0: model likes the home side vs the line (e.g. line +8, model +5 -> +3)
                      "edge_spread": None if ln["spread_home"] is None else round(ln["spread_home"] - (pa - ph), 1),
                      "home_players": hpl, "away_players": apl, "home_tid": int(ht), "away_tid": int(at)})

    if TOMORROW:
        return write(games, [])
    # ---- props
    league = pm.league_rates(p)
    tabs, opp_league = pm.opp_tables(g)
    hist = {pid: d for pid, d in p.groupby("PLAYER_ID")}
    tpace = {}
    for tid, d in g.assign(day=(g.date - pm.DAY0).dt.days).sort_values("day").groupby("TEAM_ID"):
        tpace[tid] = pm.weighted_asof(d.day.to_numpy(), d.poss.to_numpy(), None, len(d), DAY, 60)
    proj_rows = []
    for gm in games:
        for side, opp_side in (("home", "away"), ("away", "home")):
            tid, oid = gm[f"{side}_tid"], gm[f"{opp_side}_tid"]
            gids, odays, oposs, ovals = tabs[oid]
            opp = pm.weighted_asof(odays, oposs, ovals, len(odays), DAY, pm.OPP_HL, opp_league, pm.OPP_K * 100.0)
            pace = gm["proj_pace"] / tpace[tid]
            for pl in gm[f"{side}_players"]:
                if pl["p_out"] >= 0.5 or pl["player_id"] not in hist:
                    continue
                d = hist[pl["player_id"]]
                em, r = pm.player_asof(d.day.to_numpy(), d.MIN.to_numpy(), {s: d[s].to_numpy() for s in pm.STATS},
                                       len(d), DAY, pm.MIN_HL, pm.RATE_HL, pm.K, league)
                minutes = min(12.0 if np.isnan(em) else em, 42.0)
                pr = {s: minutes * r[s] * pace * opp[s] for s in pm.STATS}
                pr.update({c: sum(pr[s] for s in parts) for c, parts in pm.COMBOS.items()})
                proj_rows.append({"game": f"{gm['away']} @ {gm['home']}", "start_utc": gm["start_utc"],
                                  "team": gm[side], "opp": gm[opp_side], "player": pl["player"],
                                  "key": norm(pl["player"]), "exp_min": round(minutes, 1), "p_out": pl["p_out"],
                                  **{f"proj_{k}": round(v, 2) for k, v in pr.items()}})
    props = []
    try:
        lines = pd.DataFrame(actionnet.props(TODAY, teams_of))
    except Exception as e:
        print("props lines failed:", e)
        lines = pd.DataFrame()
    if len(lines) and proj_rows:
        lines["team"] = lines.team.map(gameday.code)
        lines["key"] = lines.player.map(norm)
        pj = pd.DataFrame(proj_rows)
        for (team, key, market), d in lines.groupby(["team", "key", "market"]):
            row = pj[(pj.team == team) & (pj.key == key)]
            cons = d[d.book == "consensus"]
            if row.empty or cons.empty:
                continue
            row, c = row.iloc[0], cons.iloc[0]
            same = d[(d.line == c.line) & ~d.book.isin(["consensus", "open"])]
            bo_ = same.loc[same.over.idxmax()] if same.over.notna().any() else None
            bu_ = same.loc[same.under.idxmax()] if same.under.notna().any() else None
            op = d[d.book == "open"]
            proj = row[f"proj_{MARKET_STAT[market]}"]
            props.append({"game": row.game, "start_utc": row.start_utc, "team": team, "opp": row.opp,
                          "player": row.player, "market": market, "exp_min": row.exp_min, "p_out": row.p_out,
                          "proj": proj, "line": c.line, "over": c.over, "under": c.under,
                          "open_line": None if op.empty else op.iloc[0].line,
                          "edge_pct": round((proj - c.line) / max(c.line, 0.5), 3),
                          "p_over": round(p_over(market, proj, c.line), 3),
                          "mkt_over": None if pd.isna(c.over) or pd.isna(c.under) else round(no_vig(c.over, c.under), 3),
                          "best_over": None if bo_ is None else {"book": bo_.book, "odds": bo_.over},
                          "best_under": None if bu_ is None else {"book": bu_.book, "odds": bu_.under}})
    write(games, props)


def write(games, props):
    for gm in games:
        for k in ("home_players", "away_players"):
            gm[k] = sorted(gm[k], key=lambda x: -x["min"])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out = {"generated_et": NOW.strftime("%Y-%m-%d %H:%M"), "date": str(TODAY),
           "model": {"team": f"v1 / v2 / v3 (half_life {tm.HALF_LIFE}, lam {tm.LAM}, v2 repl {availability.REPL})",
                     "props": f"v1 (min_hl {pm.MIN_HL}, rate_hl {pm.RATE_HL}, K {pm.K})"},
           "games": games, "props": props}
    json.dump(out, open(OUT, "w"), indent=1, default=lambda x: x.item() if hasattr(x, "item") else str(x))
    print(f"wrote {OUT}: {len(games)} games, {len(props)} props")


if __name__ == "__main__":
    main()
