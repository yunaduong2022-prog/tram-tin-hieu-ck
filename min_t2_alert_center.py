"""Read-only, EOD T+2 alert center. No order/execution or portfolio assumptions.

Uses the existing T+2 signals and min_t2_position_guard logic, all from the
same confirmed as-of daily data. Scope is the shared Top-10 sector/cap filters.
"""
from __future__ import annotations

import html
import numpy as np
import pandas as pd

ACTIVE_AGE = 15
LIMIT = 100
RED = {"ĐÃ CHẠM CẮT LỖ GỐC", "CHẠM CẢ CẮT LỖ VÀ TP TRONG CÙNG PHIÊN"}
MA_RISK = {"BÁN / HẠ TỶ TRỌNG", "CẢNH BÁO BÁN", "SUY YẾU"}


def _num(value):
    try:
        x = float(pd.to_numeric(value, errors="coerce"))
        return x if np.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def allowed_symbols(groups, sector, cap, group_lists=None):
    """Reuse the exact sector and index-member semantics of Top 10.

    Missing capital-group roster must fail closed, not become 'all market'.
    """
    selected = None
    if sector != "Toàn thị trường":
        selected = {str(x).upper().strip() for x in (groups or {}).get(sector, [])}
    if cap != "Tất cả nhóm vốn hóa":
        names = {"Vốn hóa lớn · VN30": "VN30",
                 "Vốn hóa vừa · VNMidcap": "VNMIDCAP",
                 "Vốn hóa nhỏ · VNSmallcap": "VNSMALLCAP"}
        key = names.get(cap)
        if key is None:
            return set(), "Không nhận diện được nhóm vốn hóa đã chọn."
        if group_lists is None:
            try:
                import cap_groups
                group_lists = cap_groups.group_lists(None)
            except (ImportError, OSError, ValueError) as exc:
                return set(), "Không đọc được danh sách vốn hóa: " + str(exc)
        members = {str(x).upper().strip() for x in (group_lists or {}).get(key, [])}
        if not members:
            return set(), "Thiếu danh sách thành viên " + key + "; không tự gán vốn hóa."
        selected = members if selected is None else selected & members
    return selected, ""


def compute_alerts(history, daily, asof, scope=None, age_limit=ACTIVE_AGE):
    """Evaluate at most one latest signal per ticker; no future-bar reading.

    Risk ordering: original stop/ambiguous > EOD sell/weak MA20 > original
    target observed > near original target > T+0 new > active watch.
    Does NOT infer entries, exits, fills or a user's holding.
    """
    columns = ["Mã", "Mức độ", "Cảnh báo", "Tín hiệu", "Tuổi", "Giá EOD",
               "Cắt lỗ gốc", "TP1 gốc", "Vol/TB20", "Giải thích"]
    needed = {"Mã", "Ngày tín hiệu", "Phiên từ tín hiệu", "Tín hiệu", "Giá EOD", "Giá tín hiệu", "Cắt lỗ tham khảo", "Mục tiêu 1"}
    needed_daily = {"Mã", "Ngày", "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"}
    if history is None or daily is None or history.empty or daily.empty or not needed.issubset(history.columns) or not needed_daily.issubset(daily.columns):
        return pd.DataFrame(columns=columns)
    day = pd.Timestamp(asof).normalize()
    h = history.copy()
    h["Mã"] = h["Mã"].astype(str).str.upper().str.strip()
    h["Ngày tín hiệu"] = pd.to_datetime(h["Ngày tín hiệu"], errors="coerce").dt.normalize()
    h["Phiên từ tín hiệu"] = pd.to_numeric(h["Phiên từ tín hiệu"], errors="coerce")
    h = h[h["Phiên từ tín hiệu"].between(0, age_limit) & h["Ngày tín hiệu"].notna()]
    if scope is not None:
        h = h[h["Mã"].isin(scope)]
    if h.empty:
        return pd.DataFrame(columns=columns)
    # Latest signal per ticker. Signals of different types on the same day
    # are resolved deterministically by label; this is a watchlist, not history.
    h = (h.sort_values(["Ngày tín hiệu", "Mã", "Tín hiệu"], ascending=[False, True, True])
           .drop_duplicates("Mã", keep="first"))
    d = daily.loc[:, list(needed_daily)].copy()
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce").dt.normalize()
    d = d[d["Ngày"].notna() & (d["Ngày"] <= day)]
    # Full calendar is checked BEFORE using per-ticker slices in lifecycle.
    market_days = set(d["Ngày"])
    wanted = set(h["Mã"])
    by_code = {code: g.sort_values("Ngày") for code, g in d[d["Mã"].isin(wanted)].groupby("Mã", sort=False)}
    from min_t2_position_guard import exit_condition, signal_lifecycle
    records = []
    for _, signal in h.iterrows():
        code = signal["Mã"]
        g = by_code.get(code)
        if g is None or g.empty or g["Ngày"].iloc[-1] != day:
            continue  # no current EOD, no alert status
        date = signal["Ngày tín hiệu"]
        current = _num(signal["Giá EOD"])
        actual = _num(g["Giá đóng cửa"].iloc[-1])
        if not np.isfinite(current) or not np.isfinite(actual) or abs(actual - current) > .011:
            continue
        window = g[g["Ngày"] >= date]
        calendar = {x for x in market_days if date <= x <= day}
        missing = bool(calendar - set(window["Ngày"])) or window["Ngày"].duplicated().any()
        if missing:
            life = {"status": "CHƯA ĐỦ DỮ LIỆU", "note": "Thiếu nến EOD trong thời gian tín hiệu; không xác định đã chạm mức gốc."}
        else:
            # Already checked the global calendar; pass the much smaller per-code
            # frame to the existing lifecycle classifier for performance.
            life = signal_lifecycle(g, signal, day)
        risk = exit_condition(g, code, day)
        life_status = life["status"]
        risk_status = risk["status"]
        stop = _num(signal.get("Cắt lỗ gốc", signal.get("Cắt lỗ tham khảo")))
        tp1 = _num(signal.get("TP1 gốc", signal.get("Mục tiêu 1")))
        age = int(signal["Phiên từ tín hiệu"])
        if life_status in RED:
            level, alert, explanation = "Rủi ro", "Chạm cắt lỗ gốc", life["note"]
        elif life_status == "CHƯA ĐỦ DỮ LIỆU" or risk_status == "CHƯA ĐỦ DỮ LIỆU":
            level, alert, explanation = "Thiếu dữ liệu", "Không đủ dữ liệu", life.get("note", "") + " " + risk.get("reason", "")
        elif risk_status in MA_RISK:
            level, alert, explanation = "Rủi ro", risk_status, risk["reason"]
        elif life_status in {"ĐÃ CHẠM TP1 GỐC", "ĐÃ CHẠM TP2 GỐC"}:
            level, alert, explanation = "Mục tiêu", life_status, life["note"]
        elif np.isfinite(tp1) and tp1 > 0 and 0 <= (tp1 / current - 1) * 100 <= 3:
            level, alert, explanation = "Mục tiêu", "Gần TP1 gốc", f"Cách TP1 gốc {(tp1/current-1)*100:.1f}%; không phải TP động."
        elif age == 0:
            level, alert, explanation = "Tín hiệu mới", "T+0 · Theo dõi điểm mua", "Tín hiệu tại EOD; không xác nhận lệnh mua đã khớp."
        else:
            level, alert, explanation = "Theo dõi", "Tín hiệu đang theo dõi", "Chưa có cảnh báo rủi ro theo các điều kiện đang kiểm tra."
        records.append({"Mã": code, "Mức độ": level, "Cảnh báo": alert,
                        "Tín hiệu": str(signal["Tín hiệu"]), "Tuổi": "T+" + str(age),
                        "Giá EOD": round(current, 2), "Cắt lỗ gốc": round(stop, 2) if np.isfinite(stop) else np.nan,
                        "TP1 gốc": round(tp1, 2) if np.isfinite(tp1) else np.nan,
                        "Vol/TB20": round(_num(risk.get("vol_ratio")), 2),
                        "Giải thích": explanation})
    if not records:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(records)
    rank = {"Rủi ro": 0, "Thiếu dữ liệu": 1, "Mục tiêu": 2, "Tín hiệu mới": 3, "Theo dõi": 4}
    result["_rank"] = result["Mức độ"].map(rank)
    result = result.sort_values(["_rank", "Mã"], ascending=[True, True]).drop(columns="_rank")
    return result.reset_index(drop=True)[columns]


def _table_html(frame):
    headers = list(frame.columns)
    texts = []
    for _, row in frame.iterrows():
        cells = []
        for name in headers:
            value = row[name]
            label = "—" if pd.isna(value) else (f"{value:.2f}" if isinstance(value, (float, np.floating)) else str(value))
            safe = html.escape(label, quote=True)
            if name == "Mã":
                safe = '<strong class="a-ticker">' + safe + '</strong>'
            elif name == "Mức độ":
                cls = {"Rủi ro": "a-risk", "Thiếu dữ liệu": "a-unknown", "Mục tiêu": "a-target", "Tín hiệu mới": "a-new", "Theo dõi": "a-watch"}.get(str(value), "a-watch")
                safe = '<span class="a-chip ' + cls + '">' + safe + '</span>'
            cells.append('<td>' + safe + '</td>')
        texts.append('<tr>' + ''.join(cells) + '</tr>')
    style = """<style>
      .t2-alert-scroll{max-width:100%;overflow-x:auto;border:1px solid #36574a;border-radius:10px;background:#0e221b}
      .t2-alert-table{min-width:1300px;width:100%;border-collapse:collapse;color:#e9f4ee;font-size:13px;line-height:1.5}
      .t2-alert-table th{padding:11px 10px;background:#223f34;color:#f6fff9;text-align:left;white-space:nowrap}
      .t2-alert-table td{padding:10px;color:#e7f3eb;border-bottom:1px solid #305044;vertical-align:middle}
      .t2-alert-table tbody tr:nth-child(even) td{background:#153128}
      .t2-alert-table .a-ticker{color:#f7fff9;font-size:15px}
      .t2-alert-table .a-chip{border-radius:6px;padding:4px 8px;white-space:nowrap;font-weight:700}
      .t2-alert-table .a-risk{background:#532d37;color:#ffd3dc}
      .t2-alert-table .a-unknown{background:#51452b;color:#ffe3a5}
      .t2-alert-table .a-target{background:#274661;color:#c9e8ff}
      .t2-alert-table .a-new{background:#24513d;color:#b7f6d3}
      .t2-alert-table .a-watch{background:#32413d;color:#e5f2eb}
    </style>"""
    return (style + '<div class="t2-alert-scroll" role="region" aria-label="Trung tâm cảnh báo Trading T+2" tabindex="0">'
            + '<table class="t2-alert-table"><thead><tr>'
            + ''.join('<th>' + html.escape(h, quote=True) + '</th>' for h in headers)
            + '</tr></thead><tbody>' + ''.join(texts) + '</tbody></table></div>')


def render_alert_center(history, daily, asof, groups=None):
    import streamlit as st
    # MIN_T2_ALERT_EXPANDER_V1
    with st.expander("🚨 TRUNG TÂM CẢNH BÁO TRADING T+2 · EOD — Nhấn để xem danh sách", expanded=False):
        st.markdown("### TRUNG TÂM CẢNH BÁO TRADING T+2 · EOD")
        st.caption("Chỉ quan sát tín hiệu T+0–T+15 theo EOD; không phải lệnh mua/bán, không giả định đang nắm giữ.")
        sector = st.session_state.get("t2_top10_sector", "Toàn thị trường")
        cap = st.session_state.get("t2_top10_cap", "Tất cả nhóm vốn hóa")
        allowed, problem = allowed_symbols(groups, sector, cap)
        st.caption("Dùng chung phạm vi ngành/vốn hóa với Top 10 ở phía trên: " + sector + " · " + cap + ".")
        if problem:
            st.warning(problem)
            return
        result = compute_alerts(history, daily, asof, scope=allowed)
        if result.empty:
            st.info("Không có tín hiệu T+0–T+15 với dữ liệu EOD khớp phiên trong phạm vi này.")
            return
        levels = ["Rủi ro", "Thiếu dữ liệu", "Mục tiêu", "Tín hiệu mới", "Theo dõi"]
        selected = st.selectbox("Lọc mức cảnh báo", ["Tất cả"] + levels, key="t2_alert_level")
        cols = st.columns(4)
        counts = [("Tín hiệu mới", "Tín hiệu mới"), ("Theo dõi", "Theo dõi"),
                  ("Rủi ro", "Rủi ro"), ("Cần xác minh", "Thiếu dữ liệu")]
        for col, (label, name) in zip(cols, counts):
            col.metric(label, int((result["Mức độ"] == name).sum()))
        if selected != "Tất cả":
            result = result[result["Mức độ"] == selected]
        st.caption(f"{len(result)} mã sau lọc · tối đa {LIMIT} dòng · cảnh báo từ tín hiệu gần nhất mỗi mã.")
        if result.empty:
            st.info("Không có mã trong mức cảnh báo đang chọn.")
            return
        show = result.head(LIMIT).copy()
        show["Vol/TB20"] = show["Vol/TB20"].map(lambda x: f"{x:.2f}x" if pd.notna(x) else "—")
        st.markdown(_table_html(show), unsafe_allow_html=True)
        st.caption("Chạm cắt lỗ/TP gốc dựa vào High–Low từ phiên sau tín hiệu; không suy ra khớp lệnh. Cảnh báo MA20 dùng trạng thái giá/khối lượng EOD. 'Gần TP1' dùng TP1 gốc, không thay thế TP động trong bảng chi tiết. Thiếu phiên hoặc giá không khớp thì không kết luận an toàn.")
