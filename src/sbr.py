"""NBA game lines (open/close spread + total, moneyline) from the SportsBookReviewsOnline archive.

The archive covers 2007-08 to January 2023 (later season pages exist but are empty). Each game is two rows (V = visitor, H = home):
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
# page slug -> season start year
PAGES = {f"{y}-{str(y + 1)[2:]}": y for y in range(2007, 2023)}


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
    total, spread = (a, -b) if a > b else (b, a)  # bigger number = total; spread sits on the favorite's row
    if total < 100:  # archive typo (e.g. a 41.0 "total" in 2022-23): treat as no line
        return None, None
    return total, spread


def parse(html, start_year):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    cells = [[re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
             for r in rows]
    cells = [c for c in cells if len(c) >= 12 and c[2] in ("V", "H", "N")]
    out = []
    i = 0
    year, prev_month = start_year, 0
    while i + 1 < len(cells):
        v, h = cells[i], cells[i + 1]
        i += 2
        mmdd = int(v[0])
        if mmdd // 100 < prev_month:  # rows are in date order: month going back (Dec -> Jan) = new year.
            year += 1                 # (the 2019-20 bubble ran Jul-Oct 2020, so month alone can't tell)
        prev_month = mmdd // 100
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


def same_team(sbr_name, nba_name):
    if not isinstance(nba_name, str):
        return False
    a = sbr_name.replace(" ", "").lower().replace("losangeles", "la")
    b = nba_name.replace(" ", "").lower().replace("losangeles", "la")
    return b.startswith(a) or a.startswith(b[:6])


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
    names = t.drop_duplicates("TEAM_ABBREVIATION", keep="last").set_index("TEAM_ABBREVIATION").TEAM_NAME
    g = g[["game_id", "season", "season_type", "date", "away", "home", "away_pts", "home_pts"]]
    g["home_name"] = g.home.map(names)
    # neutral games list both teams as away, so each appears twice above: either orientation can match
    sbr = sbr.reset_index(drop=True).assign(sbr_row=lambda d: d.index)
    m = sbr.merge(g, on=["date", "away_pts", "home_pts"], how="left")
    # two games the same night with the same final score can't be told apart: leave them unmatched
    key = ["date", "away_pts", "home_pts"]
    amb = m.groupby(key).game_id.transform("nunique") > 1
    # ...unless SBR's home team name points to one of them: 'NewYork' ~ 'New York Knicks', 'LALakers' ~ 'Los Angeles Lakers'
    same = m.apply(lambda r: same_team(r.sbr_home, r.home_name), axis=1)
    m = m[~amb | same | ~(same.groupby(m.sbr_row).transform("any"))]  # no name match at all: keep, blank below
    amb = m.groupby("sbr_row").game_id.transform("nunique") > 1
    m.loc[amb, ["game_id", "season", "season_type", "away", "home"]] = None
    m = m.drop_duplicates("sbr_row")
    # second try for the rest at +-1 day (SBR dates some games a day off, e.g. Christmas games as Dec 24)
    miss = m.game_id.isna()
    for shift in (1, -1):
        d = m[miss].copy()
        d["date2"] = (pd.to_datetime(d.date) + pd.Timedelta(days=shift)).dt.strftime("%Y-%m-%d")
        hit = d.drop(columns=["game_id", "season", "season_type", "away", "home", "home_name"]).merge(
            g, left_on=["date2", "away_pts", "home_pts"], right_on=["date", "away_pts", "home_pts"],
            suffixes=("", "_nba"))
        hit = hit[hit.apply(lambda r: same_team(r.sbr_home, r.home_name), axis=1)].drop_duplicates("sbr_row", keep=False)
        for c in ["game_id", "season", "season_type", "away", "home"]:
            m.loc[m.sbr_row.isin(hit.sbr_row), c] = m.sbr_row.map(hit.set_index("sbr_row")[c])
        miss = m.game_id.isna()
    assert len(m) == len(sbr), "every SBR game must appear exactly once"
    return m, int(amb.sum())


def report(m, n_amb):
    """Per-season quality report. Returns False if a season looks broken."""
    good = True
    # season from nba.com when matched (the 2019-20 bubble ran into Oct 2020), else from the date
    guess = m.date.str[:4].astype(int) - (m.date.str[5:7].astype(int) < 8)
    m = m.assign(start=m.season.str[:4].astype(float).fillna(guess).astype(int))
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
