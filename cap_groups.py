"""Thị trường > Nhóm vốn hóa: dòng tiền đang ở nhóm vốn hóa lớn hay nhỏ.

Dữ liệu: VN30 / VNMidcap / VNSmallcap / VN100 lấy từ data/index_prices.csv (do update_index.py ghi),
VNINDEX lấy từ data/eod_prices.csv như trang Nhận định VNINDEX.

Hai tỷ số chính (tăng = dòng tiền chấp nhận rủi ro, nhóm nhỏ mạnh hơn):
  - VNSmallcap / VN30
  - VNSmallcap / VNINDEX
Giảm = dòng tiền co về cổ phiếu vốn hóa lớn.
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import vnindex_view as VV

_HERE = os.path.dirname(os.path.abspath(__file__))
IDX_CSV = os.path.join(_HERE, "data", "index_prices.csv")
O, H, L, C, V = VV.O, VV.H, VV.L, VV.C, VV.V
OHLC = VV.OHLC
UP, DN = VV.UP, VV.DN
MA_COLORS = VV.MA_COLORS
TF_LABEL, TF_NOUN, MA_SET = VV.TF_LABEL, VV.TF_NOUN, VV.MA_SET
BAR_CHOICES, BAR_DEFAULT = VV.BAR_CHOICES, VV.BAR_DEFAULT

NAMES = {"VN30": "VN30 (vốn hóa lớn)", "VNMIDCAP": "VNMidcap (vốn hóa vừa)",
         "VNSMALLCAP": "VNSmallcap (vốn hóa nhỏ)", "VN100": "VN100 (tham chiếu)", "VNINDEX": "VN-Index"}
SHORT = {"VN30": "VN30", "VNMIDCAP": "VNMidcap", "VNSMALLCAP": "VNSmallcap", "VN100": "VN100", "VNINDEX": "VN-Index"}
MAIN_CODES = ["VN30", "VNMIDCAP", "VNSMALLCAP"]


# ------------------------------------------------------------------ DỮ LIỆU
@st.cache_data(show_spinner=False)
def _read_idx(path: str, mtime: float) -> pd.DataFrame:
    d = pd.read_csv(path, dtype={"Mã": str})
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", format="mixed", dayfirst=True).dt.normalize()
    for c in OHLC + [V]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d[V] = d[V].fillna(0)
    return d.dropna(subset=["Ngày"] + OHLC)


def load_series(raw: pd.DataFrame | None) -> dict[str, pd.DataFrame]:
    """{mã chỉ số: DataFrame Ngày/O/H/L/C/V theo ngày}. Mã nào chưa có dữ liệu thì không có trong kết quả."""
    out: dict[str, pd.DataFrame] = {}
    vni = VV.index_daily(raw)
    if not vni.empty:
        out["VNINDEX"] = vni
    if os.path.exists(IDX_CSV):
        d = _read_idx(IDX_CSV, os.path.getmtime(IDX_CSV))
        for code, g in d.groupby(d["Mã"].astype(str).str.upper().str.strip()):
            g = g[["Ngày"] + OHLC + [V]].drop_duplicates("Ngày", keep="last").sort_values("Ngày").reset_index(drop=True)
            if len(g) > 1:
                out[code] = g
    return out


def ratio(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Tỷ số giá đóng cửa a/b theo ngày (chỉ các ngày cả hai cùng có)."""
    m = a[["Ngày", C]].merge(b[["Ngày", C]], on="Ngày", suffixes=("_a", "_b"))
    m["r"] = m[f"{C}_a"] / m[f"{C}_b"]
    return m[["Ngày", "r"]].replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


def ratio_state(r: pd.DataFrame, n: int = 20) -> dict | None:
    """Trạng thái tỷ số theo ngày: so với MA20 và thay đổi sau n phiên."""
    if r is None or len(r) < n + 1:
        return None
    s = r["r"]
    last, ma, base = float(s.iloc[-1]), float(s.tail(n).mean()), float(s.iloc[-1 - n])
    chg = (last / base - 1) * 100 if base else np.nan
    above = last >= ma
    if above and chg > 0:
        trend = "tăng"
    elif (not above) and chg < 0:
        trend = "giảm"
    else:
        trend = "đi ngang"
    return {"last": last, "ma": ma, "chg": chg, "above": above, "trend": trend}


def verdict(s1: dict | None, s2: dict | None) -> tuple[str, str, str]:
    """(biểu tượng, tiêu đề, giải thích) từ hai tỷ số."""
    if s1 is None or s2 is None:
        return "ℹ️", "Chưa đủ dữ liệu để kết luận", "Cần có VN30, VNSmallcap và VN-Index với tối thiểu 21 phiên."
    t1, t2 = s1["trend"], s2["trend"]
    if t1 == "tăng" and t2 == "tăng":
        return "🟢", "Dòng tiền đang chấp nhận rủi ro", "Nhóm vốn hóa nhỏ đang mạnh hơn cả VN30 lẫn VN-Index."
    if t1 == "giảm" and t2 == "giảm":
        return "🔴", "Dòng tiền đang co về cổ phiếu vốn hóa lớn", "Nhóm vốn hóa nhỏ đang yếu hơn cả VN30 lẫn VN-Index."
    if "đi ngang" in (t1, t2) and "tăng" not in (t1, t2) and "giảm" not in (t1, t2):
        return "🟡", "Chưa có xu hướng rõ", "Hai tỷ số đều đi ngang, dòng tiền chưa nghiêng hẳn về nhóm nào."
    return "🟡", "Tín hiệu phân hóa", "Hai tỷ số đang cho kết quả khác nhau, nên chờ thêm xác nhận."


def perf_table(series: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for code in ["VNINDEX", "VN30", "VNMIDCAP", "VNSMALLCAP", "VN100"]:
        d = series.get(code)
        if d is None or len(d) < 2:
            continue
        c = d.set_index("Ngày")[C]
        last = float(c.iloc[-1])

        def chg(n):
            return (last / float(c.iloc[-1 - n]) - 1) * 100 if len(c) > n else np.nan

        prev_year = c[c.index < pd.Timestamp(year=c.index[-1].year, month=1, day=1)]
        ytd = (last / float(prev_year.iloc[-1]) - 1) * 100 if len(prev_year) else np.nan
        rows.append({"Chỉ số": SHORT[code], "Điểm": last, "1 phiên": chg(1), "1 tuần": chg(5), "1 tháng": chg(20),
                     "3 tháng": chg(60), "Từ đầu năm": ytd})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ BIỂU ĐỒ
def _ticks(dates: pd.Series, tf: str) -> list[tuple[int, str]]:
    if tf in ("D", "W"):
        t = [(i, f"Th{m}/{y}" if (m == 1 or i == 0) else f"Th{m}") for i, (m, y, pm) in
             enumerate(zip(dates.dt.month, dates.dt.year, dates.dt.month.shift())) if i == 0 or m != pm]
    else:
        t = [(i, str(y)) for i, (y, py) in enumerate(zip(dates.dt.year, dates.dt.year.shift())) if i == 0 or y != py]
    if len(t) > 1 and t[1][0] - t[0][0] < 3:
        t = t[1:]
    return t


def _style(fig, g: pd.DataFrame, tf: str, x: list[str], height: int, tag_val: float, tag_col: str,
           y_lo: float, y_hi: float, tick_fmt: str):
    fig.add_shape(type="line", xref="paper", x0=0, x1=1, yref="y", y0=tag_val, y1=tag_val,
                  line=dict(color=tag_col, width=1, dash="dot"))
    fig.add_annotation(xref="paper", yref="y", x=1, y=tag_val, xanchor="left", xshift=2, showarrow=False,
                       text=f"<b>{tag_val:,.{3 if tick_fmt == '.3f' else 2}f}</b>", bgcolor=tag_col,
                       font=dict(size=12, color="#0A1122"), borderpad=3)
    ticks = _ticks(g["Ngày"], tf)
    fig.update_xaxes(type="category", rangeslider_visible=False, showgrid=False, showline=True,
                     linecolor="rgba(128,128,128,.35)")
    if ticks:
        fig.update_xaxes(tickmode="array", tickvals=[x[i] for i, _ in ticks], ticktext=[t for _, t in ticks],
                         ticks="outside", ticklen=4, tickangle=0, tickfont=dict(size=11), showticklabels=True)
    else:
        fig.update_xaxes(showticklabels=False)
    pad = max(y_hi - y_lo, 1e-9) * 0.08
    fig.update_yaxes(range=[y_lo - pad, y_hi + pad], side="right", tickformat=tick_fmt, showgrid=True,
                     gridcolor="rgba(128,128,128,.18)", zeroline=False, showline=True, linecolor="rgba(128,128,128,.35)")
    fig.update_layout(height=height, margin=dict(l=8, r=72, t=8, b=34), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", dragmode=False, hovermode="closest", showlegend=True,
                      legend=dict(orientation="h", x=0.01, y=0.995, xanchor="left", yanchor="top", bgcolor="rgba(0,0,0,0)"),
                      hoverlabel=dict(bgcolor="#14203F", font=dict(color="#EAF0FF", size=12)))
    return fig


def candle_fig(d: pd.DataFrame, tf: str, n_show: int, name: str, height: int = 340):
    g = VV.resample_period(d, tf)
    mas = MA_SET[tf][:2]
    for m in mas:
        g[f"MA{m}"] = g[C].rolling(m).mean()
    g = g.tail(max(10, n_show)).reset_index(drop=True)
    x = [VV._label(pd.Timestamp(t), tf) for t in g["Ngày"]]
    cross = [VV._cross_label(pd.Timestamp(t), tf) for t in g["Ngày"]]
    hover = [f"<b>{name} · {lb}</b><br>Mở {r[O]:,.2f} · Cao {r[H]:,.2f}<br>Thấp {r[L]:,.2f} · Đóng {r[C]:,.2f}"
             for lb, (_, r) in zip(cross, g.iterrows())]
    fig = go.Figure(go.Candlestick(x=x, open=g[O], high=g[H], low=g[L], close=g[C], text=hover, hoverinfo="text",
                                   showlegend=False, whiskerwidth=0, meta=cross,
                                   increasing=dict(line=dict(color=UP, width=1), fillcolor=UP),
                                   decreasing=dict(line=dict(color=DN, width=1), fillcolor=DN)))
    for m, col in zip(mas, MA_COLORS):
        s = g[f"MA{m}"]
        if s.notna().any():
            fig.add_trace(go.Scatter(x=x, y=s, mode="lines", name=f"MA{m}", line=dict(color=col, width=1.5),
                                     hovertemplate=f"MA{m}: %{{y:,.2f}}<extra></extra>"))
    up_last = float(g[C].iloc[-1]) >= float(g[O].iloc[-1])
    return _style(fig, g, tf, x, height, float(g[C].iloc[-1]), UP if up_last else DN,
                  float(g[L].min()), float(g[H].max()), ",d")


def ratio_fig(a: pd.DataFrame, b: pd.DataFrame, tf: str, n_show: int, name: str, height: int = 300):
    ga, gb = VV.resample_period(a, tf)[["Ngày", C]], VV.resample_period(b, tf)[["Ngày", C]]
    r = ratio(ga, gb)
    n_ma = MA_SET[tf][0]
    r["MA"] = r["r"].rolling(n_ma).mean()
    r = r.tail(max(10, n_show)).reset_index(drop=True)
    x = [VV._label(pd.Timestamp(t), tf) for t in r["Ngày"]]
    fig = go.Figure(go.Scatter(x=x, y=r["r"], mode="lines", name=name, line=dict(color="#2DD4A7", width=2),
                               hovertemplate=f"{name}: %{{y:.4f}}<extra></extra>"))
    if r["MA"].notna().any():
        fig.add_trace(go.Scatter(x=x, y=r["MA"], mode="lines", name=f"MA{n_ma}", line=dict(color="#F5B942", width=1.5),
                                 hovertemplate=f"MA{n_ma}: %{{y:.4f}}<extra></extra>"))
    last, ma = float(r["r"].iloc[-1]), r["MA"].iloc[-1]
    col = UP if (pd.isna(ma) or last >= float(ma)) else DN
    lo, hi = float(r["r"].min()), float(r["r"].max())
    return _style(fig, r, tf, x, height, last, col, lo, hi, ".3f")


# ------------------------------------------------------------------ TRANG
def _color_pct(v):
    if pd.isna(v):
        return ""
    return f"color:{UP}" if v > 0 else (f"color:{DN}" if v < 0 else "")


def _perf_view(tbl: pd.DataFrame):
    sty = tbl.style.format({"Điểm": "{:,.2f}", **{c: "{:+.2f}%" for c in tbl.columns[2:]}}, na_rep="–")
    mapper = getattr(sty, "map", None) or sty.applymap
    return mapper(_color_pct, subset=list(tbl.columns[2:]))


def render(raw: pd.DataFrame | None = None, data_key: str = ""):
    st.title("🏷️ Nhóm vốn hóa")
    S = load_series(raw)
    have = [c for c in MAIN_CODES if c in S]
    if not have:
        st.info("Chưa có dữ liệu VN30, VNMidcap, VNSmallcap. Chạy `python update_index.py` (hoặc update_eod.bat) "
                "để tạo file data/index_prices.csv rồi đẩy lên GitHub.")
        return

    last_day = max(S[c]["Ngày"].iloc[-1] for c in have)
    cols = st.columns(len(have))
    for col, code in zip(cols, have):
        d = S[code]
        c1, c0 = float(d[C].iloc[-1]), float(d[C].iloc[-2])
        col.metric(SHORT[code], f"{c1:,.2f}", f"{c1 - c0:+,.2f} điểm ({(c1 / c0 - 1) * 100:+.2f}%)")

    # --- kết luận dòng tiền từ hai tỷ số (tính theo ngày, không đổi theo khung đang xem)
    r_sv, r_si = None, None
    if "VNSMALLCAP" in S and "VN30" in S:
        r_sv = ratio(S["VNSMALLCAP"], S["VN30"])
    if "VNSMALLCAP" in S and "VNINDEX" in S:
        r_si = ratio(S["VNSMALLCAP"], S["VNINDEX"])
    s_sv, s_si = ratio_state(r_sv), ratio_state(r_si)
    icon, head, why = verdict(s_sv, s_si)
    with st.container(border=True):
        st.markdown(f"**{icon} {head}**")
        st.write(why)
        parts = []
        for nm, s in (("VNSmallcap/VN30", s_sv), ("VNSmallcap/VN-Index", s_si)):
            if s:
                parts.append(f"{nm}: {s['last']:.3f}, {s['chg']:+.1f}% sau 20 phiên, "
                             f"{'trên' if s['above'] else 'dưới'} MA20 ({s['trend']})")
        if parts:
            st.caption(" · ".join(parts))

    c1, c2, c3 = st.columns([2.0, 1.3, 1.6])
    tf = c1.segmented_control("Khung", list(TF_LABEL), default="D", key="cap_tf", format_func=TF_LABEL.get,
                              label_visibility="collapsed") or "D"
    choices = BAR_CHOICES[tf]
    n_show = c2.selectbox("Số nến hiển thị", choices, index=choices.index(BAR_DEFAULT[tf]), key=f"cap_n_{tf}",
                          format_func=lambda v: f"{v} nến", label_visibility="collapsed")
    show_100 = c3.checkbox("Hiện VN100 (tham chiếu)", value=False, key="cap_vn100", disabled="VN100" not in S)

    st.subheader("Tỷ số sức mạnh")
    rc1, rc2 = st.columns(2, gap="medium")
    with rc1:
        st.markdown("**VNSmallcap / VN30**")
        if r_sv is not None:
            VV._plot(ratio_fig(S["VNSMALLCAP"], S["VN30"], tf, int(n_show), "VNSmallcap/VN30"), f"cap_r1_{tf}")
        else:
            st.info("Thiếu dữ liệu VN30 hoặc VNSmallcap.")
    with rc2:
        st.markdown("**VNSmallcap / VN-Index**")
        if r_si is not None:
            VV._plot(ratio_fig(S["VNSMALLCAP"], S["VNINDEX"], tf, int(n_show), "VNSmallcap/VN-Index"), f"cap_r2_{tf}")
        else:
            st.info("Thiếu dữ liệu VNSmallcap hoặc VN-Index.")
    st.caption("Tỷ số tăng: nhóm vốn hóa nhỏ mạnh hơn, dòng tiền chấp nhận rủi ro. "
               "Tỷ số giảm: dòng tiền co về cổ phiếu vốn hóa lớn. Đường vàng là MA của tỷ số theo khung đang chọn.")

    st.subheader("Biểu đồ nến theo nhóm vốn hóa")
    shown = have + (["VN100"] if show_100 and "VN100" in S else [])
    for code in shown:
        st.markdown(f"**{NAMES[code]}**")
        VV._plot(candle_fig(S[code], tf, int(n_show), SHORT[code]), f"cap_c_{code}_{tf}")
    try:
        import crosshair as CH
        CH.inject()
    except Exception:  # noqa: BLE001
        pass

    st.subheader("Hiệu suất so sánh")
    tbl = perf_table(S)
    if not tbl.empty:
        st.dataframe(_perf_view(tbl), hide_index=True, use_container_width=True)
    missing = [SHORT[c] for c in MAIN_CODES if c not in S]
    st.caption(f"Dữ liệu cuối phiên đến {last_day:%d/%m/%Y}. Đường MA tính theo khung {TF_NOUN[tf]}: "
               + ", ".join(f"MA{m}" for m in MA_SET[tf][:2]) + "."
               + (f" Chưa có dữ liệu: {', '.join(missing)}." if missing else ""))
