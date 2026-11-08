"""Player-name matching across sources (nba.com vs Action Network / Rotowire / ESPN)."""
import re
import unicodedata


def norm(name):
    """'Luka Dončić' -> 'lukadoncic'; drops Jr./Sr./II/III/IV and punctuation."""
    n = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b\.?", "", n)
    return re.sub(r"[^a-z]", "", n)
