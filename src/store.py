"""Load the nba.com season files (data/nbacom) into Supabase tables nba_player_games / nba_team_games.

Needs SUPABASE_URL and SUPABASE_KEY (service key) in the environment (GitHub secrets).
Without them it prints a note and does nothing. Upserts, so re-running a season is safe.

  python src/store.py 2003-04 2025-26
"""
import json
import os
import sys
import time
import urllib.request

import pandas as pd

from nbacom import OUT, seasons

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_KEY", "")
STATS = ["min", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk",
         "tov", "pf", "pts", "plus_minus"]


def tidy(df, player):
    """nba.com columns -> table columns; opp/home come from MATCHUP ('CLE vs. BOS' home, 'CLE @ BOS' away)."""
    df = df.rename(columns=str.lower).rename(columns={"team_abbreviation": "team"})
    df["home"] = df.matchup.str.contains(" vs. ")
    df["opp"] = df.matchup.str[-3:]
    df["game_date"] = pd.to_datetime(df.game_date).dt.strftime("%Y-%m-%d")
    keys = ["game_id", "player_id", "player_name"] if player else ["game_id"]
    cols = keys + ["team_id", "team", "opp", "season", "season_type", "game_date", "home", "wl"] + STATS
    return df[cols]


def send(table, df, on_conflict, chunk=2000):
    headers = {"apikey": KEY, "Content-Type": "application/json",
               "Prefer": "resolution=merge-duplicates,return=minimal",
               **({"Authorization": f"Bearer {KEY}"} if KEY.startswith("eyJ") else {})}
    rows = json.loads(df.to_json(orient="records"))  # NaN -> null
    for i in range(0, len(rows), chunk):
        body = json.dumps(rows[i:i + chunk]).encode()
        for t in range(3):
            try:
                req = urllib.request.Request(f"{URL}/rest/v1/{table}?on_conflict={on_conflict}",
                                             data=body, method="POST", headers=headers)
                urllib.request.urlopen(req, timeout=120).read()
                break
            except Exception as e:
                if t == 2:
                    raise
                print(f"  retry {table} chunk {i}: {e}", flush=True)
                time.sleep(10)


if __name__ == "__main__":
    if not (URL and KEY):
        print("SUPABASE_URL / SUPABASE_KEY not set: skipping the Supabase load (files are still committed)")
        sys.exit(0)
    for s in seasons(sys.argv[1], sys.argv[2]):
        p = tidy(pd.read_csv(f"{OUT}/player_games_{s}.csv.gz", dtype={"GAME_ID": str}), True)
        t = tidy(pd.read_csv(f"{OUT}/team_games_{s}.csv.gz", dtype={"GAME_ID": str}), False)
        send("nba_player_games", p, "game_id,player_id")
        send("nba_team_games", t, "game_id,team_id")
        print(f"{s}: {len(p):,} player rows, {len(t):,} team rows loaded", flush=True)
