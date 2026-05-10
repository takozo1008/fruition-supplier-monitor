import hashlib
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://fruition-marche-default-rtdb.firebaseio.com"
import os as _os
_FB_SECRET = _os.environ.get("FIREBASE_DB_SECRET", "")

# url と instagram の両方を監視。空文字はスキップ。
SUPPLIERS = [
    {"id": "s1",  "name": "生豆本舗",                "url": "https://www.namamamehonpo.com",      "instagram": "https://www.instagram.com/namamamehonpo/"},
    {"id": "s2",  "name": "ASLAN Coffee Factory",    "url": "https://aslancoffee.thebase.in",      "instagram": "https://www.instagram.com/aslan_coffee_factory/"},
    {"id": "s3",  "name": "Heirroom Wholesale",      "url": "",                                    "instagram": "https://www.instagram.com/wholesale_heirroom/"},
    {"id": "s4",  "name": "GREEN COFFEE STORE",      "url": "https://www.greencoffee.co.jp",       "instagram": "https://www.instagram.com/dcs_green/"},
    {"id": "s5",  "name": "TSUKIKOYA COFFEE ROASTR", "url": "",                                    "instagram": "https://www.instagram.com/tsukikoya_coffee_roaster/"},
    {"id": "s6",  "name": "海の向こうコーヒー",        "url": "",                                    "instagram": "https://www.instagram.com/uminomuko_coffee/"},
    {"id": "s7",  "name": "コーヒーマート63",          "url": "",                                    "instagram": "https://www.instagram.com/coffeemart63/"},
    {"id": "s8",  "name": "エモ珈琲",                 "url": "",                                    "instagram": "https://www.instagram.com/emocoffee.co/"},
    {"id": "s9",  "name": "LiLo Coffee Roasters",    "url": "",                                    "instagram": "https://www.instagram.com/lilocoffee/"},
    {"id": "s10", "name": "White Monkey",            "url": "",                                    "instagram": "https://www.instagram.com/white_monkey_coffee/"},
    {"id": "s11", "name": "TYPICA",                  "url": "https://typica.coffee/ja/",           "instagram": "https://www.instagram.com/typica.jp/"},
    {"id": "s12", "name": "Days Coffee Roaster",     "url": "",                                    "instagram": "https://www.instagram.com/dayscoffeeroaster/"},
    {"id": "s13", "name": "ALPS COFFEE LAB",         "url": "",                                    "instagram": "https://www.instagram.com/alps.coffee.lab/"},
    {"id": "s14", "name": "みさごコーヒー",            "url": "",                                    "instagram": "https://www.instagram.com/misagocoffee/"},
    {"id": "s15", "name": "Coffee Network",          "url": "",                                    "instagram": ""},
    {"id": "s16", "name": "珈琲豆 山倉",              "url": "",                                    "instagram": "https://www.instagram.com/coffee_beans_yamakura/"},
    {"id": "s17", "name": "switch",                  "url": "",                                    "instagram": "https://www.instagram.com/coffeestandswitch/"},
    {"id": "s18", "name": "SUZUKI COFFEE",           "url": "",                                    "instagram": ""},
    {"id": "s19", "name": "丸山珈琲",                 "url": "",                                    "instagram": "https://www.instagram.com/maruyama_coffee/"},
    {"id": "s20", "name": "大阪箕面珈琲焙煎所",        "url": "",                                    "instagram": "https://www.instagram.com/minoh_coffee/"},
    {"id": "s21", "name": "ワイルド珈琲ストア",         "url": "",                                    "instagram": "https://www.instagram.com/wildcoffee.store/"},
    {"id": "s22", "name": "コーヒー焙煎所ZERO",        "url": "",                                    "instagram": ""},
    {"id": "s23", "name": "まだゆめのつづき",           "url": "",                                    "instagram": "https://www.instagram.com/seiko_fullofdreams/"},
    {"id": "s24", "name": "珈琲問屋",                 "url": "",                                    "instagram": ""},
    {"id": "s25", "name": "lohas beans",             "url": "",                                    "instagram": "https://www.instagram.com/lohasbeansroasters/"},
    {"id": "s26", "name": "post coffee",             "url": "",                                    "instagram": ""},
    {"id": "s27", "name": "アマノアオイ商店",           "url": "",                                    "instagram": "https://www.instagram.com/aoiamano5/"},
    {"id": "s28", "name": "NITTA COFFEE",            "url": "",                                    "instagram": "https://www.instagram.com/nitta_coffee/"},
]

def fetch_url(url, is_instagram=False):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Accept-Language": "ja,en;q=0.9",
        }
        if is_instagram:
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  FETCH ERROR: {e}")
        return None

def content_hash(html, is_instagram=False):
    if is_instagram:
        # Instagramは投稿数・フォロワー数など数値の変化を検知する
        numbers = re.findall(r'"edge_followed_by":\{"count":(\d+)\}|"edge_owner_to_timeline_media":\{"count":(\d+)\}', html)
        if numbers:
            return hashlib.sha256(str(numbers).encode()).hexdigest()
        # フォールバック：og:descriptionタグの内容
        desc = re.findall(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', html)
        if desc:
            return hashlib.sha256(desc[0].encode()).hexdigest()
        # さらにフォールバック：ページ全体
    text = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(text.encode()).hexdigest()

def _fb_url(path):
    auth_param = f"?auth={_FB_SECRET}" if _FB_SECRET else ""
    return f"{FIREBASE_URL}/{path}.json{auth_param}"

def firebase_get(path):
    try:
        with urllib.request.urlopen(_fb_url(path), timeout=10) as r:
            data = r.read()
            return json.loads(data) if data else None
    except Exception as e:
        print(f"  FIREBASE GET ERROR: {e}")
        return None

def firebase_put(path, data):
    req = urllib.request.Request(
        _fb_url(path),
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

def firebase_post(path, data):
    req = urllib.request.Request(
        _fb_url(path),
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

def check_one(sid, name, url, label, is_instagram, hashes, new_hashes, now):
    key = f"{sid}_{label}"
    print(f"\n  [{label}] {url}")
    html = fetch_url(url, is_instagram=is_instagram)
    if not html:
        print("    SKIP: could not fetch")
        return
    h = content_hash(html, is_instagram=is_instagram)
    old_h = hashes.get(key)
    if old_h is None:
        print("    INIT: storing initial hash")
    elif old_h != h:
        print("    CHANGED: writing update to Firebase")
        firebase_post("fruition/supplierUpdates", {
            "supplierId":   sid,
            "supplierName": name,
            "url":          url,
            "label":        "Instagram" if is_instagram else "Website",
            "detectedAt":   now,
            "read":         False
        })
    else:
        print("    NO CHANGE")
    new_hashes[key] = h

def main():
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%dT%H:%M:%S+09:00")

    print("=== Supplier Update Check ===")
    print(f"Time: {now}")

    hashes = firebase_get("fruition/supplierHashes") or {}
    new_hashes = dict(hashes)

    for s in SUPPLIERS:
        sid, name = s["id"], s["name"]
        print(f"\nChecking: {name}")
        if s.get("url"):
            check_one(sid, name, s["url"], "site", False, hashes, new_hashes, now)
        if s.get("instagram"):
            check_one(sid, name, s["instagram"], "instagram", True, hashes, new_hashes, now)

    firebase_put("fruition/supplierHashes", new_hashes)
    print("\nDone.")

if __name__ == "__main__":
    main()
