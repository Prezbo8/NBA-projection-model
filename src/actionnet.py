"""Action Network: NBA game lines + player props, saved per day (final lines as Action Network keeps them).

Action Network still serves lines for past dates: game lines (spread / total / ML / team totals,
public + money %) back to at least 2022-23, player props for every book from about Jan 2025 and
consensus-only in 2023-24 (none before: props are only requested from PROPS_FROM on). Book 15 = consensus (the closing line), book 30 = opening line.

Writes one pair of files per day with games:
  data/odds/<season>/<YYYY-MM-DD>_games.csv.gz   one row per game per book
  data/odds/<season>/<YYYY-MM-DD>_props.csv.gz   one row per player / market / book (over + under odds)
Action Network player ids are NOT nba.com ids: rows keep the player's name and team for matching.

  python src/actionnet.py 2026-11-07                 # one day
  python src/actionnet.py 2022-10-18 2023-06-20      # a range (days already saved are skipped)
"""
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
API = "https://api.actionnetwork.com/web"
# consensus, open, DK, FanDuel, BetRivers, BetMGM, bet365, Caesars, Fanatics (NJ ids; NY copies skipped)
BOOKS = {15: "consensus", 30: "open", 68: "DK", 69: "FanDuel", 71: "BetRivers", 75: "BetMGM",
         79: "bet365", 123: "Caesars", 2789: "Fanatics"}
MARKETS = {"core_bet_type_27_points": "pts", "core_bet_type_23_rebounds": "reb", "core_bet_type_26_assists": "ast",
           "core_bet_type_21_3fgm": "fg3m", "core_bet_type_85_points_rebounds_assists": "pra",
           "core_bet_type_86_points_rebounds": "pr", "core_bet_type_87_points_assists": "pa",
           "core_bet_type_88_rebounds_assists": "ra", "core_bet_type_24_steals": "stl",
           "core_bet_type_25_blocks": "blk", "core_bet_type_89_steals_blocks": "stocks"}
GAME_COLS = ["spread_home", "spread_home_line", "spread_away_line", "total", "over", "under", "ml_home", "ml_away",
             "home_total", "home_over", "home_under", "away_total", "away_over", "away_under",
             "spread_home_public", "spread_home_money", "total_over_public", "total_over_money",
             "ml_home_public", "ml_home_money"]
PAUSE = 1.0
PROPS_FROM = date(2023, 10, 1)  # Action Network has no props for older dates: don't ask (11 requests/day)


def get(path, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(f"{API}/{path}", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as f:
                return json.load(f)
        except (urllib.error.URLError, TimeoutError) as e:  # 504s happen; back off and retry
            if i == tries - 1:
                raise
            print(f"  retry {path[:80]}: {e}", flush=True)
            time.sleep(10 * (i + 1))


def season_of(d):
    y = d.year if d.month >= 8 else d.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def games(d):
    """One row per game per book. Returns (rows, {an_game_id: (away, home)})."""
    data = get(f"v1/scoreboard/nba?period=game&bookIds={','.join(map(str, BOOKS))}&date={d:%Y%m%d}")
    rows, teams_of = [], {}
    for g in data.get("games", []):
        abbr = {t["id"]: t["abbr"] for t in g["teams"]}
        away, home = abbr[g["away_team_id"]], abbr[g["home_team_id"]]
        teams_of[g["id"]] = (away, home)
        box = g.get("boxscore") or {}
        base = {"date": d.isoformat(), "an_game_id": g["id"], "start_utc": g["start_time"], "status": g["status"],
                "away": away, "home": home,
                "away_pts": box.get("total_away_points"), "home_pts": box.get("total_home_points")}
        for o in g.get("odds", []):
            if o.get("book_id") in BOOKS and o.get("type", "game") == "game":
                rows.append({**base, "book": BOOKS[o["book_id"]], **{c: o.get(c) for c in GAME_COLS}})
    return rows, teams_of


def props(d, teams_of):
    """One row per player / market / book / line, with over and under odds side by side."""
    out = []
    for key, short in MARKETS.items():
        data = get(f"v2/scoreboard/nba/markets?bookIds={','.join(map(str, BOOKS))}&customPickTypes={key}&date={d:%Y%m%d}")
        players = {p["id"]: p for p in data.get("players", [])}
        team_abbr = {}
        for g in data.get("games", []):
            for side in ("home_team", "away_team"):
                team_abbr[g[side]["id"]] = g[side]["abbr"]
        sides = {}
        for book_id, m in data.get("markets", {}).items():
            if int(book_id) not in BOOKS:
                continue
            for o in m.get("event", {}).get(key, []):
                if o.get("is_alt_market") or o.get("side") not in ("over", "under") or o.get("player_id") is None:
                    continue
                k = (o["event_id"], o["player_id"], BOOKS[int(book_id)], o.get("value"))
                sides.setdefault(k, {})[o["side"]] = o.get("odds")
        for (gid, pid, book, line), odds in sides.items():
            p = players.get(pid, {})
            away, home = teams_of.get(gid, (None, None))
            out.append({"date": d.isoformat(), "an_game_id": gid, "away": away, "home": home,
                        "an_player_id": pid, "player": p.get("full_name"), "team": team_abbr.get(p.get("team_id")),
                        "market": short, "book": book, "line": line,
                        "over": odds.get("over"), "under": odds.get("under")})
        time.sleep(PAUSE)
    return out


PROP_COLS = ["date", "an_game_id", "away", "home", "an_player_id", "player", "team", "market", "book", "line",
             "over", "under"]


def save(rows, path, cols=None):
    """cols: header to write even when there are no rows (an empty file breaks readers)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.GzipFile(path, "wb", mtime=0) as gz, io.TextIOWrapper(gz) as f:  # mtime=0: stable bytes
        pd.DataFrame(rows, columns=cols).to_csv(f, index=False)


def day(d):
    """Save one finished day. Skips today and later, days with no games, and days already saved."""
    folder = os.path.join(ROOT, "data", "odds", season_of(d))
    gpath, ppath = (os.path.join(folder, f"{d.isoformat()}_{k}.csv.gz") for k in ("games", "props"))
    want_props = d >= PROPS_FROM
    if os.path.exists(gpath) and (os.path.exists(ppath) or not want_props):
        return "already saved"
    if d >= datetime.now(ZoneInfo("America/New_York")).date():  # (postponed games never turn 'complete')
        return "not over yet: only days before today (ET) are saved"
    g, teams_of = games(d)
    time.sleep(PAUSE)
    if not teams_of:
        return "no games"
    p = props(d, teams_of) if want_props else []
    save(g, gpath)
    if want_props:
        save(p, ppath, PROP_COLS)
    return f"{len(teams_of)} games, {len(g)} game-line rows, {len(p)} prop rows"


if __name__ == "__main__":
    first = date.fromisoformat(sys.argv[1])
    last = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else first
    d = first
    while d <= last:
        try:
            print(d, day(d), flush=True)
        except Exception as e:  # one bad day shouldn't stop a backfill; the summary shows it
            print(d, "ERROR", type(e).__name__, e, flush=True)
        d += timedelta(days=1)
