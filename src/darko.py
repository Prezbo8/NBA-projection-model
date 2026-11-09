"""DARKO DPM daily snapshot (darko.app, licensed): one page request a day, saved to PRIVATE Supabase storage.

The leaderboard page embeds the full table (players: {keys: [...], values: [[column], ...]}), the same data
as its "Download CSV" button (checked Nov 9 2026: 522 players, identical). Each day's file is what DARKO said
before that day's games, so the history built from these snapshots has no look-ahead.
Never written to the repo (licensed data; the repo is public).

  python src/darko.py            # fetch today's leaderboard -> nba-private/darko/<date>.csv.gz
"""
import gzip
import io
import json
import re
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import private_store

PAGE = "https://www.darko.app/"
NEEDED = ["nba_id", "player_name", "tm_id", "dpm", "o_dpm", "d_dpm", "x_minutes", "x_pace"]


def _bracket(s, start):
    """The [...] that starts at s[start], brackets matched."""
    depth = 0
    for j in range(start, len(s)):
        if s[j] == "[":
            depth += 1
        elif s[j] == "]":
            depth -= 1
            if depth == 0:
                return s[start:j + 1]
    raise ValueError("unbalanced brackets")


def parse(html):
    i = html.find("players:{keys:")
    if i < 0:
        raise ValueError("leaderboard data not found in the page (layout changed?)")
    k0 = html.find("[", i)
    keys = json.loads(_bracket(html, k0))
    raw = _bracket(html, html.find("[", html.find("values:", k0) + 7))
    raw = re.sub(r"\bvoid 0\b", "null", raw)
    raw = re.sub(r"(?<=[,\[])(-?)\.(\d)", r"\g<1>0.\2", raw)   # JS short numbers: .98 -> 0.98
    df = pd.DataFrame(dict(zip(keys, json.loads(raw))))
    missing = [c for c in NEEDED if c not in df.columns]
    if missing or len(df) < 300 or df.nba_id.duplicated().any():
        raise ValueError(f"unexpected table: {len(df)} rows, missing {missing}, dup ids {df.nba_id.duplicated().sum()}")
    return df


def main():
    req = urllib.request.Request(PAGE, headers={"User-Agent": "Mozilla/5.0 (personal research; nba-projection-model)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "ignore")
    df = parse(html)
    day = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    df.insert(0, "snapshot_date", day)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(df.to_csv(index=False).encode())
    private_store.upload(f"darko/{day}.csv.gz", buf.getvalue())
    # counts only: Actions logs of a public repo are public, so no licensed values are printed
    print(f"darko {day}: {len(df)} players, {len(df.columns)} columns saved to private storage. "
          f"Snapshots stored: {len(private_store.list_names('darko'))}")


if __name__ == "__main__":
    sys.exit(main())
