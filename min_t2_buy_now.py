# -*- coding: utf-8 -*-
"""Independent T+2-only section for 'Mua ngay' from actual T+2 EOD signals.

No hardcoded tickers. Never turns a T+2 stop into a long-horizon stop,
never modifies the waiting-buy states, original T+2 signals, or market data.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import min_t2_swing as T2
import min_t2_position_guard as GUARD

AGE_LIMIT = 5
MIN_UPSIDE = 10.0
MIN_RR = 2.5
MAX_RISK = 5.0
MIN_VOL_RATIO = 1.2
MIN_CLOSE_POSITION = 0.50   # 50-60%: eligible, but note indecisive candle explicitly
COLUMNS = ["Mã", "Ngày tín hiệu", "Tuổi", "Tín hiệu", "Giá EOD", "Cắt lỗ T+2",
           "TP1 T+2", "TP2 T+2", "Dư địa TP1 %", "R:R EOD", "Rủi ro SL %",
           "Vol/TB20 EOD", "RSI14 EOD", "Position EOD %", "Ghi chú"]


def num(value):
    x = pd.to_numeric(value, errors="coerce")
    try:
        return float(x) if pd.notna(x) and np.isfinite(float(x)) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _qualify(row: pd.Series, g: pd.DataFrame, asof, market_days=None) -> tuple[dict | None, str]:
    """Fail closed for stale bars, stop touches, exit risk or weak short-term entry."""
    if g is None or len(g) < 51:
        return None, "Thiếu ít nhất 51 nến EOD"
    day = pd.Timestamp(asof).normalize()
    age = num(row.get("Phiên từ tín hiệu"))
    event_day = pd.to_datetime(row.get("Ngày tín hiệu"), errors="coerce")
    if not (np.isfinite(age) and age == int(age) and 0 <= age <= AGE_LIMIT
            and pd.notna(event_day) and g["Ngày"].iloc[-1] == day):
        return None, "Tín hiệu T+2 quá hạn hoặc EOD không đồng bộ"
    event_day = pd.Timestamp(event_day).normalize()
    window = g.loc[g["Ngày"] >= event_day]
    if len(window) != int(age) + 1 or window.empty or window.iloc[0]["Ngày"] != event_day:
        return None, "Thiếu phiên kể từ ngày tín hiệu"
    if g["Ngày"].duplicated().any():
        return None, "Trùng phiên EOD"
    if market_days is not None:
        expected = {d for d in market_days if event_day <= d <= day}
        if set(window["Ngày"]) != expected:
            return None, "Thiếu nến trong một phiên giao dịch của thị trường"
    price, entry, stop, orig_stop = (num(row.get("Giá EOD")), num(row.get("Giá tín hiệu")),
                                    num(row.get("Cắt lỗ tham khảo")),
                                    num(row.get("Cắt lỗ gốc", row.get("Cắt lỗ tham khảo"))))
    tp1, tp2 = num(row.get("Mục tiêu 1")), num(row.get("Mục tiêu 2"))
    if not all(np.isfinite(x) for x in (price, entry, stop, orig_stop, tp1)):
        return None, "Thiếu giá EOD, giá tín hiệu, stop hoặc TP1 T+2"
    if not (0 < orig_stop < entry and 0 < stop < price < tp1):
        return None, "Stop/TP của chiến lược T+2 không hợp lệ"
    if abs(price - num(g["Giá đóng cửa"].iloc[-1])) > .011:
        return None, "EOD khác với bảng Trading T+2"
    risk = (1 - stop / price) * 100
    upside = (tp1 / price - 1) * 100
    rr = (tp1 - price) / (price - stop)
    if upside + 1e-9 < MIN_UPSIDE or rr + 1e-9 < MIN_RR or risk > MAX_RISK + 1e-9:
        return None, "Dư địa/R:R/stoploss T+2 chưa đạt ngưỡng"

    # Original stop cannot have been touched after the signal. TP1 original
    # may have been touched if the T+2 system has raised a real dynamic TP.
    life = GUARD.signal_lifecycle(g, row, day)
    status = str(life.get("status", ""))
    if status in ("CHƯA ĐỦ DỮ LIỆU", "ĐÃ CHẠM CẮT LỖ GỐC",
                  "CHẠM CẢ CẮT LỖ VÀ TP TRONG CÙNG PHIÊN", "ĐÃ CHẠM TP2 GỐC"):
        return None, "Vòng đời T+2: " + status + (" – " + str(life.get("note", "")) if life.get("note") else "")
    if status not in ("ĐÃ CHẠM TP1 GỐC", "CHƯA CHẠM CẮT LỖ/TP GỐC"):
        return None, "Không xác nhận được vòng đời tín hiệu"
    if status == "ĐÃ CHẠM TP1 GỐC":
        tp_orig = num(row.get("TP1 gốc"))
        if not np.isfinite(tp_orig) or tp1 <= tp_orig + 1e-8:
            return None, "TP gốc đã chạm nhưng không có TP động mới"

    # If breakeven was armed at completed T+2 EOD, reject later bars that
    # already traded through the ACTIVE raised stop. T+2 candle itself is not
    # retroactively tested against that stop.
    if stop > orig_stop + 1e-8 and age > 2:
        lows_after_arm = pd.to_numeric(window.iloc[3:]["Giá thấp nhất"], errors="coerce")
        if lows_after_arm.isna().any() or (lows_after_arm <= stop).any():
            return None, "Đã chạm stop T+2 nâng về hòa vốn ở các phiên sau"

    guard = GUARD.exit_condition(g, str(row["Mã"]), day)
    if guard.get("status") != "THEO DÕI GIỮ":
        return None, "T+2 có cảnh báo MA20/bán hoặc thiếu dữ liệu"
    ind = T2._indicators(g)
    curr = ind.iloc[-1]
    prev = ind.iloc[-2]
    o, prevclose = num(curr.get("Giá mở cửa")), num(prev.get("Giá đóng cửa"))
    ma9, ma20 = num(curr.get("MA9")), num(curr.get("MA20"))
    rsi, volratio, pos = (num(curr.get("RSI14")), num(curr.get("VolRatio")),
                          num(curr.get("ClosePos")))
    if not all(np.isfinite(x) for x in (o, prevclose, ma9, ma20, rsi, volratio, pos)):
        return None, "Chỉ báo Trading T+2 chưa đủ dữ liệu"
    if not (price > prevclose and price >= o and price > ma9 and price > ma20
            and price <= ma9 * 1.08 and volratio >= MIN_VOL_RATIO
            and 45 <= rsi <= 78 and pos >= MIN_CLOSE_POSITION):
        return None, "Cần nến tăng, MA9/20, RSI, Vol và vị trí đóng cửa T+2 hợp lệ"
    if not (0 <= pos <= 1):
        return None, "Position EOD không hợp lệ"
    caution = "Nến đóng cửa chưa thật mạnh (Position dưới 60%); theo dõi cản gần." if pos < .60 else "Nến EOD xác nhận tương đối tích cực."
    if status == "ĐÃ CHẠM TP1 GỐC":
        caution += " TP1 gốc đã chạm; đang theo dõi mục tiêu động mới."
    record = {
        "Mã": str(row["Mã"]).strip().upper(), "Ngày tín hiệu": event_day,
        "Tuổi": "T+" + str(int(age)), "Tín hiệu": str(row.get("Tín hiệu", "")),
        "Giá EOD": price, "Cắt lỗ T+2": stop, "TP1 T+2": tp1, "TP2 T+2": tp2,
        "Dư địa TP1 %": upside, "R:R EOD": rr, "Rủi ro SL %": risk,
        "Vol/TB20 EOD": volratio, "RSI14 EOD": rsi,
        "Position EOD %": pos * 100,
        "Ghi chú": "CHỈ TRADING T+2 – KHÔNG NẮM GIỮ DÀI HẠN. " + caution + " " + str(row.get("Ghi chú", "")) + " Kiểm tra lại giá khớp, stop và TP trước lệnh."
    }
    return record, "OK"


def from_scanned_history(history: pd.DataFrame, daily: pd.DataFrame, asof) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Share one exact eligibility path between Streamlit and read-only EOD audit.

    `history` is an already calculated T+2 historical signal table. No extra
    scanner calls; no stock-specific exceptions, and no changes to source data.
    """
    empty = pd.DataFrame(columns=COLUMNS)
    notes: dict[str, list[str]] = {}
    if history is None or history.empty or daily is None or daily.empty:
        return empty, notes
    day = pd.Timestamp(asof).normalize()
    h = history.copy()
    h["Phiên từ tín hiệu"] = pd.to_numeric(h["Phiên từ tín hiệu"], errors="coerce")
    h = h[h["Phiên từ tín hiệu"].between(0, AGE_LIMIT)].copy()
    if h.empty:
        return empty, notes
    # Use the unmodified engine to calculate active T+2 targets and stop.
    h = T2._add_dynamic_targets(h, daily, 3.0)
    market_days = set(daily["Ngày"])
    by_code = {str(code): g.sort_values("Ngày").reset_index(drop=True)
               for code, g in daily[daily["Mã"].isin(h["Mã"])].groupby("Mã", sort=False)}
    accepted = []
    for _, row in h.iterrows():
        code = str(row["Mã"]).strip().upper()
        item, why = _qualify(row, by_code.get(code), day, market_days)
        if item is None:
            notes.setdefault(code, []).append(
                f"T+{int(row['Phiên từ tín hiệu'])}: {why}")
        else:
            accepted.append(item)
    if not accepted:
        return empty, notes
    out = pd.DataFrame(accepted).sort_values(
        ["Ngày tín hiệu", "R:R EOD"], ascending=[False, False])
    return out.drop_duplicates("Mã", keep="first").reset_index(drop=True)[COLUMNS], notes


def candidates(daily: pd.DataFrame, asof) -> pd.DataFrame:
    """Run the existing market scanner once, then apply the same audit gates."""
    d = T2.prepare(daily, asof)
    if d.empty:
        return pd.DataFrame(columns=COLUMNS)
    _, history = T2.scan(d, asof=pd.Timestamp(asof).normalize())
    eligible, _ = from_scanned_history(history, d, asof)
    return eligible
