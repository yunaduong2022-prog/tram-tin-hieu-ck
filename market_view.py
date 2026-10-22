"""Thị trường > Góc nhìn thị trường.

Mỗi ngày một file Markdown trong data/goc_nhin_thi_truong/YYYY-MM-DD.md:

    # Tiêu đề bản tin
    > Một dòng tóm tắt hiển thị ở danh sách bên trái
    (dòng trống)
    Nội dung chi tiết (Markdown) hiển thị ở khung bên phải.
    Dòng "## ..." đầu tiên được tô thành thanh tiêu đề "Tổng kết phiên".

Thêm bản tin mới = thêm một file mới, không cần sửa code.
"""
from __future__ import annotations

import glob
import html
import os
import re
from datetime import date, datetime

import streamlit as st

import market_stats as MS

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "goc_nhin_thi_truong")
_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
_META_RE = re.compile(r"^@(\w+)\s*:\s*(.*)$")        # dòng khai báo số liệu nhập tay, ví dụ: @khoi_ngoai: 340
EOD_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "eod_prices.csv")
FF_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "foreign_flow.csv")

CSS = """
<style>
/* ----- danh sách bản tin (cột trái) ----- */
.mv-head{font-weight:800;font-size:16px;color:var(--txt2);margin:0 0 4px}
[class*="st-key-mvc_"]{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:10px 14px 14px;margin-bottom:10px;gap:4px!important;transition:border-color .15s,background .15s}
[class*="st-key-mvc_"]:hover{border-color:var(--accent)}
[class*="st-key-mvc_"][class*="__sel"]{border-color:var(--accent);background:var(--card2);box-shadow:0 0 0 1px var(--accent) inset}
[class*="st-key-mvc_"] .stButton>button{width:100%;min-height:0!important;height:auto!important;padding:2px 0!important;
  justify-content:flex-start!important;text-align:left!important;background:transparent!important;border:none!important;
  box-shadow:none!important;white-space:normal!important}
[class*="st-key-mvc_"] [data-testid="stMarkdownContainer"]{margin:0!important}
[class*="st-key-mvc_"] [data-testid="stMarkdownContainer"] p{margin:0!important}
[class*="st-key-mvc_"] .stButton>button>div,[class*="st-key-mvc_"] .stButton>button [data-testid="stMarkdownContainer"]{
  width:100%!important;justify-content:flex-start!important;text-align:left!important}
[class*="st-key-mvc_"] .stButton>button p{text-align:left!important;font-weight:700!important;font-size:14px!important;
  line-height:1.4!important;color:var(--txt2)!important}
[class*="st-key-mvc_"] .stButton>button:hover p{color:var(--accent)!important}
.mv-date{font-size:12px;color:var(--muted)}
.mv-sum{font-size:12.5px;line-height:1.5;color:var(--muted)}

/* ----- chi tiết (cột phải) ----- */
.st-key-mv-detail{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.mv-dhead{padding:18px 26px 16px;border-bottom:1px solid var(--line);background:var(--bg2)}
.mv-dhead .mv-date{font-size:13px;margin-bottom:6px}
.mv-dhead h1{margin:0!important;padding:0!important;font-size:26px!important;line-height:1.3;color:var(--txt2)!important}
.mv-panel{margin:18px 26px 0;border:1px solid var(--line);border-radius:14px;background:var(--bg2);overflow:hidden}
.mv-ph{padding:12px 20px;font-weight:800;font-size:15px;color:var(--txt2);border-bottom:1px solid var(--line)}
.mv-stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1px;background:var(--line)}
.mv-tile{background:var(--bg2);padding:14px 20px}
.mv-tl{font-size:13px;color:var(--muted);margin-bottom:2px}
.mv-tv{font-size:27px;font-weight:800;color:var(--txt2);line-height:1.3}
.mv-ts{font-size:13.5px;color:var(--muted);line-height:1.6}
.mv-up{color:var(--green)!important}.mv-dn{color:var(--red)!important}
.mv-tile code{font-size:12px}
.mv-checks{padding:14px 20px;border-top:1px solid var(--line);font-size:15px;line-height:2;color:var(--txt);columns:2 300px}
.mv-note{padding:0 20px 14px;font-size:12px;color:var(--muted)}
.st-key-mv-body{padding:18px 26px 26px}
.st-key-mv-body h2{background:linear-gradient(135deg,var(--hero),#0E5A47 160%);color:var(--cream)!important;
  padding:14px 18px!important;border-radius:10px;font-size:18px!important;margin:0 0 14px!important}
.st-key-mv-body h3{font-size:18px!important;margin:22px 0 8px!important;color:var(--accent)!important}
.st-key-mv-body li,.st-key-mv-body p{font-size:15px;line-height:1.7}
.st-key-mv-body strong{color:var(--txt2)}
</style>
"""


def _num(x) -> float | None:
    """'340', '-120', '+340', '1250,5' -> số; không đọc được -> None (không dùng dấu chấm ngăn cách nghìn)."""
    if not x:
        return None
    try:
        return float(x.replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _parse(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8-sig") as f:
            return _parse_text(os.path.basename(path), f.read())
    except OSError:
        return None


def _parse_text(name: str, text: str) -> dict | None:
    m = _NAME_RE.match(name if name.endswith(".md") else name + ".md")
    if not m:
        return None
    try:
        d = date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
    meta, lines = {}, []
    for ln in text.replace("\r\n", "\n").split("\n"):
        mm = _META_RE.match(ln.strip())
        if mm:
            meta[mm[1].lower()] = mm[2].strip()
        else:
            lines.append(ln)
    title, summary, i = d.strftime("%d/%m/%Y"), "", 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip():
        title = lines[i].lstrip("#").strip() or title
        i += 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].startswith(">"):
        summary = lines[i].lstrip("> ").strip()
        i += 1
    return {"date": d, "title": title, "summary": summary, "body": "\n".join(lines[i:]).strip(),
            "foreign": _num(meta.get("khoi_ngoai"))}


@st.cache_data(ttl=300, show_spinner=False)
def load_entries(_stamp: float) -> list[dict]:
    """Đọc toàn bộ bản tin, mới nhất trước. _stamp = thời điểm sửa thư mục, để cache tự làm mới khi có file mới."""
    out = [e for e in (_parse(p) for p in glob.glob(os.path.join(DATA_DIR, "*.md"))) if e]
    if not out:  # chưa có thư mục dữ liệu -> dùng bản tin mẫu nhúng sẵn để trang vẫn hoạt động
        from market_view_seed import SEED
        out = [e for e in (_parse_text(k, v) for k, v in SEED.items()) if e]
    return sorted(out, key=lambda e: e["date"], reverse=True)


def _stamp() -> float:
    files = glob.glob(os.path.join(DATA_DIR, "*.md"))
    return max((os.path.getmtime(p) for p in files), default=0.0) + len(files)


@st.cache_data(show_spinner=False)
def _load_eod(mtime: float):
    """Tự đọc data/eod_prices.csv (chỉ các cột cần) khi app không truyền dữ liệu sang."""
    import pandas as pd
    df = pd.read_csv(EOD_CSV, dtype={"Mã": str}, usecols=["Mã", "Ngày", "Giá đóng cửa", "Khối lượng khớp lệnh"])
    df["Ngày"] = pd.to_datetime(df["Ngày"], format="mixed", dayfirst=True, errors="coerce")
    for c in ("Giá đóng cửa", "Khối lượng khớp lệnh"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["Mã", "Ngày", "Giá đóng cửa"])


@st.cache_data(show_spinner=False)
def _daily(_raw, key: str):
    return MS.daily_table(_raw)


def _n(x, dec=0) -> str:
    """Số kiểu Việt Nam: 1.738,67"""
    return f"{x:,.{dec}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _sg(x, dec=2, suffix="") -> str:
    return ("+" if x > 0 else "") + _n(x, dec) + suffix


def _cls(x) -> str:
    return "mv-up" if x and x > 0 else "mv-dn" if x and x < 0 else ""


@st.cache_data(show_spinner=False)
def _ff_csv(mtime: float):
    return MS.foreign_from_csv(FF_CSV)


def _foreign_series(entries: list[dict]):
    """Khối ngoại theo ngày: cộng từ foreign_flow.csv (nếu có), số ghi trong bản tin (@khoi_ngoai) được ưu tiên."""
    import pandas as pd
    try:
        s = _ff_csv(os.path.getmtime(FF_CSV) if os.path.exists(FF_CSV) else 0.0).copy()
    except Exception:  # noqa: BLE001
        s = pd.Series(dtype=float)
    for e in entries:
        if e.get("foreign") is not None:
            s.loc[pd.Timestamp(e["date"])] = e["foreign"]
    return s.sort_index()


def _stats_html(st_: dict | None, fx: dict | None = None, day=None) -> str:
    """Khối số liệu (thẻ số + danh sách kiểm tra) cho một ngày. st_: số tự tính từ giá; fx: khối ngoại."""
    st_ = st_ or {}
    tiles, checks = [], []
    if "index" in st_:
        sub = ""
        if "index_pts" in st_:
            sub = f'<span class="{_cls(st_["index_pts"])}">{_sg(st_["index_pts"])} điểm ({_sg(st_["index_pct"], 2, "%")})</span>'
        tiles.append(f'<div class="mv-tile"><div class="mv-tl">VN-Index</div><div class="mv-tv">{_n(st_["index"], 2)}</div>'
                     f'<div class="mv-ts">{sub}</div></div>')
        if "ma20" in st_:
            above = st_["index"] >= st_["ma20"]
            tiles.append(f'<div class="mv-tile"><div class="mv-tl">MA20</div><div class="mv-tv">{_n(st_["ma20"], 2)}</div>'
                         f'<div class="mv-ts">VN-Index đang <b class="{"mv-up" if above else "mv-dn"}">{"trên" if above else "dưới"}</b> MA20 '
                         f'({_sg(st_["index"] - st_["ma20"], 1)} điểm)</div></div>')
            checks.append((above, "VN-Index đóng cửa trên MA20"))
            if "ma20_5ago" in st_:
                checks.append((st_["ma20"] > st_["ma20_5ago"], "MA20 dốc lên so với 5 phiên trước"))
        if "hi20" in st_:
            tiles.append(f'<div class="mv-tile"><div class="mv-tl">Biên độ 20 phiên (giá đóng cửa)</div>'
                         f'<div class="mv-tv">{_n(st_["lo20"], 0)} – {_n(st_["hi20"], 0)}</div>'
                         f'<div class="mv-ts">Cách đáy 20 phiên {_sg(st_["from_lo20_pct"], 1, "%")}</div></div>')
    if "value" in st_:
        sub = []
        if st_.get("value_prev_pct") is not None:
            sub.append(f'<span class="{_cls(st_["value_prev_pct"])}">{_sg(st_["value_prev_pct"], 1, "%")}</span> so với phiên trước')
        if st_.get("value_avg20_pct") is not None:
            sub.append(f'<span class="{_cls(st_["value_avg20_pct"])}">{_sg(st_["value_avg20_pct"], 1, "%")}</span> so với TB 20 phiên')
        if st_.get("value_highest_n"):
            sub.append(f'cao nhất {st_["value_highest_n"]} phiên')
        tiles.append(f'<div class="mv-tile"><div class="mv-tl">Thanh khoản (rổ theo dõi)</div>'
                     f'<div class="mv-tv">{_n(st_["value"], 0)} tỷ</div><div class="mv-ts">{"<br>".join(sub)}</div></div>')
        if st_.get("value_avg20_pct") is not None:
            checks.append((st_["value_avg20_pct"] > 0, "Thanh khoản cao hơn trung bình 20 phiên"))
        tiles.append(f'<div class="mv-tile"><div class="mv-tl">Độ rộng (rổ {st_["n"]} mã)</div>'
                     f'<div class="mv-tv"><span class="mv-up">{st_["up"]}</span> / <span class="mv-dn">{st_["down"]}</span></div>'
                     f'<div class="mv-ts">mã tăng / giảm · {st_["flat"]} đứng giá</div></div>')
        checks.append((st_["up"] > st_["down"], "Số mã tăng nhiều hơn số mã giảm"))
    if fx:
        v = fx["value"]
        lab = "Mua ròng" if v > 0 else "Bán ròng" if v < 0 else "Cân bằng"
        cum = (f'<br>5 phiên gần nhất: <span class="{_cls(fx["cum5"])}">{_sg(fx["cum5"], 0, " tỷ")}</span>' if "cum5" in fx else "")
        tiles.append(f'<div class="mv-tile"><div class="mv-tl">Khối ngoại</div>'
                     f'<div class="mv-tv {_cls(v)}">{_sg(v, 0, " tỷ")}</div><div class="mv-ts">{lab} toàn thị trường{cum}</div></div>')
        checks.append((v > 0, "Khối ngoại mua ròng"))
    else:
        tiles.append('<div class="mv-tile"><div class="mv-tl">Khối ngoại</div><div class="mv-tv">Chưa có</div>'
                     '<div class="mv-ts">Thêm dòng <code>@khoi_ngoai: 340</code> vào file bản tin (tỷ đồng, âm = bán ròng)</div></div>')
    if not tiles:
        return '<div class="mv-note">Chưa có dữ liệu giá của ngày này trong data/eod_prices.csv nên chưa tự tính được số liệu.</div>'
    chk = "<br>".join(f'<span class="{"mv-up" if ok else "mv-dn"}">{"✓" if ok else "✗"}</span> {txt}' for ok, txt in checks)
    note = ("Số liệu giá tự tính từ dữ liệu cuối phiên. Thanh khoản và độ rộng chỉ tính trên rổ mã theo dõi của app, "
            "không phải toàn thị trường nên không dùng để so với con số của sàn."
            + ("" if "index" in st_ else " Chưa có VNINDEX hoặc chưa có giá ngày này nên chưa hiện số VN-Index."))
    head = f'Số liệu phiên {day:%d/%m/%Y}' if day is not None else 'Số liệu phiên'
    return (f'<div class="mv-panel"><div class="mv-ph">{head}</div><div class="mv-stats">{"".join(tiles)}</div>'
            f'<div class="mv-checks">{chk}</div><div class="mv-note">{note}</div></div>')


def _reset_sel():
    st.session_state["mv_sel"] = None


def _pick(key: str):
    st.session_state["mv_sel"] = key


def render(raw=None, data_key: str = ""):
    st.markdown(CSS, unsafe_allow_html=True)
    entries = load_entries(_stamp())
    st.title("🧭 Góc nhìn thị trường")
    today = date.today()
    years = sorted({e["date"].year for e in entries} | {today.year}, reverse=True)
    latest = entries[0]["date"] if entries else today
    st.session_state.setdefault("mv_month", latest.month)
    st.session_state.setdefault("mv_year", latest.year)
    if st.session_state["mv_year"] not in years:
        st.session_state["mv_year"] = years[0]

    left, right = st.columns([1, 2.3], gap="medium")

    with left:
        st.markdown('<div class="mv-head">Bản tin theo ngày</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        month = c1.selectbox("Tháng", list(range(1, 13)), key="mv_month", format_func=lambda m: f"Tháng {m}",
                             label_visibility="collapsed", on_change=_reset_sel)
        year = c2.selectbox("Năm", years, key="mv_year", label_visibility="collapsed", on_change=_reset_sel)
        shown = [e for e in entries if e["date"].month == month and e["date"].year == year]

        keys = [e["date"].isoformat() for e in shown]
        if st.session_state.get("mv_sel") not in keys:
            st.session_state["mv_sel"] = keys[0] if keys else None
        sel = st.session_state["mv_sel"]

        if not shown:
            st.caption(f"Chưa có bản tin nào trong tháng {month}/{year}. "
                       f"Thêm file `YYYY-MM-DD.md` vào `data/goc_nhin_thi_truong/`.")
        with st.container(height=720, border=False, key="mv-list"):
            for e, k in zip(shown, keys):
                with st.container(key=f"mvc_{k}{'__sel' if k == sel else ''}"):
                    st.markdown(f'<div class="mv-date">{e["date"]:%d/%m/%Y}</div>', unsafe_allow_html=True)
                    st.button(e["title"], key=f"mvb_{k}", on_click=_pick, args=(k,), use_container_width=True)
                    if e["summary"]:
                        st.markdown(f'<div class="mv-sum">{html.escape(e["summary"])}</div>', unsafe_allow_html=True)

    with right:
        cur = next((e for e in shown if e["date"].isoformat() == sel), None)
        if cur is None:
            st.info("Chọn một ngày ở danh sách bên trái để xem chi tiết.")
            return
        with st.container(key="mv-detail"):
            st.markdown(f'<div class="mv-dhead"><div class="mv-date">{cur["date"]:%d/%m/%Y}</div>'
                        f'<h1>{html.escape(cur["title"])}</h1></div>', unsafe_allow_html=True)
            try:
                src, key = raw, data_key
                if src is None and os.path.exists(EOD_CSV):
                    key = str(os.path.getmtime(EOD_CSV))
                    src = _load_eod(os.path.getmtime(EOD_CSV))
                px = MS.stats_for(_daily(src, key), cur["date"]) if src is not None else None
                fx = MS.foreign_stats(_foreign_series(entries), cur["date"])
                st.markdown(_stats_html(px, fx, cur["date"]), unsafe_allow_html=True)
            except Exception as e:  # noqa: BLE001  số liệu tự động lỗi thì không làm hỏng cả trang
                st.caption(f"Không tính được số liệu tự động: {type(e).__name__}")
            with st.container(key="mv-body"):
                if cur["body"]:
                    st.markdown(cur["body"])
                else:
                    st.markdown(f"**Tóm tắt:** {cur['summary']}" if cur["summary"] else "")
                    st.caption("Bản tin ngày này chưa có nội dung chi tiết.")
        st.caption("Nội dung chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.")
