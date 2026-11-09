"""Does a plain `requests` call with kyleskom/NBA-Machine-Learning-Sports-Betting's Safari headers reach stats.nba.com?
(Nov 9 2026: yes from the Mac, 200 in 0.9 s.) Run on GitHub to see if it also works from cloud runners."""
import time

import requests

H = {"Accept": "*/*", "Accept-Encoding": "gzip, deflate, br", "Accept-Language": "en-US,en;q=0.9", "Connection": "keep-alive",
     "Origin": "https://www.nba.com", "Priority": "u=3, i", "Referer": "https://www.nba.com/", "Sec-Fetch-Dest": "empty",
     "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-site",
     "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
                   "Version/26.0.1 Safari/605.1.15"}
URLS = {
    "leaguedashteamstats": "https://stats.nba.com/stats/leaguedashteamstats?Conference=&DateFrom=10%2F01%2F2025&DateTo=11%2F01%2F2025"
    "&Division=&GameScope=&GameSegment=&LastNGames=0&LeagueID=00&Location=&MeasureType=Base&Month=0&OpponentTeamID=0&Outcome="
    "&PORound=0&PaceAdjust=N&PerMode=PerGame&Period=0&PlayerExperience=&PlayerPosition=&PlusMinus=N&Rank=N&Season=2025-26"
    "&SeasonSegment=&SeasonType=Regular+Season&ShotClockRange=&StarterBench=&TeamID=0&TwoWay=0&VsConference=&VsDivision=",
    "leaguegamelog": "https://stats.nba.com/stats/leaguegamelog?Counter=0&Direction=DESC&LeagueID=00&PlayerOrTeam=T"
    "&Season=2025-26&SeasonType=Regular+Season&Sorter=DATE",
}
for name, u in URLS.items():
    t = time.time()
    try:
        r = requests.get(u, headers=H, timeout=30)
        print(f"{name}: {r.status_code} {len(r.content):,} bytes {time.time() - t:.1f}s {r.text[:80]}", flush=True)
    except Exception as e:
        print(f"{name}: FAIL {type(e).__name__} {time.time() - t:.1f}s {str(e)[:120]}", flush=True)
    time.sleep(2)
