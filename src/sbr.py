"""NBA game lines (open/close spread + total, moneyline) from the SportsBookReviewsOnline archive.

The archive covers 2007-08 to about 2022-23. Each game is two rows (V = visitor, H = home):
  Date | Rot | VH | Team | 1st | 2nd | 3rd | 4th | Final | Open | Close | ML | 2H
Open / Close hold the spread on the favorite's row and the total on the other row, so the bigger
number is the total. 'pk' = pick'em (spread 0), 'NL' = no line.

Games are matched to nba.com games by date + final score (no team-name table needed), which also
gives nba.com's game_id and team codes. Writes data/lines/sbr_nba.csv.

  python src/sbr.py
"""
import glob
import os
import re
import sys
import time
import urllib.error
import urllib.request

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "data", "lines", "sbr_nba.csv")
URL = "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nba-odds-{}/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
# page slug -> season start year (2020-21 may be just "2021" on the site, as it is for NHL)
PAGES = {f"{y}-{str(y + 1)[2:]}": y for y in range(2007, 2026)}
PAGES["2021"] = 2020


def num(x):
    x = x.strip().lower().replace("½", ".5")
    if x in ("pk", "pick", "ev", "even"):
        return 0.0
    try:
        return float(x)
    except ValueError:
        return None  # NL / blank


def split(v, h):
    """(visitor cell, home cell) -> (total, home spread). Spread is on the favorite's row."""
    a, b = num(v), num(h)
    if a is None or b is None:
        return None, None
    if a > b:   # visitor row has the total -> home row has the spread -> home is the favorite
        return a, -b
    return b, a  # home row has the total -> visitor is the favorite -> home gets +spread


def parse(html, start_year):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    cells = [[re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
             for r in rows]
    cells = [c for c in cells if len(c) >= 12 and c[2] in ("V", "H", "N")]
    out = []
    i = 0
    while i + 1 < len(cells):
        v, h = cells[i], cells[i + 1]
        i += 2
        mmdd = int(v[0])
        year = start_year if mmdd >= 800 else start_year + 1
        open_total, open_spread = split(v[9], h[9])
        close_total, close_spread = split(v[10], h[10])
        out.append({
            "date": f"{year}-{mmdd // 100:02d}-{mmdd % 100:02d}", "sbr_away": v[3], "sbr_home": h[3],
            "neutral_sbr": v[2] == "N", "away_pts": num(v[8]), "home_pts": num(h[8]),
            "open_total": open_total, "close_total": close_total,
            "open_spread_home": open_spread, "close_spread_home": close_spread,
            "away_ml": num(v[11]), "home_ml": num(h[11]),
        })
    return out


def fetch_all():
    rows = []
    for slug, y in PAGES.items():
        req = urllib.request.Request(URL.format(slug), headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as f:
                got = parse(f.read().decode("utf-8", "replace"), y)
        except urllib.error.HTTPError as e:
            print(f"{slug}: HTTP {e.code} (no page)", flush=True)
            continue
        print(f"{slug}: {len(got)} games", flush=True)
        rows += got
        time.sleep(2)
    return pd.DataFrame(rows).drop_duplicates()


def match(sbr):
    """Attach nba.com game_id / team codes by date + final score."""
    t = pd.concat([pd.read_csv(f, dtype={"GAME_ID": str})
                   for f in glob.glob(os.path.join(ROOT, "data", "nbacom", "team_games_*.csv.gz"))])
    t["date"] = pd.to_datetime(t.GAME_DATE).dt.strftime("%Y-%m-%d")
    away = t[t.MATCHUP.str.contains(" @ ")]
    g = away.merge(t[["GAME_ID", "TEAM_ABBREVIATION", "PTS"]], on="GAME_ID", suffixes=("_a", "_h"))
    g = g[g.TEAM_ABBREVIATION_a != g.TEAM_ABBREVIATION_h]
    g = g.rename(columns={"GAME_ID": "game_id", "SEASON": "season", "SEASON_TYPE": "season_type",
                          "TEAM_ABBREVIATION_a": "away", "TEAM_ABBREVIATION_h": "home",
                          "PTS_a": "away_pts", "PTS_h": "home_pts"})
    g = g[["game_id", "season", "season_type", "date", "away", "home", "away_pts", "home_pts"]]
    # neutral games list both teams as away, so each appears twice above: either orientation can match
    m = sbr.merge(g, on=["date", "away_pts", "home_pts"], how="left")
    # two games the same night with the same final score can't be told apart: leave them unmatched
    key = ["date", "away_pts", "home_pts"]
    amb = m.groupby(key).game_id.transform("nunique") > 1
    m.loc[amb, ["game_id", "season", "season_type", "away", "home"]] = None
    return m.drop_duplicates(subset=["date", "sbr_away", "sbr_home", "away_pts", "home_pts"]), int(amb.sum())


def report(m, n_amb):
    """Per-season quality report. Returns False if a season looks broken."""
    good = True
    m = m.assign(year=m.date.str[:4].astype(int), mo=m.date.str[5:7].astype(int))
    m["start"] = m.year - (m.mo < 8)
    print(f"\nsame-night same-score games left unmatched: {n_amb}")
    print("season | games | matched | close total range | median |close spread| | fav ML<0 when fav by spread | close total vs final (MAE)")
    for y, d in m.groupby("start"):
        ok = d.game_id.notna().mean()
        tot = d.close_total.dropna()
        sp = d.close_spread_home.dropna()
        fav_home = d.close_spread_home < 0
        ml_ok = ((fav_home & (d.home_ml < 0)) | (~fav_home & (d.away_ml < 0)) | (d.close_spread_home == 0))[d.home_ml.notna()].mean()
        mae = (d.close_total - (d.away_pts + d.home_pts)).abs().mean()
        bad = ok < 0.98 or tot.min() < 150 or tot.max() > 270 or sp.abs().max() > 25
        good &= not bad
        print(f"{'FAIL ' if bad else 'ok   '}{y}-{str(y + 1)[2:]} | {len(d):>5} | {ok:6.1%} | {tot.min():.1f}-{tot.max():.1f} | "
              f"{sp.abs().median():.1f} | {ml_ok:6.1%} | {mae:.1f}")
    for _, r in m[m.game_id.isna()].head(15).iterrows():
        print(f"     unmatched {r.date} {r.sbr_away} @ {r.sbr_home} {r.away_pts}-{r.home_pts}")
    return good


if __name__ == "__main__":
    sbr = fetch_all()
    if sbr.empty:
        sys.exit("no SBR pages parsed")
    m, n_amb = match(sbr)
    ok = report(m, n_amb)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    cols = ["game_id", "season", "season_type", "date", "away", "home", "away_pts", "home_pts",
            "open_total", "close_total", "open_spread_home", "close_spread_home", "away_ml", "home_ml",
            "sbr_away", "sbr_home", "neutral_sbr"]
    m[cols].sort_values("date").to_csv(OUT, index=False)
    print(f"wrote {len(m):,} games to {OUT}")
    sys.exit(0 if ok else 1)
