"""Tin tức theo mã: ưu tiên vnstock (Company.news), dự phòng RSS (data/rss_feeds.txt)."""
from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import pandas as pd

RSS_FILE = "data/rss_feeds.txt"
DEFAULT_FEEDS = [  # dùng khi không có data/rss_feeds.txt; một số link lấy từ danh sách bên thứ ba, chưa kiểm tra trực tiếp
    "https://cafef.vn/thi-truong-chung-khoan.rss",
    "https://vietstock.vn/830/chung-khoan/co-phieu.rss",
    "https://vneconomy.vn/chung-khoan.rss",
    "https://cafebiz.vn/rss/chung-khoan.rss",
    "https://vnexpress.net/rss/kinh-doanh.rss",
]
TITLE_KEYS = ("title", "newstitle", "headline", "name")
LINK_KEYS = ("newssourcelink", "sourcelink", "link", "url", "newsurl")
DATE_KEYS = ("publishdate", "publicdate", "date", "time", "publishtime", "createdat", "pubdate")
SRC_KEYS = ("source", "newssource", "publisher")


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s).replace("đ", "d").replace("Đ", "D")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def _pick(cols: dict, keys):
    for k in keys:
        if k in cols:
            return cols[k]
    for k in keys:  # khớp một phần
        for n, c in cols.items():
            if k in n:
                return c
    return None


def _from_frame(df, code: str) -> list[dict]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(x) for x in c) for c in df.columns]
    cols = {_norm(c): c for c in df.columns}
    t, l, d = (_pick(cols, k) for k in (TITLE_KEYS, LINK_KEYS, DATE_KEYS))
    s = next((cols[k] for k in SRC_KEYS if k in cols), None)
    if t is None:
        return []
    out = []
    for _, r in df.iterrows():
        dt = pd.to_datetime(r[d], errors="coerce") if d is not None else pd.NaT
        out.append({"title": str(r[t]), "link": str(r[l]) if l is not None and pd.notna(r[l]) else "",
                    "date": dt if pd.notna(dt) else None, "source": str(r[s]) if s is not None else "vnstock"})
    return [x for x in out if x["title"].strip() and x["title"] != "nan"]


def _vnstock_calls(code: str):
    def v5():
        from vnstock import Reference
        return Reference().company(code).news()

    def kbs():
        from vnstock import Company
        return Company(symbol=code, source="KBS").news()

    def vci():
        from vnstock import Company
        return Company(symbol=code, source="VCI").news()

    def tcbs():
        from vnstock import Company
        return Company(symbol=code, source="TCBS").news()

    def legacy():
        from vnstock import Vnstock
        return Vnstock().stock(symbol=code, source="TCBS").company.news()

    return [v5, kbs, vci, tcbs, legacy]


def _vnstock_news(code: str, errs: list) -> list[dict]:
    for fn in _vnstock_calls(code):
        try:
            items = _from_frame(fn(), code)
            if items:
                return items
        except Exception as e:  # noqa: BLE001
            errs.append(f"{fn.__name__}: {type(e).__name__}")
    return []


def _feeds() -> list[str]:
    if os.path.exists(RSS_FILE):
        lines = [l.strip() for l in open(RSS_FILE, encoding="utf-8") if l.strip() and not l.startswith("#")]
        if lines:
            return lines
    return DEFAULT_FEEDS


def _name_key(name):
    """Rút gọn tên công ty thành cụm dễ khớp trong tiêu đề (bỏ 'Công ty cổ phần', 'CTCP', ...)."""
    if not isinstance(name, str):
        return None
    n = re.sub(r"(?i)^(công ty cổ phần|công ty cp|ctcp|tổng công ty cổ phần|ngân hàng thương mại cổ phần|tập đoàn)\s+", "", name.strip())
    return n if len(n) >= 6 else None


def _rss_news(code: str, errs: list, name=None) -> list[dict]:
    parts = [rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])"]
    nk = _name_key(name)
    if nk:
        parts.append(re.escape(nk))
    pat = re.compile("|".join(parts), re.I if nk else 0)
    out = []
    for url in _feeds():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(urllib.request.urlopen(req, timeout=8).read())
        except Exception as e:  # noqa: BLE001
            errs.append(f"RSS {url.split('/')[2]}: {type(e).__name__}")
            continue
        for it in root.iter("item"):
            title, desc = (it.findtext("title") or "").strip(), (it.findtext("description") or "")
            if not (pat.search(title) or pat.search(desc)):
                continue
            try:
                dt = pd.Timestamp(parsedate_to_datetime(it.findtext("pubDate"))).tz_localize(None)
            except Exception:  # noqa: BLE001
                dt = None
            out.append({"title": title, "link": (it.findtext("link") or "").strip(), "date": dt, "source": url.split("/")[2]})
    return out


CACHE_FILE = "data/news_cache.json"


def _load_cache() -> dict:
    try:
        return json.load(open(CACHE_FILE, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(code: str, items: list[dict]) -> None:
    try:
        c = _load_cache()
        c[code] = {"fetched": pd.Timestamp.now().isoformat(timespec="seconds"),
                   "items": [{**i, "date": i["date"].isoformat() if i["date"] is not None else None} for i in items]}
        os.makedirs("data", exist_ok=True)
        json.dump(c, open(CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass


def fetch_news(code: str, limit: int = 20, name=None) -> tuple[list[dict], list[str], dict]:
    """Trả về (tin, lỗi, meta). meta = {'fetched': thời điểm lấy, 'stale': True nếu là bản lưu cũ}."""
    errs: list[str] = []
    items = _vnstock_news(code, errs) or _rss_news(code, errs, name)
    items.sort(key=lambda x: x["date"] or pd.Timestamp.min, reverse=True)
    items = items[:limit]
    now = pd.Timestamp.now()
    if items:
        _save_cache(code, items)
        return items, errs, {"fetched": now, "stale": False}
    old = _load_cache().get(code)
    if old and old.get("items"):
        its = [{**i, "date": pd.to_datetime(i["date"]) if i.get("date") else None} for i in old["items"]]
        return its, errs, {"fetched": pd.Timestamp(old["fetched"]), "stale": True}
    return [], errs, {"fetched": now, "stale": False}


# ------------------------------------------------------------------ TIN CHUNG + KHỚP THEO DANH MỤC / NHÓM NGÀNH
import html as _html

SECTOR_KEYWORDS = {  # từ khóa (không phân biệt hoa thường) để gắn tin với nhóm ngành; sửa tự do
    "Dầu khí": ["dầu khí", "giá dầu", "xăng dầu", "lọc dầu", "khí đốt", "petrovietnam", "pvn"],
    "Cảng biển": ["cảng biển", "cảng container", "logistics cảng", "cước container", "hàng hải"],
    "Vận tải": ["vận tải", "hàng không", "vận tải biển", "cước vận tải", "vận chuyển"],
    "Cao su": ["cao su", "giá mủ"],
    "Phân bón": ["phân bón", "urê", "ure ", "phân đạm", "phân lân"],
    "Bán lẻ": ["bán lẻ", "chuỗi bán lẻ", "sức mua", "tiêu dùng"],
    "Ngân hàng": ["ngân hàng", "lãi suất", "tín dụng", "nợ xấu", "ngân hàng nhà nước", "nhnn"],
    "Chứng khoán": ["công ty chứng khoán", "ctck", "margin", "thanh khoản thị trường", "vn-index", "vnindex"],
    "Bất động sản": ["bất động sản", "bđs", "nhà ở", "căn hộ", "khu công nghiệp", "đất nền", "chung cư"],
    "Khoáng sản": ["khoáng sản", "đất hiếm", "vonfram", "antimon", "khai khoáng"],
    "Thép": ["thép", "quặng sắt", "phôi thép", "tôn mạ"],
    "Thủy sản": ["thủy sản", "cá tra", "tôm", "xuất khẩu thủy sản"],
    "Dược phẩm": ["dược phẩm", "thuốc", "dược", "y tế"],
}
AMBIGUOUS = {"CEO": re.compile(r"(?i:cổ phiếu|mã|cp)\s+CEO|\(CEO\)|(?:HOSE|HNX|UPCOM)\s*:\s*CEO")}


def _fetch_one(url: str, timeout: int):
    """Tải 1 RSS -> (danh sách bài, lỗi hoặc None)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        root = ET.fromstring(urllib.request.urlopen(req, timeout=timeout).read())
    except Exception as e:  # noqa: BLE001
        return [], f"RSS {url.split('/')[2]}: {type(e).__name__}"
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        desc = re.sub(r"<[^>]+>", " ", _html.unescape(it.findtext("description") or ""))
        desc = re.sub(r"\s+", " ", desc).strip()[:400]
        try:
            dt = pd.Timestamp(parsedate_to_datetime(it.findtext("pubDate"))).tz_localize(None)
        except Exception:  # noqa: BLE001
            dt = None
        items.append({"title": title, "desc": desc, "link": (it.findtext("link") or "").strip(),
                      "date": dt, "source": url.split("/")[2]})
    return items, None


def fetch_feed_items(feeds: tuple[str, ...] | None = None, timeout: int = 8):
    """Tải song song toàn bộ RSS. Trả về (danh sách bài, lỗi, số nguồn tải được, tổng số nguồn)."""
    from concurrent.futures import ThreadPoolExecutor
    feeds = list(feeds) if feeds else _feeds()
    items, errs, ok = [], [], 0
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(feeds)))) as ex:
        for got, err in ex.map(lambda u: _fetch_one(u, timeout), feeds):
            if err:
                errs.append(err)
            else:
                ok += 1
                items += got
    seen, uniq = set(), []
    for x in sorted(items, key=lambda x: x["date"] or pd.Timestamp.min, reverse=True):
        k = x["link"] or x["title"]
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    return uniq, errs, ok, len(feeds)


def codes_regex(codes):
    cs = sorted({c for c in codes if c not in AMBIGUOUS}, key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z0-9])(" + "|".join(map(re.escape, cs)) + r")(?![A-Za-z0-9])") if cs else None


def name_index(fund_map: dict, codes) -> dict[str, str]:
    """Cụm tên công ty rút gọn (chữ thường) -> mã, để khớp tin chỉ nêu tên công ty."""
    out = {}
    for c in codes:
        nm = (fund_map or {}).get(c, {}).get("Tên công ty")
        k = _name_key(_name_key(nm) or nm)  # bỏ tiền tố lồng nhau: "Công ty cổ phần Tập đoàn ..."
        if k:
            out[k.lower()] = c
    return out


def match_codes(item: dict, rx, codes, names: dict | None = None) -> list[str]:
    text = item["title"] + " " + item.get("desc", "")
    hit = set(rx.findall(text)) if rx else set()
    low = text.lower()
    for k, c in (names or {}).items():
        if k in low:
            hit.add(c)
    for c, pat in AMBIGUOUS.items():
        if c in codes and pat.search(text):
            hit.add(c)
    return sorted(hit)


def match_groups(item: dict, matched_codes: list[str], groups: dict[str, list[str]]) -> list[str]:
    text = (item["title"] + " " + item.get("desc", "")).lower()
    out = []
    for g, members in groups.items():
        kws = SECTOR_KEYWORDS.get(g, [g.lower()])
        if any(k in text for k in kws) or any(c in members for c in matched_codes):
            out.append(g)
    return out
