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


def rank_top10(history, daily, asof, max_results=10, allowed_codes=None):
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
    # Sector + cap intersection applied BEFORE Top 10 selection and scoring.
    if allowed_codes is not None:
        allowed = {str(code).strip().upper() for code in allowed_codes}
        h = h[h["Mã"].astype(str).str.strip().str.upper().isin(allowed)]
        if h.empty:
            return pd.DataFrame(columns=columns)
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


# MIN_T2_TOP10_CONTRAST_UI_V1

def _top10_table_html(show):
    """Dark-theme legible, horizontally scrollable shortlist; presentation only."""
    from html import escape as _esc
    import pandas as pd

    headers = list(show.columns)
    def text(value):
        if pd.isna(value):
            return "—"
        return _esc(str(value), quote=True)

    rows = []
    for _, row in show.iterrows():
        rank = int(row["Hạng"])
        cells = []
        for name in headers:
            val = text(row[name])
            if name == "Hạng":
                rank_style = {1: "t2top-gold", 2: "t2top-silver", 3: "t2top-bronze"}.get(rank, "t2top-normal")
                val = '<span class="t2top-rank ' + rank_style + '">' + val + '</span>'
            elif name == "Mã":
                val = '<strong class="t2top-ticker">' + val + '</strong>'
            elif name == "Điểm T+":
                val = '<strong class="t2top-score">' + val + '</strong>'
            cls = ' class="t2top-num"' if name in {"Hạng", "Điểm T+", "Giá EOD", "Vol/TB20 EOD", "RSI14 EOD", "Position", "TP1 động", "Dư địa TP1", "R:R EOD"} else ''
            cells.append('<td' + cls + '>' + val + '</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    style = """<style>
    .t2top-wrap{width:100%;max-width:100%;overflow-x:auto;overscroll-behavior-x:contain;
      border:1px solid #3d5b50;border-radius:10px;background:#0d211b;
      scrollbar-color:#658b7a #142720}
    .t2top-table{border-collapse:separate;border-spacing:0;min-width:1420px;width:100%;
      font-size:13px;line-height:1.5;color:#e9f4ee;font-variant-numeric:tabular-nums}
    .t2top-table th{background:#203b30;color:#f5fff9;font-weight:750;
      font-size:12px;letter-spacing:.015em;border-bottom:1px solid #537668;
      padding:12px 11px;text-align:left;white-space:nowrap}
    .t2top-table td{color:#e6f0eb;padding:11px;border-bottom:1px solid #305044;
      vertical-align:middle;white-space:nowrap;background:#10271f}
    .t2top-table tbody tr:nth-child(even) td{background:#153027}
    .t2top-table tbody tr:hover td{background:#244336}
    .t2top-table tbody tr:last-child td{border-bottom:0}
    .t2top-table .t2top-num{text-align:right}
    .t2top-table .t2top-ticker{font-size:15px;color:#f7fff9;letter-spacing:.02em}
    .t2top-table .t2top-score{color:#83e2b4;font-size:16px;font-weight:800}
    .t2top-rank{display:inline-flex;align-items:center;justify-content:center;
      min-width:29px;padding:2px 7px;border-radius:7px;font-size:13px;font-weight:800}
    .t2top-gold{background:#554124;color:#ffdc88;border:1px solid #b28b47}
    .t2top-silver{background:#344248;color:#dce8f0;border:1px solid #8295a1}
    .t2top-bronze{background:#503c30;color:#f1c5a4;border:1px solid #aa7557}
    .t2top-normal{color:#c9ddd2}
    @media(max-width:720px){.t2top-table{font-size:12px;min-width:1250px}
      .t2top-table th,.t2top-table td{padding:9px 8px}}
    </style>"""
    return (style + '<div class="t2top-wrap" role="region" aria-label="Top 10 cổ phiếu T+2" tabindex="0">'
            + '<table class="t2top-table"><thead><tr>'
            + ''.join('<th scope="col">' + _esc(str(h), quote=True) + '</th>' for h in headers)
            + '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>')


# MIN_T2_TOP10_SECTOR_CAP_V2
def render_top10(history, daily, asof, groups=None):
    """Rank only eligible stocks in the chosen sector and index-cap member group.

    The upper and lower sector controls share user selection via callbacks.
    Market-cap groups use existing index-membership rosters, not guessed cap.
    """
    import streamlit as st
    st.markdown("### TOP 10 CỔ PHIẾU MẠNH CÓ TÍN HIỆU MUA T+2")
    st.caption("EOD " + pd.Timestamp(asof).strftime("%d/%m/%Y") +
               " · T+0–T+5 · Xếp hạng sau khi lọc ngành và nhóm vốn hóa · Không phải khuyến nghị mua tự động")
    sector_groups = {str(name): {str(c).strip().upper() for c in members}
                     for name, members in (groups or {}).items() if members}
    options = ["Toàn thị trường"] + sorted(sector_groups)
    if "t2_top10_sector" not in st.session_state:
        lower = st.session_state.get("t2_sector", "Toàn thị trường")
        st.session_state["t2_top10_sector"] = lower if lower in options else "Toàn thị trường"
    elif st.session_state["t2_top10_sector"] not in options:
        st.session_state["t2_top10_sector"] = "Toàn thị trường"

    def sync_sector_to_lower():
        st.session_state["t2_sector"] = st.session_state["t2_top10_sector"]

    a, b = st.columns(2)
    with a:
        selected_sector = st.selectbox("Ngành xếp hạng Top 10", options,
                                        key="t2_top10_sector", on_change=sync_sector_to_lower,
                                        help="Đồng bộ hai chiều với ô Ngành ở bộ lọc Trading T+2 bên dưới.")
    with b:
        selected_cap = st.selectbox("Nhóm vốn hóa Top 10", [
            "Tất cả nhóm vốn hóa", "Vốn hóa lớn · VN30",
            "Vốn hóa vừa · VNMidcap", "Vốn hóa nhỏ · VNSmallcap"],
            key="t2_top10_cap",
            help="Dùng danh sách thành viên VN30, VNMidcap, VNSmallcap của website; không phải phân loại theo mức vốn hóa tức thời.")

    allowed = None if selected_sector == "Toàn thị trường" else sector_groups.get(selected_sector, set())
    if selected_cap != "Tất cả nhóm vốn hóa":
        # Reuse exactly the membership source already used by Thị trường > Nhóm vốn hóa.
        import cap_groups as CG
        members = CG.group_lists(None)
        group_code = {"Vốn hóa lớn · VN30":"VN30", "Vốn hóa vừa · VNMidcap":"VNMIDCAP",
                      "Vốn hóa nhỏ · VNSmallcap":"VNSMALLCAP"}[selected_cap]
        group_members = {str(code).strip().upper() for code in members.get(group_code, [])}
        if not group_members:
            st.warning("Chưa có danh sách thành viên " + group_code +
                       " trong dữ liệu nhóm vốn hóa. Không tự suy đoán phân loại cho các mã.")
            return
        allowed = group_members if allowed is None else allowed & group_members
    if allowed is not None and not allowed:
        st.info("Không có mã nào thuộc đồng thời ngành và nhóm vốn hóa đã chọn.")
        return
    scope = selected_sector + " · " + selected_cap
    st.caption("Phạm vi đang xếp hạng: " + scope + ".")
    leaders = rank_top10(history, daily, asof, allowed_codes=allowed)
    if leaders.empty:
        st.info("Không có mã đáp ứng điều kiện mua T+2 trong phạm vi này. Không thêm mã chỉ để đủ Top 10.")
        return
    show = leaders.copy()
    show["Vol/TB20 EOD"] = show["Vol/TB20 EOD"].map(lambda x: f"{x:.2f}x")
    show["Dư địa TP1"] = show["Dư địa TP1"].map(lambda x: f"{x:.1f}%")
    show["Position"] = show["Position"].map(lambda x: f"{x:.0f}%")
    st.markdown(_top10_table_html(show), unsafe_allow_html=True)
    with st.expander("Điều kiện Top 10 và cách tính điểm"):
        st.write("Chỉ lấy tín hiệu T+0–T+5, giá trên MA9/MA20, nến tăng và đóng cửa ở ≥60% biên độ, Vol/TB20 EOD ≥1.1x, RSI14 EOD 45–78, giá không quá 8% trên MA9, còn dư địa TP1 ≥5%, R:R EOD ≥2, chưa chạm cắt lỗ gốc theo dữ liệu có sẵn.")
        st.write("Điểm 100 = MA 25 + RSI14 20 + Volume 20 + chất lượng nến 20 + dư địa/R:R 15. Phân loại vốn hóa theo danh sách rổ chỉ số có sẵn; mã chưa được phân loại không xuất hiện trong bộ lọc nhóm tương ứng.")
