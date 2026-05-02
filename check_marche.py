"""
マルシェ候補自動収集スクリプト
対象: fmfm.jp（複数都道府県対応）
実行: GitHub Actions で毎朝8時JST
      環境変数 PREFECTURES でカンマ区切りで都道府県コードを指定可能
      例: PREFECTURES=kanagawa,tokyo,shizuoka

fmfm.jp 都道府県コード一覧:
  hokkaido / aomori / iwate / miyagi / akita / yamagata / fukushima /
  ibaraki / tochigi / gunma / saitama / chiba / tokyo / kanagawa /
  niigata / toyama / ishikawa / fukui / yamanashi / nagano / shizuoka /
  aichi / mie / shiga / kyoto / osaka / hyogo / nara / wakayama /
  tottori / shimane / okayama / hiroshima / yamaguchi /
  tokushima / kagawa / ehime / kochi /
  fukuoka / saga / nagasaki / kumamoto / oita / miyazaki / kagoshima / okinawa
"""
import json
import os
import re
import urllib.request
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://fruition-marche-default-rtdb.firebaseio.com"

# 環境変数 PREFECTURES があればそれを使う、なければ kanagawa のみ
_env_prefs = os.environ.get("PREFECTURES", "kanagawa")
TARGET_PREFS = [p.strip() for p in _env_prefs.split(",") if p.strip()]

SOURCES = []
for pref in TARGET_PREFS:
    SOURCES.append(f"https://fmfm.jp/area/{pref}")
    SOURCES.append(f"https://fmfm.jp/area/{pref}?page=2")

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

def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s).strip()

def parse_fmfm(html):
    events = []
    seen = set()

    # eventItem ブロックを抽出（<a ... class="eventItem"> ... </a>）
    blocks = re.findall(
        r'(<a\s[^>]*class="[^"]*eventItem[^"]*"[^>]*>.*?</a>)',
        html, re.DOTALL
    )
    print(f"  eventItem ブロック数: {len(blocks)}")

    # 日付ヘッダー（<h3 class="eventDate">2026年05月16日（土）</h3>）
    # HTMLを分割してブロックごとに直前の日付を取得
    date_headers = re.findall(r'<h3[^>]*class="eventDate"[^>]*>([^<]+)</h3>', html)

    # ブロック全体を処理
    for block in blocks:
        # URL
        url_m = re.search(r'href="(https://fmfm\.jp/(?:event|regular)/detail/\d+)"', block)
        if not url_m:
            continue
        url = url_m.group(1)
        if url in seen:
            continue
        seen.add(url)

        # イベント名
        name_m = re.search(r'class="eventItem__name"[^>]*>([^<]+)', block)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        if not name:
            continue

        # カレンダー日付（例: "05/16 (土)"）
        cal_m = re.search(r'class="eventItem__calendar"[^>]*>([^<]+)', block)
        date_str = cal_m.group(1).strip() if cal_m else ""

        # YYYY-MM-DD に変換
        date = ""
        dm = re.search(r'(\d{1,2})/(\d{1,2})', date_str)
        if dm:
            jst = timezone(timedelta(hours=9))
            year = datetime.now(jst).year
            date = f"{year}-{dm.group(1).zfill(2)}-{dm.group(2).zfill(2)}"

        # 住所
        addr_m = re.search(r'class="eventItem__address"[^>]*>([^<]+)', block)
        location = addr_m.group(1).strip() if addr_m else "神奈川県"

        # カテゴリ
        cat_m = re.search(r'class="eventItem__category"[^>]*>([^<]+)', block)
        category = cat_m.group(1).strip() if cat_m else ""

        events.append({
            "name":     f"[{category}] {name}" if category else name,
            "date":     date,
            "location": location,
            "url":      url,
            "source":   "fmfm.jp",
        })

    return events

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
    for src_url in SOURCES:
        print(f"Fetching: {src_url}")
        html = fetch(src_url)
        if not html:
            continue
        print(f"  HTMLサイズ: {len(html)} bytes")

        events = parse_fmfm(html)
        print(f"  パース結果: {len(events)} 件")

        for ev in events:
            if ev["url"] in existing_urls:
                continue
            firebase_post("fruition/marcheCandidates", {
                "name":     ev["name"],
                "date":     ev["date"],
                "location": ev["location"],
                "url":      ev["url"],
                "source":   ev["source"],
                "status":   "pending",
                "addedAt":  now,
            })
            existing_urls.add(ev["url"])
            added += 1
            print(f"  ADD: {ev['name']} ({ev['date']}) {ev['location']}")

    print(f"\n完了: {added} 件を追加しました")

if __name__ == "__main__":
    main()
