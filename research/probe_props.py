"""Phase 2 probe: Action Network NBA props: market names and response shape."""
import json
import re
import sys
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
date = sys.argv[1]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as f:
        return f.read().decode("utf-8", "replace")


names = set()
for page in ("points", "rebounds", "assists", "3pt", "stat-combos"):
    try:
        names |= set(re.findall(r"core_bet_type_\d+_[a-z0-9_]+", get(f"https://www.actionnetwork.com/nba/props/{page}")))
    except Exception as e:
        print("page", page, e)
print("market names:", sorted(names))

books = "15,30,68,69,71,75,79,123,972,1005,1006,1548,1902,1903,2194,2292,2789,3612,4621,4727,4795,5203"
d = json.loads(get(f"https://api.actionnetwork.com/web/v2/scoreboard/nba/markets?bookIds={books}"
                   f"&customPickTypes=core_bet_type_23_rebounds&date={date}"))


def shape(x, depth=0, key="root"):
    pad = "  " * depth
    if isinstance(x, dict):
        print(f"{pad}{key}: dict {list(x)[:25]}")
        for k, v in list(x.items())[:25]:
            if isinstance(v, (dict, list)) and depth < 6:
                shape(v, depth + 1, k)
    elif isinstance(x, list):
        print(f"{pad}{key}: list[{len(x)}]")
        if x and depth < 6:
            shape(x[0], depth + 1, key + "[0]")


shape(d)
print(json.dumps(d, default=str)[:3000])
