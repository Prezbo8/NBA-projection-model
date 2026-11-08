"""Phase 2 probe: game-day sources: ESPN injuries JSON, Rotowire lineups HTML, official.nba.com refs."""
import json
import re
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as f:
        return f.read().decode("utf-8", "replace")


print("=== ESPN injuries")
d = json.loads(get("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"))
print("top keys", list(d), "| teams", len(d.get("injuries", [])))
t = d["injuries"][0]
print("team keys", list(t), t.get("displayName"))
print("injury sample", json.dumps(t["injuries"][0])[:1500])

print("\n=== Rotowire lineups")
h = get("https://www.rotowire.com/basketball/nba-lineups.php")
print("len", len(h), "| lineup blocks", h.count('class="lineup is-nba'), "| classes:",
      sorted(set(re.findall(r'class="(lineup__[a-z-]+)', h)))[:40])
i = h.find('class="lineup is-nba')
print(re.sub(r"\s+", " ", re.sub(r"<script.*?</script>", "", h[i:i + 6000], flags=re.S))[:3500])

print("\n=== official.nba.com referee assignments")
h = get("https://official.nba.com/referee-assignments/")
i = h.find("<table")
print(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", h[i:i + 4000]))[:2000])

print("\n=== official.nba.com injury report page (PDF links)")
h = get("https://official.nba.com/nba-injury-report-2026-27-season/")
links = re.findall(r'https?://[^"\']+Injury-Report[^"\']+\.pdf', h)
print(len(links), "pdf links; last 3:", links[-3:])
