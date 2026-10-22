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

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "goc_nhin_thi_truong")
_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")

CSS = """
<style>
/* ----- danh sách bản tin (cột trái) ----- */
.mv-head{font-weight:800;font-size:16px;color:var(--txt2);margin:0 0 4px}
[class*="st-key-mvc_"]{background:var(--card);border:1px solid var(--line);border-radius:12px;
  padding:10px 14px 11px;margin-bottom:10px;gap:4px!important;transition:border-color .15s,background .15s}
[class*="st-key-mvc_"]:hover{border-color:var(--accent)}
[class*="st-key-mvc_"][class*="__sel"]{border-color:var(--accent);background:var(--card2);box-shadow:0 0 0 1px var(--accent) inset}
[class*="st-key-mvc_"] .stButton>button{width:100%;min-height:0!important;height:auto!important;padding:2px 0!important;
  justify-content:flex-start!important;text-align:left!important;background:transparent!important;border:none!important;
  box-shadow:none!important;white-space:normal!important}
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
.st-key-mv-body{padding:18px 26px 26px}
.st-key-mv-body h2{background:linear-gradient(135deg,var(--hero),#0E5A47 160%);color:var(--cream)!important;
  padding:14px 18px!important;border-radius:10px;font-size:18px!important;margin:0 0 14px!important}
.st-key-mv-body h3{font-size:18px!important;margin:22px 0 8px!important;color:var(--accent)!important}
.st-key-mv-body li,.st-key-mv-body p{font-size:15px;line-height:1.7}
.st-key-mv-body strong{color:var(--txt2)}
</style>
"""


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
    lines = text.replace("\r\n", "\n").split("\n")
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
    return {"date": d, "title": title, "summary": summary, "body": "\n".join(lines[i:]).strip()}


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


def _reset_sel():
    st.session_state["mv_sel"] = None


def _pick(key: str):
    st.session_state["mv_sel"] = key


def render():
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
            with st.container(key="mv-body"):
                if cur["body"]:
                    st.markdown(cur["body"])
                else:
                    st.markdown(f"**Tóm tắt:** {cur['summary']}" if cur["summary"] else "")
                    st.caption("Bản tin ngày này chưa có nội dung chi tiết.")
        st.caption("Nội dung chỉ mang tính tham khảo, không phải khuyến nghị đầu tư.")
