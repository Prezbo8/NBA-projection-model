"""Game-day sources, saved as time-stamped snapshots: injuries (ESPN), lineups (Rotowire), refs (official.nba.com).

Every source's team names are converted to nba.com codes (DEN, GSW, ...). A name that can't be
converted is kept as-is and reported, so the health check catches it instead of a silent mismatch.

  python src/gameday.py          # writes data/gameday/<season>/<date>/<source>_<HHMM>.csv.gz, prints status
Exit code 0 always; data/gameday/health.json holds each source's consecutive failure count.
"""
import gzip
import html as htmllib
import io
import json
import os
import re
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
NOW = datetime.now(ZoneInfo("America/New_York"))
HEALTH = os.path.join(ROOT, "data", "gameday", "health.json")

# full name, city / short city (refs page), nba.com code
TEAMS = [("Atlanta Hawks", "Atlanta", "ATL"), ("Boston Celtics", "Boston", "BOS"), ("Brooklyn Nets", "Brooklyn", "BKN"),
         ("Charlotte Hornets", "Charlotte", "CHA"), ("Chicago Bulls", "Chicago", "CHI"),
         ("Cleveland Cavaliers", "Cleveland", "CLE"), ("Dallas Mavericks", "Dallas", "DAL"),
         ("Denver Nuggets", "Denver", "DEN"), ("Detroit Pistons", "Detroit", "DET"),
         ("Golden State Warriors", "Golden State", "GSW"), ("Houston Rockets", "Houston", "HOU"),
         ("Indiana Pacers", "Indiana", "IND"), ("LA Clippers", "LA Clippers", "LAC"),
         ("Los Angeles Lakers", "LA Lakers", "LAL"), ("Memphis Grizzlies", "Memphis", "MEM"),
         ("Miami Heat", "Miami", "MIA"), ("Milwaukee Bucks", "Milwaukee", "MIL"),
         ("Minnesota Timberwolves", "Minnesota", "MIN"), ("New Orleans Pelicans", "New Orleans", "NOP"),
         ("New York Knicks", "New York", "NYK"), ("Oklahoma City Thunder", "Oklahoma City", "OKC"),
         ("Orlando Magic", "Orlando", "ORL"), ("Philadelphia 76ers", "Philadelphia", "PHI"),
         ("Phoenix Suns", "Phoenix", "PHX"), ("Portland Trail Blazers", "Portland", "POR"),
         ("Sacramento Kings", "Sacramento", "SAC"), ("San Antonio Spurs", "San Antonio", "SAS"),
         ("Toronto Raptors", "Toronto", "TOR"), ("Utah Jazz", "Utah", "UTA"), ("Washington Wizards", "Washington", "WAS")]
CODE = {}
for full, city, code in TEAMS:
    for k in (full, city, code, full.replace("Los Angeles", "LA"), city.replace("LA ", "L.A. "),
              city.replace("LA ", "Los Angeles ")):
        CODE[k.lower()] = code
CODE.update({"gs": "GSW", "ny": "NYK", "sa": "SAS", "no": "NOP", "pho": "PHX", "utah": "UTA", "wsh": "WAS",
             "la clippers": "LAC", "l.a. clippers": "LAC", "los angeles clippers": "LAC"})
unknown = set()


def code(name):
    if not isinstance(name, str):   # missing team (NaN) stays missing
        return name
    c = CODE.get(name.strip().lower())
    if c is None:
        unknown.add(name)
    return c or name


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as f:
                return f.read().decode("utf-8", "replace")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(10 * (i + 1))


def text(s):
    return htmllib.unescape(re.sub(r"<[^>]+>", " ", s)).split()


def injuries():
    d = json.loads(get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"))
    rows = []
    for t in d["injuries"]:
        for i in t["injuries"]:
            rows.append({"team": code(t["displayName"]), "player": i["athlete"]["displayName"], "status": i.get("status"),
                         "updated": i.get("date"), "comment": i.get("shortComment")})
    return rows


def lineups():
    h = get("https://www.rotowire.com/basketball/nba-lineups.php")
    rows = []
    for block in h.split('<div class="lineup is-nba')[1:]:
        tm = re.search(r'class="lineup__time">([^<]+)<', block)
        abbrs = re.findall(r'class="lineup__abbr">([^<]+)<', block)
        if len(abbrs) < 2:
            continue
        away, home = code(abbrs[0]), code(abbrs[1])
        for side, team, opp in (("is-visit", away, home), ("is-home", home, away)):
            m = re.search(rf'<ul class="lineup__list {side}">(.*?)</ul>', block, re.S)
            if not m:
                continue
            ul = m.group(1)
            st = re.search(r'class="lineup__status ([^"]+)"', ul)
            status = st.group(1).replace("is-", "") if st else None
            section = "starter"
            for li in re.findall(r"<li[^>]*class=\"([^\"]*)\"[^>]*>(.*?)</li>", ul, re.S):
                cls, body = li
                if "lineup__title" in cls:
                    section = "may_not_play"
                    continue
                if "lineup__player" not in cls:
                    continue
                name = re.search(r'<a title="([^"]+)"', body)
                pos = re.search(r'class="lineup__pos"\s*>([^<]*)<', body)
                inj = re.search(r'class="lineup__inj">([^<]*)<', body)
                pct = re.search(r"is-pct-play-(\d+)", cls)
                rows.append({"time": tm.group(1).strip() if tm else None, "team": team, "opp": opp,
                             "home": side == "is-home", "lineup_status": status, "section": section,
                             "player": htmllib.unescape(name.group(1)) if name else None,
                             "pos": pos.group(1).strip() if pos else None,
                             "injury": inj.group(1).strip() if inj else None,
                             "pct_play": int(pct.group(1)) if pct else None})
    return rows


def refs():
    h = get("https://official.nba.com/referee-assignments/")
    rows = []
    table = h[h.find("<table"):h.find("</table>")]
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S)[1:]:
        cells = [" ".join(text(c)) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 4 or " @ " not in cells[0]:
            continue
        a, b = cells[0].split(" @ ")
        ref = [re.sub(r"\s*\(#\d+\)", "", c).strip() for c in cells[1:5]] + [None] * 4
        rows.append({"away": code(a), "home": code(b), "crew_chief": ref[0], "referee": ref[1],
                     "umpire": ref[2], "alternate": ref[3] or None})
    return rows


def yesterday_had_games():
    y = (NOW - pd.Timedelta(days=1)).strftime("%Y%m%d")
    d = json.loads(get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={y}"))
    return len(d.get("events", [])) > 0


def fresh_nbacom():
    """The Mac's morning job (9:05 AM ET) saved yesterday's games? (fails when the Mac was asleep / off)"""
    if not yesterday_had_games():
        return "yesterday had no games"
    f = os.path.join(ROOT, "data", "nbacom", f"player_games_{season()}.csv.gz")
    last = pd.read_csv(f, usecols=["GAME_DATE"]).GAME_DATE.max() if os.path.exists(f) else "none"
    want = (NOW - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if last < want:
        raise ValueError(f"latest nba.com game is {last}, expected {want}: is the Mac runner online?")
    return f"latest game {last}"


def fresh_odds():
    """The morning odds job saved yesterday's lines + props?"""
    if not yesterday_had_games():
        return "yesterday had no games"
    want = (NOW - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    f = os.path.join(ROOT, "data", "odds", season(), f"{want}_props.csv.gz")
    if not os.path.exists(f):
        raise ValueError(f"no odds file for {want}")
    return f"{want} saved"


def season():
    y = NOW.year if NOW.month >= 8 else NOW.year - 1
    return f"{y}-{str(y + 1)[2:]}"


def save(rows, name):
    folder = os.path.join(ROOT, "data", "gameday", season(), NOW.strftime("%Y-%m-%d"))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{name}_{NOW:%H%M}.csv.gz")
    with gzip.GzipFile(path, "wb", mtime=0) as gz, io.TextIOWrapper(gz) as f:
        pd.DataFrame(rows).assign(fetched_et=NOW.strftime("%Y-%m-%d %H:%M")).to_csv(f, index=False)


if __name__ == "__main__":
    health = json.load(open(HEALTH)) if os.path.exists(HEALTH) else {}
    for name, fn in (("injuries", injuries), ("lineups", lineups), ("refs", refs),
                     ("nbacom_fresh", fresh_nbacom), ("odds_fresh", fresh_odds)):
        if name.endswith("_fresh"):
            if NOW.hour < 11:  # the morning jobs run 8:40-10:05 AM ET
                continue
            try:
                print(f"ok   {name}: {fn()}", flush=True)
                health[name] = 0
            except Exception as e:
                health[name] = health.get(name, 0) + 1
                print(f"FAIL {name} ({health[name]} runs in a row): {e}", flush=True)
            continue
        try:
            rows = fn()
            if not rows and name != "refs":  # refs are posted at 9 AM; an empty page before that is normal
                raise ValueError("no rows parsed")
            save(rows, name)
            health[name] = 0
            print(f"ok   {name}: {len(rows)} rows", flush=True)
        except Exception as e:
            health[name] = health.get(name, 0) + 1
            print(f"FAIL {name} ({health[name]} runs in a row): {type(e).__name__}: {e}", flush=True)
    if unknown:
        print(f"WARN team names not converted: {sorted(unknown)}")
    os.makedirs(os.path.dirname(HEALTH), exist_ok=True)
    json.dump(health, open(HEALTH, "w"), indent=1, sort_keys=True)
