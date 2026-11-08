"""Phase 2 probe: Action Network book names + NBA game-line fields (spread/total/ML), today and 2023."""
import json
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as f:
        return json.load(f)


books = {b["id"]: b["display_name"] for b in get("https://api.actionnetwork.com/web/v1/books")["books"]}
for i in (15, 30, 68, 69, 71, 75, 79, 123, 972, 1005, 1006, 1548, 2194, 2789, 4795, 5203):
    print("book", i, books.get(i))
for date in ("20261107", "20230301", "20221115"):
    d = get(f"https://api.actionnetwork.com/web/v1/scoreboard/nba?period=game&bookIds=15,30,68,69&date={date}")
    g = d["games"][0]
    print(date, "games", len(d["games"]), "| game keys", list(g)[:30])
    for o in g.get("odds", [])[:2]:
        print("  odds", json.dumps(o)[:700])
