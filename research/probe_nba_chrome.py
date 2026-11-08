"""Phase 0b: do the nba.com endpoints answer when the request connects like Chrome (curl_cffi)?

Plain `requests` gets timeouts (stats.nba.com) and 403s (cdn/www) even from the Mac runner,
which points at nba.com's bot check rejecting non-browser clients rather than at the IP address.
"""
import time

from curl_cffi import requests as cr

import probe_sources as p

for name, url, headers, must in p.SOURCES:
    if "nba.com" not in url or "official" in url:
        continue
    t = time.time()
    try:
        r = cr.get(url, headers=headers, impersonate="chrome", timeout=30)
        ok = r.status_code == 200 and must.lower() in r.text.lower()
        print(f"CHROME {'OK  ' if ok else 'FAIL'} | {r.status_code} | {len(r.content):>9,} B | "
              f"{time.time() - t:5.1f}s | {name} | {' '.join(r.text[:120].split())}", flush=True)
    except Exception as e:
        print(f"CHROME FAIL | --- | {time.time() - t:5.1f}s | {name} | {type(e).__name__}: {str(e)[:150]}", flush=True)
    time.sleep(2)
