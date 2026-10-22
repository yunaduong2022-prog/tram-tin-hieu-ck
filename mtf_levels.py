"""Phân tích đa khung theo mây Ichimoku (9-17-26): xu hướng, hỗ trợ / kháng cự gần nhất, nhận xét tự động và kế hoạch
giao dịch (vùng gom, cắt lỗ, chốt lời, R:R). Không phụ thuộc Streamlit.

- analyze_dwm_timeframe(df_d, df_w, df_m): Ngày - Tuần - Tháng (đang dùng trong app, cắt lỗ = hỗ trợ -4%).
- analyze_multi_timeframe(df_1h, df_d, df_w): 1 giờ - Ngày - Tuần (cắt lỗ = hỗ trợ -3%; app hiện không có nến giờ)."""
from __future__ import annotations

import pandas as pd

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
    if "Ngày" in out.columns:      # luôn xếp theo thời gian: iloc[-20:] phải đúng là 20 nến GẦN NHẤT, không phụ thuộc thứ tự dòng đầu vào
        out = out.sort_values("Ngày").drop_duplicates("Ngày", keep="last").rename(columns={"Ngày": "date"})
    cols = [c for c in ("date", "open", "high", "low", "close", "volume") if c in out.columns]
    return out[cols].reset_index(drop=True)


# Kháng cự = ĐỈNH SÓNG (swing high) gần nhất phía trên giá, giống cách nhìn trên biểu đồ.
# Đỉnh sóng: nến có giá cao nhất trong K nến trước và K nến sau nó (nên cần K nến để xác nhận).
PIVOT_K = {"1h": 3, "D": 3, "W": 2, "M": 2}
PIVOT_LOOKBACK = {"1h": 120, "D": 120, "W": 104, "M": 120}   # chỉ xét các đỉnh trong ngần ấy nến gần nhất


def _swing_highs(h, k, lookback):
    """Danh sách (vị trí, giá) các đỉnh sóng trong `lookback` nến gần nhất, theo thứ tự thời gian."""
    n = len(h)
    out = []
    for i in range(max(k, n - lookback), n - k):
        w = h.iloc[i - k:i + k + 1]
        if h.iloc[i] >= w.max():
            out.append((i, float(h.iloc[i])))
    return out


def _resistances(df, tf, close):
    """(kháng cự 1, kháng cự 2, ngày của kháng cự 1): hai đỉnh sóng GẦN GIÁ NHẤT phía trên giá.
    Không có đỉnh sóng nào phía trên thì quay về cách cũ: đỉnh 20 nến, rồi đỉnh 60 nến."""
    h = df["high"]
    above = sorted({round(p, 4): i for i, p in _swing_highs(h, PIVOT_K[tf], PIVOT_LOOKBACK[tf]) if p > close * 1.002}.items())
    if above:
        r1 = above[0]
        r2 = above[1][0] if len(above) > 1 else None
        d1 = df["date"].iloc[r1[1]] if "date" in df.columns else None
        return r1[0], r2, d1
    high20, high60 = float(h.iloc[-20:].max()), float(h.iloc[-60:].max())
    res = next((x for x in (high20, high60) if x > close * 1.002), None)
    return res, None, None


def _not_enough(tf, n):
    return {"ok": False, "trend": "Không đủ dữ liệu", "sup": None, "res": None, "close": None, "n": n,
            "cmt": f"Chưa đủ dữ liệu khung {TF_LABEL[tf]} (có {n} nến, cần ≥ {MIN_BARS})."}


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

    # Hỗ trợ phải nằm dưới giá: đáy mây; giá đã xuống dưới mây thì dùng đáy 20 / 60 nến gần nhất.
    low20, low60 = float(l.iloc[-20:].min()), float(l.iloc[-60:].min())
    sup = next((x for x in (bot, low20, low60) if x < close), None)
    # Kháng cự phải nằm trên giá: đỉnh sóng gần giá nhất phía trên; không có = không có kháng cự rõ.
    res, res2, res_date = _resistances(df, tf, close)
    if res is None:
        cmt += " Giá đang ở vùng đỉnh, chưa có kháng cự rõ phía trên."
    if sup is None:
        cmt += " Giá đang ở vùng đáy mới, chưa có hỗ trợ rõ phía dưới."
    sup_hi = top if (sup == bot and top < close and round(top, 2) > round(bot, 2)) else None   # giá trên mây: dải mây là vùng hỗ trợ
    return {"ok": True, "trend": trend, "cmt": cmt, "close": close, "n": n, "cloud": (round(bot, 2), round(top, 2)),
            "sup": round(sup, 2) if sup is not None else None, "sup_hi": round(sup_hi, 2) if sup_hi is not None else None,
            "res": round(res, 2) if res is not None else None,
            "res2": round(res2, 2) if res2 is not None else None, "res_date": res_date}


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
    return {"ok": True, "entry": f"{round(entry_min, 1):,.1f}" + " – " + f"{round(entry_max, 1):,.1f}", "sl": f"{round(stop_loss, 1):,.1f}",
            "tp": f"{round(take_profit, 1):,.1f}", "rr": f"1 : {rr} ({label})", "rr_value": rr, "rr_label": label,
            "status": status, "tp_note": tp_note, "warn": warn, "sl_pct": round(sl_pct * 100),
            "num": {"entry_lo": entry_min, "entry_hi": entry_max, "sl": stop_loss, "tp": take_profit, "close": d["close"]}}


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
