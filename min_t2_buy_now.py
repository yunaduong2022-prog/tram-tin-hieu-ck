# -*- coding: utf-8 -*-
"""Independent T+2-only section for 'Mua ngay' from actual T+2 EOD signals.

No hardcoded tickers. Never turns a T+2 stop into a long-horizon stop,
never modifies the waiting-buy states, original T+2 signals, or market data.
"""
from __future__ import annotations

import re

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


def _qualify(row: pd.Series, g: pd.DataFrame, asof, market_days=None, *, allow_soft=False) -> tuple[dict | None, str]:
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
    technical_ok = (price > prevclose and price >= o and price > ma9 and price > ma20
                    and price <= ma9 * 1.08 and volratio >= MIN_VOL_RATIO
                    and 45 <= rsi <= 78 and pos >= MIN_CLOSE_POSITION)
    if not technical_ok:
        # WAIT only for a mild, fixable candle/volume confirmation. Never
        # downgrade a broken MA trend, missing EOD or invalid lifecycle to WAIT.
        soft_ok = (price >= prevclose and price >= o * .995
                   and price > ma9 and price > ma20 and price <= ma9 * 1.08
                   and 45 <= rsi <= 78 and volratio >= 1.0 and pos >= MIN_CLOSE_POSITION)
        if not (allow_soft and soft_ok):
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
    return record, ("CHỜ XÁC NHẬN NẾN/KHỐI LƯỢNG" if not technical_ok else "OK")


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


# MIN_T2_WAIT_CONFIRM_V1: one scanner / one dynamic-level pass / two mutually
# exclusive display lists. This does not change the original signal engine.
WAIT_COLUMNS = COLUMNS + ["Cản cần vượt", "R:R đến cản", "Điều kiện kích hoạt"]


def _near_barrier(g: pd.DataFrame, price: float) -> tuple[float, str, bool]:
    """Use exactly the T+2 engine's *confirmed* overhead resistance warning.

    The EOD T+2 engine already consolidates peaks, suppresses invalidated
    peaks and gives a caution for barriers within 3%. Parse that diagnostic
    rather than inferring a new level or using the distant TP1 as free space.
    `uncertain=True` fails closed into WAIT, never BUY.
    """
    try:
        _, _, _, _, caution = T2._dynamic_resistance_eod(g, 3.0)
    except Exception:
        return np.nan, "Không xác minh được kháng cự EOD", True
    if not isinstance(caution, str):
        return np.nan, "Dữ liệu cản gần không hợp lệ", True
    if not caution:
        return np.nan, "", False
    if not caution.startswith("Cản gần:"):
        return np.nan, "Không đọc được chú thích cản gần", True
    values = [float(v) for v in re.findall(r"(?<![\d.])(\d+(?:\.\d+)?)\s*\(", caution)]
    near = sorted(v for v in values if np.isfinite(v) and price < v <= price * 1.03 + 1e-8)
    if not near:
        return np.nan, "Không xác thực được giá cản gần: " + caution, True
    return near[0], caution, False


def split_from_scanned_history(history: pd.DataFrame, daily: pd.DataFrame, asof) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, list[str]]]:
    """Classify in one pass after one T+2 scan: BUY or WAIT, never both.

    Hard exits/expired signals cannot become WAIT. A valid signal waits if a
    confirmed nearby resistance remains or EOD candle/volume needs confirmation.
    """
    empty_buy = pd.DataFrame(columns=COLUMNS)
    empty_wait = pd.DataFrame(columns=WAIT_COLUMNS)
    notes: dict[str, list[str]] = {}
    if history is None or daily is None or history.empty or daily.empty:
        return empty_buy, empty_wait, notes
    day = pd.Timestamp(asof).normalize()
    h = history.copy()
    h["Phiên từ tín hiệu"] = pd.to_numeric(h["Phiên từ tín hiệu"], errors="coerce")
    h = h[h["Phiên từ tín hiệu"].between(0, AGE_LIMIT)].copy()
    if h.empty:
        return empty_buy, empty_wait, notes
    # Exactly ONE recalculation of dynamic targets and raised T+2 stop.
    h = T2._add_dynamic_targets(h, daily, 3.0)
    market_days = set(daily["Ngày"])
    by_code = {str(code): g.sort_values("Ngày").reset_index(drop=True)
               for code, g in daily[daily["Mã"].isin(h["Mã"])].groupby("Mã", sort=False)}
    barrier_cache = {}
    accepted = []
    for _, row in h.iterrows():
        code = str(row["Mã"]).strip().upper()
        g = by_code.get(code)
        item, reason = _qualify(row, g, day, market_days, allow_soft=True)
        if item is None:
            notes.setdefault(code, []).append(f"T+{int(row['Phiên từ tín hiệu'])}: {reason}")
            continue
        if code not in barrier_cache:
            barrier_cache[code] = _near_barrier(g, item["Giá EOD"])
        barrier, warning, uncertain = barrier_cache[code]
        waiting = np.isfinite(barrier) or uncertain or reason != "OK"
        item["_Loại T+2"] = "CHỜ MUA" if waiting else "MUA NGAY"
        if waiting:
            item["Cản cần vượt"] = barrier
            item["R:R đến cản"] = ((barrier - item["Giá EOD"]) / (item["Giá EOD"] - item["Cắt lỗ T+2"])
                                     if np.isfinite(barrier) else np.nan)
            triggers = []
            if np.isfinite(barrier):
                triggers.append(f"Chờ đóng cửa vượt {barrier:.2f} với nến tăng, Position ≥60% và Vol/TB20 ≥1.2x")
            elif uncertain:
                triggers.append("Xác minh lại kháng cự gần từ dữ liệu EOD")
            if reason != "OK":
                triggers.append("Chờ nến tăng và xác nhận khối lượng T+2")
            triggers.append("Sau xác nhận: tính lại stop, TP, R:R và vòng đời tín hiệu")
            item["Điều kiện kích hoạt"] = "; ".join(triggers)
            item["Ghi chú"] += " CHỜ MUA T+2: " + (warning or reason) + ". Không vào trước khi xác nhận."
        accepted.append(item)
    if not accepted:
        return empty_buy, empty_wait, notes
    # Choose the most recent eligible setup per code; a ticker cannot appear
    # in both lists or be duplicated by several signal variants on one EOD.
    all_valid = pd.DataFrame(accepted).sort_values(
        ["Ngày tín hiệu", "R:R EOD", "Mã"], ascending=[False, False, True]
    ).drop_duplicates("Mã", keep="first").reset_index(drop=True)
    buy = all_valid[all_valid["_Loại T+2"] == "MUA NGAY"]
    wait = all_valid[all_valid["_Loại T+2"] == "CHỜ MUA"]
    return (buy.reindex(columns=COLUMNS).reset_index(drop=True),
            wait.reindex(columns=WAIT_COLUMNS).reset_index(drop=True), notes)


def candidates_both(daily: pd.DataFrame, asof) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Shared Streamlit cache target: one market scan for BUY + WAIT tabs."""
    d = T2.prepare(daily, asof)
    if d.empty:
        return pd.DataFrame(columns=COLUMNS), pd.DataFrame(columns=WAIT_COLUMNS)
    _, history = T2.scan(d, asof=pd.Timestamp(asof).normalize())
    buy, wait, _ = split_from_scanned_history(history, d, asof)
    return buy, wait


def candidates(daily: pd.DataFrame, asof) -> pd.DataFrame:
    """Compatibility: BUY-only view, excluding uncleared nearby resistance."""
    return candidates_both(daily, asof)[0]
