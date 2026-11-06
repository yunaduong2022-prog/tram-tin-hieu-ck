"""Min Invest — Cấu trúc MA. Read-only view over already prepared EOD daily bars."""
from __future__ import annotations

import html
import numpy as np
import pandas as pd
import streamlit as st

MAS = (10, 20, 50, 100, 200)
TREND_UP = "TĂNG"
TREND_DOWN = "GIẢM"
TREND_OTHER = "CHƯA XÁC ĐỊNH"


def trend_state(row: pd.Series, horizon: str) -> str:
    """Only strict MA orderings count; equality/missing values are indeterminate."""
    if horizon == "Ngắn hạn":
        keys = ("MA10", "MA20")
    elif horizon == "Trung hạn":
        keys = ("MA20", "MA50", "MA100")
    else:
        keys = ("MA50", "MA100", "MA200")
    values = [pd.to_numeric(row.get(k), errors="coerce") for k in keys]
    if not all(pd.notna(v) and np.isfinite(v) and v > 0 for v in values):
        return TREND_OTHER
    if all(a > b for a, b in zip(values, values[1:])):
        return TREND_UP
    if all(a < b for a, b in zip(values, values[1:])):
        return TREND_DOWN
    return TREND_OTHER


def snapshot(daily: pd.DataFrame) -> pd.DataFrame:
    """Get one newest genuine daily row per symbol; do not forward-fill missing bars."""
    required = {"Mã", "Ngày", "Giá đóng cửa"}
    if daily is None or daily.empty or not required.issubset(daily.columns):
        return pd.DataFrame()
    d = daily.copy()
    d["Mã"] = d["Mã"].astype(str).str.strip().str.upper()
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", dayfirst=True)
    d["Giá đóng cửa"] = pd.to_numeric(d["Giá đóng cửa"], errors="coerce")
    d = d.dropna(subset=["Ngày", "Giá đóng cửa"])
    d = d[d["Giá đóng cửa"] > 0]
    d = d.sort_values("Ngày").drop_duplicates("Mã", keep="last")
    if d.empty:
        return d
    for n in MAS:
        col = f"MA{n}"
        if col not in d:
            d[col] = np.nan
        d[col] = pd.to_numeric(d[col], errors="coerce")
    for key in ("Ngắn hạn", "Trung hạn", "Dài hạn"):
        d[key] = d.apply(lambda row: trend_state(row, key), axis=1)
    return d


def _fmt(v, digits=2):
    return "—" if pd.isna(v) else f"{float(v):,.{digits}f}"


def _tag(s):
    fg, bg = {TREND_UP:("#08794b", "#e4f6ec"), TREND_DOWN:("#ca3434", "#fcebec"),
              TREND_OTHER:("#a66c00", "#fff5d9")}[s]
    return f'<span style="color:{fg};background:{bg};font-size:11px;font-weight:750;padding:5px 7px;border-radius:7px">{s}</span>'


def _card(row: pd.Series, asof: pd.Timestamp):
    symbol = html.escape(str(row["Mã"]))
    company = str(row.get("Tên công ty", "") or "").strip()
    price = float(row["Giá đóng cửa"])
    dt = pd.Timestamp(row["Ngày"])
    with st.container(border=True):
        h1, h2 = st.columns([2, 1], vertical_alignment="center")
        with h1:
            st.markdown(f"### {symbol}")
            if company:
                st.caption(company)
            st.caption(f"{_fmt(price)} nghìn đồng · EOD {dt:%d/%m/%Y}")
        with h2:
            if dt.normalize() < asof.normalize():
                st.warning("Giá cũ", icon="⚠️")
            else:
                st.markdown(_tag(str(row["Ngắn hạn"])), unsafe_allow_html=True)
        cols = st.columns(3, gap="small")
        for col, label in zip(cols, ("Ngắn hạn", "Trung hạn", "Dài hạn")):
            with col:
                st.caption(label)
                st.markdown(_tag(str(row[label])), unsafe_allow_html=True)
        st.markdown("**GIÁ SO VỚI MA**")
        support, resist = [], []
        for n in MAS:
            ma = row.get(f"MA{n}", np.nan)
            pct = (price / ma - 1) * 100 if pd.notna(ma) and ma > 0 else np.nan
            if pd.notna(pct):
                (support if pct > 0 else resist if pct < 0 else []).append((f"MA{n}", float(ma), pct))
            label, mid, val = st.columns([1, 3, 1.8], vertical_alignment="center", gap="small")
            with label:
                st.caption(f"MA{n}")
            with mid:
                if pd.notna(pct):
                    length = min(100, int(abs(pct) * 10))
                    color = "#28a977" if pct >= 0 else "#d86b6b"
                    st.markdown(f'<div style="background:#e8edf2;border-radius:8px;height:5px"><div style="width:{length}%;background:{color};height:5px;border-radius:8px"></div></div>', unsafe_allow_html=True)
                else:
                    st.caption("Chưa đủ dữ liệu")
            with val:
                st.markdown(f'<div style="text-align:right;font-size:12px">{_fmt(ma)}<div style="color:{"#14935b" if pd.notna(pct) and pct >= 0 else "#d25151"}">{pct:+.2f}%</div></div>' if pd.notna(pct) else '—', unsafe_allow_html=True)
        left, right = st.columns(2, gap="small")
        for pane, title, values in ((left, "HỖ TRỢ MA TIỀM NĂNG", support), (right, "KHÁNG CỰ MA TIỀM NĂNG", resist)):
            with pane:
                st.caption(title)
                if values:
                    for name, ma, delta in sorted(values, key=lambda x: abs(x[2]))[:3]:
                        st.markdown(f'<div style="font-size:12px">{name}: {_fmt(ma)} <small>({delta:+.2f}%)</small></div>', unsafe_allow_html=True)
                else:
                    st.caption("Không có MA phù hợp")


def render(daily: pd.DataFrame, groups: dict[str, list[str]], eod_date=None, name_of=None) -> None:
    st.title("Khung cấu trúc – MA")
    st.caption("Theo dõi giá so với MA10 · MA20 · MA50 · MA100 · MA200 và xu hướng ngắn, trung, dài hạn. Dữ liệu EOD, không phải giá trực tiếp.")
    d = snapshot(daily)
    if d.empty:
        st.info("Chưa có nến ngày hợp lệ để phân tích MA.")
        return
    # Name source reuses the verified lookup from the stock chart; never call the network.
    def _name(code):
        if not callable(name_of):
            return ""
        try:
            value = name_of(str(code))
            return value.strip() if isinstance(value, str) else ""
        except Exception:
            return ""
    d["Tên công ty"] = d["Mã"].map(_name)
    asof = pd.Timestamp(eod_date) if eod_date is not None else d["Ngày"].max()
    # Newest common EOD session is the only source for current headline statistics.
    today = d[d["Ngày"].dt.normalize() == asof.normalize()].copy()
    m = st.columns(4)
    metrics = [("TỔNG SỐ MÃ", len(d)), ("NGẮN HẠN · TĂNG", int((today["Ngắn hạn"] == TREND_UP).sum())),
               ("TRUNG HẠN · TĂNG", int((today["Trung hạn"] == TREND_UP).sum())),
               ("DÀI HẠN · TĂNG", int((today["Dài hạn"] == TREND_UP).sum()))]
    for col, (label, value) in zip(m, metrics):
        col.metric(label, value)
    st.caption(f"Nguồn: nến ngày đã xác nhận đến {asof:%d/%m/%Y}. {len(today)}/{len(d)} mã có giá đúng ngày. Các mã thiếu dữ liệu được đánh dấu.")

    symbols = set(d["Mã"])
    sector_options = ["Toàn thị trường"] + [g for g, syms in groups.items() if symbols.intersection(syms)]
    c1, c2 = st.columns([2, 2])
    with c1:
        sector = st.selectbox("Nhóm ngành", sector_options, key="ma_structure_sector")
    with c2:
        query = st.text_input("Tìm mã hoặc tên công ty", key="ma_structure_search", placeholder="VD: VHM, Khang Điền, Đất Xanh")
    c3, c4 = st.columns(2)
    with c3:
        horizon = st.selectbox("Khung xu hướng", ["Tất cả", "Ngắn hạn", "Trung hạn", "Dài hạn"], key="ma_structure_horizon")
    with c4:
        status = st.selectbox("Trạng thái", ["Tất cả", TREND_UP, TREND_DOWN, TREND_OTHER, "Giá trên MA20", "Giá về gần MA20 (±2%)", "Giá về gần MA50 (±2%)", "MA10 cắt lên MA20"], key="ma_structure_status")
    # MIN_MA_TOP10_V1: rank verified same-session EOD before card-only filters.
    import ma_top10 as _ma_top10
    _ma_top10.render_top10(d, daily, asof, sector, groups)
    if sector != "Toàn thị trường":
        d = d[d["Mã"].isin(groups[sector])]
    if query.strip():
        q = query.strip().upper()
        d = d[d["Mã"].str.contains(q, regex=False) | d["Tên công ty"].str.upper().str.contains(q, regex=False)]
    if status in (TREND_UP, TREND_DOWN, TREND_OTHER) and horizon == "Tất cả":
        st.info("Chọn Ngắn hạn, Trung hạn hoặc Dài hạn để lọc theo trạng thái.")
    elif status in (TREND_UP, TREND_DOWN, TREND_OTHER):
        d = d[d[horizon] == status]
    elif status == "Giá trên MA20":
        d = d[d["Giá đóng cửa"] > d["MA20"]]
    elif "gần MA" in status:
        n = 20 if "MA20" in status else 50
        ma = d[f"MA{n}"]
        d = d[(ma > 0) & ((d["Giá đóng cửa"] / ma - 1).abs() <= .02)]
    elif status == "MA10 cắt lên MA20":
        # A cross requires previous-day values, not just latest MA ordering.
        if {"MA10", "MA20"}.issubset(daily.columns):
            prev = daily.copy()
            prev["Ngày"] = pd.to_datetime(prev["Ngày"], errors="coerce", dayfirst=True)
            prev = prev.sort_values(["Mã", "Ngày"])
            prev["prev10"] = pd.to_numeric(prev.groupby("Mã")["MA10"].shift(1), errors="coerce")
            prev["prev20"] = pd.to_numeric(prev.groupby("Mã")["MA20"].shift(1), errors="coerce")
            prev = prev.drop_duplicates("Mã", keep="last").set_index("Mã")
            good = prev[(prev["prev10"] <= prev["prev20"]) & (prev["MA10"] > prev["MA20"])].index
            d = d[d["Mã"].isin(good)]
        else:
            d = d.iloc[0:0]
    sort = st.selectbox("Sắp xếp", ["Mã A–Z", "Giá giảm dần", "Giá tăng dần", "Gần MA20 nhất"], key="ma_structure_sort")
    if sort == "Mã A–Z":
        d = d.sort_values("Mã")
    elif sort.startswith("Giá"):
        d = d.sort_values("Giá đóng cửa", ascending=sort.endswith("tăng dần"))
    else:
        d = d.assign(_distance=((d["Giá đóng cửa"] / d["MA20"] - 1).abs())).sort_values("_distance", na_position="last")
    st.caption(f"Hiển thị {len(d)} mã · giá và MA là cùng một nến ngày, không trộn giá DNSE intraday với MA EOD.")
    if d.empty:
        st.info("Không có mã phù hợp bộ lọc.")
        return
    limit = st.selectbox("Số mã hiển thị", [15, 30, 60, 100, "Tất cả"], key="ma_structure_limit")
    max_count = len(d) if limit == "Tất cả" else int(limit)
    visible = d.head(max_count)
    for offset in range(0, len(visible), 3):
        cols = st.columns(3, gap="small")
        for col, (_, row) in zip(cols, visible.iloc[offset:offset + 3].iterrows()):
            with col:
                _card(row, asof)
    st.caption("Lưu ý: MA là vùng tham khảo động, không đảm bảo hỗ trợ/kháng cự; không phải khuyến nghị mua bán.")
