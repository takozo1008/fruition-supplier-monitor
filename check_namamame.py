"""
生豆本舗（namamame.jp）のインフューズド豆在庫チェック
Firebase /fruition/namamameStock に保存
"""
import json, re, html as html_mod, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://fruition-marche-default-rtdb.firebaseio.com"
# GitHub Secret: FIREBASE_DB_SECRET（Firebase Console → プロジェクトの設定 → サービスアカウント → Database secret）
import os as _os
_FB_SECRET = _os.environ.get("FIREBASE_DB_SECRET", "")

# サイト上の商品名と FLAVORS の id を対応付け
FLAVOR_KEYWORDS = {
    'strawberry': ['ストロベリー', '苺', 'イチゴ'],
    'grape':      ['グレープ', 'ぶどう', 'ブドウ'],
    'peach':      ['ピーチ', '桃', 'もも'],
    'lychee':     ['ライチ'],
    'passion':    ['パッションフルーツ', 'パッション'],
    'banana':     ['バナナ'],
    'melon':      ['メロン'],
}

# 検索結果ページ（advanced_search_result が正しい）
SEARCH_URL = (
    "https://www.namamame.jp/index.php"
    "?main_page=advanced_search_result"
    "&search_in_description=1"
    "&keyword=" + urllib.parse.quote("インフューズド")
)

# 商品IDの直接指定（検索より確実）
DIRECT_PRODUCTS = [
    ('2220', 'strawberry'),   # ストロベリー
    ('2218', 'peach'),        # ピーチ
    ('2219', 'lychee'),       # ライチ
    ('1901', 'passion'),      # パッションフルーツ（旧1612から変更）
    ('2134', 'melon'),        # メロン
]

def fetch(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "ja,en;q=0.9",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"  FETCH ERROR {url}: {e}")
        return None

def match_flavor(text):
    for fid, kws in FLAVOR_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                return fid
    return None

def parse_stock(html):
    """
    サイト構造:
      <th>在庫</th>
      <td>87970&nbsp;g</td>
    → HTMLタグを除去してからテキスト検索する
    """
    # HTMLエンティティ解決 → タグ除去 → 空白正規化
    text = html_mod.unescape(html)
    text = text.replace('\xa0', ' ')
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    m = re.search(r'在庫\s*(\d[\d,]*)\s*g', text)
    if m:
        return int(m.group(1).replace(',', ''))
    return None

def firebase_get(path):
    auth_param = f"?auth={_FB_SECRET}" if _FB_SECRET else ""
    url = f"{FIREBASE_URL}/{path}.json{auth_param}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = r.read()
            return json.loads(data) if data and data != b"null" else None
    except Exception as e:
        print(f"  FB GET ERROR: {e}")
        return None

def firebase_put(path, data):
    auth_param = f"?auth={_FB_SECRET}" if _FB_SECRET else ""
    url = f"{FIREBASE_URL}/{path}.json{auth_param}"
    req = urllib.request.Request(
        url,
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

def main():
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    print(f"=== 生豆本舗 在庫チェック ===\nTime: {now}\n")

    # 既存データを先に取得（前回履歴保存のため）
    existing = firebase_get("fruition/namamameStock") or {}

    result = {}
    for pid, fid in DIRECT_PRODUCTS:
        url = (
            "https://www.namamame.jp/index.php"
            f"?main_page=product_amountselling_info&products_id={pid}"
        )
        phtml = fetch(url)
        if not phtml:
            print(f"  pid={pid} ({fid}): SKIP")
            continue

        title_m = re.search(r'<title[^>]*>([^<]+)</title>', phtml)
        title = title_m.group(1).split(':')[0].strip() if title_m else ''
        stock = parse_stock(phtml)
        print(f"  pid={pid}: '{title}' → fid={fid}, 在庫={stock}g")

        if stock is not None:
            old = existing.get(fid, {}) if isinstance(existing, dict) else {}
            entry = {"stock": stock, "updatedAt": now}
            # 在庫量が変わった場合のみ前回履歴を更新
            if old.get("stock") is not None and old.get("stock") != stock:
                entry["prevStock"]     = old["stock"]
                entry["prevUpdatedAt"] = old.get("updatedAt", "")
            else:
                # 変化なしでも前回履歴はそのまま引き継ぐ
                if old.get("prevStock") is not None:
                    entry["prevStock"]     = old["prevStock"]
                    entry["prevUpdatedAt"] = old.get("prevUpdatedAt", "")
            result[fid] = entry

    if result:
        firebase_put("fruition/namamameStock", result)
        print(f"\n✅ {len(result)}件を Firebase に保存しました")
        for fid, v in result.items():
            prev = f"  前回: {v['prevStock']:,}g" if v.get('prevStock') is not None else ""
            print(f"  {fid}: {v['stock']:,}g{prev}")
    else:
        print("⚠️  保存データなし")

if __name__ == "__main__":
    main()
