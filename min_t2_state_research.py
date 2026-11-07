"""Historical, descriptive T+2 signal outcome by EOD MA regime at signal date.

Research only: do not confuse subsequent close-to-close changes with tradable
returns or market-state tab's current-day classification. No future leakage.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (2, 5, 10, 15, 20, 30)
REGIMES = ("TÍCH LŨY", "HỒI PHỤC", "TĂNG MẠNH", "SUY YẾU", "PHÂN HÓA", "CHƯA ĐỦ DỮ LIỆU")


def _classify_at_event(g, i):
    """MA context through the event date (inclusive), NEVER from current EOD."""
    if i < 49:
        return "CHƯA ĐỦ DỮ LIỆU"
    c = g["Giá đóng cửa"].iloc[:i + 1].astype(float)
    if c.isna().any() or (c <= 0).any():
        return "CHƯA ĐỦ DỮ LIỆU"
    ma20 = c.iloc[-20:].mean()
    ma50 = c.iloc[-50:].mean()
    prior_ma20 = c.iloc[-25:-5].mean()  # 20-bar SMA five sessions before event
    close = c.iloc[-1]
    lo20, hi20 = c.iloc[-20:].min(), c.iloc[-20:].max()
    if not all(np.isfinite(x) and x > 0 for x in (ma20, ma50, prior_ma20, close, lo20)):
        return "CHƯA ĐỦ DỮ LIỆU"
    slope = ma20 / prior_ma20 - 1
    spread = abs(ma20 / ma50 - 1)
    tight = hi20 / lo20 - 1
    if (spread <= .05 and abs(close / ma20 - 1) <= .07 and
            tight <= .18 and abs(slope) <= .025):
        return "TÍCH LŨY"
    if close > ma20 > ma50 and slope > .008:
        return "TĂNG MẠNH"
    if close >= ma20 and slope > 0 and (ma20 <= ma50 * 1.025 or c.iloc[-6] <= c.iloc[-25:-5].mean()):
        return "HỒI PHỤC"
    if close < ma20 and (slope < 0 or close < ma50):
        return "SUY YẾU"
    return "PHÂN HÓA"


def event_regimes(history, daily, asof):
    """Return one label per actual event from actual signal-date EOD bars.

    Strictly require unique event date, valid price series, and complete date
    continuity against the ticker's own observed sessions. A missing day can't
    be inferred; these categories are descriptive rather than verified trades.
    """
    if history is None or history.empty or daily is None or daily.empty:
        return pd.DataFrame()
    need_h = {"Mã", "Ngày tín hiệu", "Tín hiệu"}
    need_d = {"Mã", "Ngày", "Giá đóng cửa"}
    if not need_h.issubset(history) or not need_d.issubset(daily):
        return pd.DataFrame()
    end = pd.Timestamp(asof).normalize()
    h = history.copy()
    h["Ngày tín hiệu"] = pd.to_datetime(h["Ngày tín hiệu"], errors="coerce", dayfirst=True).dt.normalize()
    h["Mã"] = h["Mã"].astype(str).str.upper().str.strip()
    h = h[h["Ngày tín hiệu"].notna() & (h["Ngày tín hiệu"] <= end)].copy()
    if h.empty:
        return pd.DataFrame()
    d = daily[["Mã", "Ngày", "Giá đóng cửa"]].copy()
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", dayfirst=True).dt.normalize()
    d["Giá đóng cửa"] = pd.to_numeric(d["Giá đóng cửa"], errors="coerce")
    d = d[d["Ngày"].notna() & (d["Ngày"] <= end)].sort_values(["Mã", "Ngày"])
    lookup = {}
    for code, g in d.groupby("Mã", sort=False):
        if g["Ngày"].duplicated().any():
            continue
        g = g.reset_index(drop=True)
        lookup[code] = (g, {v: k for k, v in enumerate(g["Ngày"])})
    labels = []
    for code, day in zip(h["Mã"], h["Ngày tín hiệu"]):
        item = lookup.get(code)
        if item is None or day not in item[1]:
            labels.append("CHƯA ĐỦ DỮ LIỆU")
        else:
            g, positions = item
            labels.append(_classify_at_event(g, positions[day]))
    h["Trạng thái MA tại tín hiệu"] = labels
    return h


def regime_stats(events, horizon=5, min_samples=20):
    """All eligible completed horizons; no imputation for unfinished events."""
    label = f"T+{int(horizon)} (%)"
    cols = ["Tín hiệu", "Trạng thái MA tại tín hiệu", "Số mẫu", "Tỷ lệ tăng (%)", "Trung vị (%)", "TB (%)", "P25 (%)", "P75 (%)", "Độ tin cậy mẫu"]
    if events is None or events.empty or label not in events:
        return pd.DataFrame(columns=cols)
    d = events[["Tín hiệu", "Trạng thái MA tại tín hiệu", label]].copy()
    d[label] = pd.to_numeric(d[label], errors="coerce")
    d = d.replace([np.inf, -np.inf], np.nan).dropna(subset=[label])
    if d.empty:
        return pd.DataFrame(columns=cols)
    records = []
    for (signal, regime), g in d.groupby(["Tín hiệu", "Trạng thái MA tại tín hiệu"], sort=True):
        x = g[label]
        n = len(x)
        records.append({"Tín hiệu": signal, "Trạng thái MA tại tín hiệu": regime,
                        "Số mẫu": n, "Tỷ lệ tăng (%)": round(float((x > 0).mean() * 100), 1),
                        "Trung vị (%)": round(float(x.median()), 2),
                        "TB (%)": round(float(x.mean()), 2),
                        "P25 (%)": round(float(x.quantile(.25)), 2),
                        "P75 (%)": round(float(x.quantile(.75)), 2),
                        "Độ tin cậy mẫu": "Mẫu nhỏ – tham khảo" if n < min_samples else "Đủ ngưỡng mẫu mô tả"})
    return pd.DataFrame(records, columns=cols).sort_values(["Số mẫu", "Tín hiệu"], ascending=[False, True]).reset_index(drop=True)


def render_state_research(history, daily, asof):
    import streamlit as st
    st.subheader("Kiểm chứng tín hiệu T+2 theo trạng thái MA lịch sử")
    st.caption("Trạng thái MA tính tại NGÀY TÍN HIỆU (không dùng trạng thái EOD hiện nay). Đây là thống kê quan sát từ tín hiệu lịch sử trong cửa sổ quét, không phải backtest lệnh mua/bán.")
    with st.expander("Xem thống kê theo tín hiệu × trạng thái MA", expanded=False):
        c1, c2 = st.columns([1, 2])
        with c1:
            horizon = st.selectbox("Mốc sau tín hiệu", HORIZONS, format_func=lambda x: f"T+{x} phiên", key="t2_state_research_h")
        with c2:
            minimum = st.selectbox("Ngưỡng mẫu tham khảo", [10, 20, 30, 50], index=1, key="t2_state_research_min")
        events = event_regimes(history, daily, asof)
        report = regime_stats(events, horizon=horizon, min_samples=minimum)
        if report.empty:
            st.info("Chưa có mẫu tín hiệu hoàn thành mốc được chọn. Không suy diễn kết quả từ dữ liệu thiếu.")
            return
        st.dataframe(report, hide_index=True, use_container_width=True)
        st.caption("Nhóm: TÍCH LŨY (MA20/MA50 sát nhau, biên độ hẹp), HỒI PHỤC (trở lên MA20, động lượng cải thiện), TĂNG MẠNH (Giá > MA20 > MA50 và MA20 dốc lên), SUY YẾU (dưới MA20 và động lượng kém), PHÂN HÓA (khác), CHƯA ĐỦ DỮ LIỆU. Ngưỡng là quy tắc nghiên cứu, không phải chính nhãn Bản đồ trạng thái hiện tại.")
        st.caption("Tỷ lệ tăng = phần trăm mẫu có GIÁ ĐÓNG CỬA T+h > giá đóng cửa tín hiệu. Không tính phí/thuế, trượt giá, khớp lệnh hay quyền bán T+2. Chỉ dùng mẫu đủ h phiên, mẫu nhỏ dễ nhiễu; không kết luận một loại tín hiệu tốt hơn nếu chưa kiểm định ngoài mẫu và theo thời kỳ.")
