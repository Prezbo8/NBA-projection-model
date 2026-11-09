"""Private file storage for licensed stats (DARKO, databallr): a PRIVATE Supabase Storage bucket, never the repo.

The repo is public, so licensed data must not be committed. Jobs upload daily snapshots here and the model
downloads them at run time. Needs SUPABASE_URL and SUPABASE_KEY (secret key) in the environment (GitHub secrets).
New sb_secret_ keys go in the `apikey` header only (same as the NHL model's store.py).

  python src/private_store.py check     # key present, bucket exists + private, round trip works, no-key read fails
"""
import os
import sys
import urllib.error
import urllib.request

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_KEY", "")
BUCKET = "nba-private"


def _headers(**extra):
    return {"apikey": KEY, **({"Authorization": f"Bearer {KEY}"} if KEY.startswith("eyJ") else {}), **extra}


def _req(method, path, body=None, headers=None, auth=True):
    h = (_headers() if auth else {}) | (headers or {})
    req = urllib.request.Request(f"{URL}/storage/v1/{path}", data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def ensure_bucket():
    """Create the bucket as private if it doesn't exist; refuse to continue if it exists and is public."""
    st, body = _req("GET", f"bucket/{BUCKET}")
    if st == 200:
        if b'"public":true' in body.replace(b" ", b""):
            raise SystemExit(f"bucket {BUCKET} is PUBLIC - fix it in the Supabase dashboard before storing licensed data")
        return "exists (private)"
    import json
    st, body = _req("POST", "bucket", json.dumps({"id": BUCKET, "name": BUCKET, "public": False}).encode(),
                    {"Content-Type": "application/json"})
    if st not in (200, 201):
        raise SystemExit(f"could not create bucket: HTTP {st} {body[:200]!r}")
    return "created (private)"


def upload(name, data, content_type="application/gzip"):
    st, body = _req("POST", f"object/{BUCKET}/{name}", data, {"Content-Type": content_type, "x-upsert": "true"})
    if st not in (200, 201):
        raise RuntimeError(f"upload {name}: HTTP {st} {body[:200]!r}")


def download(name):
    st, body = _req("GET", f"object/{BUCKET}/{name}")
    if st != 200:
        raise RuntimeError(f"download {name}: HTTP {st} {body[:200]!r}")
    return body


def list_names(prefix):
    import json
    st, body = _req("POST", f"object/list/{BUCKET}", json.dumps({"prefix": prefix, "limit": 1000}).encode(),
                    {"Content-Type": "application/json"})
    if st != 200:
        raise RuntimeError(f"list {prefix}: HTTP {st} {body[:200]!r}")
    return sorted(f"{prefix.rstrip('/')}/{o['name']}" for o in json.loads(body) if o.get("id"))


def check():
    if not URL or not KEY:
        raise SystemExit("SUPABASE_URL / SUPABASE_KEY missing")
    print(f"key: {len(KEY)} chars, starts {KEY[:10]}...")   # prefix only, never the key
    print(f"bucket {BUCKET}: {ensure_bucket()}")
    upload("_check.txt", b"ok", "text/plain")
    print(f"round trip with key: {download('_check.txt') == b'ok'}")
    st1, _ = _req("GET", f"object/{BUCKET}/_check.txt", auth=False)
    st2, _ = _req("GET", f"object/public/{BUCKET}/_check.txt", auth=False)
    private = st1 != 200 and st2 != 200
    print(f"read without key: HTTP {st1}, public URL: HTTP {st2} -> {'PRIVATE ok' if private else 'NOT PRIVATE'}")
    if not private:
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.argv[1:] == ["check"]:
        check()
