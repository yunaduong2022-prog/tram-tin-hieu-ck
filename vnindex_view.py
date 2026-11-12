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
import theme as TH
import supertrend as SPT
import hull_suite as HUL
import ichimoku_dual as IDU
import crosshair as CH
import vnindex_draw_tools as VDT  # MIN_VNINDEX_DRAW_TOOLBAR_V1
from vnindex_chart_range import RANGE_OPTIONS, chart_range_view
from vnindex_chart_right_pad import right_axis_range

_HERE = os.path.dirname(os.path.abspath(__file__))
EOD_CSV = os.path.join(_HERE, "data", "eod_prices.csv")
INDEX_CSV = os.path.join(_HERE, "data", "index_prices.csv")
O, H, L, C = "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa"
V = getattr(E, "VOL", "Khối lượng khớp lệnh")
OHLC = [O, H, L, C]
INDEX_CODES = getattr(E, "INDEX_CODES", {"VNINDEX", "VN-INDEX", "VNI", "VN INDEX", "^VNINDEX"})
TF_LABEL = {"D": "Phiên", "W": "Tuần", "M": "Tháng", "Q": "Quý"}
TF_NOUN = {"D": "phiên", "W": "tuần", "M": "tháng", "Q": "quý"}
MA_SET = {"D": (20, 50, 200), "W": (10, 30, 52), "M": (6, 12, 24), "Q": (4, 8, 12)}      # đường MA theo khung
UP, DN = "#089981", "#F23645"
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
    """Latest real VNINDEX session, never silently truncated by an old index CSV.

    Prefer index_prices on overlapping dates; include newer raw/EOD sessions.
    Original date-validated candles only; no fabrication or interpolation.
    """
    from vnindex_freshness_guard import merge_index_candidates

    # Candidate order is low -> high priority on the same trading session.
    sources = []
    raw_has_index = False
    if raw is not None and not raw.empty and "Mã" in raw.columns:
        raw_has_index = bool(raw["Mã"].astype(str).str.upper().str.strip().isin(INDEX_CODES).any())
    if not raw_has_index and os.path.exists(EOD_CSV):
        try:
            sources.append(("eod_prices.csv", _csv_index(EOD_CSV, os.path.getmtime(EOD_CSV))))
        except (OSError, ValueError, KeyError, pd.errors.ParserError):
            pass
    if raw is not None and not raw.empty:
        sources.append(("raw EOD", raw))
    if os.path.exists(INDEX_CSV):
        try:
            sources.append(("index_prices.csv", _csv_index(INDEX_CSV, os.path.getmtime(INDEX_CSV))))
        except (OSError, ValueError, KeyError, pd.errors.ParserError):
            pass
    return merge_index_candidates(sources, INDEX_CODES, OHLC, V)


# ------------------------------------------------------------------ CHUAN BI DU LIEU BIEU DO (ham thuan, de kiem tra)
def resample_period(d: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Gộp nến Ngày thành Tuần (T2-T6) / Tháng / Quý. Nến kỳ cuối có thể chưa đủ kỳ (đang hình thành)."""
    if tf == "D":
        return d.reset_index(drop=True)
    key = {"W": d["Ngày"].dt.to_period("W-FRI"), "M": d["Ngày"].dt.to_period("M"), "Q": d["Ngày"].dt.to_period("Q")}[tf]
    g = d.groupby(key)
    return pd.DataFrame({"Ngày": g["Ngày"].last(), O: g[O].first(), H: g[H].max(), L: g[L].min(), C: g[C].last(),
                         V: g[V].sum()}).reset_index(drop=True)


_WD = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
DATE_GAP_PX = 34       # khe (px) giữa biểu đồ nến và khung khối lượng: chứa dải nhãn tháng + nhãn ngày của đường gióng


def _cross_label(ts: pd.Timestamp, tf: str) -> str:
    """Nhãn ngày hiện trên đường gióng: 'T4, 16/09/2026' (khung Tuần: ngày cuối tuần; Tháng / Quý: tên kỳ)."""
    if tf in ("D", "W"):
        d = f"{_WD[ts.weekday()]}, {ts:%d/%m/%Y}"
        return d if tf == "D" else f"Tuần kết thúc {d}"
    return _label(ts, tf)


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
    # MIN_FINANCE_LIGHT_V2_1_VNINDEX: bypass Streamlit's dark Plotly skin in light mode.
    # The app's config.toml intentionally stays dark by default; Plotly must use
    # the chart's own plotly_white template when the user chooses Sáng.
    if not TH.is_dark() and "theme" in params:
        kw["theme"] = None
    st.plotly_chart(fig, key=key, **kw)


def build_chart(P: dict, supertrend: bool = True, hull: bool = True):
    g, tf = P["g"], P["tf"]
    n = len(g)
    x = P["labels"]
    up = (g[C] >= g[O]).to_numpy()
    cross = [_cross_label(pd.Timestamp(t), tf) for t in g["Ngày"]]          # "T6, 24/10/2026"
    hover = [f"<b>{lb}</b><br>Mở {r[O]:,.2f} · Cao {r[H]:,.2f}<br>Thấp {r[L]:,.2f} · Đóng {r[C]:,.2f}"
             f"<br>KL {r[V] / 1e6:,.1f} triệu cp" for lb, (_, r) in zip(cross, g.iterrows())]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.78, 0.22], vertical_spacing=DATE_GAP_PX / 620)
    fig.add_trace(go.Candlestick(x=x, name="VNINDEX", customdata=[pd.Timestamp(t).strftime("%Y-%m-%d") for t in g["Ngày"]], open=g[O], high=g[H], low=g[L], close=g[C], text=hover, hoverinfo="text",
                                 showlegend=False, whiskerwidth=0, meta=cross,
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
        _stv = g[[c for c in g.columns if c.startswith("ST_")]]
        for _tr in SPT.traces(x, _stv):
            fig.add_trace(_tr, row=1, col=1)
        # Supertrend formats annotation dates via pd.Timestamp; chart x is a text category.
        # First use actual bar dates, then return the annotation to the exact x-axis label.
        for _an in SPT.annotations(list(g["Ngày"]), _stv):
            _an["x"] = _label(pd.Timestamp(_an["x"]), tf)
            fig.add_annotation(**_an, row=1, col=1)
    fig.add_trace(go.Bar(x=x, y=g[V], marker=dict(color=np.where(up, "rgba(8,153,129,.5)", "rgba(242,54,69,.5)"), line=dict(width=0)), showlegend=False,
                         hovertext=hover, hoverinfo="text"), row=2, col=1)

    last_c = float(g[C].iloc[-1])
    tag = UP if up[-1] else DN
    fig.add_shape(type="line", xref="paper", x0=0, x1=1, yref="y", y0=last_c, y1=last_c, line=dict(color=tag, width=1, dash="dot"))
    fig.add_annotation(xref="paper", yref="y", x=1, y=last_c, xanchor="left", xshift=2, showarrow=False, text=f"<b>{last_c:,.2f}</b>",
                       bgcolor=tag, font=dict(size=12, color="#0A1122"), borderpad=3)

    lo, hi = float(g[L].min()), float(g[H].max())
    pad = max(hi - lo, 1.0) * 0.06
    # Two panes share the same candle positions; ONLY the volume pane shows time.
    # Space at the right is inside the plot, not between VNINDEX and DÒNG TIỀN.
    visible_x_range = right_axis_range(n, tf)
    fig.update_xaxes(type="category", range=visible_x_range, rangeslider_visible=False,
                     showgrid=False, showline=True, linecolor="rgba(128,128,128,.35)",
                     showticklabels=False, row=1, col=1)
    fig.update_xaxes(type="category", range=visible_x_range, rangeslider_visible=False,
                     showgrid=False, showline=True, linecolor="rgba(128,128,128,.35)",
                     showticklabels=bool(P["ticks"]), row=2, col=1)
    if P["ticks"]:
        # A single month/year time row BELOW volume; keep hover/crosshair intact.
        fig.update_xaxes(tickmode="array", tickvals=[x[i] for i, _ in P["ticks"]],
                         ticktext=[t for _, t in P["ticks"]], ticks="outside",
                         ticklen=4, tickangle=0, tickfont=dict(size=11),
                         showticklabels=True, row=2, col=1)
    fig.update_yaxes(range=[lo - pad, hi + pad], side="right", tickformat=",d", showgrid=True, gridcolor="rgba(128,128,128,.18)",
                     zeroline=False, showline=True, linecolor="rgba(128,128,128,.35)", row=1, col=1)
    fig.update_yaxes(range=[0, float(g[V].max()) * 1.08], showticklabels=False, showgrid=False, zeroline=False,
                     showline=True, linecolor="rgba(128,128,128,.35)", row=2, col=1)
    fig.update_layout(height=620, margin=dict(l=8, r=72, t=8, b=34), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      dragmode=False, hovermode="closest", bargap=0.25,
                      legend=dict(orientation="h", x=0.01, y=0.995, xanchor="left", yanchor="top", bgcolor="rgba(0,0,0,0)"),
                      showlegend=True, hoverlabel=dict(bgcolor="#14203F", font=dict(color="#EAF0FF", size=12)))
    return fig


# MIN_VNINDEX_DUAL_ICHI_V1: reuse stock dual-Ichimoku formula on VNINDEX categorical chart.
def _vnindex_dual_ichimoku(fig, full, visible, tf, labels):
    """Draw Ichimoku 1 projected Kumo + Ichimoku 2 Tenkan/Kijun.

    Compute with the FULL resampled index history, never just the visible window.
    Keep bar labels/crosshair/volume on the original categorical X axis.
    """
    if full.empty or visible.empty:
        return fig
    last_date = pd.Timestamp(full["Ngày"].iat[-1])

    def future_date(k):
        if tf == "D":
            return last_date + pd.offsets.BDay(k)
        if tf == "W":
            return last_date + pd.Timedelta(weeks=k)
        if tf == "M":
            return last_date.to_period("M").end_time.normalize() + pd.offsets.MonthEnd(k)
        return last_date.to_period("Q").end_time.normalize() + pd.offsets.QuarterEnd(k)

    n = len(visible)
    indicator = IDU.compute(full, n, future_date)
    ext_x = list(labels) + [
        _label(pd.Timestamp(date), tf) for date in indicator["x"][n:]
    ]
    a = np.asarray(indicator["a"], dtype=float)
    b = np.asarray(indicator["b"], dtype=float)
    if len(ext_x) != len(a) or len(a) != len(b):
        raise ValueError("VNINDEX_ICHIMOKU_AXIS_MISMATCH")

    original_count = len(fig.data)
    cloud_positions = []
    line_positions = []
    good = np.isfinite(a) & np.isfinite(b)
    rising = good & (a >= b)
    falling = good & (a < b)
    high, low = np.maximum(a, b), np.minimum(a, b)

    # Categorical axis: plot the cloud using existing candle labels, plus 25
    # future category labels; never invent OHLCV candles or volume.
    for mask, color, name in (
        (rising, IDU.COL["up"], "Ichimoku 1 · Kumo tăng"),
        (falling, IDU.COL["down"], "Ichimoku 1 · Kumo giảm"),
    ):
        px, py = IDU._polygons(
            ext_x, np.where(mask, high, np.nan),
            np.where(mask, low, np.nan)
        )
        if px:
            fig.add_trace(go.Scatter(
                x=px, y=py, mode="lines", fill="toself",
                fillcolor=color, line=dict(width=0),
                name=name, hoverinfo="skip", legendgroup="vni_kumo"
            ), row=1, col=1)
            cloud_positions.append(len(fig.data) - 1)

    for name, values, color, width in (
        ("Ichi 1 · Lead 1 (Span A)", a, IDU.COL["span_a"], IDU.W_EDGE),
        ("Ichi 1 · Leading Span B", b, IDU.COL["span_b"], IDU.W_EDGE),
        (f"Ichi 2 · Tenkan {IDU.CFG['t2']}", indicator["tenkan2"], IDU.COL["tenkan2"], IDU.W_LINE),
        (f"Ichi 2 · Kijun {IDU.CFG['k2']}", indicator["kijun2"], IDU.COL["kijun2"], IDU.W_LINE),
    ):
        xi = ext_x if len(values) == len(ext_x) else list(labels)
        fig.add_trace(go.Scatter(
            x=xi, y=values, mode="lines", name=name,
            line=dict(color=color, width=width),
            hovertemplate=f"{name}: %{{y:,.2f}}<extra></extra>"
        ), row=1, col=1)
        line_positions.append(len(fig.data) - 1)

    # Cloud behind the candles, blue/orange Ichimoku lines above the candles.
    all_traces = list(fig.data)
    fig.data = tuple(
        all_traces[i] for i in
        cloud_positions + list(range(original_count)) + line_positions
    )
    # Existing index chart uses categorical dates. Predeclare future categories
    # so the displacement matches 25 trading periods without moving real bars.
    fig.update_xaxes(categoryorder="array", categoryarray=ext_x)
    existing_end = right_axis_range(n, tf)[1]
    show_future = min(int(indicator["off"]), max(2, round(n * 0.2)))
    right_end = max(existing_end, n - 0.5 + show_future)
    fig.update_xaxes(range=[-0.5, right_end])
    # Keep the Y axis fitted to real candles plus visible Kumo projection.
    visible_limit = min(len(a), n + show_future)
    cloud_values = np.concatenate((a[:visible_limit], b[:visible_limit]))
    cloud_values = cloud_values[np.isfinite(cloud_values)]
    if len(cloud_values):
        lo = min(float(visible["Giá thấp nhất"].min()), float(cloud_values.min()))
        hi = max(float(visible["Giá cao nhất"].max()), float(cloud_values.max()))
        pad = max(hi - lo, 1.0) * .06
        fig.update_yaxes(range=[lo - pad, hi + pad], row=1, col=1)
    # MIN_VNINDEX_ICHI2_PRICE_TAGS_V1: Plotly value badges on right price axis.
    # Take the LAST computed value of each Ichi 2 line (not the future Kumo).
    # Same dynamic calculation and colors as the stock chart; no hardcoded levels.
    tag_specs = (
        (indicator["tenkan2"][-1], IDU.COL["tenkan2"], "#FFFFFF"),
        (indicator["kijun2"][-1], IDU.COL["kijun2"], "#131722"),
    )
    valid_tags = [(float(v), bg, fg) for v, bg, fg in tag_specs if np.isfinite(v)]

    # If the lines almost coincide, separate only the VISUAL badges slightly.
    # Their y coordinates remain the true indicator prices on the right axis.
    tag_yshifts = [0] * len(valid_tags)
    if len(valid_tags) == 2:
        y_range = fig.layout.yaxis.range
        if y_range is not None:
            price_span = abs(float(y_range[1]) - float(y_range[0]))
            px_per_price = 340.0 / max(price_span, 1.0)
            if abs(valid_tags[0][0] - valid_tags[1][0]) * px_per_price < 22:
                tag_yshifts = [11, -11]

    for (price, background, foreground), shift in zip(valid_tags, tag_yshifts):
        fig.add_annotation(
            xref="paper", x=1, xanchor="left", xshift=2,
            yref="y", y=price, yanchor="middle", yshift=shift,
            text=f"<b>{price:,.2f}</b>",
            font=dict(color=foreground, size=12),
            bgcolor=background, borderpad=3,
            showarrow=False,
        )
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
def _auto_view(_raw, data_key: str, tf: str, use_news: bool, bucket: int, entries_stamp: float, sector_format_rev: str):
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


def _bulletin_heading(source_title: str) -> str:
    """Convert automatic period title into a client-facing bulletin heading."""
    title = str(source_title).strip()
    if title.startswith("VNINDEX · "):
        title = title[len("VNINDEX · "):]
    for period in ("PHIÊN", "TUẦN", "THÁNG", "QUÝ"):
        prefix = f"NHẬN ĐỊNH {period}"
        if title.startswith(prefix):
            return f"VNINDEX - NHẬN ĐỊNH {period}" + title[len(prefix):]
    return "VNINDEX - " + title


def _item_html(it: dict, compact: bool = False) -> str:
    txt = html.escape(it["text"])
    glyph = "" if it["text"].lstrip().startswith("*") else (TONE_ICON.get(it["tone"], "•") + " ")
    col = TONE_COL.get(it["tone"])
    main = f'<span style="color:{col};font-weight:600">{glyph}{txt}</span>' if col else f"{glyph}{txt}"
    left_pad = 14 if compact else 22
    subs = "".join(f'<div style="padding-left:{left_pad}px;opacity:.85">{html.escape(s)}</div>' for s in it["subs"])
    style = ("margin:0 0 4px;line-height:1.42;font-size:12.5px" if compact
             else "margin:0 0 7px;line-height:1.55;font-size:14.5px")
    return f'<div style="{style}">{main}{subs}</div>'


def _flow_card_without_intro(sec: dict | None) -> dict | None:
    """Hide the three circled summary bullets; preserve all group rankings.

    Display-only transformation. Never mutate the computed/cached report.
    """
    if sec is None or sec.get("name") != "DÒNG TIỀN":
        return sec
    kept = []
    for item in sec.get("items", []):
        label = str(item.get("text", "")).lstrip("• ").strip()
        hide = (
            (label.startswith("VN-Index ") and "lực mua" in label and "lực bán" in label)
            or label.startswith("GTGD rổ theo dõi")
            or label.startswith("Độ rộng ")
        )
        if not hide:
            kept.append(item)
    return {**sec, "items": kept}


def _vnindex_card(sec: dict, *, compact: bool = False):
    """Render one existing report section without modifying its contents."""
    with st.container(border=True):
        st.markdown(f"**{html.escape(sec['name'])}**")
        st.markdown("".join(_item_html(it) for it in sec['items']), unsafe_allow_html=True)


def _sections(sections: list[dict]):
    if not sections:
        return
    columns_per_row = 2 if len(sections) in (4, 5) else 3
    for row in range(0, len(sections), columns_per_row):
        chunk = sections[row:row + columns_per_row]
        if len(chunk) == 1:
            with st.container(border=True):
                st.markdown(f"**{html.escape(chunk[0]['name'])}**")
                st.markdown("".join(_item_html(it) for it in chunk[0]["items"]), unsafe_allow_html=True)
        else:
            for col, sec in zip(st.columns(len(chunk), gap="medium"), chunk):
                with col, st.container(border=True):
                    st.markdown(f"**{html.escape(sec['name'])}**")
                    st.markdown("".join(_item_html(it, compact=compact) for it in sec["items"]), unsafe_allow_html=True)



# MIN_VNINDEX_EDITORIAL_STORY_V1: Tóm tắt tự động theo dữ liệu EOD, dùng được ở cả Sáng/Tối.
# MIN_VNINDEX_EDITORIAL_COMPACT_V2: Thu gọn card và đổi tên bản tin.
def _vni_streak_sentence(d: pd.DataFrame) -> str:
    """Đếm chuỗi tăng/giảm giá đóng cửa theo PHIÊN liên tiếp, kể cả phiên hiện tại.

    Phiên đi ngang hoặc thiếu giá ngắt chuỗi. Không nhầm lần đầu tăng sau giảm
    với phiên tăng thứ N của một chuỗi tăng đã hình thành.
    """
    prices = pd.to_numeric(d[C], errors="coerce").tolist()
    if len(prices) < 2:
        return "Chưa đủ dữ liệu để xác định chuỗi phiên tăng/giảm"

    directions = []
    for prev, cur in zip(prices[:-1], prices[1:]):
        if pd.isna(prev) or pd.isna(cur):
            directions.append(None)
        else:
            diff = float(cur) - float(prev)
            directions.append(1 if diff > 1e-7 else -1 if diff < -1e-7 else 0)

    latest = directions[-1]
    if latest is None:
        return "Chưa đủ dữ liệu giá đóng cửa để xác định diễn biến phiên"
    if latest == 0:
        return "VNINDEX đi ngang so với phiên trước, chuỗi tăng/giảm đã ngắt"

    n = 0
    j = len(directions) - 1
    while j >= 0 and directions[j] == latest:
        n += 1
        j -= 1
    up = latest > 0
    word = "tăng" if up else "giảm"
    opposite = "giảm" if up else "tăng"
    if n >= 2:
        return f"Phiên {word} thứ {n} liên tiếp"

    prior = 0
    while j >= 0 and directions[j] == -latest:
        prior += 1
        j -= 1
    if prior >= 2:
        return f"Phiên {word} đầu tiên sau chuỗi {prior} phiên {opposite} liên tiếp"
    if prior == 1:
        return f"Phiên {word} sau 1 phiên {opposite}"
    if len(directions) >= 2 and directions[-2] == 0:
        return f"Phiên {word} sau phiên đi ngang"
    return f"VNINDEX ghi nhận phiên {word}"


def _vni_editorial_bullets(s: dict, d: pd.DataFrame) -> list[str]:
    bullets = [_vni_streak_sentence(d)]
    close, ma20, dist = s.get("close"), s.get("ma20"), s.get("from_hi")
    ma_part = None
    if close is not None and ma20 is not None and pd.notna(ma20):
        pos = "trên" if float(close) > float(ma20) else ("dưới" if float(close) < float(ma20) else "ngay tại")
        ma_part = f"{pos.capitalize()} MA20 ({float(ma20):,.2f})"
    top_part = None
    if dist is not None and pd.notna(dist):
        if abs(float(dist)) < 0.05:
            top_part = "đang ở vùng đỉnh 52 tuần"
        elif float(dist) < 0:
            top_part = f"cách đỉnh 52 tuần {abs(float(dist)):.1f}%"
        else:
            top_part = f"cao hơn đỉnh 52 tuần {float(dist):.1f}%"
    if ma_part and top_part:
        bullets.append(ma_part + ", " + top_part)
    elif ma_part or top_part:
        bullets.append(ma_part or top_part)
    else:
        bullets.append("Chưa đủ dữ liệu MA20 và đỉnh 52 tuần")

    vol_diff = s.get("vol_vs")
    if vol_diff is None or pd.isna(vol_diff):
        bullets.append("Chưa đủ dữ liệu để so sánh khối lượng với trung bình 20 phiên")
    elif abs(float(vol_diff)) < 0.5:
        bullets.append("Khối lượng tương đương trung bình 20 phiên")
    elif vol_diff > 0:
        bullets.append(f"Khối lượng cao hơn trung bình 20 phiên {abs(float(vol_diff)):.0f}%")
    else:
        bullets.append(f"Khối lượng thấp hơn trung bình 20 phiên {abs(float(vol_diff)):.0f}%")
    return bullets



# MIN_VNINDEX_SR_LEVELS_V4: mức MA theo phiên D + pivot đã xác nhận; đọc dữ liệu EOD.
def _vni_recent_confirmed_pivots(d: pd.DataFrame) -> tuple:
    """Đáy/đỉnh swing gần nhất: 2 phiên trái + 2 phiên phải xác nhận.

    Ưu tiên pivot mới nhất trong 60 phiên đã qua (không dùng 2 phiên cuối
    làm điểm pivot vì chưa có hai phiên phía sau xác nhận). Nếu không có,
    trả về cực trị 20 phiên với nhãn trung thực, không giả làm swing.
    """
    g = d[["Ngày", L, H]].sort_values("Ngày").reset_index(drop=True).copy()
    low = pd.to_numeric(g[L], errors="coerce")
    high = pd.to_numeric(g[H], errors="coerce")
    n = len(g)
    low_found = None
    high_found = None
    for i in range(n - 3, max(1, n - 63), -1):
        if i < 2:
            continue
        lo = low.iloc[i-2:i+3]
        hi = high.iloc[i-2:i+3]
        if len(lo) != 5 or len(hi) != 5:
            continue
        if low_found is None and lo.notna().all():
            v = float(low.iat[i])
            if v < float(lo.iloc[:2].min()) and v <= float(lo.iloc[3:].min()):
                low_found = ("Đáy gần nhất", v, pd.Timestamp(g["Ngày"].iat[i]))
        if high_found is None and hi.notna().all():
            v = float(high.iat[i])
            if v > float(hi.iloc[:2].max()) and v >= float(hi.iloc[3:].max()):
                high_found = ("Đỉnh gần nhất", v, pd.Timestamp(g["Ngày"].iat[i]))
        if low_found is not None and high_found is not None:
            break

    # Fallback nếu chưa xác nhận được một swing hợp lệ.
    if low_found is None:
        tail = low.tail(20).dropna()
        if not tail.empty:
            pos = int(tail.idxmin())
            low_found = ("Thấp nhất 20 phiên", float(low.iat[pos]), pd.Timestamp(g["Ngày"].iat[pos]))
    if high_found is None:
        tail = high.tail(20).dropna()
        if not tail.empty:
            pos = int(tail.idxmax())
            high_found = ("Cao nhất 20 phiên", float(high.iat[pos]), pd.Timestamp(g["Ngày"].iat[pos]))
    return low_found, high_found


def _vni_sr_strip(d: pd.DataFrame, s: dict) -> str:
    """Hiển thị vùng hỗ trợ (trái) và kháng cự (phải) theo khoảng cách tới đóng cửa.

    Dữ liệu: MA10/20/50/200 ngày và swing high/low đã xác nhận (giữ từ V4).
    Chỉ gộp hai MA khi khoảng cách không quá 1.5% giá đóng cửa; không gộp
    đỉnh/đáy vào MA. Giá tròn điểm để dễ đọc; hover cho giá chính xác 2 số.
    """
    close = float(s["close"])
    closes = pd.to_numeric(d.sort_values("Ngày")[C], errors="coerce").dropna()
    support, resistance, unavailable = [], [], []
    for period in (10, 20, 50, 200):
        if len(closes) < period:
            unavailable.append(f"MA{period}: chưa đủ {period} phiên")
            continue
        value = float(closes.tail(period).mean())
        item = (f"MA{period}", value, "sát giá" if abs(value - close) < 1e-8 else "", "")
        (support if value <= close else resistance).append(item)

    pivot_low, pivot_high = _vni_recent_confirmed_pivots(d)
    if pivot_low is not None:
        name, value, when = pivot_low
        support.append((name, value, "đã thủng" if value > close else "", f"{when:%d/%m/%Y}"))
    if pivot_high is not None:
        name, value, when = pivot_high
        resistance.append((name, value, "đã vượt" if value < close else "", f"{when:%d/%m/%Y}"))

    def format_group(items: list, side: str) -> str:
        if not items:
            msg = "Chưa có hỗ trợ tham khảo" if side == "support" else "Chưa có kháng cự tham khảo"
            return '<div class="min-vni-sr-empty">' + html.escape(msg) + '</div>'

        active = [x for x in items if x[2] not in ("đã thủng", "đã vượt")]
        crossed = [x for x in items if x[2] in ("đã thủng", "đã vượt")]
        is_support = side == "support"
        ordered_mas = sorted((x for x in active if x[0].startswith("MA")),
                             key=lambda x: -x[1] if is_support else x[1])
        groups = []
        gap_limit = close * 0.015
        for it in ordered_mas:
            if (groups and len(groups[-1]) < 2 and
                    abs(it[1] - groups[-1][0][1]) <= gap_limit):
                groups[-1].append(it)
            else:
                groups.append([it])
        groups.extend([[it] for it in active if not it[0].startswith("MA")])
        # Cụm gần giá hiện tại nhất luôn đứng trên cùng.
        groups.sort(key=lambda group: -max(x[1] for x in group) if is_support
                    else min(x[1] for x in group))
        # Những pivot đã thủng/vượt được đánh dấu và đưa xuống cuối.
        groups.extend([[it] for it in crossed])

        rows = []
        for group in groups:
            ordered = sorted(group, key=lambda x: -x[1] if is_support else x[1])
            numbers = [f"{x[1]:,.0f}" for x in ordered]
            # Không lặp một giá khi nhiều MA làm tròn cùng số điểm.
            numbers = list(dict.fromkeys(numbers))
            display = " – ".join(numbers)
            source = " · ".join(x[0] for x in ordered)
            note = next((x[2] for x in ordered if x[2]), "")
            detail = " | ".join(f"{x[0]}: {x[1]:,.2f}" +
                                (f" ({x[3]})" if x[3] else "") for x in ordered)
            crossed_class = " is-crossed" if note in ("đã thủng", "đã vượt") else ""
            suffix = f" · {note}" if note else ""
            rows.append(
                '<div class="min-vni-sr-row' + crossed_class + '" title="' +
                html.escape(detail, quote=True) + '">'
                '<strong class="min-vni-sr-price">' + html.escape(display) + '</strong>'
                '<span class="min-vni-sr-source">' + html.escape(source + suffix) + '</span>'
                '</div>'
            )
        return '<div class="min-vni-sr-levels">' + ''.join(rows) + '</div>'

    missing = '' if not unavailable else (
        '<div class="min-vni-sr-missing">' + html.escape(' · '.join(unavailable)) + '</div>'
    )
    return (
        '<div class="min-vni-sr-wrap">'
        '<div class="min-vni-sr-caption">VÙNG GIÁ THAM KHẢO '
        '<small>· MA khung Phiên (D) · so với giá đóng cửa</small></div>'
        '<div class="min-vni-sr-grid">'
        '<div class="min-vni-sr-column">'
        '<div class="min-vni-sr-heading support">HỖ TRỢ</div>'
        + format_group(support, 'support') + '</div>'
        '<div class="min-vni-sr-column">'
        '<div class="min-vni-sr-heading resistance">KHÁNG CỰ</div>'
        + format_group(resistance, 'resistance') + '</div>'
        '</div>' + missing + '</div>'
    )

def render_vnindex_editorial(d_all: pd.DataFrame, s: dict) -> None:
    """Thay đúng 4 metric ở đầu trang; giữ nguyên biểu đồ và các bộ lọc phía dưới."""
    light = not TH.is_dark()
    css_mode = "light" if light else "dark"
    chg, pct = s.get("chg"), s.get("pct")
    direction = "gain" if chg is not None and chg > 0 else ("loss" if chg is not None and chg < 0 else "flat")
    points_text = f"{float(chg):+,.2f}" if chg is not None else "—"
    pct_text = f"{float(pct):+.2f}%" if pct is not None else "—"
    close_text = f"{float(s['close']):,.2f}"
    date_value = s.get("date")
    date_text = f"{date_value:%d/%m/%Y}" if date_value is not None else "chưa xác định"
    bullets = _vni_editorial_bullets(s, d_all)
    items = "".join(f"<li>{html.escape(item)}</li>" for item in bullets)
    # CSS chỉ áp dụng trong khối .min-vni-story, không đổi giao diện các tab khác.
    st.markdown("""
<style>
.min-vni-story{--vni-ink:#19392E;--vni-muted:#4C685B;--vni-panel:#F7F4E9;--vni-panel2:#EDF4EE;--vni-line:#D4DCCB;
    --vni-up:#087C4E;--vni-down:#C0364B;--vni-flat:#8D6A2D;
    position:relative;overflow:hidden;padding:15px 21px 13px;border:1px solid var(--vni-line);border-radius:18px;
    background:linear-gradient(105deg,var(--vni-panel),var(--vni-panel2));color:var(--vni-ink);
    box-shadow:0 5px 18px rgba(20,51,40,.06);margin:3px 0 12px;max-width:1120px;width:100%;}
.min-vni-story.dark{--vni-ink:#E7F2E9;--vni-muted:#A8C0B4;--vni-panel:#183328;--vni-panel2:#10251D;--vni-line:#315547;
    --vni-up:#38DB9A;--vni-down:#FF7387;--vni-flat:#F2C46D;box-shadow:none;}
.min-vni-story .min-vni-kicker{font-family:Georgia,'Times New Roman',serif;font-size:17px;letter-spacing:1.5px;font-weight:800;}
.min-vni-story .min-vni-points{display:flex;align-items:baseline;flex-wrap:wrap;gap:8px;line-height:1.05;margin:4px 0 2px;
    font-family:Georgia,'Times New Roman',serif;font-weight:700;}
.min-vni-story .min-vni-number{font-size:clamp(43px,5vw,68px);font-variant-numeric:tabular-nums;letter-spacing:-2px;}
.min-vni-story .min-vni-unit{font-size:clamp(19px,1.8vw,27px);}
.min-vni-story.gain .min-vni-points{color:var(--vni-up)}
.min-vni-story.loss .min-vni-points{color:var(--vni-down)}
.min-vni-story.flat .min-vni-points{color:var(--vni-flat)}
.min-vni-story .min-vni-close{font-family:Georgia,'Times New Roman',serif;font-size:clamp(15px,1.6vw,20px);margin:3px 0 7px;}
.min-vni-story .min-vni-list{padding:0;margin:0;list-style:none;display:grid;gap:3px;}
.min-vni-story .min-vni-list li{font-size:clamp(13px,1vw,15.5px);font-weight:550;line-height:1.35;}
.min-vni-story .min-vni-list li:before{content:'—';display:inline-block;margin-right:9px;font-weight:800;}
.min-vni-story .min-vni-date{font-size:11px;color:var(--vni-muted);margin-top:8px;border-top:1px solid var(--vni-line);
    padding-top:6px;font-weight:600;}
@media(max-width:650px){.min-vni-story{padding:13px 15px;margin-bottom:10px}.min-vni-story .min-vni-number{letter-spacing:-1px;}}

/* MIN_VNINDEX_EDITORIAL_TWO_COLUMN_V3: Cột trái là điểm số, cột phải nhận định. */
.min-vni-story{padding:13px 20px 11px;max-width:1120px;}
.min-vni-story .min-vni-content{
    display:grid;grid-template-columns:minmax(0,.87fr) minmax(0,1.13fr);
    gap:clamp(18px,2.8vw,38px);align-items:center;
}
.min-vni-story .min-vni-left,.min-vni-story .min-vni-right{min-width:0;}
.min-vni-story .min-vni-right{
    border-left:1px solid var(--vni-line);padding-left:clamp(18px,2.4vw,32px);
}
.min-vni-story .min-vni-highlights-head{
    color:var(--vni-muted);font-size:11px;letter-spacing:1.1px;
    font-weight:800;margin:0 0 8px;
}
.min-vni-story .min-vni-kicker{font-size:16px;}
.min-vni-story .min-vni-number{font-size:clamp(43px,4.8vw,61px);letter-spacing:-1.5px;}
.min-vni-story .min-vni-unit{font-size:clamp(19px,1.9vw,26px);}
.min-vni-story .min-vni-close{font-size:clamp(15px,1.5vw,19px);margin:3px 0 0;}
.min-vni-story .min-vni-list{gap:7px;}
.min-vni-story .min-vni-list li{font-size:clamp(13px,1vw,15px);line-height:1.42;}
.min-vni-story .min-vni-date{margin-top:9px;padding-top:6px;font-size:11px;}
@media(max-width:760px){
    .min-vni-story{padding:13px 15px 11px;}
    .min-vni-story .min-vni-content{grid-template-columns:1fr;gap:12px;}
    .min-vni-story .min-vni-right{
        border-left:0;border-top:1px solid var(--vni-line);padding-left:0;padding-top:12px;
    }
    .min-vni-story .min-vni-number{font-size:clamp(43px,8vw,59px);}
    .min-vni-story .min-vni-list{gap:5px;}
}

/* MIN_VNINDEX_SR_V4_CSS: chỉ dùng trong khung tóm tắt VNINDEX. */
.min-vni-story .min-vni-sr-wrap{border-top:1px solid var(--vni-line);margin-top:9px;padding-top:9px;}
.min-vni-story .min-vni-sr-caption{font-size:11px;letter-spacing:.65px;color:var(--vni-muted);font-weight:800;margin-bottom:6px;}
.min-vni-story .min-vni-sr-caption small{font-size:10px;letter-spacing:0;font-weight:500;}
.min-vni-story .min-vni-sr-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;}
.min-vni-story .min-vni-sr-column{min-width:0;}
.min-vni-story .min-vni-sr-heading{font-weight:800;font-size:11px;letter-spacing:.7px;margin:0 0 5px;}
.min-vni-story .min-vni-sr-heading.support{color:var(--vni-up);}
.min-vni-story .min-vni-sr-heading.resistance{color:var(--vni-down);}
.min-vni-story .min-vni-sr-chips{display:flex;gap:5px;align-items:center;flex-wrap:wrap;}
.min-vni-story .min-vni-sr-chip{display:inline-flex;align-items:baseline;gap:6px;min-width:0;
    border:1px solid var(--vni-line);padding:4px 7px;border-radius:7px;font-size:11px;
    line-height:1.2;background:rgba(125,145,115,.07);font-variant-numeric:tabular-nums;white-space:nowrap;}
.min-vni-story .min-vni-sr-chip b{font-weight:650;color:var(--vni-muted);}
.min-vni-story .min-vni-sr-chip span{font-weight:800;color:var(--vni-ink);}
.min-vni-story .min-vni-sr-chip em{font-size:9px;opacity:.82;font-style:normal;}
.min-vni-story .min-vni-sr-chip.is-crossed{opacity:.72;border-style:dashed;}
.min-vni-story .min-vni-sr-empty,.min-vni-story .min-vni-sr-missing{font-size:11px;color:var(--vni-muted);}
.min-vni-story .min-vni-sr-missing{margin-top:5px;}
.min-vni-story .min-vni-date{margin-top:7px;padding-top:6px;}
@media(max-width:760px){
    .min-vni-story .min-vni-sr-grid{grid-template-columns:1fr;gap:10px;}
    .min-vni-story .min-vni-sr-caption small{display:block;margin-top:3px;}
    .min-vni-story .min-vni-sr-chip{white-space:normal;}
}

/* MIN_VNINDEX_MA10_20_50_200_COMPACT_V5: bản tin nhỏ gọn, hai cột desktop. */
.min-vni-story{padding:10px 16px 8px;max-width:1120px;margin:2px 0 10px;border-radius:13px;}
.min-vni-story .min-vni-content{grid-template-columns:minmax(0,.72fr) minmax(0,1.28fr);gap:clamp(12px,2vw,25px);}
.min-vni-story .min-vni-right{padding-left:clamp(12px,1.6vw,22px);}
.min-vni-story .min-vni-kicker{font-size:13px;letter-spacing:1.2px;line-height:1.15;}
.min-vni-story .min-vni-points{gap:5px;line-height:1; margin:1px 0 1px;}
.min-vni-story .min-vni-number{font-size:clamp(36px,3.5vw,48px);letter-spacing:-1px;}
.min-vni-story .min-vni-unit{font-size:clamp(15px,1.5vw,20px);}
.min-vni-story .min-vni-close{font-size:clamp(13px,1.2vw,16px);line-height:1.2;margin:1px 0 0;}
.min-vni-story .min-vni-highlights-head{font-size:10px;letter-spacing:.7px;margin:0 0 4px;}
.min-vni-story .min-vni-list{gap:3px;}
.min-vni-story .min-vni-list li{font-size:clamp(11.5px,.94vw,13px);line-height:1.24;}
.min-vni-story .min-vni-list li:before{margin-right:6px;}
.min-vni-story .min-vni-sr-wrap{margin-top:6px;padding-top:6px;}
.min-vni-story .min-vni-sr-caption{font-size:10px;margin-bottom:4px;line-height:1.2;}
.min-vni-story .min-vni-sr-caption small{font-size:9.5px;}
.min-vni-story .min-vni-sr-grid{gap:10px;}
.min-vni-story .min-vni-sr-heading{font-size:10px;margin-bottom:3px;}
.min-vni-story .min-vni-sr-chips{gap:4px;}
.min-vni-story .min-vni-sr-chip{padding:3px 6px;gap:4px;font-size:10.5px;border-radius:6px;}
.min-vni-story .min-vni-date{font-size:10px;margin-top:5px;padding-top:4px;line-height:1.2;}
@media(max-width:760px){
  .min-vni-story{padding:10px 12px 9px;}
  .min-vni-story .min-vni-content{grid-template-columns:1fr;gap:8px;}
  .min-vni-story .min-vni-right{padding:8px 0 0;border-left:0;border-top:1px solid var(--vni-line);}
  .min-vni-story .min-vni-number{font-size:clamp(36px,8vw,46px);}
  .min-vni-story .min-vni-sr-grid{grid-template-columns:1fr;gap:7px;}
  .min-vni-story .min-vni-sr-chip{white-space:normal;}
}

/* MIN_VNINDEX_EDITORIAL_ONE_ROW_V7: VNINDEX | DIEM NHAN | HO TRO | KHANG CU */
.min-vni-story{
    display:grid;
    grid-template-columns:minmax(0,.93fr) minmax(0,1.95fr) minmax(0,1fr) minmax(0,1.06fr);
    column-gap:clamp(12px,1.4vw,19px);
    row-gap:5px;
    align-items:start;
    max-width:1200px;
    padding:12px 18px 7px;
    margin:3px 0 9px;
    width:100%;
}
.min-vni-story .min-vni-content,
.min-vni-story .min-vni-sr-wrap,
.min-vni-story .min-vni-sr-grid{display:contents;}
.min-vni-story .min-vni-left,
.min-vni-story .min-vni-right,
.min-vni-story .min-vni-sr-column{min-width:0;align-self:start;text-align:left;}
.min-vni-story .min-vni-right,
.min-vni-story .min-vni-sr-column{
    border-left:1px solid var(--vni-line);
    padding:0 0 0 clamp(11px,1.25vw,17px);
    border-top:0;
    margin:0;
}
.min-vni-story .min-vni-kicker{font-size:13px;line-height:1.2;letter-spacing:1px;}
.min-vni-story .min-vni-points{gap:3px;line-height:1;margin:2px 0 3px;white-space:nowrap;flex-wrap:nowrap;}
.min-vni-story .min-vni-number{font-size:clamp(32px,3vw,42px);letter-spacing:-.8px;}
.min-vni-story .min-vni-unit{font-size:clamp(13px,1.2vw,17px);}
.min-vni-story .min-vni-close{font-size:clamp(11px,.95vw,13px);line-height:1.23;margin:1px 0 0;}
.min-vni-story .min-vni-highlights-head{margin:0 0 7px;font-size:10px;letter-spacing:.6px;}
.min-vni-story .min-vni-list{margin:0;padding:0;gap:6px;}
.min-vni-story .min-vni-list li{font-size:clamp(11px,.85vw,12.5px);line-height:1.28;}
.min-vni-story .min-vni-list li:before{margin-right:6px;}
.min-vni-story .min-vni-sr-caption{display:none;}
.min-vni-story .min-vni-sr-heading{font-size:11px;line-height:1.2;letter-spacing:.7px;margin:0 0 9px;}
.min-vni-story .min-vni-sr-levels{display:flex;flex-direction:column;gap:8px;}
.min-vni-story .min-vni-sr-row{
    display:flex;flex-direction:column;align-items:flex-start;justify-content:flex-start;
    gap:2px;flex-wrap:nowrap;min-width:0;padding:0;line-height:1.25;text-align:left;
}
.min-vni-story .min-vni-sr-price{font-size:clamp(12px,.99vw,14px);font-weight:800;white-space:normal;letter-spacing:-.1px;}
.min-vni-story .min-vni-sr-source{font-size:9.5px;line-height:1.2;color:var(--vni-muted);white-space:normal;}
.min-vni-story .min-vni-sr-empty{font-size:11px;line-height:1.35;}
.min-vni-story .min-vni-sr-missing{grid-column:1/-1;margin:3px 0 0;font-size:10px;}
.min-vni-story .min-vni-date{
    grid-column:1/-1;margin:4px 0 0;padding:5px 0 0;
    border-top:1px solid var(--vni-line);font-size:10px;line-height:1.2;
}
@media(max-width:1050px){
    .min-vni-story{grid-template-columns:minmax(0,1fr) minmax(0,1.45fr);row-gap:14px;}
    .min-vni-story .min-vni-sr-column:nth-child(1){border-left:0;padding-left:0;}
    .min-vni-story .min-vni-sr-heading{margin-bottom:5px;}
}
@media(max-width:650px){
    .min-vni-story{grid-template-columns:minmax(0,1fr);padding:11px 13px 9px;row-gap:9px;}
    .min-vni-story .min-vni-right,
    .min-vni-story .min-vni-sr-column{border-left:0;border-top:1px solid var(--vni-line);padding:8px 0 0;}
    .min-vni-story .min-vni-points{white-space:normal;flex-wrap:wrap;}
    .min-vni-story .min-vni-number{font-size:40px;}
    .min-vni-story .min-vni-sr-levels{gap:4px;}
    .min-vni-story .min-vni-date{margin-top:0;}
}
</style>
""", unsafe_allow_html=True)
    st.markdown(
        f'<section class="min-vni-story {css_mode} {direction}">'
        f'<div class="min-vni-content">'
        f'<div class="min-vni-left">'
        f'<div class="min-vni-kicker">VNINDEX</div>'
        f'<div class="min-vni-points"><span class="min-vni-number">{html.escape(points_text)}</span>'
        f'<span class="min-vni-unit">điểm</span></div>'
        f'<div class="min-vni-close">Đóng cửa <strong>{html.escape(close_text)}</strong>, '
        f'<strong>{html.escape(pct_text)}</strong></div>'
        f'</div>'
        f'<div class="min-vni-right">'
        f'<div class="min-vni-highlights-head">ĐIỂM NHẤN PHIÊN</div>'
        f'<ul class="min-vni-list">{items}</ul>'
        f'</div>'
        f'</div>'
        f'{_vni_sr_strip(d_all, s)}'
        f'<div class="min-vni-date">Dữ liệu chốt phiên {html.escape(date_text)}</div>'
        '</section>',
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------ TRANG
def render(raw: pd.DataFrame | None = None, data_key: str = ""):
    st.title("📈 Nhận định VNINDEX")
    d_all = index_daily(raw)
    if d_all.empty:
        st.error("Không tìm thấy dữ liệu VNINDEX (mã VNINDEX) trong dữ liệu cuối phiên.")
        return
    # Invalidate report cache when index CSV changes, independent of stock EOD.
    index_mtime = os.path.getmtime(INDEX_CSV) if os.path.exists(INDEX_CSV) else 0.0
    eod_mtime = os.path.getmtime(EOD_CSV) if os.path.exists(EOD_CSV) else 0.0
    key = f"{data_key}|index:{index_mtime}|eod:{eod_mtime}"

    s = _stats(d_all)
    render_vnindex_editorial(d_all, s)

    c1, c2, c3, c4, c5 = st.columns([2.0, 1.0, 1.15, 1.15, 1.5])
    tf = c1.segmented_control("Khung", list(TF_LABEL), default="D", key="vnv_tf", format_func=TF_LABEL.get,
                              label_visibility="collapsed") or "D"
    use_news = c2.checkbox("Tin RSS", value=False, key="vnv_news", help="Lấy tin từ các RSS trong data/rss_feeds.txt (làm mới mỗi 30 phút)")
    show_st = c3.checkbox("Supertrend", value=False, key="vnv_st", help=f"Supertrend (ATR {SPT.PERIOD}, hệ số {SPT.MULTIPLIER:g}): xanh = xu hướng tăng, đỏ = xu hướng giảm")
    show_hull = c4.checkbox("Hull Suite", value=False, key="vnv_hull", help=f"Hull Suite (HMA {HUL.LENGTH})")
    show_ichi = c5.checkbox("Dual Ichimoku", value=True, key="vnv_ichi", help="Kumo 9-17-26, Tenkan 65, Kijun 129; dùng dữ liệu VNINDEX cùng khung")
    # Selector is intentionally BELOW the chart. Read its previous widget state
    # here; Streamlit reruns the script automatically after any pill click.
    chart_range = st.session_state.get("vnv_chart_range", "1Y")
    if chart_range not in RANGE_OPTIONS:
        chart_range = "1Y"
    entries, _ = _entries()
    view, info = _auto_view(raw, key, tf, use_news, int(time.time() // 1800), len(entries), "sector-reasons-v1")
    if view is None:
        st.warning(info)
        return
    st.subheader(_bulletin_heading(view["title"]))
    # Dates still drive freshness checks; hide the read-only metadata row.
    index_day = pd.Timestamp(d_all["Ngày"].iloc[-1]).normalize()
    stock_day = None
    if raw is not None and not raw.empty and "Ngày" in raw.columns:
        parsed = pd.to_datetime(raw["Ngày"], errors="coerce", format="mixed", dayfirst=True)
        if parsed.notna().any():
            stock_day = pd.Timestamp(parsed.max()).normalize()
    sector_data_behind = stock_day is not None and stock_day < index_day
    if sector_data_behind:
        st.warning(f"Dữ liệu nhóm ngành chỉ đến {stock_day:%d/%m/%Y}, sau VNINDEX "
                   f"{index_day:%d/%m/%Y}. Tạm ẩn xếp hạng dòng tiền để tránh nhầm kỳ.")
    # Refresh warning for all timeframes even when their report is cached.
    A, _ = _auto_mods()
    sections = (A.refresh_fomo_sections(view["sections"], _panel(raw, key), s["date"])
                if A is not None else view["sections"])
    # Sync ranking with Ngành > Dòng dẫn sóng (same sector data and period_stats).
    from vnindex_leading_sync import leading_from_eod, replace_strong_sector_block
    # Render-time action shares the EXACT leading groups of the visible flow card.
    from vnindex_flow_actions import flow_action_items, replace_action_section, unavailable_action
    leading = None
    action_panel = None
    try:
        source_raw = raw if raw is not None else (_csv_all(EOD_CSV, os.path.getmtime(EOD_CSV)) if os.path.exists(EOD_CSV) else None)
        _A, _WL = _auto_mods()
        if sector_data_behind:
            # Never label an old sector panel as if it belonged to the newer index date.
            sections = [{**section, "items": [{"tone": "vang", "text":
                        "Nhóm ngành chưa đồng bộ ngày dữ liệu với VNINDEX; chưa xếp hạng.", "subs": []}]}
                        if section.get("name") == "DÒNG TIỀN" else section
                        for section in sections]
        else:
            leading = leading_from_eod(source_raw, d_all, tf, _WL.GROUPS)
            sections = replace_strong_sector_block(sections, leading, tf)
            action_panel = _panel(raw, key)
    except Exception as exc:
        # Fail closed: never show unfiltered representative tickers if cap sync fails.
        st.error(f"Không thể xác minh xếp hạng ngành và vốn hóa ({type(exc).__name__}); tạm ẩn DÒNG TIỀN.")
        sections = [
            {**section, "items": [{"tone": "vang", "text":
                         "Chưa xác minh được dữ liệu nhóm ngành/vốn hóa; tạm ẩn xếp hạng.", "subs": []}]}
            if section.get("name") == "DÒNG TIỀN" else section
            for section in sections
        ]
        leading = None  # Never fall back to cached VNINDEX-only actions.
    # Rebuild only HÀNH ĐỘNG from the verified visible DÒNG TIỀN sectors.
    # No stale group => no buy candidates. Preserve all other sections unchanged.
    try:
        action_lines = flow_action_items(sections, leading, action_panel, index_day, tf)
    except Exception:
        action_lines = unavailable_action()
    sections = replace_action_section(sections, action_lines)
    # Separate read-only institution net-flow card: never mutate upstream report/cache.
    from vnindex_institutional_flow import net_flow_sections
    sections = list(sections) + [net_flow_sections(d_all["Ngày"], tf, __import__("pathlib").Path(_HERE) / "data")]
    # VNINDEX_LANDSCAPE_LAYOUT_V1: chart + cashflow side-by-side; other cards below.
    report_by_name = {section.get("name"): section for section in sections}
    flow_card = _flow_card_without_intro(report_by_name.get("DÒNG TIỀN"))
    chart_col, flow_col = st.columns([2, 1], gap="medium")
    with chart_col:
        # Indicators use full EOD history; presets only crop the rendered bars.
        P_full = prep_chart(d_all, tf, len(d_all))
        P = chart_range_view(P_full, d_all["Ngày"], chart_range)
        fig = build_chart(P, show_st, show_hull)
        if show_ichi:
            fig = _vnindex_dual_ichimoku(fig, P_full["g"], P["g"], tf, P["labels"])
        fig.update_layout(height=485, meta=dict(vn_code="VNINDEX", vn_tf=tf))
        TH.style_fig(fig)
        if not TH.is_dark():
            # Ensure clear legend and date/price ticks on a light background.
            # Do not alter candle, volume, MA or report computations.
            chart_txt = TH.palette()["txt"]
            chart_muted = "#526F62"
            fig.update_layout(
                font=dict(color=chart_txt),
                legend=dict(font=dict(color=chart_txt, size=11)),
                hoverlabel=dict(bgcolor="#FFFFFF", font=dict(color=chart_txt, size=12)),
            )
            fig.update_xaxes(tickfont=dict(color=chart_muted, size=11), tickcolor="#9AB2A6")
            fig.update_yaxes(tickfont=dict(color=chart_muted, size=11), tickcolor="#9AB2A6")
        _plot(fig, f"vnv_chart_{tf}_{chart_range}")
        CH.inject()        # đường gióng dọc/ngang + nhãn Thứ, Ngày Tháng Năm và nhãn giá khi rê chuột
        VDT.inject(tf)  # Thanh công cụ vẽ bên trái, lưu theo VNINDEX và khung thời gian
        st.pills("Khoảng thời gian hiển thị", list(RANGE_OPTIONS),
                 selection_mode="single", default="1Y",
                 key="vnv_chart_range", label_visibility="collapsed")
        st.caption(f"Dữ liệu cuối phiên đến {s['date']:%d/%m/%Y}; tự có nến mới mỗi khi cập nhật data/eod_prices.csv. "
                   f"Đường MA tính theo khung {TF_NOUN[tf]}: " + ", ".join(f"MA{m}" for m in P["mas"]) + ". Rê chuột vào nến để xem giá." + (f" Supertrend (ATR {SPT.PERIOD}, hệ số {SPT.MULTIPLIER:g}) tính theo khung {TF_NOUN[tf]}." if show_st else "") + (f" Hull Suite (HMA {HUL.LENGTH}) cũng tính theo khung {TF_NOUN[tf]}." if show_hull else ""))

    with flow_col:
        if flow_card is not None:
            _vnindex_card(flow_card, compact=True)
        else:
            st.info("Chưa có nhận định DÒNG TIỀN cho khung đang chọn.")
    # Action + note first, full-width institutional flow next, then news.
    action_note = [report_by_name[n] for n in ("HÀNH ĐỘNG", "LƯU Ý") if n in report_by_name]
    if len(action_note) == 2:
        act_col, note_col = st.columns([1.35, 1.0], gap="medium")
        with act_col:
            _vnindex_card(action_note[0])
        with note_col:
            _vnindex_card(action_note[1])
    else:
        for sec in action_note:
            _vnindex_card(sec)
    for name in ("KHỐI NGOẠI – TỰ DOANH", "TIN TỨC"):
        if name in report_by_name:
            _vnindex_card(report_by_name[name])
    known = {"DÒNG TIỀN", "HÀNH ĐỘNG", "LƯU Ý", "KHỐI NGOẠI – TỰ DOANH", "TIN TỨC"}
    for sec in sections:
        if sec.get("name") not in known:
            _vnindex_card(sec)
    st.caption("Nhận định tự động tính theo luật cố định trên dữ liệu, mang tính tham khảo, không phải khuyến nghị đầu tư.")