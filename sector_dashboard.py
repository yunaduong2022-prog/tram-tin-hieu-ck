"""Phân tích sức mạnh ngành và luân chuyển dòng tiền từ dữ liệu OHLCV hiện có.

Các số liệu ngành dùng bình quân đều các cổ phiếu có dữ liệu trong ngành.
Nếu không có chuỗi VN-Index chuẩn trong dữ liệu đầu vào, RS được tính so với
proxy thị trường (trung vị hiệu suất các mã), và giao diện phải ghi rõ điều này.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import fund_guard as FG
import watchlist as WL

INDEX_NAMES = {"VNINDEX", "VN-INDEX", "VN_INDEX", "VNINDEXINDEX", "VNINDEX1", "^VNINDEX"}
PERIODS = {"1 phiên": 1, "1 tuần": 5, "1 tháng": 21, "3 tháng": 63}


def _clean(raw: pd.DataFrame) -> pd.DataFrame:
    if raw is None or raw.empty:
        return pd.DataFrame()
    d = raw.copy()
    required = {"Mã", "Ngày", "Giá đóng cửa"}
    if not required.issubset(d.columns):
        return pd.DataFrame()
    d["Mã"] = d["Mã"].astype(str).str.strip().str.upper()
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", dayfirst=True)
    d["Giá đóng cửa"] = pd.to_numeric(d["Giá đóng cửa"], errors="coerce")
    if "Khối lượng khớp lệnh" in d:
        d["Khối lượng khớp lệnh"] = pd.to_numeric(d["Khối lượng khớp lệnh"], errors="coerce")
    else:
        d["Khối lượng khớp lệnh"] = np.nan
    d = d.dropna(subset=["Mã", "Ngày", "Giá đóng cửa"])
    d = d[d["Giá đóng cửa"] > 0].sort_values(["Mã", "Ngày"])
    return d.drop_duplicates(["Mã", "Ngày"], keep="last")


def _returns_by_symbol(d: pd.DataFrame, sessions: int) -> pd.Series:
    """Return theo số phiên thị trường, chỉ nhận mã có đủ điểm đầu/cuối."""
    piv = d.pivot(index="Ngày", columns="Mã", values="Giá đóng cửa").sort_index()
    if len(piv) <= sessions:
        return pd.Series(dtype=float)
    start, end = piv.iloc[-sessions-1], piv.iloc[-1]
    valid = start.notna() & end.notna() & (start > 0)
    return ((end[valid] / start[valid] - 1) * 100).dropna()


def _benchmark_returns(d: pd.DataFrame, sessions: int, symbol_returns: pd.Series) -> tuple[float | None, str]:
    names = {str(x).strip().upper() for x in d["Mã"].unique()}
    index_symbol = next((x for x in names if x in INDEX_NAMES), None)
    if index_symbol:
        g = d[d["Mã"] == index_symbol].sort_values("Ngày")["Giá đóng cửa"]
        if len(g) > sessions and g.iloc[-sessions-1] > 0:
            return float((g.iloc[-1] / g.iloc[-sessions-1] - 1) * 100), f"VN-Index ({index_symbol})"
    # Không giả vờ đây là VN-Index: đây chỉ là proxy dựa trên trung vị các mã.
    if not symbol_returns.empty:
        return float(symbol_returns.median()), "trung vị rổ cổ phiếu (proxy, không phải VN-Index)"
    return None, "chưa đủ dữ liệu chỉ số tham chiếu"


def calculate_sector_metrics(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    d = _clean(raw)
    if d.empty:
        return pd.DataFrame(), {"error": "Không có dữ liệu giá hợp lệ."}

    all_dates = sorted(d["Ngày"].dropna().unique())
    latest = pd.Timestamp(all_dates[-1])
    session_count = len(all_dates)
    latest_by_symbol = d[d["Ngày"] == latest].set_index("Mã")
    available = set(d["Mã"].unique())
    all_symbols = [s for s in available if s not in INDEX_NAMES]
    rows = []
    benchmarks = {}
    for label, n in PERIODS.items():
        r = _returns_by_symbol(d[d["Mã"].isin(all_symbols)], n)
        benchmarks[label] = _benchmark_returns(d, n, r)

    for sector, configured_symbols in WL.GROUPS.items():
        symbols = list(dict.fromkeys(s.upper() for s in configured_symbols))
        members = [s for s in symbols if s in available and s not in INDEX_NAMES]
        returns = {}
        for label, n in PERIODS.items():
            sr = _returns_by_symbol(d[d["Mã"].isin(members)], n)
            # _returns_by_symbol returns series keyed by ticker; equal-weight return.
            returns[label] = float(sr.mean()) if not sr.empty else np.nan
        n_members = len(members)
        day_change = []
        above_ma20 = []
        turnover_today = []
        turnover_avg20 = []
        for symbol in members:
            g = d[d["Mã"] == symbol].sort_values("Ngày")
            close = g["Giá đóng cửa"].dropna()
            # Chỉ tính độ rộng/biến động phiên gần nhất nếu mã có dữ liệu đúng ngày thị trường mới nhất.
            current_session = not g.empty and pd.Timestamp(g["Ngày"].iloc[-1]) == latest
            if current_session and len(close) >= 2:
                day_change.append(float((close.iloc[-1] / close.iloc[-2] - 1) * 100))
            if current_session and len(close) >= 20:
                ma20 = float(close.tail(20).mean())
                above_ma20.append(bool(close.iloc[-1] > ma20))
            if "Khối lượng khớp lệnh" in g and g["Khối lượng khớp lệnh"].notna().any():
                g = g.copy()
                g["GTGD_xap_xi"] = g["Giá đóng cửa"] * g["Khối lượng khớp lệnh"]
                # So sánh cùng một tập mã đủ 20 phiên, tránh lệch mẫu số giữa hiện tại và trung bình.
                if current_session and len(g) >= 20 and g["GTGD_xap_xi"].tail(20).notna().all():
                    turnover_today.append(float(g.iloc[-1]["GTGD_xap_xi"]))
                    turnover_avg20.append(float(g["GTGD_xap_xi"].tail(20).mean()))
        breadth = (sum(x > 0 for x in day_change) / len(day_change) * 100) if day_change else np.nan
        above20_pct = float(np.mean(above_ma20) * 100) if above_ma20 else np.nan
        t_today = float(np.nansum(turnover_today)) if turnover_today else np.nan
        t_avg = float(np.nansum(turnover_avg20)) if turnover_avg20 else np.nan
        liquidity_ratio = (t_today / t_avg * 100) if pd.notna(t_today) and pd.notna(t_avg) and t_avg > 0 else np.nan
        rows.append({
            "Nhóm ngành": sector, "Số mã có dữ liệu": n_members,
            "Hiệu suất 1 phiên (%)": returns["1 phiên"],
            "Hiệu suất 1 tuần (%)": returns["1 tuần"],
            "Hiệu suất 1 tháng (%)": returns["1 tháng"],
            "Hiệu suất 3 tháng (%)": returns["3 tháng"],
            "Tăng giá phiên gần nhất (%)": float(np.mean(day_change)) if day_change else np.nan,
            "Độ rộng tăng giá (%)": breadth,
            "Trên MA20 (%)": above20_pct,
            "GTGD so TB20 (%)": liquidity_ratio,
            "Mã thành viên": ", ".join(members),
        })
    result = pd.DataFrame(rows)
    for label, col in [("1 phiên", "Hiệu suất 1 phiên (%)"), ("1 tuần", "Hiệu suất 1 tuần (%)"), ("1 tháng", "Hiệu suất 1 tháng (%)"), ("3 tháng", "Hiệu suất 3 tháng (%)")]:
        bench, source = benchmarks[label]
        result[f"RS {label} (điểm %) "] = result[col] - bench if bench is not None else np.nan
    if not result.empty:
        result["Xếp hạng RS 1 tháng"] = result["RS 1 tháng (điểm %) "].rank(ascending=False, method="min").astype("Int64")
        # Nhãn mô tả, không phải khuyến nghị mua/bán.
        rs = result["RS 1 tháng (điểm %) "]
        breadth = result["Độ rộng tăng giá (%)"]
        result["Trạng thái"] = np.select(
            [rs.notna() & breadth.notna() & (rs > 0) & (breadth >= 55),
             rs.notna() & (rs > 0),
             rs.notna() & (rs < 0)],
            ["Mạnh & đồng thuận", "Mạnh tương đối", "Yếu tương đối"], default="Chưa đủ dữ liệu")
    info = {
        "latest_date": latest,
        "sessions": session_count,
        "symbols": len(all_symbols),
        "benchmark": benchmarks,
        "turnover_available": d["Khối lượng khớp lệnh"].notna().any(),
        "has_index": any(str(x).strip().upper() in INDEX_NAMES for x in d["Mã"].unique()),
    }
    return result, info


def _fmt_pct(x, digits=1):
    return "—" if pd.isna(x) else f"{x:+.{digits}f}%"


def _num(v) -> float:
    try:
        x = float(v)
        return x if np.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _diff(now: float, avg: float) -> float:
    """Chênh lệch % của chỉ số hiện tại so với trung bình 3 năm."""
    return (now / avg - 1) * 100 if pd.notna(now) and pd.notna(avg) and avg > 0 and now > 0 else np.nan


def _weighted_mult(caps: list[float], vals: list[float]) -> float:
    """P/E, P/B của nhóm = tổng vốn hóa / tổng (vốn hóa / hệ số): bình quân điều hòa theo vốn hóa; bỏ mã thiếu số hoặc hệ số <= 0."""
    pairs = [(c, v) for c, v in zip(caps, vals) if pd.notna(c) and c > 0 and pd.notna(v) and v > 0]
    if not pairs:
        return np.nan
    return sum(c for c, _ in pairs) / sum(c / v for c, v in pairs)


VAL_COLS = ["Mã CP", "Vốn hóa (tỷ)", "Thanh khoản (CP)",
            "P/E hiện tại", "P/E TB 3 năm", "P/E chênh lệch",
            "P/B hiện tại", "P/B TB 3 năm", "P/B chênh lệch"]


def valuation_frame(sector: str, symbols: list[str], clean: pd.DataFrame, cap_map: dict, fund_map: dict) -> pd.DataFrame:
    """Bảng định giá ngành: dòng đầu là cả ngành, tiếp theo là từng mã (vốn hóa giảm dần).
    Thanh khoản = khối lượng khớp bình quân 20 phiên gần nhất (cổ phiếu)."""
    rows = []
    for sym in symbols:
        fd = fund_map.get(sym, {}) or {}
        g = clean[clean["Mã"] == sym].sort_values("Ngày")
        liq = np.nan
        if not g.empty and "Khối lượng khớp lệnh" in g and g["Khối lượng khớp lệnh"].notna().any():
            liq = float(g["Khối lượng khớp lệnh"].tail(20).mean())
        pe, pe3 = _num(fd.get("P/E")), _num(fd.get("P/E TB 3N"))
        pb, pb3 = _num(fd.get("P/B")), _num(fd.get("P/B TB 3N"))

        # Fallback dữ liệu P/E, P/B cho ngành cao su từ bảng xếp hạng Q3/26
        # khi fundamentals.csv chưa có số liệu. Không suy diễn trung bình 3 năm.
        if str(sector).strip().casefold() == "cao su" and (pd.isna(pe) or pd.isna(pb)):
            try:
                rubber = pd.read_csv("data/cao_su_q3_2026.csv", encoding="utf-8-sig", dtype={"Mã CP": str})
                if {"Mã CP", "P/E", "P/B", "Vốn hóa (tỷ đồng)"} <= set(rubber.columns):
                    rubber["Mã CP"] = rubber["Mã CP"].astype(str).str.strip().str.upper()
                    rubber["Vốn hóa (tỷ đồng)"] = pd.to_numeric(rubber["Vốn hóa (tỷ đồng)"], errors="coerce")
                    rubber = rubber[rubber["Vốn hóa (tỷ đồng)"] >= 1000]
                    match = rubber[rubber["Mã CP"] == str(sym).strip().upper()]
                    if not match.empty:
                        snapshot = match.iloc[0]
                        if pd.isna(pe):
                            pe = _num(snapshot.get("P/E"))
                        if pd.isna(pb):
                            pb = _num(snapshot.get("P/B"))
            except (OSError, ValueError, pd.errors.ParserError):
                pass

        rows.append({"Mã CP": sym, "Vốn hóa (tỷ)": _num(cap_map.get(sym)), "Thanh khoản (CP)": liq,
                     "P/E hiện tại": pe, "P/E TB 3 năm": pe3, "P/E chênh lệch": _diff(pe, pe3),
                     "P/B hiện tại": pb, "P/B TB 3 năm": pb3, "P/B chênh lệch": _diff(pb, pb3)})
    stocks = pd.DataFrame(rows, columns=VAL_COLS)
    if stocks.empty:
        return stocks
    stocks = stocks.sort_values("Vốn hóa (tỷ)", ascending=False, na_position="last").reset_index(drop=True)
    caps = stocks["Vốn hóa (tỷ)"].tolist()
    agg = {"Mã CP": f"{sector}", "Vốn hóa (tỷ)": float(stocks["Vốn hóa (tỷ)"].sum(skipna=True)) if stocks["Vốn hóa (tỷ)"].notna().any() else np.nan,
           "Thanh khoản (CP)": float(stocks["Thanh khoản (CP)"].sum(skipna=True)) if stocks["Thanh khoản (CP)"].notna().any() else np.nan}
    for key, now_col, avg_col, diff_col in (("P/E", "P/E hiện tại", "P/E TB 3 năm", "P/E chênh lệch"),
                                            ("P/B", "P/B hiện tại", "P/B TB 3 năm", "P/B chênh lệch")):
        agg[now_col] = _weighted_mult(caps, stocks[now_col].tolist())
        # TB 3 năm của ngành chỉ gộp các mã có đủ cả số hiện tại lẫn TB 3 năm, tránh lệch mẫu
        both = stocks[stocks[now_col].notna() & stocks[avg_col].notna()]
        agg[avg_col] = _weighted_mult(both["Vốn hóa (tỷ)"].tolist(), both[avg_col].tolist())
        agg[diff_col] = _diff(agg[now_col], agg[avg_col])
    return pd.concat([pd.DataFrame([agg], columns=VAL_COLS), stocks], ignore_index=True)



def _render_valuation(sector: str, symbols: list[str], clean: pd.DataFrame, cap_map: dict | None, fund_map: dict | None) -> None:
    st.markdown(f"**Định giá ngành {sector} — P/E, P/B hiện tại so với trung bình 3 năm**")
    if fund_map is None:
        fund_map = FG.load_fund_map()
    if cap_map is None:
        cap_map = {}
        try:
            md = pd.read_csv("data/stock_metadata.csv", dtype={"Mã": str})
            cap_map = dict(zip(md["Mã"].str.upper().str.strip(), pd.to_numeric(md["Vốn hóa TT"], errors="coerce")))
        except Exception:  # noqa: BLE001
            pass
    val = valuation_frame(sector, symbols, clean, cap_map, fund_map)
    if val.empty:
        st.info("Chưa có dữ liệu định giá cho các mã thuộc ngành này.")
        return
    if val[["P/E hiện tại", "P/B hiện tại"]].isna().all().all():
        st.info("Chưa có số P/E, P/B của các mã trong ngành này. Số liệu lấy từ data/fundamentals.csv (bot cập nhật) hoặc điền tay ở data/nhap_tay.csv.")
    fmt = {"Vốn hóa (tỷ)": "{:,.0f}", "Thanh khoản (CP)": "{:,.0f}",
           "P/E hiện tại": "{:,.1f}", "P/E TB 3 năm": "{:,.1f}", "P/E chênh lệch": "{:+.1f}%",
           "P/B hiện tại": "{:,.2f}", "P/B TB 3 năm": "{:,.2f}", "P/B chênh lệch": "{:+.1f}%"}

    def _tone(v):
        if pd.isna(v) or v == 0:
            return ""
        return "color:#25A879" if v > 0 else "color:#E5586A"

    styler = val.style.format(fmt, na_rep="—")
    _map = getattr(styler, "map", None) or styler.applymap
    styler = _map(_tone, subset=["P/E chênh lệch", "P/B chênh lệch"])
    styler = styler.apply(lambda r: ["color:#8B7CF6;font-weight:700" if r.name == 0 else "" for _ in r], axis=1)
    st.dataframe(styler, hide_index=True, use_container_width=True)
    st.caption("Dòng đầu là cả ngành: P/E, P/B ngành = tổng vốn hóa chia tổng (vốn hóa / hệ số) của các mã có số hợp lệ; TB 3 năm của ngành chỉ gộp các mã có đủ cả số hiện tại và TB 3 năm. "
               "Chênh lệch = hiện tại / TB 3 năm − 1. Thanh khoản = khối lượng khớp bình quân 20 phiên gần nhất; vốn hóa = giá mới nhất × số CP lưu hành. "
               "Ô hiện \"—\" là chưa có số trong data/fundamentals.csv hoặc data/nhap_tay.csv (cột P/E, P/B, P/E TB 3N, P/B TB 3N).")



def render(raw: pd.DataFrame, cap_map: dict | None = None, fund_map: dict | None = None):
    st.title("🏭 Tổng quan ngành")
    st.caption("Bản đồ dòng tiền giúp nhận diện nhanh nhóm ngành mạnh/yếu, sau đó xem sức mạnh tương đối và cổ phiếu dẫn dắt. Dữ liệu lấy từ nguồn giá đang được app sử dụng; không phải khuyến nghị mua/bán.")
    metrics, info = calculate_sector_metrics(raw)
    if metrics.empty:
        st.warning(info.get("error", "Chưa có dữ liệu để tính sức mạnh ngành."))
        st.info("Hãy tải dữ liệu cuối phiên, chọn file Excel hoặc bật nguồn Vnstock trong thanh bên.")
        return

    latest = info["latest_date"]
    st.caption(f"Ngày dữ liệu mới nhất: **{latest:%d/%m/%Y}** · {info['symbols']} mã cổ phiếu · {info['sessions']} phiên thị trường trong dữ liệu")
    if not info["has_index"]:
        st.warning("Dữ liệu hiện tại không có chuỗi VN-Index chuẩn. RS đang so với trung vị hiệu suất các mã có dữ liệu (proxy), không được hiểu là RS so với VN-Index. Để có RS chuẩn, cần bổ sung chuỗi VN-Index vào dữ liệu.")

    # Bản đồ ngành đặt ở đầu trang: dùng hiệu suất thực tế theo khung được chọn.
    st.subheader("🗺️ Bản đồ ngành — Tìm tiền đang chảy vào đâu")
    map_period = st.segmented_control(
        "Khung thời gian bản đồ", ["1 phiên", "1 tuần", "1 tháng", "3 tháng"],
        default="1 phiên", key="sector_map_period"
    ) or "1 phiên"
    map_col = {
        "1 phiên": "Tăng giá phiên gần nhất (%)",
        "1 tuần": "Hiệu suất 1 tuần (%)",
        "1 tháng": "Hiệu suất 1 tháng (%)",
        "3 tháng": "Hiệu suất 3 tháng (%)",
    }[map_period]
    map_view = metrics.sort_values(map_col, ascending=False, na_position="last")
    if map_view[map_col].notna().any():
        cards_per_row = 4
        sectors = map_view.to_dict("records")
        for start in range(0, len(sectors), cards_per_row):
            cols = st.columns(cards_per_row)
            for col, item in zip(cols, sectors[start:start + cards_per_row]):
                value = item.get(map_col, np.nan)
                sector_name = str(item["Nhóm ngành"])
                if pd.isna(value):
                    delta = "Chưa đủ dữ liệu"
                else:
                    delta = f"{float(value):+.2f}%"
                with col:
                    st.metric(sector_name, delta, delta_color="normal" if not pd.isna(value) else "off")
                    if st.button("Xem chi tiết", key=f"sector_map_open_{map_period}_{sector_name}", use_container_width=True):
                        st.session_state["sector_detail"] = sector_name
                        st.session_state["sector_map_focus"] = sector_name
        if st.session_state.get("sector_map_focus"):
            st.caption(f"Ngành được chọn từ bản đồ: **{st.session_state['sector_map_focus']}**. Xem phần chi tiết bên dưới.")
    else:
        st.info("Chưa đủ dữ liệu để hiển thị bản đồ ngành ở khung thời gian này.")

    st.divider()
    c1, c2, c3 = st.columns(3)
    for col, label in zip((c1, c2, c3), ("1 tuần", "1 tháng", "3 tháng")):
        bench, source = info["benchmark"][label]
        col.metric(f"Tham chiếu · {label}", _fmt_pct(bench))
        col.caption(source)

    period = st.segmented_control("Khung xếp hạng", list(PERIODS), default="1 tháng", key="sector_period") or "1 tháng"
    rs_col = f"RS {period} (điểm %) "
    perf_col = f"Hiệu suất {period} (%)"
    view = metrics.copy()
    view = view.sort_values(rs_col, ascending=False, na_position="last")
    st.subheader("Xếp hạng ngành")
    st.caption("RS ngành = hiệu suất bình quân đều các mã trong ngành trừ hiệu suất tham chiếu cùng kỳ. Các ngành có ít mã hợp lệ cần được diễn giải thận trọng.")
    show = view[["Nhóm ngành", "Số mã có dữ liệu", perf_col, rs_col, "Độ rộng tăng giá (%)", "Trên MA20 (%)", "GTGD so TB20 (%)", "Trạng thái"]].rename(columns={
        perf_col: f"Hiệu suất {period}", rs_col: f"RS {period} (điểm %)",
        "Độ rộng tăng giá (%)": "Mã tăng phiên gần nhất (%)", "Trên MA20 (%)": "Trên MA20 (%)",
        "GTGD so TB20 (%)": "GTGD / TB20 (%)"})
    st.dataframe(show, hide_index=True, use_container_width=True, column_config={
        f"Hiệu suất {period}": st.column_config.NumberColumn(format="%+.2f%%"),
        f"RS {period} (điểm %)": st.column_config.NumberColumn(format="%+.2f"),
        "Mã tăng phiên gần nhất (%)": st.column_config.NumberColumn(format="%.1f%%"),
        "Trên MA20 (%)": st.column_config.NumberColumn(format="%.1f%%"),
        "GTGD / TB20 (%)": st.column_config.NumberColumn(format="%.0f%%"),
    })

    st.subheader("Chi tiết từng ngành")
    sector_options = view["Nhóm ngành"].tolist()
    preferred = st.session_state.get("sector_detail")
    if preferred not in sector_options:
        preferred = sector_options[0] if sector_options else None
    chosen = st.selectbox("Chọn ngành", sector_options, index=sector_options.index(preferred) if preferred else 0, key="sector_detail")
    row = metrics[metrics["Nhóm ngành"] == chosen].iloc[0]
    a, b, c, e = st.columns(4)
    a.metric("Hiệu suất 1 tuần", _fmt_pct(row["Hiệu suất 1 tuần (%)"]))
    b.metric("Hiệu suất 1 tháng", _fmt_pct(row["Hiệu suất 1 tháng (%)"]))
    c.metric("Hiệu suất 3 tháng", _fmt_pct(row["Hiệu suất 3 tháng (%)"]))
    e.metric("RS 1 tháng", _fmt_pct(row["RS 1 tháng (điểm %) "]))
    a, b, c = st.columns(3)
    a.metric("Độ rộng tăng phiên gần nhất", _fmt_pct(row["Độ rộng tăng giá (%)"]))
    b.metric("Tỷ lệ trên MA20", _fmt_pct(row["Trên MA20 (%)"]))
    c.metric("GTGD so với TB20", _fmt_pct(row["GTGD so TB20 (%)"], 0))
    symbols = [s for s in row["Mã thành viên"].split(", ") if s]
    d = _clean(raw)
    stock_rows = []
    for symbol in symbols:
        g = d[d["Mã"] == symbol].sort_values("Ngày")
        if g.empty:
            continue
        close = g["Giá đóng cửa"]
        item = {"Mã": symbol, "Giá đóng cửa": float(close.iloc[-1]), "Ngày": g["Ngày"].iloc[-1]}
        for label, n in PERIODS.items():
            item[label] = float((close.iloc[-1] / close.iloc[-n-1] - 1) * 100) if len(close) > n and close.iloc[-n-1] else np.nan
        if len(close) >= 20:
            item["Trên MA20"] = "Có" if close.iloc[-1] > close.tail(20).mean() else "Không"
        else:
            item["Trên MA20"] = "Thiếu dữ liệu"
        stock_rows.append(item)
    stock_df = pd.DataFrame(stock_rows)
    if not stock_df.empty:
        stock_df = stock_df.sort_values("1 tháng", ascending=False, na_position="last")
        st.markdown("**Cổ phiếu trong ngành — xếp theo hiệu suất 1 tháng**")
        st.dataframe(stock_df, hide_index=True, use_container_width=True, column_config={
            "Giá đóng cửa": st.column_config.NumberColumn(format="%.2f"),
            "1 phiên": st.column_config.NumberColumn(format="%+.2f%%"),
            "1 tuần": st.column_config.NumberColumn(format="%+.2f%%"),
            "1 tháng": st.column_config.NumberColumn(format="%+.2f%%"),
            "3 tháng": st.column_config.NumberColumn(format="%+.2f%%"),
        })
    else:
        st.info("Chưa có dữ liệu giá cho các mã thuộc ngành này.")
    _render_valuation(chosen, symbols, d, cap_map, fund_map)
    st.caption("Lưu ý: hiệu suất ngành hiện tính bình quân đều các mã có dữ liệu, chưa phải chỉ số ngành theo vốn hóa. GTGD xấp xỉ = giá đóng cửa × khối lượng, dùng để so sánh tương đối; không thay thế giá trị giao dịch chính thức. Dữ liệu ngắn hơn kỳ đo sẽ hiển thị thiếu thay vì tự suy diễn.")
