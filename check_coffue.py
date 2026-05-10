"""
coffue.com のコーヒーイベント情報を取得して Firebase に保存
Firebase /fruition/coffueCandidates に保存（既存のステータスは保持）
"""
import json, urllib.request
from datetime import datetime, timezone, timedelta
import os as _os

FIREBASE_URL = "https://fruition-marche-default-rtdb.firebaseio.com"
_FB_SECRET = _os.environ.get("FIREBASE_DB_SECRET", "")

COFFUE_API = "https://coffue.com/api/events?page={page}"
MAX_PAGES = 10

def fetch_json(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "ja,en;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        print(f"  FETCH ERROR {url}: {e}")
        return None

def _fb_url(path):
    auth_param = f"?auth={_FB_SECRET}" if _FB_SECRET else ""
    return f"{FIREBASE_URL}/{path}.json{auth_param}"

def firebase_get(path):
    try:
        with urllib.request.urlopen(_fb_url(path), timeout=10) as r:
            data = r.read()
            return json.loads(data) if data and data != b"null" else None
    except Exception as e:
        print(f"  FB GET ERROR: {e}")
        return None

def firebase_put(path, data):
    req = urllib.request.Request(
        _fb_url(path),
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()

def main():
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    print(f"=== coffue.com イベント取得 ===\nTime: {now}\n")

    # 全ページ取得
    all_events = []
    for page in range(1, MAX_PAGES + 1):
        url = COFFUE_API.format(page=page)
        print(f"  Fetching page {page}: {url}")
        data = fetch_json(url)
        if not data:
            break
        events = data.get("data") or []
        if not events:
            break
        all_events.extend(events)
        print(f"    → {len(events)} 件取得（累計: {len(all_events)} 件）")
        if len(events) < 20:
            break  # 最終ページ

    print(f"\n合計 {len(all_events)} 件取得\n")

    if not all_events:
        print("⚠️  イベントデータなし")
        return

    # 既存データ取得（ステータス保持のため）
    existing_raw = firebase_get("fruition/coffueCandidates") or {}
    existing = existing_raw if isinstance(existing_raw, dict) else {}

    # 既存データを id → エントリ でマッピング
    existing_by_id = {}
    for k, v in existing.items():
        if isinstance(v, dict) and v.get("id"):
            existing_by_id[v["id"]] = (k, v)

    result = dict(existing)  # 既存データを全部保持した上で上書き
    added = 0
    updated = 0

    for ev in all_events:
        ev_id = str(ev.get("id", ""))
        if not ev_id:
            continue

        key = f"coffue_{ev_id[:12]}"
        sns = ev.get("sns") or {}
        image_urls = ev.get("image_urls") or []
        image_url  = image_urls[0] if image_urls else ev.get("image_url", "")
        tags = ev.get("tag") or []

        new_entry = {
            "_key":        key,
            "id":          ev_id,
            "title":       ev.get("title")        or "",
            "start_date":  ev.get("start_date")   or "",
            "end_date":    ev.get("end_date")      or "",
            "place":       ev.get("place")         or "",
            "address":     ev.get("address")       or "",
            "official_url":ev.get("official_url")  or "",
            "sns":         sns,
            "tag":         tags,
            "image_url":   image_url,
            "image_urls":  image_urls,
            "source":      "coffue.com",
        }

        if ev_id in existing_by_id:
            # 既存エントリ：ステータス・addedAt を保持しつつイベント情報を更新
            old_key, old_entry = existing_by_id[ev_id]
            merged = dict(old_entry)
            merged.update(new_entry)
            merged["_key"]    = old_key
            merged["addedAt"] = old_entry.get("addedAt", now)
            result[old_key] = merged
            updated += 1
        else:
            new_entry["status"]  = "pending"
            new_entry["addedAt"] = now
            result[key] = new_entry
            added += 1

    firebase_put("fruition/coffueCandidates", result)
    print(f"✅ 完了: 新規 {added} 件追加・{updated} 件更新（合計 {len(result)} 件）")

if __name__ == "__main__":
    main()
