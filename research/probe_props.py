"""Phase 2 probe: Action Network NBA props: which market names exist, and how far back do dates work?"""
import json
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
BOOKS = "15,30,68,69,71,75,79,123,972,1005,1006,1548,2194,2789,4795,5203"
GUESSES = ["core_bet_type_27_points", "core_bet_type_23_rebounds", "core_bet_type_26_assists",
           "core_bet_type_21_3fgm", "core_bet_type_85_points_rebounds_assists", "core_bet_type_86_points_rebounds",
           "core_bet_type_87_points_assists", "core_bet_type_88_rebounds_assists", "core_bet_type_24_steals",
           "core_bet_type_25_blocks", "core_bet_type_22_turnovers", "core_bet_type_89_steals_blocks"]


def get(types, date):
    url = (f"https://api.actionnetwork.com/web/v2/scoreboard/nba/markets?bookIds={BOOKS}"
           f"&customPickTypes={'%2C'.join(types)}&date={date}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.load(f)


d = get(GUESSES, "20261107")
print("valid market names:", {k: v["name"] for k, v in d.get("market_rules", {}).items()})
for book, m in d["markets"].items():
    print(" book", book, {k: len(v) for k, v in m["event"].items()})
rows = d["markets"]["15"]["event"].get("core_bet_type_27_points", [])[:2]
print("sample consensus points rows:", json.dumps(rows)[:800])
print("player sample:", json.dumps(d["players"][0])[:300])
print("options:", json.dumps(d["market_rules"].get("core_bet_type_27_points", {}).get("rules", {}).get("options")))

for date in ["20261020", "20260401", "20251107", "20250115", "20240115", "20230115", "20220115", "20210115"]:
    try:
        x = get(["core_bet_type_27_points"], date)
        n = {b: len(m["event"].get("core_bet_type_27_points", [])) for b, m in x.get("markets", {}).items()}
        print(date, "games", len(x.get("games", [])), "points rows by book", n)
    except Exception as e:
        print(date, "ERROR", e)
