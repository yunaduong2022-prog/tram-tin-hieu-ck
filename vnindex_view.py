"""Thị trường > Nhận định VNINDEX: biểu đồ nến + khối lượng có chú thích (hộp vùng mua, mũi tên kịch bản) và ba khung
TIN TỨC / DÒNG TIỀN / HÀNH ĐỘNG, bố cục như ảnh nhận định phiên.

Mỗi phiên nhận định là một file Markdown data/vnindex_nhan_dinh/YYYY-MM-DD.md (ngày = phiên được nhận định):

    # VNINDEX · NHẬN ĐỊNH PHIÊN 20/10          <- tiêu đề (bỏ trống thì tự đặt)
    @vung: 1680-1720                           <- hộp trắng: giá thấp - giá cao
    @nhan_vung: VÙNG MUA GOM ~1700đ (MUA > BÁN)
    @duong_di: 0:1689.84, 3:1704, 6:1691, 16:1748   <- mũi tên kịch bản: "số nến sau nến cuối : giá"
    @nhan_duong_di: LAN TỎA
    @chan_trang: TẬP TRUNG CỔ PHIẾU HƠN CHỈ SỐ
    (tùy chọn) @du_lieu_den: 2026-10-19  @so_nen: 75  @vung_tu: 7  @khoang_phai: 36  @nguon: ...

    ## TIN TỨC                                <- mỗi "##" là một khung; tên khung chứa "TIN", "DÒNG TIỀN", "HÀNH ĐỘNG" sẽ có màu riêng
    - Một ý một dòng
      dòng thụt vào = dòng nối tiếp của ý trên
    - [xanh] ý tô xanh   - [do] ý tô đỏ   - [vang] ý tô vàng

Giá lấy từ VNINDEX trong dữ liệu cuối phiên; chỉ lấy các nến TRƯỚC ngày nhận định (hoặc đến @du_lieu_den).
Thêm một phiên mới = thêm một file, không cần sửa code.
"""
from __future__ import annotations

import glob
import hashlib
import html
import inspect
import os
import re
import unicodedata
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import engine as E

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(_HERE, "data", "vnindex_nhan_dinh")
EOD_CSV = os.path.join(_HERE, "data", "eod_prices.csv")
_NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
_META_RE = re.compile(r"^@(\w+)\s*:\s*(.*)$")
_TONE_RE = re.compile(r"^\[(xanh|do|vang)\]\s*", re.I)
OHLC = ["Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa"]

# bảng màu poster (cố định nền xanh đêm như ảnh, không theo giao diện app)
BG, PLOT_BG, GRID = "#080D1C", "#0A1122", "rgba(130,150,200,.13)"
UP, DN = "#2BD6A2", "#F2506E"
ORANGE, GREEN, GOLD, CREAM = "#F5A623", "#2BD98F", "#FFD166", "#F4D58D"
TONE_COL = {"xanh": GREEN, "do": "#FF5C7A", "vang": GOLD}
CARD_COLORS = [ORANGE, GREEN, GOLD, "#6EA8FF", "#C792EA"]           # tin tức, dòng tiền, hành động, rồi xoay vòng
FONT = "'Be Vietnam Pro','Inter','Segoe UI',Arial,sans-serif"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@500;600;700&family=Oswald:wght@500;600&display=swap');
.st-key-vnv-poster{background:#080D1C;border:1px solid #1B2748;border-radius:16px;padding:14px 26px 16px}
.vnv-title{font-family:'Oswald','Be Vietnam Pro',sans-serif;font-weight:500;font-size:44px;letter-spacing:.4px;line-height:1.15;
  color:#F4D58D;text-align:center;margin:4px 0 14px;text-transform:uppercase}
.vnv-card{position:relative;border:2px solid var(--c);border-radius:14px;background:#0F1830;padding:26px 20px 12px;margin:24px 0 26px}
.vnv-tag{position:absolute;top:-19px;left:8px;background:var(--c);color:#14161F;font-family:'Oswald','Be Vietnam Pro',sans-serif;
  font-weight:500;font-size:25px;line-height:1;padding:7px 15px 5px;border-radius:10px;text-transform:uppercase}
.vnv-card ul{list-style:none;margin:0;padding:0}
.vnv-card li{font-family:'Be Vietnam Pro',sans-serif;font-weight:600;font-size:15.5px;line-height:1.55;color:#EAF0FF;margin:0 0 7px}
.vnv-card li .sub{padding-left:15px;color:#EAF0FF}
.vnv-foot{display:flex;justify-content:space-between;align-items:center;gap:16px;border-top:2px solid #F5A623;margin-top:10px;padding-top:12px}
.vnv-foot .l{font-family:'Oswald','Be Vietnam Pro',sans-serif;font-weight:500;font-size:30px;color:#F4D58D;text-transform:uppercase;letter-spacing:.3px}
.vnv-foot .r{font-family:'Be Vietnam Pro',sans-serif;font-size:13px;color:#7F8AA6;text-align:right}
@media (max-width:900px){.vnv-title{font-size:30px}.vnv-foot .l{font-size:22px}}
</style>
"""

TEMPLATE_BODY = """## TIN TỨC
- Ý chính về tin tức
- Ý thứ hai

## DÒNG TIỀN
- Dòng tiền đang đi vào đâu
- Nhóm dẫn dắt

## HÀNH ĐỘNG
- [xanh] CHIỀU MUA : ...
  Đang nắm giữ => ...
- [do] CHIỀU BÁN : ...
- [vang] * VÙNG ... = ...
"""


# ------------------------------------------------------------------ ĐỌC FILE NHẬN ĐỊNH
def _plain(s: str) -> str:
    """Bỏ dấu, chữ thường: dùng để nhận ra tên khung (TIN TỨC, DÒNG TIỀN, HÀNH ĐỘNG)."""
    s = unicodedata.normalize("NFD", s.replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()


def _pairs(s: str) -> list[tuple[int, float]]:
    """'0:1689.84, 3:1704' -> [(0, 1689.84), (3, 1704.0)]. Số thập phân dùng dấu chấm."""
    return [(int(a), float(b)) for a, b in re.findall(r"(-?\d+)\s*:\s*(\d+(?:\.\d+)?)", s or "")]


def _range(s: str) -> tuple[float, float] | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)", s or "")
    if not m:
        return None
    a, b = float(m[1]), float(m[2])
    return (min(a, b), max(a, b))


def _int(s, default: int) -> int:
    try:
        return int(float(str(s).replace(",", ".")))
    except (TypeError, ValueError):
        return default


def parse_text(text: str) -> dict:
    meta: dict[str, str] = {}
    title, sections, cur = "", [], None
    for ln in text.replace("\r\n", "\n").split("\n"):
        s = ln.strip()
        if not s:
            continue
        m = _META_RE.match(s)
        if m:
            meta[m[1].lower()] = m[2].strip()
            continue
        if s.startswith("##"):
            cur = {"name": s.lstrip("#").strip(), "items": []}
            sections.append(cur)
            continue
        if s.startswith("#") and not title:
            title = s.lstrip("#").strip()
            continue
        if cur is None:
            continue
        if ln[:1].isspace() and cur["items"]:                 # dòng thụt vào = nối tiếp ý trên
            cur["items"][-1]["subs"].append(s.lstrip("-•· ").strip())
            continue
        body = s[1:].strip() if s[0] in "-•" else s            # "* VÙNG..." giữ nguyên dấu sao
        tm = _TONE_RE.match(body)
        tone = tm[1].lower() if tm else ""
        cur["items"].append({"text": body[tm.end():] if tm else body, "tone": tone, "subs": []})
    return {"title": title, "meta": meta, "sections": sections}


def _stamp() -> float:
    files = glob.glob(os.path.join(DATA_DIR, "*.md"))
    return max((os.path.getmtime(p) for p in files), default=0.0) + len(files)


@st.cache_data(ttl=300, show_spinner=False)
def load_files(_stamp_: float) -> dict[str, str]:
    """{'YYYY-MM-DD': nội dung}, mới nhất trước."""
    out = {}
    for p in glob.glob(os.path.join(DATA_DIR, "*.md")):
        m = _NAME_RE.match(os.path.basename(p))
        if m:
            try:
                with open(p, encoding="utf-8-sig") as f:
                    out[f"{m[1]}-{m[2]}-{m[3]}"] = f.read()
            except OSError:
                pass
    return dict(sorted(out.items(), reverse=True))


# ------------------------------------------------------------------ DỮ LIỆU GIÁ VNINDEX
@st.cache_data(show_spinner=False)
def _csv_index(path: str, mtime: float) -> pd.DataFrame:
    d = pd.read_csv(path, dtype={"Mã": str})
    return d[d["Mã"].astype(str).str.upper().str.strip().isin(E.INDEX_CODES)]


def index_daily(raw: pd.DataFrame | None) -> pd.DataFrame:
    """Chuỗi VNINDEX theo ngày. Ưu tiên bảng dữ liệu đang chạy của app, không có thì đọc thẳng data/eod_prices.csv."""
    d = pd.DataFrame()
    if raw is not None and not raw.empty:
        m = raw["Mã"].astype(str).str.upper().str.strip().isin(E.INDEX_CODES)
        d = raw[m]
    if d.empty and os.path.exists(EOD_CSV):
        d = _csv_index(EOD_CSV, os.path.getmtime(EOD_CSV))
    if d.empty:
        return d
    d = d.copy()
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", format="mixed", dayfirst=True).dt.normalize()
    for c in OHLC + [E.VOL]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d[E.VOL] = d[E.VOL].fillna(0)
    d = d.dropna(subset=["Ngày"] + OHLC)
    return d[["Ngày"] + OHLC + [E.VOL]].drop_duplicates("Ngày", keep="last").sort_values("Ngày").reset_index(drop=True)


# ------------------------------------------------------------------ HÌNH HỌC BIỂU ĐỒ (hàm thuần, dễ kiểm tra)
def layout_model(d: pd.DataFrame, meta: dict, session: pd.Timestamp) -> dict | None:
    """Cắt dữ liệu và tính vị trí hộp vùng, đường đi, trục. x = số thứ tự nến (bỏ cuối tuần/ngày lễ tự nhiên)."""
    cut = None
    if meta.get("du_lieu_den"):
        v = meta["du_lieu_den"].strip()
        cut = pd.to_datetime(v, errors="coerce", format="mixed", dayfirst=not re.match(r"^\d{4}-", v))      # 2026-10-19 hoặc 19/10/2026
    if cut is not None and pd.notna(cut):
        d = d[d["Ngày"] <= cut]
    else:
        d = d[d["Ngày"] < session]
    if d.empty:
        return None
    n_show = max(20, _int(meta.get("so_nen"), 75))
    d = d.tail(n_show).reset_index(drop=True)
    n = len(d)
    last_x = n - 1
    path = [(last_x + o, p) for o, p in _pairs(meta.get("duong_di", ""))]
    right = max(8, _int(meta.get("khoang_phai"), 36))
    x_max = last_x + right
    if path:
        x_max = max(x_max, max(x for x, _ in path) + 12)         # chừa chỗ cho nhãn cuối mũi tên
    zone = _range(meta.get("vung", ""))
    zone_back = max(1, _int(meta.get("vung_tu"), 7))
    zone_box = None
    if zone:
        zone_box = dict(x0=last_x - zone_back - 0.4, x1=x_max - 0.4, y0=zone[0], y1=zone[1])

    ys = [d["Giá cao nhất"].max(), d["Giá thấp nhất"].min()] + [p for _, p in path] + (list(zone) if zone else [])
    lo, hi = float(min(ys)), float(max(ys))
    span = max(hi - lo, 1.0)
    y_lo, y_hi = lo - 0.17 * span, hi + 0.13 * span         # đáy chừa chỗ cho nhãn vùng, đỉnh chừa chỗ cho tên VNINDEX

    ticks = [(i, f"Tháng {m}") for i, (m, pm) in enumerate(zip(d["Ngày"].dt.month, d["Ngày"].dt.month.shift())) if i > 0 and m != pm]
    return dict(d=d, n=n, last_x=last_x, x_max=x_max, path=path, zone=zone_box, y_range=(y_lo, y_hi), ticks=ticks,
                last_date=d["Ngày"].iloc[-1])


def _plot(fig, key: str):
    params = inspect.signature(st.plotly_chart).parameters
    kw = {"width": "stretch"} if "width" in params else {"use_container_width": True}
    cfg = dict(displaylogo=False, scrollZoom=False, displayModeBar="hover",
               modeBarButtonsToRemove=["zoom2d", "pan2d", "select2d", "lasso2d", "zoomIn2d", "zoomOut2d", "autoScale2d", "resetScale2d"],
               toImageButtonOptions=dict(format="png", filename="vnindex_nhan_dinh", scale=2))
    if "config" in params:
        kw["config"] = cfg
    else:
        kw.update(cfg)
    st.plotly_chart(fig, key=key, **kw)


def _wrap_label(t: str) -> str:
    """'VÙNG MUA GOM ~1700đ (MUA > BÁN)' -> hai dòng, xuống dòng trước dấu ngoặc."""
    t = html.escape(t.strip())
    return t.replace(" (", "<br>(", 1) if "<br>" not in t and " (" in t else t


def build_chart(M: dict, meta: dict):
    d, n = M["d"], M["n"]
    x = np.arange(n)
    up = (d["Giá đóng cửa"] >= d["Giá mở cửa"]).to_numpy()
    hover = [f"{r['Ngày']:%d/%m/%Y}<br>Mở {r['Giá mở cửa']:,.2f} · Cao {r['Giá cao nhất']:,.2f}"
             f"<br>Thấp {r['Giá thấp nhất']:,.2f} · Đóng {r['Giá đóng cửa']:,.2f}<br>KL {r[E.VOL] / 1e6:,.1f} triệu cp"
             for _, r in d.iterrows()]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.80, 0.20], vertical_spacing=0.025)
    fig.add_trace(go.Candlestick(x=x, open=d["Giá mở cửa"], high=d["Giá cao nhất"], low=d["Giá thấp nhất"], close=d["Giá đóng cửa"],
                                 text=hover, hoverinfo="text", showlegend=False, whiskerwidth=0,
                                 increasing=dict(line=dict(color=UP, width=1), fillcolor=UP),
                                 decreasing=dict(line=dict(color=DN, width=1), fillcolor=DN)), row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=d[E.VOL], marker=dict(color=np.where(up, UP, DN), line=dict(width=0)), showlegend=False,
                         hovertext=hover, hoverinfo="text"), row=2, col=1)

    # đường giá đóng cửa gần nhất + nhãn giá bên phải
    last_c = float(d["Giá đóng cửa"].iloc[-1])
    tag_col = UP if up[-1] else DN
    fig.add_trace(go.Scatter(x=[0, M["x_max"]], y=[last_c, last_c], mode="lines", hoverinfo="skip", showlegend=False,
                             line=dict(color=tag_col, width=1, dash="dot")), row=1, col=1)
    fig.add_annotation(xref="paper", yref="y", x=1, y=last_c, xanchor="left", xshift=2, showarrow=False, text=f"<b>{last_c:,.2f}</b>",
                       bgcolor=tag_col, font=dict(size=13, color="#0A1122"), borderpad=3)

    # hộp vùng + nhãn nối bằng đường vàng
    z = M["zone"]
    if z:
        fig.add_shape(type="rect", xref="x", yref="y", x0=z["x0"], x1=z["x1"], y0=z["y0"], y1=z["y1"], layer="below",
                      line=dict(color="#F3F4F6", width=2), fillcolor="rgba(255,236,190,.10)")
        if meta.get("nhan_vung"):
            tip_x = M["last_x"] + 0.4 * (M["x_max"] - M["last_x"])
            fig.add_annotation(xref="x", yref="y", x=tip_x, y=z["y0"], ax=-300, ay=36, axref="pixel", ayref="pixel",
                               showarrow=True, arrowhead=0, arrowwidth=1.6, arrowcolor=ORANGE, align="center",
                               text=f"<b>{_wrap_label(meta['nhan_vung'])}</b>", bgcolor="#101A33", bordercolor=ORANGE, borderwidth=2,
                               borderpad=9, font=dict(size=15, color=ORANGE))

    # mũi tên kịch bản: nét đứt xanh, chấm ở các điểm gãy, đầu mũi tên + nhãn ở cuối
    p = M["path"]
    if len(p) >= 2:
        px, py = [a for a, _ in p], [b for _, b in p]
        fig.add_trace(go.Scatter(x=px, y=py, mode="lines+markers", hoverinfo="skip", showlegend=False,
                                 line=dict(color=GREEN, width=3.2, dash="dash"),
                                 marker=dict(size=[0] + [9] * (len(p) - 2) + [0], color=GREEN, line=dict(color="#0A1122", width=1))),
                      row=1, col=1)
        sx, sy = px[-1] + 0.14 * (px[-2] - px[-1]), py[-1] + 0.14 * (py[-2] - py[-1])
        fig.add_annotation(xref="x", yref="y", axref="x", ayref="y", x=px[-1], y=py[-1], ax=sx, ay=sy, showarrow=True,
                           arrowhead=2, arrowsize=1.5, arrowwidth=3.2, arrowcolor=GREEN, text="")
        if meta.get("nhan_duong_di"):
            fig.add_annotation(xref="x", yref="y", x=px[-1], y=py[-1], xanchor="left", yanchor="middle", xshift=12, showarrow=False,
                               text=f"<b>{html.escape(meta['nhan_duong_di'])}</b>", bgcolor=GREEN, bordercolor=GREEN, borderpad=7,
                               font=dict(size=16, color="#06201A"))

    fig.add_annotation(xref="x domain", yref="y domain", x=0.015, y=0.985, xanchor="left", yanchor="top", showarrow=False,
                       text="<b><i>VNINDEX</i></b>", font=dict(size=58, color=ORANGE, family="Be Vietnam Pro, Arial Black, sans-serif"))

    ax_font = dict(size=13, color="#C9D1E6")
    fig.update_xaxes(range=[-1.5, M["x_max"]], rangeslider_visible=False, showgrid=True, gridcolor=GRID, zeroline=False,
                     showline=True, linecolor="rgba(130,150,200,.25)", tickfont=ax_font)
    if M["ticks"]:
        fig.update_xaxes(tickmode="array", tickvals=[i for i, _ in M["ticks"]], ticktext=[t for _, t in M["ticks"]],
                         ticks="outside", tickcolor="#C9D1E6", row=2, col=1)
    else:
        fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_yaxes(range=list(M["y_range"]), side="right", dtick=50, tickformat="d", showgrid=True, gridcolor=GRID, zeroline=False,
                     showline=True, linecolor="rgba(130,150,200,.25)", tickfont=ax_font, row=1, col=1)
    fig.update_yaxes(range=[0, float(d[E.VOL].max()) * 1.05], showticklabels=False, showgrid=True, gridcolor=GRID, zeroline=False,
                     showline=True, linecolor="rgba(130,150,200,.25)", row=2, col=1)
    fig.update_layout(height=660, margin=dict(l=8, r=78, t=6, b=34), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=PLOT_BG,
                      font=dict(family=FONT), dragmode=False, hovermode="closest", showlegend=False, bargap=0.28,
                      hoverlabel=dict(bgcolor="#14203F", font=dict(color="#EAF0FF", size=12)))
    return fig


# ------------------------------------------------------------------ KHUNG BÊN PHẢI + CHÂN TRANG
def _card_color(name: str, idx: int) -> str:
    p = _plain(name)
    if "tin" in p:
        return CARD_COLORS[0]
    if "dong tien" in p:
        return CARD_COLORS[1]
    if "hanh dong" in p:
        return CARD_COLORS[2]
    return CARD_COLORS[(idx + 3) % len(CARD_COLORS)]


def _item_html(it: dict) -> str:
    txt = html.escape(it["text"])
    glyph = "" if it["text"].lstrip().startswith("*") else "• "
    col = TONE_COL.get(it["tone"])
    main = f'<span style="color:{col}">{glyph}{txt}</span>' if col else f"{glyph}{txt}"
    subs = "".join(f'<div class="sub">{html.escape(s)}</div>' for s in it["subs"])
    return f"<li>{main}{subs}</li>"


def cards_html(sections: list[dict]) -> str:
    out = []
    for i, sec in enumerate(sections):
        items = "".join(_item_html(it) for it in sec["items"])
        out.append(f'<div class="vnv-card" style="--c:{_card_color(sec["name"], i)}"><span class="vnv-tag">{html.escape(sec["name"])}</span>'
                   f"<ul>{items}</ul></div>")
    return "".join(out)


# ------------------------------------------------------------------ TRANG
def _template(session: date, last_close: float | None) -> str:
    head = f"# VNINDEX · NHẬN ĐỊNH PHIÊN {session:%d/%m}\n"
    if last_close:
        c = last_close
        mid = round(c / 10) * 10
        head += (f"@vung: {c * 0.985:.0f}-{c * 1.015:.0f}\n@nhan_vung: VÙNG MUA GOM ~{mid:.0f}đ (MUA > BÁN)\n"
                 f"@duong_di: 0:{c:.2f}, 3:{c * 1.008:.2f}, 6:{c * 0.996:.2f}, 16:{c * 1.03:.2f}\n@nhan_duong_di: LAN TỎA\n")
    return head + "@chan_trang: TẬP TRUNG CỔ PHIẾU HƠN CHỈ SỐ\n\n" + TEMPLATE_BODY


def render(raw: pd.DataFrame | None = None):
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🧭 Nhận định VNINDEX")
    files = load_files(_stamp())
    d_all = index_daily(raw)
    if d_all.empty:
        st.error("Không tìm thấy dữ liệu VNINDEX (mã VNINDEX) trong dữ liệu cuối phiên.")
        return

    NEW = "➕ Soạn phiên mới"
    options = list(files) + [NEW]
    sel = st.selectbox("Phiên nhận định", options, key="vnv_sel", label_visibility="collapsed",
                       format_func=lambda k: k if k == NEW else date.fromisoformat(k).strftime("Nhận định phiên %d/%m/%Y"))
    if sel == NEW:
        nxt = pd.Timestamp(d_all["Ngày"].iloc[-1]) + pd.offsets.BDay(1)
        session = st.date_input("Ngày của phiên được nhận định", value=nxt.date(), key="vnv_new_date", format="DD/MM/YYYY")
        initial = _template(session, float(d_all["Giá đóng cửa"].iloc[-1]))
    else:
        session = date.fromisoformat(sel)
        initial = files[sel]

    poster = st.container()          # vẽ poster sau khi đọc ô soạn thảo bên dưới, nhưng hiển thị phía trên
    with st.expander("✏️ Soạn / chỉnh nội dung (xem trước ngay, bấm tải .md rồi đưa vào data/vnindex_nhan_dinh/)"):
        text = st.text_area("Nội dung", initial, height=380, key=f"vnv_txt_{sel}_{hashlib.md5(initial.encode()).hexdigest()[:8]}",
                            label_visibility="collapsed")
        st.download_button("⬇️ Tải file .md", text.encode("utf-8"), file_name=f"{session:%Y-%m-%d}.md", mime="text/markdown")
        st.caption("Cú pháp ở đầu file `vnindex_view.py`. Các dòng `@...` điều khiển hộp vùng và mũi tên; mục `##` là các khung bên phải.")

    P = parse_text(text)
    M = layout_model(d_all, P["meta"], pd.Timestamp(session))
    with poster:
        if M is None:
            st.warning("Chưa có nến VNINDEX nào trước ngày nhận định này.")
            return
        with st.container(key="vnv-poster"):
            title = P["title"] or f"VNINDEX · NHẬN ĐỊNH PHIÊN {session:%d/%m}"
            st.markdown(f'<div class="vnv-title">{html.escape(title)}</div>', unsafe_allow_html=True)
            c1, c2 = st.columns([2.7, 1], gap="medium")
            with c1:
                _plot(build_chart(M, P["meta"]), "vnv_chart")
            with c2:
                st.markdown(cards_html(P["sections"]), unsafe_allow_html=True)
            nguon = html.escape(P["meta"].get("nguon", "Dữ liệu EOD"))
            st.markdown(f'<div class="vnv-foot"><div class="l">{html.escape(P["meta"].get("chan_trang", ""))}</div>'
                        f'<div class="r">{nguon} · cập nhật {M["last_date"]:%d/%m/%Y}</div></div>', unsafe_allow_html=True)
        st.caption("Rê chuột vào nến để xem giá. Nút máy ảnh ở góc biểu đồ lưu ảnh PNG của biểu đồ. "
                   "Nhận định mang tính tham khảo, không phải khuyến nghị đầu tư.")
