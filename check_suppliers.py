import hashlib
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://fruition-marche-default-rtdb.firebaseio.com"

SUPPLIERS = [
    {"id": "s1",  "name": "生豆本舗",               "url": "https://www.namamamehonpo.com"},
    {"id": "s2",  "name": "ASLAN Coffee Factory",   "url": "https://aslancoffee.thebase.in"},
    {"id": "s4",  "name": "GREEN COFFEE STORE",     "url": "https://www.greencoffee.co.jp"},
    {"id": "s11", "name": "TYPICA",                 "url": "https://typica.coffee/ja/"},
]

def fetch_url(url):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FruitionMonitor/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  FETCH ERROR: {e}")
        return None

def content_hash(html):
    # Strip scripts/styles/comments and normalize whitespace to reduce false positives
    text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(text.encode()).hexdigest()

def firebase_get(path):
    url = f"{FIREBASE_URL}/{path}.json"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = r.read()
            return json.loads(data) if data else None
    except Exception as e:
        print(f"  FIREBASE GET ERROR: {e}")
        return None

def firebase_put(path, data):
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url,
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

def firebase_post(path, data):
    url = f"{FIREBASE_URL}/{path}.json"
    req = urllib.request.Request(
        url,
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

def main():
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%dT%H:%M:%S+09:00")

    print("=== Supplier Update Check ===")
    print(f"Time: {now}")

    hashes = firebase_get("fruition/supplierHashes") or {}
    new_hashes = dict(hashes)

    for supplier in SUPPLIERS:
        name = supplier["name"]
        url  = supplier["url"]
        sid  = supplier["id"]

        print(f"\nChecking: {name} ({url})")
        html = fetch_url(url)
        if not html:
            print("  SKIP: could not fetch")
            continue

        h = content_hash(html)
        old_h = hashes.get(sid)

        if old_h is None:
            print("  INIT: storing initial hash")
        elif old_h != h:
            print("  CHANGED: writing update to Firebase")
            update = {
                "supplierId":    sid,
                "supplierName":  name,
                "url":           url,
                "detectedAt":    now,
                "read":          False
            }
            firebase_post("fruition/supplierUpdates", update)
        else:
            print("  NO CHANGE")

        new_hashes[sid] = h

    firebase_put("fruition/supplierHashes", new_hashes)
    print("\nDone.")

if __name__ == "__main__":
    main()
