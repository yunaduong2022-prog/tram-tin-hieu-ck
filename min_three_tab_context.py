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


def render_context(context, viewed):
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
        st.caption("Trạng thái và kháng cự gần lấy từ Bản đồ trạng thái; cấu trúc MA lấy từ tab Cấu trúc MA. TP1/TP2 lấy từ tín hiệu T+2 mới nhất đang hiển thị. Cản gần không phải TP.")
