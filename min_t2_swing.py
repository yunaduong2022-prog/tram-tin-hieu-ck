"""Min Invest - independent EOD T+2 swing candidate scanner.

Research only. Signals use information available at that EOD only. Observed
forward returns are close-to-close, NOT executable T+2 P&L or backtests.
No network, orders, file writes, or changes to existing trading engines.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COLS = ["Mã", "Ngày", "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"]
HORIZONS = (2, 5, 10, 15, 20, 30)
LABELS = {
    "EARLY": "Dòng tiền vào sớm",
    "BREAKOUT": "Breakout ngắn hạn",
    "CONTINUE": "Tiếp diễn ngắn hạn",
}


def prepare(daily: pd.DataFrame, asof=None) -> pd.DataFrame:
    """Normalize source and drop newer rows before any indicator calculations."""
    if daily is None or daily.empty or not set(COLS).issubset(daily.columns):
        return pd.DataFrame(columns=COLS)
    d = daily[COLS].copy()
    d["Mã"] = d["Mã"].astype(str).str.strip().str.upper()
    d["Ngày"] = pd.to_datetime(d["Ngày"], format="mixed", dayfirst=True, errors="coerce").dt.normalize()
    for col in COLS[2:]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["Mã", "Ngày", "Giá đóng cửa", "Giá cao nhất", "Giá thấp nhất"])
    d = d[(d["Giá đóng cửa"] > 0) & (d["Giá cao nhất"] >= d["Giá thấp nhất"]) & (d["Giá thấp nhất"] > 0)]
    if asof is not None:
        d = d[d["Ngày"] <= pd.Timestamp(asof).normalize()]
    return d.sort_values(["Mã", "Ngày"]).drop_duplicates(["Mã", "Ngày"], keep="last").reset_index(drop=True)


def _indicators(g: pd.DataFrame) -> pd.DataFrame:
    g = g.copy().reset_index(drop=True)
    c, h, lo, v = [g[k].astype(float) for k in ("Giá đóng cửa", "Giá cao nhất", "Giá thấp nhất", "Khối lượng khớp lệnh")]
    g["MA9"] = c.rolling(9, min_periods=9).mean()
    g["MA20"] = c.rolling(20, min_periods=20).mean()
    g["VolTB20"] = v.shift(1).rolling(20, min_periods=20).mean()
    g["VolRatio"] = v / g["VolTB20"].where(g["VolTB20"] > 0)
    delta = c.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    # Wilder-smoothed RSI, seeded with the FIRST 14 differences to avoid
    # EMA startup-induced misleading crosses.
    avg_up = pd.Series(np.nan, index=g.index)
    avg_dn = pd.Series(np.nan, index=g.index)
    if len(g) >= 15:
        avg_up.iloc[14], avg_dn.iloc[14] = up.iloc[1:15].mean(), down.iloc[1:15].mean()
        for i in range(15, len(g)):
            avg_up.iloc[i] = (avg_up.iloc[i-1] * 13 + up.iloc[i]) / 14
            avg_dn.iloc[i] = (avg_dn.iloc[i-1] * 13 + down.iloc[i]) / 14
    rsi = 100 - 100 / (1 + avg_up / avg_dn.where(avg_dn != 0))
    rsi = rsi.mask((avg_dn == 0) & (avg_up > 0), 100).mask((avg_dn == 0) & (avg_up == 0), 50)
    g["RSI14"] = rsi
    g["RSI_prev"] = rsi.shift(1)
    g["RSI_3prev"] = rsi.shift(3)
    g["Prev20High"] = h.shift(1).rolling(20, min_periods=20).max()
    g["Prev10Low"] = lo.shift(1).rolling(10, min_periods=10).min()
    g["Prev20Low"] = lo.shift(1).rolling(20, min_periods=20).min()
    g["PrevClose"] = c.shift(1)
    day_range = (h - lo).where(h > lo)
    g["ClosePos"] = ((c - lo) / day_range).clip(0, 1)
    g["ClosePos"] = g["ClosePos"].where(day_range.notna(), 0.5)
    # No future candles in any feature above.
    return g


def _candidate(row) -> tuple[str, str] | None:
    c, pc, v, rsi, prior = [row[x] for x in ("Giá đóng cửa", "PrevClose", "VolRatio", "RSI14", "RSI_prev")]
    if not all(np.isfinite(x) for x in (c, pc, v, rsi, prior)) or not np.isfinite(row["MA20"]):
        return None
    # Remove very illiquid/low-priced observations from candidate universe.
    if c < 5 or row["VolTB20"] < 100_000 or row["Khối lượng khớp lệnh"] <= 0:
        return None
    green = c > pc and c >= row["Giá mở cửa"]
    close_high = row["ClosePos"] >= 0.60
    breakout = (green and close_high and v >= 1.5 and 50 <= rsi <= 85
                and c > row["Prev20High"])
    if breakout:
        return ("BREAKOUT", "Đóng cửa vượt đỉnh 20 phiên trước; KL ≥1.5x; RSI >50")
    # Early reversal: distinguish an improving short-term leg from MA100/200.
    recent_cross = (np.isfinite(row["RSI_3prev"]) and row["RSI_3prev"] < 50 <= rsi)
    early = (green and close_high and v >= 1.5 and 45 <= rsi <= 72
             and rsi > prior and c > row["MA9"]
             and np.isfinite(row["Prev20Low"]) and c <= row["Prev20Low"] * 1.30
             and (recent_cross or (prior < 55 and rsi >= 50)))
    if early:
        return ("EARLY", "KL ≥1.5x; RSI đang hồi; giá vượt MA9 ở vùng phục hồi")
    continue_up = (green and close_high and v >= 1.1 and 52 <= rsi <= 75
                   and rsi >= prior and c > row["MA9"] > row["MA20"]
                   and row["MA9"] > row["MA9_prev"]
                   and c <= row["MA9"] * 1.08)
    if continue_up:
        return ("CONTINUE", "Trên MA9/20; RSI tích cực; KL ≥1.1x")
    return None


def scan(daily: pd.DataFrame, asof=None, recent_sessions=90, cooldown=5):
    """Returns (current candidates, historical first events) without lookahead.

    Full historical scan uses the same no-lookahead rules for each session;
    after the event T+h observed closes are attached for research only.
    A repeated signal of the same setup is suppressed within cooldown sessions.
    """
    d = prepare(daily, asof)
    columns = ["Mã", "Ngày tín hiệu", "Tín hiệu", "Giá tín hiệu", "RSI14", "Vol/TB20",
               "Giá EOD", "Từ tín hiệu (%)", "Cắt lỗ tham khảo", "Mục tiêu gần", "R:R tham khảo", "Ghi chú", "Phiên từ tín hiệu"] + [f"T+{h} (%)" for h in HORIZONS]
    if d.empty:
        return pd.DataFrame(columns=columns), pd.DataFrame(columns=columns)
    asof_date = pd.Timestamp(asof).normalize() if asof is not None else d["Ngày"].max()
    calendars = d.groupby("Ngày")["Mã"].nunique().sort_index()
    # use the observed global calendar, excluding thin/partial sessions
    minimum = max(3, int(d["Mã"].nunique() * 0.3))
    days = calendars[calendars >= minimum].index
    if len(days) == 0 or asof_date not in days:
        return pd.DataFrame(columns=columns), pd.DataFrame(columns=columns)
    recent = set(days[-recent_sessions:])
    current = []
    events = []
    for code, g0 in d.groupby("Mã", sort=False):
        if len(g0) < 35:
            continue
        g = _indicators(g0)
        g["MA9_prev"] = g["MA9"].shift(1)
        last = {}
        for i in range(20, len(g)):
            row = g.iloc[i]
            dt = row["Ngày"]
            if dt not in recent and dt != asof_date:
                continue
            choice = _candidate(row)
            if choice is None:
                continue
            category, note = choice
            if category in last and i - last[category] <= cooldown:
                continue
            last[category] = i
            price = float(row["Giá đóng cửa"])
            stop = float(row["Prev10Low"]) if np.isfinite(row["Prev10Low"]) and row["Prev10Low"] < price else np.nan
            target = float(row["Prev20High"]) if np.isfinite(row["Prev20High"]) and row["Prev20High"] > price else np.nan
            rr = (target - price)/(price-stop) if np.isfinite(stop) and np.isfinite(target) else np.nan
            age = len(g)-1-i if g.iloc[-1]["Ngày"] == asof_date else np.nan
            item = {"Mã":code, "Ngày tín hiệu":dt, "Tín hiệu":LABELS[category], "Giá tín hiệu":price,
                    "RSI14":round(float(row["RSI14"]),2), "Vol/TB20":round(float(row["VolRatio"]),2),
                    "Giá EOD":float(g.iloc[-1]["Giá đóng cửa"]) if g.iloc[-1]["Ngày"] == asof_date else np.nan,
                    "Từ tín hiệu (%)":round((float(g.iloc[-1]["Giá đóng cửa"])/price-1)*100,2) if g.iloc[-1]["Ngày"] == asof_date else np.nan,
                    "Cắt lỗ tham khảo": stop, "Mục tiêu gần":target, "R:R tham khảo":rr,
                    "Ghi chú":note, "Phiên từ tín hiệu":age}
            for h in HORIZONS:
                item[f"T+{h} (%)"] = round((float(g.iloc[i+h]["Giá đóng cửa"])/price-1)*100,2) if i+h<len(g) else np.nan
            events.append(item)
            if dt == asof_date:
                current.append(item)
    history = pd.DataFrame(events, columns=columns)
    now = pd.DataFrame(current, columns=columns)
    if not history.empty:
        history = history.sort_values(["Ngày tín hiệu", "Mã"], ascending=[False,True]).reset_index(drop=True)
    if not now.empty:
        now = now.sort_values(["Vol/TB20", "RSI14"],ascending=[False,False]).reset_index(drop=True)
    return now, history


def summary(history: pd.DataFrame) -> pd.DataFrame:
    """Descriptive observed close-to-close returns; not realized/tradable P&L."""
    rows = []
    if history is None or history.empty:
        return pd.DataFrame(columns=["Mốc", "Số mẫu đã đủ phiên", "Tỷ lệ tăng (%)", "Trung vị (%)", "TB (%)"])
    for h in HORIZONS:
        c = pd.to_numeric(history[f"T+{h} (%)"],errors="coerce").dropna()
        rows.append({"Mốc":f"T+{h}", "Số mẫu đã đủ phiên":len(c),
                     "Tỷ lệ tăng (%)":round((c>0).mean()*100,1) if len(c) else np.nan,
                     "Trung vị (%)":round(c.median(),2) if len(c) else np.nan,
                     "TB (%)":round(c.mean(),2) if len(c) else np.nan})
    return pd.DataFrame(rows)


def render(daily, asof, groups=None):
    import streamlit as st
    st.title("Trading T+2 · Dòng tiền vào sớm")
    st.caption("Tín hiệu nghiên cứu dựa trên EOD đã xác nhận. Không phải khuyến nghị mua và không tự đặt lệnh.")
    st.info("Tập trung phát hiện sớm nhịp hồi, breakout, tiếp diễn ngắn hạn. Không cần chờ MA100/MA200 đảo chiều. RSI, KL và cấu trúc giá là điều kiện đồng thời, không bảo đảm sinh lời.")
    d = prepare(daily, asof)
    if d.empty:
        st.warning("Dữ liệu EOD chưa đầy đủ để chạy bộ lọc.")
        return
    c1,c2,c3 = st.columns(3)
    with c1:
        kind = st.selectbox("Loại tín hiệu", ["Tất cả"] + list(LABELS.values()), key="t2_kind")
    with c2:
        min_vol = st.selectbox("Vol/TB20 tối thiểu", ["Tất cả", "1.1x", "1.5x", "2.0x", "3.0x"],key="t2_vol")
    with c3:
        sector = st.selectbox("Ngành", ["Toàn thị trường"] + list((groups or {}).keys()),key="t2_sector")
    symbols = set(str(x).upper() for x in (groups or {}).get(sector, [])) if sector != "Toàn thị trường" else None
    # Cache on the EOD date and basic dataset fingerprint, not user input.
    @st.cache_data(show_spinner="Đang tính tín hiệu lịch sử EOD…", ttl=3600)
    def _cached_scan(df, date):
        return scan(df, asof=date)
    now, hist = _cached_scan(d, str(pd.Timestamp(asof).date()))
    if symbols is not None:
        now = now[now["Mã"].isin(symbols)]
        hist = hist[hist["Mã"].isin(symbols)]
    if kind != "Tất cả":
        now = now[now["Tín hiệu"] == kind]
        hist = hist[hist["Tín hiệu"] == kind]
    if min_vol != "Tất cả":
        v = float(min_vol.replace("x",""))
        now = now[now["Vol/TB20"]>=v]
        hist = hist[hist["Vol/TB20"]>=v]
    st.metric("Mã có tín hiệu mới tại EOD", len(now))
    show = ["Mã", "Tín hiệu", "Giá tín hiệu", "RSI14", "Vol/TB20", "Cắt lỗ tham khảo", "Mục tiêu gần", "R:R tham khảo", "Ghi chú"]
    st.subheader("Tín hiệu mới của phiên")
    if now.empty:
        st.caption("Phiên này không có mã đáp ứng các điều kiện. Không tự nới ngưỡng.")
    else:
        st.dataframe(now[show], hide_index=True, use_container_width=True)
    st.subheader("Lịch sử tín hiệu gần đây và diễn biến sau tín hiệu")
    st.caption("Tín hiệu được dựng lại từ lịch sử EOD bằng quy tắc không nhìn trước, chưa lưu nhật ký bất biến theo thời gian. T+n là biến động giá đóng cửa sau n phiên, không phải lợi nhuận thực nhận. Không tính phí/thuế/trượt giá và chưa mô phỏng khả năng khớp lệnh hoặc bán T+2.")
    if hist.empty:
        st.info("Chưa có sự kiện phù hợp trong 90 phiên gần đây.")
        return
    hcols = ["Ngày tín hiệu", "Mã", "Tín hiệu", "Giá tín hiệu", "Giá EOD", "Từ tín hiệu (%)", "Phiên từ tín hiệu", "Vol/TB20", "RSI14"] + [f"T+{h} (%)" for h in HORIZONS]
    st.dataframe(hist[hcols],hide_index=True,use_container_width=True)
    st.subheader("Thống kê quan sát · Chưa phải backtest giao dịch")
    st.dataframe(summary(hist),hide_index=True,use_container_width=True)
    st.caption("Các mốc T+ chưa đủ dữ liệu sẽ để trống, không giả định lợi nhuận. Cần kiểm thử ngoài mẫu và có chi phí trước khi dùng tín hiệu để giao dịch thực.")
