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
    "MA20_VOLUME": "Vượt MA20 + Volume",
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
    g["MA20_prev"] = g["MA20"].shift(1)  # MIN_T2_MA20_VOLUME_INDEPENDENT_V1
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
    # Every level is known at the signal-day EOD; historical highs exclude the signal candle.
    for period in (60, 120, 250):
        g[f"Prev{period}High"] = h.shift(1).rolling(period, min_periods=period).max()
    for period in (50, 100, 200):
        g[f"MA{period}"] = c.rolling(period, min_periods=period).mean()
    # MIN_T2_NEAREST_SUPPORT_V1: prior-session lows exclude signal candle.
    g["Prev3Low"] = lo.shift(1).rolling(3, min_periods=3).min()
    g["Prev5Low"] = lo.shift(1).rolling(5, min_periods=5).min()
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





def _ma20_volume_event(row):
    """True first close above MA20 with confirmed volume/price/RSI at this EOD.

    This is an independent early event, not a replacement for BREAKOUT/EARLY.
    Previous bar MA20 and volume denominator exclude the signal bar.
    """
    required = ("Giá đóng cửa", "PrevClose", "Giá mở cửa", "MA20",
                "MA20_prev", "VolRatio", "VolTB20", "RSI14", "RSI_prev",
                "ClosePos", "Khối lượng khớp lệnh")
    values = [pd.to_numeric(row.get(name, np.nan), errors="coerce") for name in required]
    if any(pd.isna(x) or not np.isfinite(float(x)) for x in values):
        return None
    c, prev_c, o, ma20, prev_ma20, vr, avg_v, rsi, old_rsi, close_pos, volume = map(float, values)
    if c < 5 or avg_v < 100_000 or volume <= 0:
        return None
    crossed = prev_c <= prev_ma20 and c > ma20
    if (crossed and c > prev_c and c >= o and close_pos >= 0.60
            and vr >= 1.5 and rsi > old_rsi):
        return ("MA20_VOLUME", "Vượt MA20 từ dưới lên; KL ≥1.5x TB20; RSI tăng; nến tích cực")
    return None


def _two_targets(row, price):
    """Nearest distinct overhead levels known on the signal date; never synthesize a 2R price."""
    if not np.isfinite(price) or price <= 0:
        return np.nan, "", np.nan, ""
    candidates = []
    # Price structures from completed PRIOR sessions; signal-candle MA is already known at EOD.
    for column, label in (("Prev20High", "Đỉnh 20P"), ("Prev60High", "Đỉnh 60P"),
                          ("Prev120High", "Đỉnh 120P"), ("Prev250High", "Đỉnh 250P"),
                          ("MA20", "MA20"), ("MA50", "MA50"),
                          ("MA100", "MA100"), ("MA200", "MA200")):
        val = row.get(column, np.nan)
        if pd.notna(val) and np.isfinite(float(val)) and float(val) > price:
            candidates.append((float(val), label))
    candidates.sort(key=lambda x: x[0])
    distinct = []
    # Levels closer than 0.5% are one zone, not two artificial separate targets.
    for value, label in candidates:
        if distinct and (value / distinct[-1][0] - 1) < 0.005:
            distinct[-1] = (distinct[-1][0], distinct[-1][1] + " / " + label)
        else:
            distinct.append((value, label))
    one = distinct[0] if len(distinct) > 0 else (np.nan, "")
    two = distinct[1] if len(distinct) > 1 else (np.nan, "")
    return one[0], one[1], two[0], two[1]


def _nearest_support(row, price):
    """Closest valid MA or prior low strictly below signal price, using only signal-day data.

    No arbitrary 7% cutoff or synthetic support. MA is calculated through EOD
    signal day; price lows use ONLY earlier sessions. Missing data is ignored.
    """
    if not np.isfinite(price) or price <= 0:
        return np.nan
    candidates = []
    for col in ("MA9", "MA20", "MA50", "MA100", "MA200",
                "Prev3Low", "Prev5Low", "Prev10Low", "Prev20Low"):
        value = pd.to_numeric(row.get(col, np.nan), errors="coerce")
        if pd.notna(value) and np.isfinite(float(value)) and 0 < float(value) < price:
            candidates.append(float(value))
    return max(candidates) if candidates else np.nan


def scan(daily: pd.DataFrame, asof=None, recent_sessions=90, cooldown=5):
    """Returns (current candidates, historical first events) without lookahead.

    Full historical scan uses the same no-lookahead rules for each session;
    after the event T+h observed closes are attached for research only.
    A repeated signal of the same setup is suppressed within cooldown sessions.
    """
    d = prepare(daily, asof)
    columns = ["Mã", "Ngày tín hiệu", "Tín hiệu", "Giá tín hiệu", "RSI14", "Vol/TB20",
               "Giá EOD", "Từ tín hiệu (%)", "Cắt lỗ tham khảo", "Mục tiêu 1", "Nguồn TP1",
               "Mục tiêu 2", "Nguồn TP2", "R:R TP1", "R:R TP2", "Ghi chú", "Phiên từ tín hiệu"] + [f"T+{h} (%)" for h in HORIZONS]
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
            # MIN_T2_MA20_VOLUME_INDEPENDENT_V1: independent event per setup, same-day overlap allowed.
            choices = []
            ma20_choice = _ma20_volume_event(row)
            if ma20_choice is not None:
                choices.append(ma20_choice)
            legacy_choice = _candidate(row)
            if legacy_choice is not None:
                choices.append(legacy_choice)
            for choice in choices:
                category, note = choice
                if category in last and i - last[category] <= cooldown:
                    continue
                last[category] = i
                price = float(row["Giá đóng cửa"])
                stop = _nearest_support(row, price)
                tp1, src1, tp2, src2 = _two_targets(row, price)
                valid_risk = np.isfinite(stop) and 0 < stop < price
                rr1 = (tp1 - price) / (price - stop) if valid_risk and np.isfinite(tp1) else np.nan
                rr2 = (tp2 - price) / (price - stop) if valid_risk and np.isfinite(tp2) else np.nan
                age = len(g)-1-i if g.iloc[-1]["Ngày"] == asof_date else np.nan
                item = {"Mã":code, "Ngày tín hiệu":dt, "Tín hiệu":LABELS[category], "Giá tín hiệu":price,
                        "RSI14":round(float(row["RSI14"]),2), "Vol/TB20":round(float(row["VolRatio"]),2),
                        "Giá EOD":float(g.iloc[-1]["Giá đóng cửa"]) if g.iloc[-1]["Ngày"] == asof_date else np.nan,
                        "Từ tín hiệu (%)":round((float(g.iloc[-1]["Giá đóng cửa"])/price-1)*100,2) if g.iloc[-1]["Ngày"] == asof_date else np.nan,
                        "Cắt lỗ tham khảo": stop, "Mục tiêu 1":tp1, "Nguồn TP1":src1,
                        "Mục tiêu 2":tp2, "Nguồn TP2":src2, "R:R TP1":rr1, "R:R TP2":rr2,
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



def _fmt_number(val, digits=2):
    x = pd.to_numeric(val, errors="coerce")
    return f"{float(x):,.{digits}f}" if pd.notna(x) and np.isfinite(float(x)) else "—"


def _fmt_signed(val):
    x = pd.to_numeric(val, errors="coerce")
    return f"{float(x):+.2f}%" if pd.notna(x) and np.isfinite(float(x)) else "—"


def _table_html(data):
    """One scrollable table. All percent figures under levels use the latest EOD, not entry."""
    import html
    headers = ["Mã", "Ngày tín hiệu", "Loại tín hiệu", "Tuổi", "Giá tín hiệu", "Giá EOD",
               "% từ tín hiệu", "RSI14", "Vol/TB20", "Cắt lỗ", "TP1", "TP2",
               "R:R TP1", "R:R TP2", "Ghi chú"]
    def e(x):
        return html.escape(str(x), quote=True)
    def cell(x, cls=""):
        return '<td class="' + cls + '">' + x + '</td>'
    def level(value, current, source="", stop=False):
        val = pd.to_numeric(value, errors="coerce")
        now = pd.to_numeric(current, errors="coerce")
        if pd.isna(val) or not np.isfinite(float(val)) or float(val) <= 0:
            return "—"
        pct = ((float(val) / float(now)) - 1) * 100 if pd.notna(now) and np.isfinite(float(now)) and float(now) > 0 else np.nan
        # A level already passed is still shown with its true signed percentage.
        color = "red" if stop or (np.isfinite(pct) and pct < 0) else "green"
        hint = '<span class="t2src">' + e(source) + '</span>' if source else ""
        below = '<span class="t2pct ' + color + '">' + e(_fmt_signed(pct)) + '</span>'
        return '<div class="t2stack"><b>' + e(_fmt_number(val)) + '</b>' + below + hint + '</div>'
    rows = []
    for _, r in data.iterrows():
        now = r["Giá EOD"]
        gain = pd.to_numeric(r["Từ tín hiệu (%)"], errors="coerce")
        gain_cls = "green" if pd.notna(gain) and gain > 0 else "red" if pd.notna(gain) and gain < 0 else ""
        age = pd.to_numeric(r["Phiên từ tín hiệu"], errors="coerce")
        age_txt = "T+" + str(int(age)) if pd.notna(age) and np.isfinite(float(age)) else "—"
        day = pd.to_datetime(r["Ngày tín hiệu"], errors="coerce")
        day_txt = day.strftime("%d/%m/%Y") if pd.notna(day) else "—"
        fields = [cell('<b>' + e(r["Mã"]) + '</b>'), cell(e(day_txt)), cell(e(r["Tín hiệu"])),
                  cell(e(age_txt)), cell(e(_fmt_number(r["Giá tín hiệu"]))), cell('<b>' + e(_fmt_number(now)) + '</b>'),
                  cell(e(_fmt_signed(gain)), gain_cls), cell(e(_fmt_number(r["RSI14"]))),
                  cell(e(_fmt_number(r["Vol/TB20"])) + "x"),
                  cell(level(r["Cắt lỗ tham khảo"], now, stop=True)),
                  cell(level(r["Mục tiêu 1"], now, r["Nguồn TP1"])),
                  cell(level(r["Mục tiêu 2"], now, r["Nguồn TP2"])),
                  cell(e(_fmt_number(r["R:R TP1"]))), cell(e(_fmt_number(r["R:R TP2"]))),
                  cell(e(r["Ghi chú"]), "note")]
        rows.append('<tr>' + "".join(fields) + '</tr>')
    style = """<style>
    .t2outer{overflow-x:auto;max-width:100%;border:1px solid #6b728055;border-radius:10px}
    .t2table{border-collapse:collapse;width:max-content;min-width:100%;font-size:12px;line-height:1.35}
    .t2table th,.t2table td{border-bottom:1px solid #6b728033;padding:10px 10px;text-align:left;vertical-align:middle;white-space:nowrap}
    .t2table th{background:#64748b18;position:sticky;top:0;font-weight:700}
    .t2table tr:hover td{background:#64748b12}
    .t2table .green{color:#16a34a;font-weight:600}.t2table .red{color:#dc2626;font-weight:600}
    .t2stack{display:flex;flex-direction:column;gap:2px}.t2pct{font-size:11px}
    .t2src{font-size:10px;color:inherit;opacity:.65;max-width:140px;white-space:normal}
    .t2table td.note{min-width:180px;max-width:250px;white-space:normal}
    </style>"""
    return style + '<div class="t2outer"><table class="t2table"><thead><tr>' + "".join('<th>'+e(h)+'</th>' for h in headers) + '</tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>'


def render(daily, asof, groups=None):
    import streamlit as st
    st.title("Trading T+2 · Dòng tiền vào sớm")
    st.caption("EOD đã xác nhận, không phải giá realtime. Mỗi dòng là một tín hiệu theo ngày; mức mục tiêu tính tại ngày tín hiệu.")
    st.info("Phát hiện vượt MA20 + Volume / dòng tiền vào sớm / breakout / tiếp diễn. TP1/TP2 là hai vùng cản hợp lệ gần nhất (đỉnh lịch sử hoặc MA); không bảo đảm đạt mục tiêu.")
    d = prepare(daily, asof)
    if d.empty:
        st.warning("Dữ liệu EOD chưa đầy đủ để chạy bộ lọc.")
        return
    c1,c2,c3,c4 = st.columns(4)
    with c1:
        kind = st.selectbox("Loại tín hiệu", ["Tất cả"] + list(LABELS.values()), key="t2_kind")
    with c2:
        min_vol = st.selectbox("Vol/TB20 tối thiểu", ["Tất cả", "1.1x", "1.5x", "2.0x", "3.0x"], key="t2_vol")
    with c3:
        sector = st.selectbox("Ngành", ["Toàn thị trường"] + list((groups or {}).keys()), key="t2_sector")
    with c4:
        state = st.selectbox("Trạng thái", ["Tất cả", "Mới T+0", "Đang theo dõi"], key="t2_state")
    # MIN_T2_SYMBOL_SEARCH_V1: filter only the display; preserve full-market scan/cache.
    symbol_query = st.text_input("Lọc theo mã cổ phiếu", placeholder="VD: CEO, DXG, HDG", key="t2_symbol_search")
    search_codes = {part.strip().upper() for part in symbol_query.replace(";", ",").replace(" ", ",").split(",") if part.strip()}
    symbols = set(str(x).upper() for x in (groups or {}).get(sector, [])) if sector != "Toàn thị trường" else None
    # Versioned cache function: the previous release cached the old schema
    # without "Mục tiêu 1" / "Mục tiêu 2", causing a pandas KeyError in HTML.
    @st.cache_data(show_spinner="Đang tính tín hiệu lịch sử EOD…", ttl=3600)
    def _cached_scan_t2_ma20volume_v4(df, date, schema_version):
        return scan(df, asof=date)
    _, hist = _cached_scan_t2_ma20volume_v4(d, str(pd.Timestamp(asof).date()), "t2_ma20volume_v4")
    required_schema = {"Mục tiêu 1", "Nguồn TP1", "Mục tiêu 2", "Nguồn TP2", "R:R TP1", "R:R TP2"}
    # Recover locally if a cache migration or deployment ever returns a stale frame.
    if not required_schema.issubset(hist.columns):
        _, hist = scan(d, asof=asof)
    if not required_schema.issubset(hist.columns):
        st.error("Dữ liệu bộ lọc T+2 chưa đúng phiên bản. Vui lòng kiểm tra bản triển khai.")
        return
    if symbols is not None:
        hist = hist[hist["Mã"].isin(symbols)]
    if search_codes:
        hist = hist[hist["Mã"].isin(search_codes)]
    if kind != "Tất cả":
        hist = hist[hist["Tín hiệu"] == kind]
    if min_vol != "Tất cả":
        hist = hist[hist["Vol/TB20"] >= float(min_vol.replace("x", ""))]
    if state == "Mới T+0":
        hist = hist[hist["Phiên từ tín hiệu"] == 0]
    elif state == "Đang theo dõi":
        hist = hist[hist["Phiên từ tín hiệu"] > 0]
    st.metric("Số tín hiệu phù hợp", len(hist))
    st.subheader("Bảng theo dõi Trading T+2")
    if hist.empty:
        st.info("Không có tín hiệu đáp ứng bộ lọc.")
        return
    s1, s2 = st.columns(2)
    with s1:
        order = st.selectbox("Sắp xếp", ["Ngày mới nhất", "% từ tín hiệu cao", "Vol/TB20 cao", "R:R TP1 cao"], key="t2_sort")
    with s2:
        limit = st.selectbox("Số dòng hiển thị", [30, 60, 100, "Tất cả"], key="t2_limit")
    sortkeys = {"Ngày mới nhất": "Ngày tín hiệu", "% từ tín hiệu cao": "Từ tín hiệu (%)",
                "Vol/TB20 cao": "Vol/TB20", "R:R TP1 cao": "R:R TP1"}
    hist = hist.sort_values([sortkeys[order], "Mã"], ascending=[False, True], na_position="last")
    viewed = hist if limit == "Tất cả" else hist.head(int(limit))
    st.markdown(_table_html(viewed), unsafe_allow_html=True)
    st.caption("Cắt lỗ tham khảo = hỗ trợ gần nhất dưới giá tín hiệu (MA9/20/50/100/200 hoặc đáy 3/5/10/20 phiên trước). % dưới Cắt lỗ, TP1, TP2 = (mức giá / Giá EOD − 1) × 100. Màu thể hiện khoảng cách thực tế; cắt lỗ màu đỏ. R:R TP1/TP2 tính cố định theo giá tín hiệu, không tính lại từ EOD hiện tại. '—' là thiếu mức hợp lệ.")
    st.subheader("Thống kê quan sát · Chưa phải backtest giao dịch")
    st.dataframe(summary(hist), hide_index=True, use_container_width=True)
    st.caption("T+2/5/10/15/20/30 là biến động đóng cửa của cổ phiếu sau tín hiệu, không phải lợi nhuận đã giao dịch. Chưa tính phí, thuế, trượt giá, khớp lệnh, hoặc ngày có quyền bán. Tín hiệu lịch sử dựng lại theo quy tắc không nhìn trước.")
