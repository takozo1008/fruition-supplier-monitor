"""
マルシェ候補自動収集スクリプト
対象: fmfm.jp（神奈川県）
実行: GitHub Actions で週1回（月曜朝8時JST）
"""
import hashlib
import json
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://fruition-marche-default-rtdb.firebaseio.com"
PREFECTURE   = "kanagawa"
PREF_LABEL   = "神奈川県"

SOURCES = [
    {
        "name": "fmfm.jp",
        "url":  f"https://fmfm.jp/{PREFECTURE}",
    },
    {
        "name": "fmfm.jp（次月）",
        "url":  f"https://fmfm.jp/{PREFECTURE}?page=2",
    },
]

# ── HTTP ──────────────────────────────────────────
def fetch(url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0 Safari/537.36",
            "Accept-Language": "ja,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  FETCH ERROR {url}: {e}")
        return None

# ── パーサー ──────────────────────────────────────
def parse_fmfm(html, source_url):
    """fmfm.jp のイベント一覧ページをパースする"""
    events = []

    # イベントブロックを抽出（<article> または class="event-item" など）
    # fmfm.jpの構造に合わせて複数パターンを試みる
    blocks = re.findall(
        r'<(?:article|div)[^>]*class="[^"]*(?:event|marche|item)[^"]*"[^>]*>(.*?)</(?:article|div)>',
        html, re.DOTALL | re.IGNORECASE
    )

    # ブロックが取れなかった場合はリンクベースで抽出
    if not blocks:
        links = re.findall(
            r'href="(https?://fmfm\.jp/[^"]+/\d+[^"]*)"[^>]*>([^<]{5,80})</a>',
            html
        )
        for url, name in links:
            events.append({
                "name":     name.strip(),
                "date":     "",
                "location": PREF_LABEL,
                "url":      url,
                "source":   "fmfm.jp",
            })
        return events

    for block in blocks:
        # イベント名
        name_m = re.search(r'<(?:h\d|a)[^>]*>([^<]{4,80})</(?:h\d|a)>', block)
        name   = name_m.group(1).strip() if name_m else ""

        # 日付（YYYY-MM-DD / YYYY年MM月DD日 など）
        date_m = re.search(
            r'(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})', block
        )
        date = ""
        if date_m:
            y, m, d = date_m.group(1), date_m.group(2).zfill(2), date_m.group(3).zfill(2)
            date = f"{y}-{m}-{d}"

        # URL
        url_m = re.search(r'href="(https?://fmfm\.jp/[^"]+)"', block)
        url   = url_m.group(1) if url_m else source_url

        # 場所
        loc_m = re.search(r'(神奈川[^\s<]{0,30}|横浜[^\s<]{0,20}|川崎[^\s<]{0,20}|鎌倉[^\s<]{0,20}|藤沢[^\s<]{0,20}|茅ヶ崎[^\s<]{0,20})', block)
        location = loc_m.group(1).strip() if loc_m else PREF_LABEL

        if name:
            events.append({
                "name":     name,
                "date":     date,
                "location": location,
                "url":      url,
                "source":   "fmfm.jp",
            })

    return events

# ── Firebase ──────────────────────────────────────
def firebase_get(path):
    try:
        with urllib.request.urlopen(f"{FIREBASE_URL}/{path}.json", timeout=10) as r:
            data = r.read()
            return json.loads(data) if data and data != b"null" else None
    except Exception as e:
        print(f"  FB GET ERROR: {e}")
        return None

def firebase_post(path, data):
    req = urllib.request.Request(
        f"{FIREBASE_URL}/{path}.json",
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

# ── メイン ────────────────────────────────────────
def main():
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    print(f"=== マルシェ候補チェック ===\nTime: {now}\n")

    # 既存候補のURLセット（重複登録を防ぐ）
    existing = firebase_get("fruition/marcheCandidates") or {}
    existing_urls = set()
    if isinstance(existing, dict):
        for v in existing.values():
            if isinstance(v, dict) and v.get("url"):
                existing_urls.add(v["url"])

    added = 0
    for source in SOURCES:
        print(f"Fetching: {source['url']}")
        html = fetch(source["url"])
        if not html:
            continue

        events = parse_fmfm(html, source["url"])
        print(f"  パース結果: {len(events)} 件")

        for ev in events:
            if ev["url"] in existing_urls:
                print(f"  SKIP（重複）: {ev['name']}")
                continue
            candidate = {
                "name":      ev["name"],
                "date":      ev["date"],
                "location":  ev["location"],
                "url":       ev["url"],
                "source":    ev["source"],
                "status":    "pending",   # pending / joined / dismissed
                "addedAt":   now,
            }
            result = firebase_post("fruition/marcheCandidates", candidate)
            existing_urls.add(ev["url"])
            added += 1
            print(f"  ADD: {ev['name']} ({ev['date']})")

    print(f"\n完了: {added} 件を追加しました")

if __name__ == "__main__":
    main()
