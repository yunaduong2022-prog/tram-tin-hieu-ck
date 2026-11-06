"""Min Invest: read-only stock state map from existing confirmed EOD analysis.

No API, writes, trade execution, or independent buy/sell engine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
import waiting_buy as WB
import ma_top10 as TOP


# MIN_STATE_MAP_ADVANCED_FILTER_V1
_FILTER_KEYS = ("sm_adv_state", "sm_adv_ma", "sm_adv_rs", "sm_adv_signal",
                "sm_adv_rr", "sm_adv_dist", "sm_adv_sort")


def _reset_advanced_filters():
    for key in _FILTER_KEYS:
        st.session_state.pop(key, None)
    st.session_state.pop("state_map_sector", None)
    st.session_state.pop("state_map_search", None)


def _filter_advanced(table, state=None, ma_min=None, rs_min=None,
                     signal_min=None, rr_min=None, support_max=None, sort_by="MA"):
    """Filter the ALREADY-classified rows; never recompute signals, price or RR."""
    out = table.copy()
    if state is not None:
        out = out[out["Nhóm gốc"] == state]
    for col, floor in (("Điểm MA /100", ma_min), ("RS20 (%)", rs_min),
                       ("Điểm tín hiệu", signal_min), ("R:R", rr_min)):
        if floor is not None:
            value = pd.to_numeric(out[col], errors="coerce")
            out = out[value.notna() & (value >= floor)]
    if support_max is not None:
        price = pd.to_numeric(out["Giá EOD"], errors="coerce")
        support = pd.to_numeric(out["Hỗ trợ"], errors="coerce")
        distance = (price / support - 1) * 100
        out = out[(support > 0) & (price >= support) &
                  distance.notna() & (distance <= support_max)]
    cols = {"MA": "Điểm MA /100", "RS20": "RS20 (%)",
            "R:R": "R:R", "Signal": "Điểm tín hiệu"}
    if sort_by in cols:
        out = out.sort_values([cols[sort_by], "Mã"],
                              ascending=[False, True], na_position="last")
    else:
        out = out.sort_values("Mã", ascending=True)
    return out


DISPLAY_GROUPS = (
    (WB.G1, "MUA ĐỦ ĐIỀU KIỆN THEO BỘ LỌC"),
    (WB.G2, "CHỜ ĐIỂM MUA"),
    (WB.G3, "THEO DÕI THÊM"),
    (WB.L_RECOVER, "ĐANG HỒI PHỤC"),
    (WB.L_OVERBOUGHT, "TĂNG NÓNG / KHÔNG MUA ĐUỔI"),
    (WB.L_RISK, "SUY YẾU / CẢNH BÁO"),
    (WB.L_NONE, "CHƯA CÓ ĐIỂM MUA"),
)


def _number(value):
    n = pd.to_numeric(value, errors="coerce")
    try:
        return float(n) if pd.notna(n) and np.isfinite(float(n)) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _point(x):
    x = _number(x)
    return x if np.isfinite(x) and x > 0 else np.nan


def _index_rs(daily, index_daily, asof):
    """Exact-date 20-stock-session relative performance, no synthetic index."""
    if daily is None or index_daily is None or daily.empty or index_daily.empty:
        return {}
    required = {"Mã", "Ngày", "Giá đóng cửa"}
    if not required.issubset(daily) or not {"Ngày", "Giá đóng cửa"}.issubset(index_daily):
        return {}
    asof = pd.Timestamp(asof).normalize()
    idx = index_daily[["Ngày", "Giá đóng cửa"]].copy()
    idx["Ngày"] = pd.to_datetime(idx["Ngày"], format="mixed", dayfirst=True, errors="coerce").dt.normalize()
    idx["Giá đóng cửa"] = pd.to_numeric(idx["Giá đóng cửa"], errors="coerce")
    idx = idx.dropna().sort_values("Ngày").drop_duplicates("Ngày", keep="last").set_index("Ngày")["Giá đóng cửa"]
    if asof not in idx.index or not _point(idx.loc[asof]) > 0:
        return {}
    d = daily[["Mã", "Ngày", "Giá đóng cửa"]].copy()
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    d["Ngày"] = pd.to_datetime(d["Ngày"], format="mixed", dayfirst=True, errors="coerce").dt.normalize()
    d["Giá đóng cửa"] = pd.to_numeric(d["Giá đóng cửa"], errors="coerce")
    d = d.dropna().loc[lambda f: f["Ngày"] <= asof].sort_values(["Mã", "Ngày"]).drop_duplicates(["Mã", "Ngày"], keep="last")
    out = {}
    for code, g in d.groupby("Mã"):
        if len(g) < 21 or g["Ngày"].iloc[-1] != asof:
            continue
        old = g.iloc[-21]
        past = old["Ngày"]
        a, b, c, e = _point(g["Giá đóng cửa"].iloc[-1]), _point(old["Giá đóng cửa"]), _point(idx.loc[asof]), _point(idx.loc[past]) if past in idx.index else np.nan
        if all(np.isfinite(x) and x > 0 for x in (a,b,c,e)):
            out[code] = (a / b / (c / e) - 1) * 100
    return out


def _levels(row, screener):
    price = _point(row.get("Giá"))
    support_candidates = [_point(row.get("Vùng mua đến")), _point(screener.get("Support_20")),
                          _point(screener.get("MA20")), _point(screener.get("MA50"))]
    resist_candidates = [_point(row.get("Cản gần")), _point(screener.get("Resistance_20")),
                         _point(row.get("Mục tiêu 1"))]
    below = [x for x in support_candidates if np.isfinite(x) and np.isfinite(price) and x < price]
    above = [x for x in resist_candidates if np.isfinite(x) and np.isfinite(price) and x > price]
    return (max(below) if below else np.nan, min(above) if above else np.nan)


def _rr(row):
    """Recalculate from actual entry, stop, first target; do not use placeholder RR."""
    entry, stop, target = (_point(row.get(k)) for k in ("Giá vào", "Cắt lỗ", "Mục tiêu 1"))
    if all(np.isfinite(x) for x in (entry, stop, target)) and stop < entry < target:
        return (target-entry)/(entry-stop)
    return np.nan


def _action(row):
    sell = str(row.get("Hành động bán", "") or "").strip()
    group = row.get("Danh sách")
    if sell in ("BÁN", "CHỐT LỜI"):
        return "Cảnh báo " + sell.lower()
    if group == WB.G1:
        return "Kiểm tra điểm mua" if row.get("Hành động") == "Vào ngay" else "Chờ xác nhận"
    if group in (WB.G2, WB.G3, WB.L_RECOVER):
        return "Theo dõi / chờ"
    if group == WB.L_OVERBOUGHT:
        return "Không mua đuổi"
    if group == WB.L_RISK:
        return "Thận trọng"
    return "Đứng ngoài"


def _note(rs, ma, rr, sup, price, action):
    parts = []
    if np.isfinite(rs):
        parts.append("RS20 vượt trội" if rs >= 3 else "RS20 dương" if rs >= 0 else "RS20 âm")
    else:
        parts.append("chưa đủ RS20")
    if np.isfinite(ma):
        parts.append("MA mạnh" if ma >= 80 else "MA tích cực" if ma >= 65 else "MA chưa đồng thuận" if ma >= 50 else "MA yếu")
    else:
        parts.append("chưa đủ MA")
    if np.isfinite(rr):
        parts.append("R:R tốt" if rr >= 3 else "R:R đạt 2" if rr >= 2 else "R:R thấp")
    else:
        parts.append("chưa có R:R hợp lệ")
    if np.isfinite(sup) and np.isfinite(price) and 0 <= (price / sup - 1) * 100 <= 3:
        parts.append("gần hỗ trợ")
    if "Cảnh báo" in action:
        parts.append("ưu tiên xử lý tín hiệu bán")
    return "; ".join(parts)


def build(wb, screener, daily, index_daily, asof, groups=None, sector="Toàn thị trường"):
    """One row per existing waiting_buy ticker, preserving its original classification."""
    columns = ["Mã", "Giá EOD", "Hỗ trợ", "Kháng cự", "RS20 (%)", "Điểm MA /100", "Điểm tín hiệu", "R:R", "Diễn giải", "Hành động", "Trạng thái gốc", "Nhóm gốc"]
    if wb is None or wb.empty or screener is None or screener.empty:
        return pd.DataFrame(columns=columns)
    strength, _, _ = TOP.rank_ma(daily, asof, index_daily=index_daily, limit=None)
    ma_map = strength.set_index("Mã")["Tổng hợp"].to_dict() if not strength.empty else {}
    rs_map = _index_rs(daily, index_daily, asof)
    sc = screener.drop_duplicates("Mã").set_index("Mã")
    group_codes = set(str(c).upper() for c in (groups or {}).get(sector, [])) if sector != "Toàn thị trường" else None
    rows = []
    for _, row in wb.drop_duplicates("Mã").iterrows():
        code = str(row.get("Mã", "")).upper().strip()
        if not code or code not in sc.index or (group_codes is not None and code not in group_codes):
            continue
        s = sc.loc[code]
        price = _point(row.get("Giá"))
        if not np.isfinite(price):
            price = _point(s.get("Giá"))
        sup, resist = _levels(row, s)
        rr = _rr(row)
        rs, ma = _number(rs_map.get(code)), _number(ma_map.get(code))
        action = _action(row)
        rows.append({"Mã":code, "Giá EOD":price, "Hỗ trợ":sup,"Kháng cự":resist,
                     "RS20 (%)":rs, "Điểm MA /100":ma, "Điểm tín hiệu":_number(s.get("Score")),
                     "R:R":rr, "Diễn giải":_note(rs,ma,rr,sup,price,action), "Hành động":action,
                     "Trạng thái gốc":row.get("Trạng thái", ""),"Nhóm gốc":row.get("Danh sách", "")})
    return pd.DataFrame(rows, columns=columns)


def render(wb, screener, daily, index_daily, asof, groups):
    st.title("Bản đồ trạng thái cổ phiếu")
    st.caption(f"Dữ liệu EOD {pd.Timestamp(asof):%d/%m/%Y} · phân nhóm theo bộ lọc Mua ngay/Chờ mua hiện có. Không phải giá realtime hay khuyến nghị giao dịch.")
    symbols = set(screener["Mã"].astype(str)) if screener is not None and not screener.empty else set()
    sectors = ["Toàn thị trường"] + [g for g, codes in groups.items() if symbols.intersection(codes)]
    a,b = st.columns([2,2])
    with a:
        sector = st.selectbox("Nhóm ngành", sectors, key="state_map_sector")
    with b:
        query = st.text_input("Tìm mã", placeholder="VD: KDH, VIX", key="state_map_search").upper().strip()
    table = build(wb,screener,daily,index_daily,asof,groups,sector)
    if query:
        table = table[table["Mã"].str.contains(query, regex=False)]
    # Advanced filters act on the already-calculated table, not on its signal engine.
    base_count = len(table)
    with st.expander("🔍 Lọc cổ phiếu nâng cao", expanded=False):
        f1, f2, f3 = st.columns(3)
        with f1:
            state_label = st.selectbox("Trạng thái", ["Tất cả"] + [label for _, label in DISPLAY_GROUPS], key="sm_adv_state")
            ma_label = st.selectbox("Điểm MA tối thiểu", ["Tất cả", "50", "65", "70", "80", "90"], key="sm_adv_ma")
            rs_label = st.selectbox("RS20 tối thiểu", ["Tất cả", "0%", "+3%", "+5%", "+10%"], key="sm_adv_rs")
        with f2:
            signal_label = st.selectbox("Điểm tín hiệu tối thiểu", ["Tất cả", "4", "5", "6", "7", "8"], key="sm_adv_signal")
            rr_label = st.selectbox("R:R tối thiểu", ["Tất cả", "1.5", "2", "2.5", "3"], key="sm_adv_rr")
            dist_label = st.selectbox("Khoảng cách hỗ trợ", ["Tất cả", "≤ 2%", "≤ 3%", "≤ 5%"], key="sm_adv_dist")
        with f3:
            sort_label = st.selectbox("Sắp xếp", ["Điểm MA giảm dần", "RS20 giảm dần", "R:R giảm dần", "Điểm tín hiệu giảm dần", "Mã A–Z"], key="sm_adv_sort")
            st.button("↺ Đặt lại bộ lọc", key="sm_adv_reset", on_click=_reset_advanced_filters)
    selected_state = next((source for source, label in DISPLAY_GROUPS if label == state_label), None)
    choices = {"Điểm MA giảm dần": "MA", "RS20 giảm dần": "RS20",
               "R:R giảm dần": "R:R", "Điểm tín hiệu giảm dần": "Signal", "Mã A–Z": "Code"}
    table = _filter_advanced(
        table, state=selected_state,
        ma_min=None if ma_label == "Tất cả" else float(ma_label),
        rs_min=None if rs_label == "Tất cả" else float(rs_label.replace("%", "")),
        signal_min=None if signal_label == "Tất cả" else float(signal_label),
        rr_min=None if rr_label == "Tất cả" else float(rr_label),
        support_max=None if dist_label == "Tất cả" else float(dist_label.replace("≤", "").replace("%", "").strip()),
        sort_by=choices[sort_label])
    st.caption(f"**Kết quả lọc: {len(table)}/{base_count} mã** · Các tiêu chí được kết hợp đồng thời (AND). Dữ liệu thiếu không được tự điền.")
    if table.empty:
        st.info("Không có mã phù hợp. Thử giảm ngưỡng hoặc đặt lại bộ lọc.")
    st.caption("RS20: hiệu suất tương đối 20 phiên với VN-Index · Điểm MA: /100 · Điểm tín hiệu: thang điểm gốc · R:R tính từ Giá vào/Cắt lỗ/Mục tiêu 1 thực tế; — là thiếu dữ liệu.")
    for source, label in DISPLAY_GROUPS:
        subset = table[table["Nhóm gốc"] == source].copy()
        with st.expander(f"{label} ({len(subset)})", expanded=source==WB.G1):
            if subset.empty:
                st.caption("Không có mã phù hợp.")
                continue
            view = subset.drop(columns=["Trạng thái gốc","Nhóm gốc"])
            view = view.sort_values(["Điểm MA /100", "RS20 (%)"], ascending=[False,False], na_position="last")
            st.dataframe(view, hide_index=True, use_container_width=True,
                column_config={
                    "Giá EOD":st.column_config.NumberColumn(format="%.2f"),
                    "Hỗ trợ":st.column_config.NumberColumn(format="%.2f"),
                    "Kháng cự":st.column_config.NumberColumn(format="%.2f"),
                    "RS20 (%)":st.column_config.NumberColumn(format="%+.2f"),
                    "Điểm MA /100":st.column_config.ProgressColumn(min_value=0,max_value=100,format="%.0f"),
                    "Điểm tín hiệu":st.column_config.NumberColumn(format="%.1f"),
                    "R:R":st.column_config.NumberColumn(format="%.2f"),
                    "Diễn giải":st.column_config.TextColumn(width="large"),
                })
            st.caption("Hỗ trợ/kháng cự chỉ là mức kỹ thuật tham khảo; hành động phản ánh bộ lọc hiện có, không tự suy ra lệnh mua từ RS hoặc điểm MA.")
