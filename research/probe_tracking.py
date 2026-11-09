"""Do nba.com's tracking / hustle / play-type endpoints answer from the Mac runner? One call each, offense + defense.

usage (Mac runner only): python research/probe_tracking.py [season]
Prints rows returned, the column names and one sample row per endpoint. Writes nothing.
"""
import os
import sys
import time

import pandas as pd
from curl_cffi import requests as cr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from nbacom import HEADERS  # same headers as the working game-log job

SEASON = sys.argv[1] if len(sys.argv) > 1 else "2025-26"
B = "https://stats.nba.com/stats/"
# nba.com wants every filter present, even when empty
BASE = {"LeagueID": "00", "Season": SEASON, "SeasonType": "Regular Season", "PerMode": "PerGame",
        "DateFrom": "", "DateTo": "", "GameSegment": "", "LastNGames": "0", "Location": "", "Month": "0",
        "OpponentTeamID": "0", "Outcome": "", "PORound": "0", "Period": "0", "SeasonSegment": "", "TeamID": "0",
        "VsConference": "", "VsDivision": "", "Conference": "", "Division": "", "GameScope": "",
        "PlayerExperience": "", "PlayerPosition": "", "StarterBench": "", "DraftPick": "", "DraftYear": "",
        "College": "", "Country": "", "Height": "", "Weight": "", "ISTRound": ""}
SHOT = {**BASE, "CloseDefDistRange": "", "DribbleRange": "", "GeneralRange": "", "ShotClockRange": "",
        "ShotDistRange": "", "TouchTimeRange": ""}
team_games = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "nbacom",
                                      f"team_games_{SEASON}.csv.gz"))
GAME = f"{int(team_games.GAME_ID.iloc[-1]):010d}"
DAY = pd.to_datetime(team_games[team_games.SEASON_TYPE == "Regular Season"].GAME_DATE.iloc[-1]).strftime("%m/%d/%Y")

PROBES = [
    # (label, side, endpoint, params)
    ("drives (team)", "OFF", "leaguedashptstats", {**BASE, "PlayerOrTeam": "Team", "PtMeasureType": "Drives"}),
    ("touches (player)", "OFF", "leaguedashptstats", {**BASE, "PlayerOrTeam": "Player", "PtMeasureType": "Possessions"}),
    ("passing (team)", "OFF", "leaguedashptstats", {**BASE, "PlayerOrTeam": "Team", "PtMeasureType": "Passing"}),
    ("speed/distance (team)", "BOTH", "leaguedashptstats", {**BASE, "PlayerOrTeam": "Team", "PtMeasureType": "SpeedDistance"}),
    ("catch & shoot (team)", "OFF", "leaguedashptstats", {**BASE, "PlayerOrTeam": "Team", "PtMeasureType": "CatchShoot"}),
    ("pull-ups (team)", "OFF", "leaguedashptstats", {**BASE, "PlayerOrTeam": "Team", "PtMeasureType": "PullUpShot"}),
    ("drives ONE DAY (team)", "OFF", "leaguedashptstats",
     {**BASE, "PlayerOrTeam": "Team", "PtMeasureType": "Drives", "DateFrom": DAY, "DateTo": DAY}),
    ("shots by defender 0-2 ft (team)", "OFF", "leaguedashteamptshot", {**SHOT, "CloseDefDistRange": "0-2 Feet - Very Tight"}),
    ("catch & shoot shots (team)", "OFF", "leaguedashteamptshot", {**SHOT, "GeneralRange": "Catch and Shoot"}),
    ("ALLOWED wide open 6+ ft", "DEF", "leaguedashoppptshot", {**SHOT, "CloseDefDistRange": "6+ Feet - Wide Open"}),
    ("ALLOWED pull-ups", "DEF", "leaguedashoppptshot", {**SHOT, "GeneralRange": "Pullups"}),
    ("defended FG% (team)", "DEF", "leaguedashptteamdefend", {**BASE, "DefenseCategory": "Overall"}),
    ("defended FG% at rim (player)", "DEF", "leaguedashptdefend", {**BASE, "DefenseCategory": "Less Than 6Ft"}),
    ("hustle (team)", "BOTH", "leaguehustlestatsteam", BASE),
    ("hustle (player)", "BOTH", "leaguehustlestatsplayer", BASE),
    ("play type: transition", "OFF", "synergyplaytypes",
     {"LeagueID": "00", "SeasonYear": SEASON, "SeasonType": "Regular Season", "PerMode": "PerGame",
      "PlayerOrTeam": "T", "PlayType": "Transition", "TypeGrouping": "offensive"}),
    ("play type: P&R ball handler", "DEF", "synergyplaytypes",
     {"LeagueID": "00", "SeasonYear": SEASON, "SeasonType": "Regular Season", "PerMode": "PerGame",
      "PlayerOrTeam": "T", "PlayType": "PRBallHandler", "TypeGrouping": "defensive"}),
    ("matchups (LAL defense)", "DEF", "leagueseasonmatchups",
     {"LeagueID": "00", "Season": SEASON, "SeasonType": "Regular Season", "PerMode": "Totals",
      "DefTeamID": "1610612747", "OffTeamID": "", "DefPlayerID": "", "OffPlayerID": ""}),
    (f"box score tracking, game {GAME}", "BOTH", "boxscoreplayertrackv3", {"GameID": GAME}),
    (f"box score hustle, game {GAME}", "BOTH", "boxscorehustlev2", {"GameID": GAME}),
]


def rows_of(js):
    """resultSets (most endpoints) or the v3 nested layout -> (columns, rows)"""
    if "resultSets" in js:
        rs = js["resultSets"]
        rs = rs[0] if isinstance(rs, list) else rs
        return rs["headers"], rs["rowSet"]
    if "resultSet" in js:
        return js["resultSet"]["headers"], js["resultSet"]["rowSet"]
    box = next(v for k, v in js.items() if k.startswith(("boxScore", "hustle")))
    players = box["homeTeam"]["players"] + box["awayTeam"]["players"]
    cols = list(players[0]["statistics"]) if players else []
    return cols, [list(p["statistics"].values()) for p in players]


ok = 0
for label, side, ep, params in PROBES:
    t = time.time()
    try:
        r = cr.get(B + ep, params=params, headers=HEADERS, impersonate="chrome", timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {' '.join(r.text[:150].split())}")
        cols, rows = rows_of(r.json())
        ok += bool(rows)
        print(f"{'OK  ' if rows else 'EMPTY'} [{side:<4}] {label:<38} {ep:<24} {len(rows):>4} rows  {time.time() - t:4.1f}s")
        print(f"       cols: {', '.join(map(str, cols))[:400]}")
        if rows:
            print(f"       row1: {str(rows[0])[:300]}")
    except Exception as e:
        print(f"FAIL  [{side:<4}] {label:<38} {ep:<24} {type(e).__name__}: {str(e)[:200]}")
    sys.stdout.flush()
    time.sleep(4)   # same pace as the game-log job
print(f"\n{ok}/{len(PROBES)} endpoints returned data ({SEASON}; one-day = {DAY}; game = {GAME})")
