"""Phân tích đa khung theo mây Ichimoku (9-17-26): xu hướng, hỗ trợ / kháng cự gần nhất, nhận xét tự động và kế hoạch
giao dịch (vùng gom, cắt lỗ, chốt lời, R:R). Không phụ thuộc Streamlit.

- analyze_dwm_timeframe(df_d, df_w, df_m): Ngày - Tuần - Tháng (đang dùng trong app, cắt lỗ = hỗ trợ -4%).
- analyze_multi_timeframe(df_1h, df_d, df_w): 1 giờ - Ngày - Tuần (cắt lỗ = hỗ trợ -3%; app hiện không có nến giờ)."""
from __future__ import annotations

import pandas as pd

LONG_TENKAN, LONG_KIJUN = 65, 129   # Ichimoku thứ 2 (65-129-52): đường Chuyển đổi 65 và Cơ sở 129 = vùng hỗ trợ khi giá nằm trên mây
BAND_GAP_PCT = 0.03    # hai đường cách nhau ≤ 3% giá: gộp thành một mức "x ± dung sai"; xa hơn: hiện khoảng "thấp – cao"
TOL_PCT = 0.006        # dung sai ± quanh mức hỗ trợ (0.6% giá, ví dụ 50.33 → ± 0.30)
RES_LOOKBACK = {"1h": 120, "D": 120, "W": 104, "M": 60}   # kháng cự = "Đỉnh" của vùng nhìn thấy: ~6 tháng / 2 năm / 5 năm
FAR_LINE_PCT = 1.25    # đường Ichimoku 65-129 gần nhất cao hơn giá > 25%: thêm "đỉnh gần nhất" làm mép dưới vùng kháng cự
PIVOT_K = 3            # đỉnh gần nhất = đỉnh cục bộ cao hơn 3 nến mỗi bên
MIN_BARS = 52          # mây Ichimoku 9-17-26 (span B 26 nến, dịch 26) cần ≥ 52 nến mới có mây
TF_LABEL = {"1h": "1 giờ", "D": "Ngày", "W": "Tuần", "M": "Tháng"}
VI_COLS = {"Giá mở cửa": "open", "Giá cao nhất": "high", "Giá thấp nhất": "low", "Giá đóng cửa": "close",
           "Khối lượng khớp lệnh": "volume"}
_STYLES = {
    "short": dict(flat="Đi ngang", cmt={"*": {
        "Tăng": "Nằm trên mây {n}, xu hướng ổn định.", "Giảm": "Dưới mây {n}, áp lực điều chỉnh.",
        "Đi ngang": "Dao động trong mây {n}, tích lũy."}}),
    "long": dict(flat="Tích lũy", cmt={
        "D": {"Tăng": "Trên vùng hỗ trợ ngày, xu hướng ngắn hạn ổn định.", "Giảm": "Dưới mây Ngày, áp lực điều chỉnh ngắn hạn.",
              "Tích lũy": "Dao động trong mây Ngày, ngắn hạn đang tích lũy."},
        "W": {"Tăng": "Nằm trên mây tuần, xu hướng trung hạn vững chắc.", "Giảm": "Dưới mây tuần, áp lực điều chỉnh trung hạn.",
              "Tích lũy": "Dao động trong mây tuần, trung hạn vùng nhạy cảm."},
        "M": {"Tăng": "Cấu trúc chu kỳ lớn đồng thuận tăng trưởng.", "Giảm": "Cấu trúc chu kỳ lớn suy yếu, áp lực điều chỉnh dài hạn.",
              "Tích lũy": "Chu kỳ lớn đang tích lũy, chưa xác nhận xu hướng."}}),
}


def std_ohlc(g):
    """Nhận bảng cột tiếng Việt của app hoặc cột open/high/low/close (tiếng Anh); trả về cột tiếng Anh."""
    if g is None:
        return None
    out = g.rename(columns=VI_COLS)
    if not {"high", "low", "close"} <= set(out.columns):
        return None
    return out[[c for c in ("open", "high", "low", "close", "volume") if c in out.columns]].reset_index(drop=True)


def _not_enough(tf, n):
    return {"ok": False, "trend": "Không đủ dữ liệu", "sup": None, "res": None, "close": None, "n": n,
            "cmt": f"Chưa đủ dữ liệu khung {TF_LABEL[tf]} (có {n} nến, cần ≥ {MIN_BARS})."}


def _recent_pivot_high(h, close, tf):
    """Đỉnh gần nhất: đỉnh cục bộ (cao hơn PIVOT_K nến mỗi bên) mới nhất nằm trên giá, trong RES_LOOKBACK nến."""
    arr = h.to_numpy()
    lo = max(PIVOT_K, len(arr) - RES_LOOKBACK[tf])
    for i in range(len(arr) - PIVOT_K - 1, lo - 1, -1):
        w = arr[i - PIVOT_K:i + PIVOT_K + 1]
        if arr[i] >= w.max() and arr[i] > close * 1.002:
            return float(arr[i])
    return None


def _resistance_zone(close, lines, pivot):
    """Giá dưới mây: kháng cự là các đường Ichimoku 65-129 nằm trên giá.
    - Đường gần nhất còn gần giá (≤ +25%): vùng = [đường thấp, đường cao]   (VD: SHS D 13.61 – 15.00, M 14.80 – 16.39)
    - Đường gần nhất quá xa (> +25%) mà có đỉnh gần nhất ở giữa: vùng = [đỉnh gần nhất, đường thấp]   (VD: SHS W 14.19 – 18.50)
    Trả về (mức gần, mức xa hoặc None); không có đường nào trên giá trả về (None, None)."""
    above = sorted(x for x in lines if x > close)
    if not above:
        return None, None
    if above[0] > close * FAR_LINE_PCT and pivot is not None and pivot < above[0]:
        return pivot, above[0]
    return above[0], (above[-1] if above[-1] > above[0] else None)


def _frame_levels(df, tf, style):
    n = 0 if df is None else len(df)
    if df is None or n < MIN_BARS:
        return _not_enough(tf, n)
    st = _STYLES[style]
    c, h, l = df["close"], df["high"], df["low"]
    close = float(c.iloc[-1])

    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(17).max() + l.rolling(17).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((h.rolling(26).max() + l.rolling(26).min()) / 2).shift(26)
    sa, sb = span_a.iloc[-1], span_b.iloc[-1]
    if pd.isna(sa) or pd.isna(sb):
        return _not_enough(tf, n)
    top, bot = float(max(sa, sb)), float(min(sa, sb))

    trend = "Tăng" if close > top else "Giảm" if close < bot else st["flat"]
    cmt = st["cmt"].get(tf, st["cmt"].get("*"))[trend].format(n=TF_LABEL[tf])

    sup = sup_hi = sup_tol = res = res_hi = None
    lines = None
    if n >= LONG_KIJUN:      # Ichimoku 65-129-52: đường Chuyển đổi 65 và Cơ sở 129
        tk = float(((h.rolling(LONG_TENKAN).max() + l.rolling(LONG_TENKAN).min()) / 2).iloc[-1])
        kj = float(((h.rolling(LONG_KIJUN).max() + l.rolling(LONG_KIJUN).min()) / 2).iloc[-1])
        lines = (tk, kj)
    # Giá trên mây 9-17-26: hỗ trợ = các đường 65 / 129 nằm dưới giá.
    if trend == "Tăng" and lines:
        below = sorted(x for x in lines if x < close)
        if below:
            lo, hi = below[0], below[-1]
            if hi - lo <= close * BAND_GAP_PCT:
                sup, sup_tol = lo, round(lo * TOL_PCT, 2)
            else:
                sup, sup_hi = lo, hi
    if sup is None:      # không đủ nến cho đường 129 hoặc giá chưa trên mây: đáy mây, rồi đáy 20 / 60 nến
        low20, low60 = float(l.iloc[-20:].min()), float(l.iloc[-60:].min())
        sup = next((x for x in (bot, low20, low60) if x < close), None)
        sup_hi = top if (sup == bot and top < close and round(top, 2) > round(bot, 2)) else None   # giá trên mây: dải mây là vùng hỗ trợ
    # Giá dưới / trong mây: kháng cự = các đường 65 / 129 nằm trên giá (kèm đỉnh gần nhất nếu các đường quá xa).
    if trend != "Tăng" and lines:
        res, res_hi = _resistance_zone(close, lines, _recent_pivot_high(h, close, tf))
    if res is None:      # giá trên mây (hoặc không có mốc phù hợp): "Đỉnh" cao nhất của vùng nhìn thấy, phải nằm trên giá
        res = float(h.iloc[-RES_LOOKBACK[tf]:].max())
        res = res if res > close * 1.002 else None
    if res is None:
        cmt += " Giá đang ở vùng đỉnh, chưa có kháng cự rõ phía trên."
    if sup is None:
        cmt += " Giá đang ở vùng đáy mới, chưa có hỗ trợ rõ phía dưới."
    return {"ok": True, "trend": trend, "cmt": cmt, "close": close, "n": n, "cloud": (round(bot, 2), round(top, 2)),
            "sup": round(sup, 2) if sup is not None else None, "sup_hi": round(sup_hi, 2) if sup_hi is not None else None,
            "sup_tol": sup_tol,
            "res": round(res, 2) if res is not None else None, "res_hi": round(res_hi, 2) if res_hi is not None else None}


def _strategy(res, sl_pct, watch):
    d = res["D"]
    if not d["ok"]:
        return {"ok": False, "msg": "Chưa đủ dữ liệu khung Ngày để lập kế hoạch giao dịch."}
    if d["sup"] is None:
        return {"ok": False, "msg": "Giá đang ở vùng đáy mới, chưa có hỗ trợ rõ phía dưới để đặt vùng gom. Chờ giá tạo đáy."}
    entry_min = d["sup"]
    entry_max = entry_min * 1.02
    stop_loss = entry_min * (1 - sl_pct)
    entry_mid = (entry_min + entry_max) / 2           # R:R tính từ giữa vùng gom (thận trọng hơn tính từ mép dưới)
    risk = entry_mid - stop_loss
    if d["res"] is None:
        take_profit = entry_mid + 2 * risk
        tp_note = "Không có kháng cự phía trên: chốt lời tạm tính theo R:R 1 : 2."
    else:
        take_profit, tp_note = d["res"], ""
    reward = take_profit - entry_mid
    rr = round(reward / risk, 1) if risk > 0 and reward > 0 else 0.0
    label = "Khả thi" if rr >= 1.8 else "Rủi ro cao" if rr > 0 else "Không có lợi thế"
    dist = (d["close"] / entry_max - 1) * 100
    status = ("Giá đang trong vùng gom." if d["close"] <= entry_max
              else f"Giá đang cao hơn vùng gom {dist:.1f}%: chờ giá về vùng gom, không đuổi mua.")
    warn = [f"Khung {TF_LABEL[t]} đang giảm: vùng gom có thể bị phá, ưu tiên chờ xác nhận."
            for t in watch if res[t]["ok"] and res[t]["trend"] == "Giảm"]
    return {"ok": True, "entry": f"{entry_min:,.2f} – {entry_max:,.2f}", "sl": f"{stop_loss:,.2f}",
            "tp": f"{take_profit:,.2f}", "rr": f"1 : {rr} ({label})", "rr_value": rr, "rr_label": label,
            "status": status, "tp_note": tp_note, "warn": warn, "sl_pct": round(sl_pct * 100)}


def analyze_dwm_timeframe(df_d, df_w, df_m):
    """Phân tích đa khung D - W - M. Mỗi khung có thể là None (hiện 'Không đủ dữ liệu').
    Bảng đầu vào: cột tiếng Việt của app (Giá cao nhất/Giá thấp nhất/Giá đóng cửa) hoặc high/low/close."""
    res = {tf: _frame_levels(std_ohlc(df), tf, "long") for tf, df in (("D", df_d), ("W", df_w), ("M", df_m))}
    res["strategy"] = _strategy(res, 0.04, ("D", "W", "M"))
    return res


def analyze_multi_timeframe(df_1h, df_d, df_w):
    """Phân tích đa khung 1h - D - W (app hiện không có nến giờ nên không dùng trong giao diện)."""
    res = {tf: _frame_levels(std_ohlc(df), tf, "short") for tf, df in (("1h", df_1h), ("D", df_d), ("W", df_w))}
    res["strategy"] = _strategy(res, 0.03, ("D", "W"))
    return res
