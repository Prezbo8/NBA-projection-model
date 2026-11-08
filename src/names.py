"""Player-name matching across sources (nba.com vs Action Network / Rotowire / ESPN)."""
import glob
import re
import unicodedata

import pandas as pd


def norm(name):
    """'Luka Dončić' -> 'lukadoncic'; drops Jr./Sr./II/III/IV and punctuation."""
    n = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", n)
    return re.sub(r"[^a-z]", "", n)


def read_all(pattern):
    """Concatenate every CSV(.gz) matching `pattern`, skipping empty files (days saved with no rows)."""
    parts = []
    for f in sorted(glob.glob(pattern)):
        try:
            d = pd.read_csv(f)
        except pd.errors.EmptyDataError:
            continue
        if len(d):
            parts.append(d)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
