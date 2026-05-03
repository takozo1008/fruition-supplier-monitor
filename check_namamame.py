"""
生豆本舗（namamame.jp）のインフューズド豆在庫チェック
Firebase /fruition/namamameStock に保存
"""
import json, re, urllib.request
from datetime import datetime, timezone, timedelta

FIREBASE_URL = "https://fruition-marche-default-rtdb.firebaseio.com"

FLAVOR_KEYWORDS = {
    'strawberry': ['ストロベリー', '苺', 'イチゴ'],
    'grape':      ['グレープ', 'ぶどう', 'ブドウ'],
    'peach':      ['ピーチ', '桃', 'もも'],
    'lychee':     ['ライチ'],
    'passion':    ['パッション'],
    'banana':     ['バナナ'],
    'melon':      ['メロン'],
}

SEARCH_URL = "https://www.namamame.jp/index.php?main_page=advanced_search_result&search_in_description=1&keyword=%E3%82%A4%E3%83%B3%E3%83%95%E3%83%A5%E3%83%BC%E3%82%BA%E3%83%89"

def fetch(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
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
    """在庫グラム数を抽出: '在庫\t87970 g' or '在庫87970g' などのパターン"""
    m = re.search(r'在庫[^\d]*(\d[\d,]*)\s*g', html)
    if m:
        return int(m.group(1).replace(',', ''))
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

def main():
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst).strftime("%Y-%m-%dT%H:%M:%S+09:00")
    print(f"=== 生豆本舗 在庫チェック ===\nTime: {now}\n")

    search_html = fetch(SEARCH_URL)
    if not search_html:
        print("検索ページ取得失敗")
        return

    # 商品リンク抽出 (/index.php?main_page=product_info&...)
    links = re.findall(r'href="(https://www\.namamame\.jp/index\.php\?main_page=product_info[^"]*)"', search_html)
    links = list(dict.fromkeys(links))  # 重複除去
    print(f"商品リンク数: {len(links)}")

    # 商品タイトル + URLをまとめて取得してフレーバーマッチ
    product_pages = {}
    for link in links[:30]:  # 最大30件
        html = fetch(link)
        if not html:
            continue
        # ページタイトルから商品名取得
        title_m = re.search(r'<title[^>]*>([^<]+)</title>', html)
        title = title_m.group(1) if title_m else ''
        fid = match_flavor(title) or match_flavor(html[:3000])
        if fid and fid not in product_pages:
            stock = parse_stock(html)
            product_pages[fid] = stock
            print(f"  {fid}: {title.strip()} → 在庫 {stock}g")

    # Firebase に保存
    result = {}
    for fid, stock in product_pages.items():
        result[fid] = {"stock": stock, "updatedAt": now}

    if result:
        firebase_put("fruition/namamameStock", result)
        print(f"\n{len(result)}件を保存しました")
    else:
        print("保存データなし")

if __name__ == "__main__":
    main()
