"""
マルシェ候補自動収集スクリプト
対象: fmfm.jp（神奈川県）
実行: GitHub Actions で毎朝8時JST
"""
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://fruition-marche-default-rtdb.firebaseio.com"
PREF_LABEL   = "神奈川県"

SOURCES = [
    {"name": "fmfm.jp", "url": "https://fmfm.jp/area/kanagawa"},
    {"name": "fmfm.jp", "url": "https://fmfm.jp/area/kanagawa?page=2"},
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
def parse_fmfm(html):
    """
    fmfm.jp/area/kanagawa をパース。
    イベントリンク /event/detail/[id] を起点に
    名前・日付・場所を抽出する。
    """
    events = []
    seen_urls = set()

    # /event/detail/数字 へのリンクを全て抽出
    # <a href="/event/detail/2358" ...>イベント名</a> パターン
    link_pattern = re.compile(
        r'href="(/event/detail/(\d+))[^"]*"[^>]*>\s*([^<]{2,80})\s*</a>',
        re.DOTALL
    )

    # 日付パターン（ページ内の直近の日付を検索）
    # "05/03 (日)" または "2026年05月03日" 形式
    date_patterns = [
        re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日'),
        re.compile(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})'),
        re.compile(r'(\d{1,2})/(\d{1,2})\s*[（(].[）)]'),  # 05/03 (日)
    ]

    # ページを「イベントブロック」単位で分割して処理
    # href="/event/detail/" を含む前後2000文字を切り出す
    for m in link_pattern.finditer(html):
        path      = m.group(1)
        event_url = f"https://fmfm.jp{path}"
        raw_name  = m.group(3).strip()

        # 重複スキップ
        if event_url in seen_urls:
            continue
        # ナビゲーション等の短い/無関係なテキストをスキップ
        if len(raw_name) < 3 or raw_name in ('詳細', '続きを読む', 'もっと見る', '>>>'):
            continue

        seen_urls.add(event_url)

        # 前後の文脈から日付を探す
        start = max(0, m.start() - 500)
        end   = min(len(html), m.end() + 500)
        ctx   = html[start:end]

        date = ""
        # YYYY年MM月DD日
        dm = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', ctx)
        if dm:
            date = f"{dm.group(1)}-{dm.group(2).zfill(2)}-{dm.group(3).zfill(2)}"
        else:
            # MM/DD
            dm2 = re.search(r'(\d{1,2})/(\d{1,2})', ctx)
            if dm2:
                year = datetime.now(timezone(timedelta(hours=9))).year
                date = f"{year}-{dm2.group(1).zfill(2)}-{dm2.group(2).zfill(2)}"

        # 場所（神奈川の市区町村名）
        loc_m = re.search(
            r'(横浜市|川崎市|相模原市|鎌倉市|藤沢市|茅ヶ崎市|逗子市|三浦市|小田原市|平塚市|厚木市|大和市|海老名市|座間市|綾瀬市|秦野市|伊勢原市|南足柄市|横須賀市|葉山町|寒川町|大磯町|二宮町|中井町|大井町|松田町|山北町|開成町|箱根町|真鶴町|湯河原町|愛川町|清川村)',
            ctx
        )
        location = loc_m.group(1) if loc_m else PREF_LABEL

        # クリーンアップ：HTMLエンティティ除去
        name = re.sub(r'&[a-zA-Z]+;', '', raw_name).strip()
        name = re.sub(r'\s+', ' ', name)

        if name:
            events.append({
                "name":     name,
                "date":     date,
                "location": location,
                "url":      event_url,
                "source":   "fmfm.jp",
            })
            print(f"  FOUND: {name} | {date} | {location}")

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

    existing = firebase_get("fruition/marcheCandidates") or {}
    existing_urls = set()
    if isinstance(existing, dict):
        for v in existing.values():
            if isinstance(v, dict) and v.get("url"):
                existing_urls.add(v["url"])

    print(f"既存候補数: {len(existing_urls)} 件\n")

    added = 0
    for source in SOURCES:
        print(f"Fetching: {source['url']}")
        html = fetch(source["url"])
        if not html:
            print("  SKIP: fetch失敗")
            continue

        print(f"  HTMLサイズ: {len(html)} bytes")
        events = parse_fmfm(html)
        print(f"  パース結果: {len(events)} 件")

        for ev in events:
            if ev["url"] in existing_urls:
                print(f"  SKIP（重複）: {ev['name']}")
                continue
            candidate = {
                "name":     ev["name"],
                "date":     ev["date"],
                "location": ev["location"],
                "url":      ev["url"],
                "source":   ev["source"],
                "status":   "pending",
                "addedAt":  now,
            }
            firebase_post("fruition/marcheCandidates", candidate)
            existing_urls.add(ev["url"])
            added += 1
            print(f"  ADD: {ev['name']} ({ev['date']})")

    print(f"\n完了: {added} 件を追加しました")

if __name__ == "__main__":
    main()
