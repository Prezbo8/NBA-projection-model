"""Phase 0: which data sources answer when asked from a GitHub Actions runner (a cloud IP)?

Prints one line per source: OK / FAIL, HTTP status, size, time, and a short sample of the reply.
Exit code is always 0: this is a report, not a test.
"""
import time

import requests

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
BROWSER = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}
NBA_STATS = {**BROWSER, "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com",
             "Accept": "application/json, text/plain, */*",
             "x-nba-stats-origin": "stats", "x-nba-stats-token": "true"}

# (name, url, headers, text that must appear in a good reply)
SOURCES = [
    ("nba.com stats: player game log 2008-09",
     "https://stats.nba.com/stats/leaguegamelog?Counter=0&Direction=DESC&LeagueID=00"
     "&PlayerOrTeam=P&Season=2008-09&SeasonType=Regular%20Season&Sorter=DATE",
     NBA_STATS, "resultSets"),
    ("nba.com stats: LeBron 2003-04 game log",
     "https://stats.nba.com/stats/playergamelog?PlayerID=2544&Season=2003-04"
     "&SeasonType=Regular%20Season",
     NBA_STATS, "resultSets"),
    ("nba.com stats: team advanced 2025-26",
     "https://stats.nba.com/stats/leaguedashteamstats?MeasureType=Advanced&PerMode=PerGame"
     "&Season=2025-26&SeasonType=Regular%20Season&LeagueID=00&LastNGames=0&Month=0"
     "&OpponentTeamID=0&PaceAdjust=N&Period=0&PlusMinus=N&Rank=N&DateFrom=&DateTo=",
     NBA_STATS, "resultSets"),
    ("nba.com CDN: season schedule",
     "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json", BROWSER, "leagueSchedule"),
    ("nba.com CDN: today's scoreboard",
     "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json", BROWSER, "scoreboard"),
    ("official.nba.com: injury report page",
     "https://official.nba.com/nba-injury-report-2025-26-season/", BROWSER, "Injury"),
    ("official.nba.com: referee assignments",
     "https://official.nba.com/referee-assignments/", BROWSER, "Referee"),
    ("ESPN: scoreboard",
     "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard", BROWSER, "events"),
    ("ESPN: injuries",
     "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries", BROWSER, "injuries"),
    ("Basketball-Reference: LeBron 2004 game log",
     "https://www.basketball-reference.com/players/j/jamesle01/gamelog/2004", BROWSER, "pgl_basic"),
    ("pbpstats: team totals 2024-25",
     "https://api.pbpstats.com/get-totals/nba?Season=2024-25&SeasonType=Regular%2BSeason&Type=Team",
     BROWSER, "multi_row_table_data"),
    ("hashtagbasketball: defense vs position",
     "https://hashtagbasketball.com/nba-defense-vs-position", BROWSER, "PG"),
    ("databallr: home page",
     "https://databallr.com/", BROWSER, "<"),
    ("Rotowire: lineups",
     "https://www.rotowire.com/basketball/nba-lineups.php", BROWSER, "lineup"),
    ("Action Network: NBA scoreboard + odds",
     "https://api.actionnetwork.com/web/v1/scoreboard/nba?period=game&bookIds=15,30", BROWSER, "games"),
    ("SBR archive: NBA odds 2021-22",
     "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nba-odds-2021-22/", BROWSER, "Rot"),
    ("SBR archive: NBA odds 2008-09",
     "https://www.sportsbookreviewsonline.com/scoresoddsarchives/nba-odds-2008-09/", BROWSER, "Rot"),
]


def probe(name, url, headers, must):
    t = time.time()
    try:
        r = requests.get(url, headers=headers, timeout=30)
        took = time.time() - t
        good = r.status_code == 200 and must.lower() in r.text.lower()
        sample = " ".join(r.text[:120].split())
        return f"{'OK  ' if good else 'FAIL'} | {r.status_code} | {len(r.content):>9,} B | {took:5.1f}s | {name} | {sample}"
    except Exception as e:  # timeouts are the usual nba.com block: it just never answers
        return f"FAIL | --- | {'':>11} | {time.time() - t:5.1f}s | {name} | {type(e).__name__}: {e}"[:300]


if __name__ == "__main__":
    for i, s in enumerate(SOURCES):
        if s[0].startswith("Basketball-Reference"):
            time.sleep(3)  # stay far under its ~20 requests/minute limit
        print(probe(*s), flush=True)
