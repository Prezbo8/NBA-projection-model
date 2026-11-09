"""Evening opener watch (gameday.yml's 8:30 PM ET run loops on this every 5 min until 12:30 AM ET).

NBA totals for the next day open around 9:30 PM ET the night before (Action Network 'inserted' times, Nov 8 2026)
and can move 5 points within two hours. Prints how many of tomorrow's games have a total posted but aren't in
data/paper/slate.csv yet (= need projecting + paper logging now), or 'done' once every game on the slate is in.

  python src/watch_openers.py
"""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

import actionnet

ROOT = os.path.join(os.path.dirname(__file__), "..")
SLATE = os.path.join(ROOT, "data", "paper", "slate.csv")

tomorrow = datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=1)
rows, teams_of = actionnet.games(tomorrow)
posted = {str(r["an_game_id"]) for r in rows if r["book"] == "consensus" and r.get("total") is not None}
seen = set(pd.read_csv(SLATE, dtype={"an_game_id": str}).an_game_id) if os.path.exists(SLATE) else set()
print("done" if teams_of and {str(g) for g in teams_of} <= seen else len(posted - seen))
