"""Read-only, same-EOD cross-tab context for a single T+2 ticker.

Reuse MA and State Map's EXISTING classifiers: never classify the ticker again.
No trades, API calls, cached price rewriting, or modifications to screening.
"""
from __future__ import annotations

import pandas as pd


def build_context(code, daily, wb, screener, index_daily, asof, groups):
    import ma_structure_view as MAV
    import state_map_view as SMV

    symbol = str(code).strip().upper()
    asof_day = pd.Timestamp(asof).normalize()
    snapshot = MAV.snapshot(daily)
    if snapshot.empty:
        return None
    matches = snapshot[snapshot["Mã"] == symbol]
    if len(matches) != 1:
        return None
    ma = matches.iloc[0]
    ma_date = pd.Timestamp(ma["Ngày"]).normalize()
    if ma_date != asof_day:
        # Do not combine a stale MA snapshot with an up-to-date T+2 row.
        return None

    # Narrow WB input to the one symbol: build() still evaluates its MA/RS
    # on the full EOD universe, exactly as the original State Map tab does.
    state = None
    if wb is not None and not wb.empty and "Mã" in wb.columns:
        one = wb[wb["Mã"].astype(str).str.upper().str.strip() == symbol]
        if not one.empty:
            table = SMV.build(one, screener, daily, index_daily, asof_day, groups)
            if not table.empty:
                row = table[table["Mã"] == symbol]
                if len(row) == 1:
                    state = row.iloc[0]

    def value(src, key):
        return src.get(key) if src is not None else None

    group = value(state, "Nhóm gốc")
    state_label = next((label for group_key, label in SMV.DISPLAY_GROUPS if group_key == group), "Chưa có phân nhóm")

    # Never combine mismatched EOD prices from independent panels.
    state_price = pd.to_numeric(value(state, "Giá EOD"), errors="coerce")
    ma_price = pd.to_numeric(value(ma, "Giá đóng cửa"), errors="coerce")
    state_valid = (pd.notna(state_price) and pd.notna(ma_price)
                   and abs(float(state_price) - float(ma_price)) <= 0.011)
    if not state_valid:
        state_label = "Chưa có dữ liệu đồng nhất"
        state = None

    return {
        "code": symbol,
        "asof": asof_day,
        "price": float(ma_price),
        "ma_short": value(ma, "Ngắn hạn"),
        "ma_medium": value(ma, "Trung hạn"),
        "ma_long": value(ma, "Dài hạn"),
        "ma100": value(ma, "MA100"),
        "ma200": value(ma, "MA200"),
        "state_label": state_label,
        "action": value(state, "Hành động"),
        "rs20": value(state, "RS20 (%)"),
        "ma_score": value(state, "Điểm MA /100"),
        "near_resistance": value(state, "Kháng cự"),
    }


# MIN_T2_EOD_VOLUME_CONTEXT_V1

def _eod_volume_context(daily, code, asof):
    """Latest completed EOD close/volume vs the PREVIOUS 20 bars, no lookahead.

    Returns None on missing/incomplete/mismatched as-of data. The source is
    exactly the prepared T+2 daily bars, never signal-day volume or realtime.
    """
    import numpy as np
    import pandas as pd
    required = {"Mã", "Ngày", "Giá đóng cửa", "Giá mở cửa", "Giá cao nhất",
                "Giá thấp nhất", "Khối lượng khớp lệnh"}
    if daily is None or daily.empty or not required.issubset(daily.columns):
        return None
    g = daily[daily["Mã"].astype(str).str.upper().str.strip() == str(code).upper()].copy()
    if len(g) < 21:
        return None
    g["Ngày"] = pd.to_datetime(g["Ngày"], errors="coerce").dt.normalize()
    g = g.dropna(subset=["Ngày"]).sort_values("Ngày").drop_duplicates("Ngày", keep="last")
    asof_day = pd.Timestamp(asof).normalize()
    g = g[g["Ngày"] <= asof_day]
    if len(g) < 21 or g.iloc[-1]["Ngày"] != asof_day:
        return None
    tail = g.iloc[-21:]
    volumes = pd.to_numeric(tail["Khối lượng khớp lệnh"], errors="coerce")
    o, h, l, c = [pd.to_numeric(tail.iloc[-1][col], errors="coerce") for col in
                  ("Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa")]
    previous_close = pd.to_numeric(tail.iloc[-2]["Giá đóng cửa"], errors="coerce")
    prior = volumes.iloc[:-1]
    if (not np.all(np.isfinite(prior)) or (prior < 0).any() or
            not all(pd.notna(x) and np.isfinite(float(x)) for x in (o, h, l, c, previous_close, volumes.iloc[-1])) or
            float(prior.mean()) <= 0 or float(volumes.iloc[-1]) < 0 or
            float(c) <= 0 or float(previous_close) <= 0 or float(h) < float(l)):
        return None
    # MIN_T2_EOD_CANDLE_EXPLAIN_V1: use the SAME close-location definition
    # as engine.Position_% and T2.ClosePos; do not mutate signal logic.
    high, low, opened, close = map(float, (h, l, o, c))
    if low <= 0 or not (low <= min(opened, close) <= max(opened, close) <= high):
        return None  # malformed OHLC: do not infer buying/selling pressure
    candle_range = high - low
    pos = (close - low) / candle_range if candle_range > 0 else 0.5
    range_pct = (candle_range / low * 100.0) if candle_range > 0 else 0.0
    upper_wick = (high - max(opened, close)) / candle_range * 100.0 if candle_range > 0 else 0.0
    lower_wick = (min(opened, close) - low) / candle_range * 100.0 if candle_range > 0 else 0.0
    # MIN_T2_EOD_BODY_RANGE_V1: physical candle body, excluding wicks.
    body_pct = abs(close - opened) / candle_range * 100.0 if candle_range > 0 else 0.0
    return {"vol_ratio": float(volumes.iloc[-1] / prior.mean()), "close": close,
            "prev_close": float(previous_close), "open": opened,
            "close_pos": pos, "range_pct": range_pct,
            "upper_wick_pct": upper_wick, "lower_wick_pct": lower_wick,
            "body_pct": body_pct, "flat_candle": candle_range == 0.0}


def _t2_trade_assessment(context, latest, volume):
    """Context label only; never changes scan, original state map, or orders."""
    import numpy as np
    import pandas as pd
    age = pd.to_numeric(latest.get("Phiên từ tín hiệu"), errors="coerce")
    if pd.isna(age) or not 0 <= float(age) <= 15:
        return "Tín hiệu lịch sử · Không đánh giá mua mới"
    if not volume:
        return "Chưa đủ dữ liệu khối lượng EOD"
    price = float(volume["close"])
    tp = pd.to_numeric(latest.get("Mục tiêu 1"), errors="coerce")
    rr = pd.to_numeric(latest.get("R:R TP1"), errors="coerce")
    # For T+0..15 displayed R:R must use active TP/stop and EOD, not original R:R.
    age = pd.to_numeric(latest.get("Phiên từ tín hiệu"), errors="coerce")
    stop = pd.to_numeric(latest.get("Cắt lỗ tham khảo"), errors="coerce")
    if pd.notna(age) and 0 <= float(age) <= 15:
        rr = (float(tp)-price)/(price-float(stop)) if (pd.notna(tp) and pd.notna(stop) and
             np.isfinite([float(tp),float(stop)]).all() and float(stop)<price<float(tp)) else np.nan
    upside = (float(tp)/price-1)*100 if pd.notna(tp) and np.isfinite(float(tp)) and float(tp)>price else np.nan
    worthy = np.isfinite(upside) and upside >= 5 and pd.notna(rr) and np.isfinite(float(rr)) and float(rr) >= 2
    vr = volume["vol_ratio"]
    bullish = price > volume["prev_close"] and price >= volume["open"] and volume["close_pos"] >= 0.6
    near = pd.to_numeric(context.get("near_resistance"), errors="coerce")
    at_barrier = pd.notna(near) and np.isfinite(float(near)) and price <= float(near)
    broken = (pd.notna(near) and np.isfinite(float(near)) and
              volume["prev_close"] <= float(near) < price)
    if vr >= 1.5 and price < volume["open"] and volume["close_pos"] <= 0.35:
        return "Cảnh báo áp lực bán EOD"
    if worthy and bullish and vr >= 1.5 and broken:
        return "Xác nhận giá–khối lượng · Xem xét điểm mua T+"
    if worthy and bullish and vr >= 1.2:
        return "Có dư địa T+ · Chờ xác nhận vượt cản" if at_barrier else "Dòng tiền tích cực · Theo dõi điểm mua"
    if worthy and broken and vr < 1.0:
        return "Vượt cản nhưng khối lượng chưa xác nhận"
    if worthy:
        # High volume ≠ buying pressure. Make the candle reason explicit.
        if vr >= 1.5 and volume.get("flat_candle"):
            return "Có dư địa T+ · Nến một giá, chưa xác nhận lực mua"
        if vr >= 1.5 and volume["close_pos"] < 0.60:
            return "Có dư địa T+ · Khối lượng cao nhưng đóng cửa chưa mạnh"
        if vr >= 1.5 and price <= volume["prev_close"]:
            return "Có dư địa T+ · Khối lượng cao nhưng giá chưa tăng"
        if vr >= 1.5 and price < volume["open"]:
            return "Có dư địa T+ · Khối lượng cao nhưng nến đỏ"
        return "Có dư địa T+ · Chưa đủ xác nhận giá–khối lượng"
    return "Chưa đủ điều kiện T+ theo dư địa và R:R"


# MIN_T2_EOD_BODY_RANGE_V1

def _t2_body_label(volume):
    """Descriptive shape, NOT inferred order flow or a buy/sell signal."""
    if not volume:
        return "Chưa đủ dữ liệu nến"
    if volume.get("flat_candle"):
        return "Nến một giá · Không xác nhận lực mua/bán"
    body = float(volume["body_pct"])
    close, opened = float(volume["close"]), float(volume["open"])
    if body < 25:
        return "Thân nhỏ · Giằng co"  # includes a doji, regardless of tiny color
    direction = "Nến xanh" if close > opened else "Nến đỏ" if close < opened else "Nến trung tính"
    strength = "thân lớn" if body >= 60 else "thân vừa"
    return f"{direction} {strength}"


def _t2_candle_explanation(volume):
    """Read-only human explanation of the most recent finished EOD candle."""
    if not volume:
        return "Chưa đủ dữ liệu nến EOD."
    if volume.get("flat_candle"):
        return "Nến một giá: không thể suy ra ưu thế bên mua chỉ từ vị trí đóng cửa."
    pos = float(volume["close_pos"]) * 100.0
    wick = float(volume["upper_wick_pct"])
    vr = float(volume["vol_ratio"])
    if pos <= 35 and vr >= 1.5:
        return f"Đóng cửa thấp trong biên độ ({pos:.0f}%) dù Vol/TB20 {vr:.2f}x: cần kiểm tra áp lực bán."
    if pos < 60:
        return f"Đóng cửa ở {pos:.0f}% biên độ: nến chưa đạt ngưỡng tích cực 60% của Trading T+2."
    if wick >= 35:
        return f"Đóng cửa {pos:.0f}% biên độ, nhưng bóng trên {wick:.0f}%: cần kiểm tra lực bán ở vùng giá cao."
    if volume["close"] > volume["prev_close"] and volume["close"] >= volume["open"]:
        return f"Đóng cửa {pos:.0f}% biên độ, giá tăng với nến không đỏ; tiếp tục kiểm tra cản gần."
    return f"Đóng cửa {pos:.0f}% biên độ nhưng giá chưa xác nhận tăng so với phiên trước."


def render_context(context, viewed, daily=None):
    """Small display panel only for explicit single-ticker filtering."""
    import streamlit as st
    if not context or viewed is None or viewed.empty:
        return
    code = context["code"]
    latest = viewed[viewed["Mã"] == code]
    if latest.empty:
        return
    # Most recent signal comes first, but this is a dashboard, NOT an entry recommendation.
    latest = latest.sort_values("Ngày tín hiệu", ascending=False).iloc[0]
    price = pd.to_numeric(context["price"], errors="coerce")
    displayed_price = pd.to_numeric(latest.get("Giá EOD"), errors="coerce")
    if pd.isna(price) or pd.isna(displayed_price) or abs(float(price) - float(displayed_price)) > 0.011:
        st.caption("Bối cảnh MA/trạng thái chưa đồng bộ với EOD Trading T+2; không hiển thị thông tin trộn phiên.")
        return

    def fmt(v, suffix=""):
        x = pd.to_numeric(v, errors="coerce")
        return f"{float(x):.2f}{suffix}" if pd.notna(x) else "—"

    # EOD-only volume: 20 strictly prior sessions, never signal-day ratio.
    vol = _eod_volume_context(daily, code, context["asof"])
    if vol is not None and abs(float(vol["close"]) - float(price)) > 0.011:
        vol = None  # fail closed on inconsistent prices
    age = pd.to_numeric(latest.get("Phiên từ tín hiệu"), errors="coerce")
    if vol is not None and pd.notna(age) and 0 <= float(age) <= 15:
        from min_t2_swing import _rr_for_display
        rr1 = _rr_for_display(latest, "Mục tiêu 1", "R:R TP1")
    else:
        rr1 = latest.get("R:R TP1")

    with st.container(border=True):
        st.markdown(f"**Tổng quan {code} · EOD {context['asof']:%d/%m/%Y}**")
        a, b, c = st.columns(3)
        with a:
            st.caption("CẤU TRÚC MA")
            st.write("Ngắn hạn:", context["ma_short"] or "—")
            st.write("Trung hạn:", context["ma_medium"] or "—")
            st.write("Dài hạn:", context["ma_long"] or "—")
        with b:
            st.caption("BẢN ĐỒ TRẠNG THÁI")
            st.write(context["state_label"])
            if context["action"]:
                st.caption("Hành động: " + str(context["action"]))
            st.write("RS20:", fmt(context["rs20"], "%"), " · Điểm MA:", fmt(context["ma_score"]))
        with c:
            st.caption("CẢN GẦN / MỤC TIÊU")
            st.write("Cản gần:", fmt(context["near_resistance"]))
            st.write("TP1:", fmt(latest.get("Mục tiêu 1")))
            st.write("TP2:", fmt(latest.get("Mục tiêu 2")))
        # Separate Trading T+ view; never overwrite original State Map label.
        st.markdown("**ĐÁNH GIÁ GIAO DỊCH T+ (GIÁ & KHỐI LƯỢNG EOD)**")
        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric("Vol/TB20 EOD", fmt(vol["vol_ratio"], "x") if vol else "—")
        with k2:
            tp = pd.to_numeric(latest.get("Mục tiêu 1"), errors="coerce")
            upside = (float(tp)/float(price)-1)*100 if pd.notna(tp) and float(tp)>float(price) else float("nan")
            st.metric("Dư địa đến TP1", fmt(upside, "%"))
        with k3:
            st.metric("R:R TP1", fmt(rr1))
        # Explain close location and candle shape alongside volume EOD.
        if vol is not None:
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Vị trí đóng cửa (Position)", fmt(vol["close_pos"] * 100, "%"))
            with c2:
                st.metric("Biên độ nến High–Low", fmt(vol["range_pct"], "%"))
            with c3:
                st.metric("Bóng trên / biên độ", fmt(vol["upper_wick_pct"], "%"))
            with c4:
                st.metric("Thân nến / biên độ", fmt(vol["body_pct"], "%"))
            st.write("Phân loại nến EOD:", _t2_body_label(vol))
            st.caption(_t2_candle_explanation(vol))
        else:
            st.caption("Nến EOD: Chưa đủ dữ liệu OHLC đồng nhất để phân tích.")
        st.write("Đánh giá T+:", _t2_trade_assessment(context, latest, vol))
        # MIN_T2_EXIT_GUARD_V1
        from min_t2_position_guard import render_guard
        render_guard(context, viewed, daily)
        st.caption("Position = (Đóng cửa − Thấp nhất) / (Cao nhất − Thấp nhất) × 100; biên độ nến = (Cao nhất − Thấp nhất) / Thấp nhất × 100. Thân/biên độ = |Đóng cửa − Mở cửa| / (Cao nhất − Thấp nhất) × 100. Thân nhỏ <25%, thân vừa 25–<60%, thân lớn ≥60% (ngưỡng mô tả, không phải tín hiệu mua). Nến một giá: Position quy ước 50%, thân 0%.")
        st.caption("Vol/TB20 EOD lấy khối lượng phiên mới nhất chia trung bình 20 phiên trước. Không phải Vol/TB20 của ngày phát tín hiệu.")
        st.caption("Trạng thái và kháng cự gần lấy từ Bản đồ trạng thái; cấu trúc MA lấy từ tab Cấu trúc MA. TP1/TP2 lấy từ tín hiệu T+2 mới nhất đang hiển thị. Cản gần không phải TP.")
