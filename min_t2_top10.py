"""Read-only Top 10 T+2 EOD candidates, independent of display filters.

A technical screening shortlist, not executable advice. Uses only the full
market scan and daily OHLCV through the selected asof. Never writes orders.
"""
from __future__ import annotations

import html
import numpy as np
import pandas as pd

AGE_LIMIT = 5
MIN_VOL_RATIO = 1.10
MIN_UPSIDE_PCT = 5.0
MIN_RR = 2.0


def _number(value):
    x = pd.to_numeric(value, errors="coerce")
    try:
        return float(x) if pd.notna(x) and np.isfinite(float(x)) else np.nan
    except (TypeError, ValueError):
        return np.nan


def rank_top10(history, daily, asof, max_results=10):
    """Select one recent eligible buy setup per ticker and rank it (0..100).

    Conservative exclusions: missing/invalid daily bars, mismatched EOD,
    missing sessions since the event, original stop touched after signal,
    weak present EOD, no valid overhead target, or unappealing current R:R.
    This does not claim a purchase occurred or model dynamic-stop fills.
    """
    columns = ["Hạng", "Mã", "Điểm T+", "Loại tín hiệu", "Tuổi", "Giá EOD", "Vol/TB20 EOD",
               "RSI14 EOD", "Position", "TP1 động", "Dư địa TP1", "R:R EOD", "Nhận định"]
    if history is None or history.empty or daily is None or daily.empty:
        return pd.DataFrame(columns=columns)
    needed = {"Mã", "Ngày tín hiệu", "Phiên từ tín hiệu", "Giá EOD", "Giá tín hiệu",
              "Cắt lỗ tham khảo", "Mục tiêu 1", "Tín hiệu"}
    required_daily = {"Mã", "Ngày", "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất",
                      "Giá đóng cửa", "Khối lượng khớp lệnh"}
    if not needed.issubset(history.columns) or not required_daily.issubset(daily.columns):
        return pd.DataFrame(columns=columns)
    h = history.copy()
    h["Phiên từ tín hiệu"] = pd.to_numeric(h["Phiên từ tín hiệu"], errors="coerce")
    h = h[h["Phiên từ tín hiệu"].between(0, AGE_LIMIT)].copy()
    if h.empty:
        return pd.DataFrame(columns=columns)
    h["Ngày tín hiệu"] = pd.to_datetime(h["Ngày tín hiệu"], errors="coerce").dt.normalize()
    h = h.dropna(subset=["Ngày tín hiệu"])
    asof_day = pd.Timestamp(asof).normalize()
    d = daily.copy()
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce").dt.normalize()
    d = d.loc[d["Ngày"].notna() & (d["Ngày"] <= asof_day)]
    market_days = set(d["Ngày"])
    grouped = {str(k): g.sort_values("Ngày") for k, g in d.groupby("Mã", sort=False)}
    # Same dynamic TP calculation as the main Trading T+2 table, but only for
    # recent candidates. Do not modify the original cached scan dataframe.
    from min_t2_swing import _add_dynamic_targets, _indicators
    h = _add_dynamic_targets(h, daily, 3.0)
    records = []
    for _, r in h.iterrows():
        code = str(r["Mã"]).upper()
        bars = grouped.get(code)
        if bars is None or len(bars) < 51 or bars.iloc[-1]["Ngày"] != asof_day:
            continue
        if bars["Ngày"].duplicated().any():
            continue
        event_day = r["Ngày tín hiệu"]
        window = bars.loc[bars["Ngày"] >= event_day]
        if window.empty or window.iloc[0]["Ngày"] != event_day:
            continue
        if market_days.intersection(set(pd.date_range(event_day, asof_day, freq="D"))) - set(window["Ngày"]):
            # A ticker can be suspended; without trustworthy complete EOD,
            # don't claim a stop/TP history is safe for a buy shortlist.
            continue
        values = window[["Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"]].apply(pd.to_numeric, errors="coerce")
        if not (values.notna().all().all() and (values["Giá thấp nhất"] > 0).all()
                and (values["Giá cao nhất"] >= values["Giá thấp nhất"]).all()
                and ((values["Giá đóng cửa"] >= values["Giá thấp nhất"]) & (values["Giá đóng cửa"] <= values["Giá cao nhất"])).all()
                and ((values["Giá mở cửa"] >= values["Giá thấp nhất"]) & (values["Giá mở cửa"] <= values["Giá cao nhất"])).all()
                and (values["Khối lượng khớp lệnh"] >= 0).all()):
            continue
        entry = _number(r["Giá tín hiệu"])
        price = _number(r["Giá EOD"])
        stop_orig = _number(r.get("Cắt lỗ gốc", r.get("Cắt lỗ tham khảo")))
        stop_active = _number(r["Cắt lỗ tham khảo"])
        tp1 = _number(r["Mục tiêu 1"])
        if not all(np.isfinite(x) for x in (price, entry, stop_orig, stop_active, tp1)):
            continue
        if not (0 < stop_orig < entry and 0 < stop_active < price < tp1):
            continue
        if len(window) > 1 and (values.iloc[1:]["Giá thấp nhất"] <= stop_orig).any():
            continue
        # EOD technical indicators are computed through asof, not signal day.
        g = _indicators(bars)
        row = g.iloc[-1]
        prior = g.iloc[-2]
        eod_close = _number(row["Giá đóng cửa"])
        o = _number(row["Giá mở cửa"])
        ma9 = _number(row["MA9"])
        ma20 = _number(row["MA20"])
        ma50 = _number(row["MA50"])
        vol = _number(row["VolRatio"])
        pos = _number(row["ClosePos"])
        rsi = _number(row["RSI14"])
        prev_close = _number(prior["Giá đóng cửa"])
        if not all(np.isfinite(x) for x in (eod_close, o, ma9, ma20, vol, pos, rsi, prev_close)):
            continue
        if abs(eod_close - price) > .011:
            continue
        if not (price >= ma20 and price >= ma9 and price <= ma9 * 1.08
                and price >= o and price > prev_close and pos >= .60
                and vol >= MIN_VOL_RATIO and 45 <= rsi <= 78):
            continue
        upside = (tp1 / price - 1) * 100
        rr = (tp1 - price) / (price - stop_active)
        if upside < MIN_UPSIDE_PCT or rr < MIN_RR or not np.isfinite(rr):
            continue
        # Transparent composite: MA 25, RSI 20, volume 20, candle 20,
        # room/risk 15. RSI is not falsely presented as market-relative RS20.
        trend_score = (10 if price > ma9 else 0) + (10 if price > ma20 else 0) + (5 if np.isfinite(ma50) and price > ma50 else 0)
        rsi_score = 20 * max(0., 1 - abs(rsi - 62) / 30)
        vol_score = 20 * min(max((vol - 1) / 1.5, 0), 1)
        candle_score = 10 * min(max((pos - .5) / .5, 0), 1) + 10 * min(max((price / o - 1) / .04, 0), 1)
        reward_score = 7.5 * min(upside / 12, 1) + 7.5 * min(rr / 4, 1)
        score = round(trend_score + rsi_score + vol_score + candle_score + reward_score, 1)
        records.append({"Mã": code, "Điểm T+": score, "Loại tín hiệu": str(r["Tín hiệu"]),
                        "Tuổi": "T+" + str(int(r["Phiên từ tín hiệu"])),
                        "Giá EOD": round(price, 2), "Vol/TB20 EOD": round(vol, 2),
                        "RSI14 EOD": round(rsi, 1), "Position": round(pos * 100, 1),
                        "TP1 động": round(tp1, 2), "Dư địa TP1": round(upside, 1),
                        "R:R EOD": round(rr, 2),
                        "Nhận định": "Đạt bộ lọc kỹ thuật · Chưa phải lệnh mua",
                        "_day": event_day})
    if not records:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(records)
    result = result.sort_values(["Điểm T+", "_day", "Mã"], ascending=[False, False, True])
    result = result.drop_duplicates("Mã", keep="first").head(max_results).reset_index(drop=True)
    result.insert(0, "Hạng", np.arange(1, len(result) + 1))
    return result[columns]


def render_top10(history, daily, asof):
    import streamlit as st
    st.markdown("### TOP 10 CỔ PHIẾU MẠNH CÓ TÍN HIỆU MUA T+2")
    st.caption("Xếp hạng độc lập các bộ lọc bên dưới · EOD " + pd.Timestamp(asof).strftime("%d/%m/%Y") +
               " · T+0–T+5 · Không phải khuyến nghị mua tự động")
    leaders = rank_top10(history, daily, asof)
    if leaders.empty:
        st.info("Hiện không có mã đáp ứng đồng thời tín hiệu mua mới, xu hướng, khối lượng, vùng mua và R:R. Không bổ sung mã chỉ để đủ Top 10.")
        return
    show = leaders.copy()
    show["Vol/TB20 EOD"] = show["Vol/TB20 EOD"].map(lambda x: f"{x:.2f}x")
    show["Dư địa TP1"] = show["Dư địa TP1"].map(lambda x: f"{x:.1f}%")
    show["Position"] = show["Position"].map(lambda x: f"{x:.0f}%")
    st.dataframe(show, hide_index=True, use_container_width=True, height=min(430, 70 + 36 * len(show)))
    with st.expander("Điều kiện Top 10 và cách tính điểm"):
        st.write("Chỉ lấy tín hiệu T+0–T+5, giá trên MA9/MA20, nến tăng và đóng cửa ở ≥60% biên độ, Vol/TB20 EOD ≥1.1x, RSI14 EOD 45–78, giá không quá 8% trên MA9, còn dư địa TP1 ≥5%, R:R EOD ≥2, chưa chạm cắt lỗ gốc theo dữ liệu có sẵn.")
        st.write("Điểm 100 = MA 25 + RSI14 20 + Volume 20 + chất lượng nến 20 + dư địa/R:R 15. Đây là điểm xếp hạng T+ riêng, không phải điểm MA hoặc RS20 của các tab khác. Không xác nhận lệnh mua đã khớp.")
