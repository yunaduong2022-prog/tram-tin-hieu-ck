"""Thị trường > Nhận định VNINDEX: biểu đồ nến VNINDEX + khối lượng + đường MA, kèm nhận định tự động bên dưới.

Dữ liệu lấy từ mã VNINDEX trong data/eod_prices.csv (dữ liệu cuối phiên), nên mỗi lần cập nhật dữ liệu (update_eod.bat rồi push)
biểu đồ tự có nến phiên mới nhất, không phải sửa gì thêm. Chọn khung Phiên / Tuần / Tháng / Quý và số nến hiển thị ngay trên trang.
Nhận định tự động (tin tức, dòng tiền, hành động) do vnindex_auto.compose() soạn từ dữ liệu, cùng khung đang chọn.
"""
from __future__ import annotations

import html
import inspect
import os
import time

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import engine as E
import supertrend as SPT
import hull_suite as HUL

_HERE = os.path.dirname(os.path.abspath(__file__))
EOD_CSV = os.path.join(_HERE, "data", "eod_prices.csv")
O, H, L, C = "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa"
V = getattr(E, "VOL", "Khối lượng khớp lệnh")
OHLC = [O, H, L, C]
INDEX_CODES = getattr(E, "INDEX_CODES", {"VNINDEX", "VN-INDEX", "VNI", "VN INDEX", "^VNINDEX"})
TF_LABEL = {"D": "Phiên", "W": "Tuần", "M": "Tháng", "Q": "Quý"}
TF_NOUN = {"D": "phiên", "W": "tuần", "M": "tháng", "Q": "quý"}
MA_SET = {"D": (20, 50, 200), "W": (10, 30, 52), "M": (6, 12, 24), "Q": (4, 8, 12)}      # đường MA theo khung
UP, DN = "#2BD6A2", "#F2506E"
MA_COLORS = ["#F5A623", "#6EA8FF", "#C792EA"]
BAR_CHOICES = {"D": [60, 120, 250, 500], "W": [26, 52, 104, 260], "M": [24, 60, 120], "Q": [20, 40, 80]}      # số nến cho chọn, theo khung
BAR_DEFAULT = {"D": 120, "W": 104, "M": 60, "Q": 40}          # số nến mặc định theo khung
TONE_COL = {"xanh": "#1FA97A", "do": "#D92D4A", "vang": "#C98A00"}
TONE_ICON = {"xanh": "🟢", "do": "🔴", "vang": "🟡"}


# ------------------------------------------------------------------ DỮ LIỆU GIÁ VNINDEX
@st.cache_data(show_spinner=False)
def _csv_index(path: str, mtime: float) -> pd.DataFrame:
    d = pd.read_csv(path, dtype={"Mã": str})
    return d[d["Mã"].astype(str).str.upper().str.strip().isin(INDEX_CODES)]


def index_daily(raw: pd.DataFrame | None) -> pd.DataFrame:
    """Chuỗi VNINDEX theo ngày. Ưu tiên bảng dữ liệu đang chạy của app, không có thì đọc thẳng data/eod_prices.csv."""
    d = pd.DataFrame()
    if raw is not None and not raw.empty:
        m = raw["Mã"].astype(str).str.upper().str.strip().isin(INDEX_CODES)
        d = raw[m]
    if d.empty and os.path.exists(EOD_CSV):
        d = _csv_index(EOD_CSV, os.path.getmtime(EOD_CSV))
    if d.empty:
        return d
    d = d.copy()
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", format="mixed", dayfirst=True).dt.normalize()
    for c in OHLC + [V]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d[V] = d[V].fillna(0)
    d = d.dropna(subset=["Ngày"] + OHLC)
    return d[["Ngày"] + OHLC + [V]].drop_duplicates("Ngày", keep="last").sort_values("Ngày").reset_index(drop=True)


# ------------------------------------------------------------------ CHUẨN BỊ DỮ LIỆU BIỂU ĐỒ (hàm thuần, dễ kiểm tra)
def resample_period(d: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Gộp nến Ngày thành Tuần (T2-T6) / Tháng / Quý. Nến kỳ cuối có thể chưa đủ kỳ (đang hình thành)."""
    if tf == "D":
        return d.reset_index(drop=True)
    key = {"W": d["Ngày"].dt.to_period("W-FRI"), "M": d["Ngày"].dt.to_period("M"), "Q": d["Ngày"].dt.to_period("Q")}[tf]
    g = d.groupby(key)
    return pd.DataFrame({"Ngày": g["Ngày"].last(), O: g[O].first(), H: g[H].max(), L: g[L].min(), C: g[C].last(),
                         V: g[V].sum()}).reset_index(drop=True)


def _label(ts: pd.Timestamp, tf: str) -> str:
    if tf == "D":
        return f"{ts:%d/%m/%Y}"
    if tf == "W":
        return f"Tuần kết thúc {ts:%d/%m/%Y}"
    if tf == "M":
        return f"Tháng {ts.month}/{ts.year}"
    return f"Quý {(ts.month - 1) // 3 + 1}/{ts.year}"


def prep_chart(d: pd.DataFrame, tf: str, n_show: int) -> dict | None:
    """Gộp nến theo khung, tính MA trên TOÀN BỘ lịch sử (để nến đầu cửa sổ vẫn có MA), rồi lấy n_show nến cuối."""
    if d is None or d.empty:
        return None
    g = resample_period(d, tf)
    mas = MA_SET[tf]
    for m in mas:
        g[f"MA{m}"] = g[C].rolling(m).mean()
    g = g.join(SPT.compute(g)).join(HUL.compute(g)).tail(max(10, n_show)).reset_index(drop=True)     # Supertrend tính trên toàn bộ lịch sử
    dates = g["Ngày"]
    if tf in ("D", "W"):       # nhãn tháng ở nến đầu tháng; tháng 1 (và nhãn đầu tiên) kèm năm
        ticks = [(i, f"Th{m}/{y}" if (m == 1 or i == 0) else f"Th{m}") for i, (m, y, pm) in
                 enumerate(zip(dates.dt.month, dates.dt.year, dates.dt.month.shift())) if i == 0 or m != pm]
    else:
        ticks = [(i, str(y)) for i, (y, py) in enumerate(zip(dates.dt.year, dates.dt.year.shift())) if i == 0 or y != py]
    if len(ticks) > 1 and ticks[1][0] - ticks[0][0] < 3:       # nhãn đầu sát nhãn kế tiếp thì bỏ nhãn đầu
        ticks = ticks[1:]
    return dict(g=g, tf=tf, mas=mas, ticks=ticks, labels=[_label(t, tf) for t in dates])


def _plot(fig, key: str):
    params = inspect.signature(st.plotly_chart).parameters
    kw = {"width": "stretch"} if "width" in params else {"use_container_width": True}
    cfg = dict(displaylogo=False, scrollZoom=False, displayModeBar="hover",
               modeBarButtonsToRemove=["select2d", "lasso2d"],
               toImageButtonOptions=dict(format="png", filename="vnindex", scale=2))
    if "config" in params:
        kw["config"] = cfg
    else:
        kw.update(cfg)
    st.plotly_chart(fig, key=key, **kw)


def build_chart(P: dict, supertrend: bool = True, hull: bool = True):
    g, tf = P["g"], P["tf"]
    n = len(g)
    x = P["labels"]
    up = (g[C] >= g[O]).to_numpy()
    hover = [f"<b>{lb}</b><br>Mở {r[O]:,.2f} · Cao {r[H]:,.2f}<br>Thấp {r[L]:,.2f} · Đóng {r[C]:,.2f}"
             f"<br>KL {r[V] / 1e6:,.1f} triệu cp" for lb, (_, r) in zip(x, g.iterrows())]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=x, open=g[O], high=g[H], low=g[L], close=g[C], text=hover, hoverinfo="text",
                                 showlegend=False, whiskerwidth=0,
                                 increasing=dict(line=dict(color=UP, width=1), fillcolor=UP),
                                 decreasing=dict(line=dict(color=DN, width=1), fillcolor=DN)), row=1, col=1)
    for m, col in zip(P["mas"], MA_COLORS):
        s = g[f"MA{m}"]
        if s.notna().any():
            fig.add_trace(go.Scatter(x=x, y=s, mode="lines", name=f"MA{m}", line=dict(color=col, width=1.6),
                                     hovertemplate=f"MA{m}: %{{y:,.2f}}<extra></extra>"), row=1, col=1)
    if hull and "HU_M" in g:
        for _tr in HUL.traces(x, g[["HU_M", "HU_S", "HU_up"]]):
            fig.add_trace(_tr, row=1, col=1)
    if supertrend and "ST_trend" in g:
        for _tr in SPT.traces(x, g[[c for c in g.columns if c.startswith("ST_")]]):
            fig.add_trace(_tr, row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=g[V], marker=dict(color=np.where(up, UP, DN), line=dict(width=0)), showlegend=False,
                         hovertext=hover, hoverinfo="text"), row=2, col=1)

    last_c = float(g[C].iloc[-1])
    tag = UP if up[-1] else DN
    fig.add_shape(type="line", xref="paper", x0=0, x1=1, yref="y", y0=last_c, y1=last_c, line=dict(color=tag, width=1, dash="dot"))
    fig.add_annotation(xref="paper", yref="y", x=1, y=last_c, xanchor="left", xshift=2, showarrow=False, text=f"<b>{last_c:,.2f}</b>",
                       bgcolor=tag, font=dict(size=12, color="#0A1122"), borderpad=3)

    lo, hi = float(g[L].min()), float(g[H].max())
    pad = max(hi - lo, 1.0) * 0.06
    fig.update_xaxes(type="category", rangeslider_visible=False, showgrid=False, showline=True, linecolor="rgba(128,128,128,.35)")
    if P["ticks"]:
        fig.update_xaxes(tickmode="array", tickvals=[x[i] for i, _ in P["ticks"]], ticktext=[t for _, t in P["ticks"]],
                         ticks="outside", row=2, col=1)
    else:
        fig.update_xaxes(showticklabels=False, row=2, col=1)
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_yaxes(range=[lo - pad, hi + pad], side="right", tickformat=",d", showgrid=True, gridcolor="rgba(128,128,128,.18)",
                     zeroline=False, showline=True, linecolor="rgba(128,128,128,.35)", row=1, col=1)
    fig.update_yaxes(range=[0, float(g[V].max()) * 1.08], showticklabels=False, showgrid=False, zeroline=False,
                     showline=True, linecolor="rgba(128,128,128,.35)", row=2, col=1)
    fig.update_layout(height=620, margin=dict(l=8, r=72, t=8, b=34), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      dragmode=False, hovermode="closest", bargap=0.25,
                      legend=dict(orientation="h", x=0.01, y=0.995, xanchor="left", yanchor="top", bgcolor="rgba(0,0,0,0)"),
                      showlegend=True, hoverlabel=dict(bgcolor="#14203F", font=dict(color="#EAF0FF", size=12)))
    return fig


# ------------------------------------------------------------------ SỐ LIỆU PHIÊN MỚI NHẤT
def _stats(d: pd.DataFrame) -> dict:
    last, prev = d.iloc[-1], (d.iloc[-2] if len(d) > 1 else None)
    c = float(last[C])
    out = {"date": pd.Timestamp(last["Ngày"]), "close": c, "chg": None, "pct": None, "vol": float(last[V]), "vol_vs": None,
           "from_hi": None, "ma20": None, "ma50": None}
    if prev is not None and float(prev[C]) > 0:
        out["chg"] = c - float(prev[C])
        out["pct"] = (c / float(prev[C]) - 1) * 100
    v20 = d[V].tail(21).iloc[:-1].mean() if len(d) > 21 else np.nan
    if pd.notna(v20) and v20 > 0:
        out["vol_vs"] = (out["vol"] / v20 - 1) * 100
    hi52 = float(d[H].tail(250).max())
    if hi52 > 0:
        out["from_hi"] = (c / hi52 - 1) * 100
    for m in (20, 50):
        if len(d) >= m:
            out[f"ma{m}"] = float(d[C].tail(m).mean())
    return out


# ------------------------------------------------------------------ NHẬN ĐỊNH TỰ ĐỘNG (bên dưới biểu đồ)
@st.cache_data(ttl=1800, show_spinner=False)
def _feed_items(bucket: int):
    """Tin RSS (làm mới mỗi 30 phút). Lỗi mạng -> danh sách rỗng, trang vẫn chạy."""
    try:
        import news_feed as NF
        items, _errs, ok, total = NF.fetch_feed_items()
        return items, ok, total
    except Exception:  # noqa: BLE001
        return [], 0, 0


@st.cache_data(show_spinner=False)
def _csv_all(path: str, mtime: float) -> pd.DataFrame:
    d = pd.read_csv(path, dtype={"Mã": str})
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", format="mixed", dayfirst=True)
    for c in OHLC + [V]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def _auto_mods():
    """(vnindex_auto, watchlist), hoặc (None, None) nếu repo chưa có vnindex_auto.py: khi đó chỉ ẩn phần nhận định, biểu đồ vẫn chạy."""
    try:
        import vnindex_auto as A
        import watchlist as WL
        return A, WL
    except Exception:  # noqa: BLE001
        return None, None


@st.cache_data(show_spinner="Đang tính dòng tiền theo nhóm ngành...")
def _panel(_raw, data_key: str):
    A, _ = _auto_mods()
    if A is None:
        return None
    src = _raw if _raw is not None else (_csv_all(EOD_CSV, os.path.getmtime(EOD_CSV)) if os.path.exists(EOD_CSV) else None)
    return A.build_panel(src) if src is not None else None


def _entries():
    try:
        import market_view as MV
        return MV.load_entries(MV._stamp()), MV
    except Exception:  # noqa: BLE001
        return [], None


@st.cache_data(show_spinner="Đang tự soạn nhận định...")
def _auto_view(_raw, data_key: str, tf: str, use_news: bool, bucket: int, entries_stamp: float):
    """-> ({"title", "sections", "session"}, thông tin phụ) hoặc (None, lý do). Cache theo dữ liệu + khung + 30 phút."""
    A, WL = _auto_mods()
    if A is None:
        return None, "Chưa có file vnindex_auto.py trong repo nên chưa hiện nhận định tự động (biểu đồ nến vẫn dùng bình thường)."
    d = index_daily(_raw)
    if d.empty:
        return None, "Không có dữ liệu VNINDEX."
    items, ok, total = _feed_items(bucket) if use_news else ([], 0, 0)
    entries, MV = _entries()
    foreign = None
    if MV is not None:
        try:
            foreign = MV._foreign_series(entries)
        except Exception:  # noqa: BLE001
            foreign = None
    res = A.compose(d, _panel(_raw, data_key), WL.GROUPS, tf, items, entries, foreign)
    if res is None:
        return None, f"Chưa đủ lịch sử VNINDEX để tính khung {TF_NOUN[tf]} (cần ít nhất {A.MIN_BARS[tf]} nến)."
    return ({"title": res["title"], "sections": res["sections"], "session": res["session"]},
            dict(feeds=(ok, total), news=use_news, state=A.STATE_TXT[res["view"]["state"]]))


def _item_html(it: dict) -> str:
    txt = html.escape(it["text"])
    glyph = "" if it["text"].lstrip().startswith("*") else (TONE_ICON.get(it["tone"], "•") + " ")
    col = TONE_COL.get(it["tone"])
    main = f'<span style="color:{col};font-weight:600">{glyph}{txt}</span>' if col else f"{glyph}{txt}"
    subs = "".join(f'<div style="padding-left:22px;opacity:.85">{html.escape(s)}</div>' for s in it["subs"])
    return f'<div style="margin:0 0 7px;line-height:1.55;font-size:14.5px">{main}{subs}</div>'


def _sections(sections: list[dict]):
    if not sections:
        return
    for row in range(0, len(sections), 3):
        chunk = sections[row:row + 3]
        for col, sec in zip(st.columns(len(chunk), gap="medium"), chunk):
            with col, st.container(border=True):
                st.markdown(f"**{html.escape(sec['name'])}**")
                st.markdown("".join(_item_html(it) for it in sec["items"]), unsafe_allow_html=True)


# ------------------------------------------------------------------ TRANG
def render(raw: pd.DataFrame | None = None, data_key: str = ""):
    st.title("📈 Nhận định VNINDEX")
    d_all = index_daily(raw)
    if d_all.empty:
        st.error("Không tìm thấy dữ liệu VNINDEX (mã VNINDEX) trong dữ liệu cuối phiên.")
        return
    key = data_key or (str(os.path.getmtime(EOD_CSV)) if os.path.exists(EOD_CSV) else "")

    s = _stats(d_all)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("VN-Index", f"{s['close']:,.2f}",
              None if s["chg"] is None else f"{s['chg']:+,.2f} điểm ({s['pct']:+.2f}%)")
    m2.metric("Khối lượng", f"{s['vol'] / 1e6:,.0f} triệu cp",
              None if s["vol_vs"] is None else f"{s['vol_vs']:+.0f}% so với TB 20 phiên", delta_color="off")
    m3.metric("Cách đỉnh 52 tuần", "–" if s["from_hi"] is None else f"{s['from_hi']:+.1f}%", delta_color="off")
    trend = " · ".join(f"{'trên' if s['close'] >= s[k] else 'dưới'} {k.upper()}" for k in ("ma20", "ma50") if s[k] is not None)
    m4.metric("Vị trí so với MA", trend or "–", f"Phiên {s['date']:%d/%m/%Y}", delta_color="off")

    c1, c2, c3, c4, c5 = st.columns([2.0, 1.3, 0.9, 1.2, 1.2])
    tf = c1.segmented_control("Khung", list(TF_LABEL), default="D", key="vnv_tf", format_func=TF_LABEL.get,
                              label_visibility="collapsed") or "D"
    choices = BAR_CHOICES[tf]
    n_show = c2.selectbox("Số nến hiển thị", choices, index=choices.index(BAR_DEFAULT[tf]), key=f"vnv_n_{tf}",
                          format_func=lambda v: f"{v} nến", label_visibility="collapsed")
    use_news = c3.checkbox("Tin RSS", value=True, key="vnv_news", help="Lấy tin từ các RSS trong data/rss_feeds.txt (làm mới mỗi 30 phút)")

    show_st = c4.checkbox("Supertrend", value=True, key="vnv_st", help=f"Supertrend (ATR {SPT.PERIOD}, hệ số {SPT.MULTIPLIER:g}): xanh = xu hướng tăng, đỏ = xu hướng giảm")
    show_hull = c5.checkbox("Hull Suite", value=True, key="vnv_hull", help=f"Hull Suite (HMA {HUL.LENGTH}): dải xanh = Hull đang hướng lên, đỏ = hướng xuống")
    P = prep_chart(d_all, tf, int(n_show))
    _plot(build_chart(P, show_st, show_hull), f"vnv_chart_{tf}")
    st.caption(f"Dữ liệu cuối phiên đến {s['date']:%d/%m/%Y}; tự có nến mới mỗi khi cập nhật data/eod_prices.csv. "
               f"Đường MA tính theo khung {TF_NOUN[tf]}: " + ", ".join(f"MA{m}" for m in P["mas"]) + ". Rê chuột vào nến để xem giá." + (f" Supertrend (ATR {SPT.PERIOD}, hệ số {SPT.MULTIPLIER:g}) tính theo khung {TF_NOUN[tf]}." if show_st else "") + (f" Hull Suite (HMA {HUL.LENGTH}) cũng tính theo khung {TF_NOUN[tf]}." if show_hull else ""))

    entries, _ = _entries()
    view, info = _auto_view(raw, key, tf, use_news, int(time.time() // 1800), len(entries))
    if view is None:
        st.warning(info)
        return
    st.subheader(view["title"].replace("VNINDEX · ", "").capitalize())
    note = f"🤖 Tự động từ giá VNINDEX, khối lượng, độ rộng, nhóm ngành · trạng thái {TF_NOUN[tf]}: {info['state']}."
    if use_news:
        ok, total = info["feeds"]
        note += f" Tin RSS: {ok}/{total} nguồn tải được." if total else " Tin RSS: không tải được nguồn nào, dùng bản tin gần nhất và bối cảnh kỹ thuật."
    st.caption(note)
    _sections(view["sections"])
    st.caption("Nhận định tự động tính theo luật cố định trên dữ liệu, mang tính tham khảo, không phải khuyến nghị đầu tư.")
