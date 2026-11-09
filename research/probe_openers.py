import sys, json, collections, datetime as dt
sys.path.insert(0, "src")
import actionnet, gameday
d = dt.date.today() + dt.timedelta(days=1)
data = actionnet.get(f"v1/scoreboard/nba?period=game&bookIds=15,30,68,69&date={d:%Y%m%d}")
g = data["games"][0]
print("game keys:", sorted(g))
for o in g["odds"]:
    if o.get("book_id") in (30, 68):
        print("book", o["book_id"], json.dumps({k: v for k, v in o.items() if "total" in k or "time" in k or "insert" in k or "date" in k or k in ("book_id", "type")}))
for gm in data["games"]:
    op = [o for o in gm["odds"] if o.get("book_id") == 30 and o.get("type", "game") == "game"]
    print(gm["id"], {k: op[0].get(k) for k in op[0] if "insert" in k or "time" in k or "date" in k} if op else None)
inj = gameday.injuries()
print("ESPN statuses:", collections.Counter(r["status"] for r in inj))
for r in inj:
    if r["team"] in ("DEN", "HOU", "SAS", "PHX") :
        print("  ", r["team"], r["player"], r["status"], r["updated"], (r["comment"] or "")[:70])
for url in ("https://www.rotowire.com/basketball/nba-lineups.php?date=tomorrow",):
    h = gameday.get(url)
    import re
    print(url, "games:", h.count('<div class="lineup is-nba'), "abbrs:", re.findall(r'class="lineup__abbr">([^<]+)<', h)[:16])
