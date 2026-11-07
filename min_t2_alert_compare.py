"""Read-only comparison of existing warning systems for one confirmed EOD ticker.

No new buy/sell classifiers, no order execution, no cache or EOD writes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _number(value):
    value = pd.to_numeric(value, errors="coerce")
    return float(value) if pd.notna(value) and np.isfinite(float(value)) else np.nan


def compare(context, signal, daily):
    """Independent assessments: waiting_buy state, historical signal, current MA20."""
    if not context or signal is None or daily is None or daily.empty:
        return None
    required = {"Mã", "Ngày", "Giá đóng cửa", "Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Khối lượng khớp lệnh"}
    if not required.issubset(daily.columns):
        return None
    code = str(context.get("code", "")).strip().upper()
    asof = pd.Timestamp(context.get("asof")).normalize()
    if not code or str(signal.get("Mã", "")).strip().upper() != code:
        return None
    closing = _number(signal.get("Giá EOD"))
    source_price = _number(context.get("price"))
    if not np.isfinite(closing) or not np.isfinite(source_price) or abs(closing - source_price) > .011:
        return None
    rows = daily.loc[daily["Mã"].astype(str).str.upper().str.strip() == code].copy()
    rows["Ngày"] = pd.to_datetime(rows["Ngày"], errors="coerce").dt.normalize()
    rows = rows.loc[rows["Ngày"] == asof]
    if len(rows) != 1 or not np.isfinite(_number(rows.iloc[0]["Giá đóng cửa"])) or abs(_number(rows.iloc[0]["Giá đóng cửa"]) - closing) > .011:
        return None

    from min_t2_position_guard import exit_condition, signal_lifecycle
    life = signal_lifecycle(daily, signal, asof)
    ma = exit_condition(daily, code, asof)
    wb = context.get("wb_alert_context")
    group = str(wb.get("group") or "") if wb else ""
    state = str(wb.get("state") or "") if wb else ""
    detail = str(wb.get("reason") or "") if wb else ""
    age = _number(signal.get("Phiên từ tín hiệu"))
    return {
        "code": code,
        "date": asof,
        "age": int(age) if np.isfinite(age) and age >= 0 else None,
        "trend_status": state or "Chưa có phân loại EOD đồng nhất",
        "trend_group": group or "Chưa có phân loại",
        "trend_reason": detail or "Không có lý do trạng thái từ bộ lọc xu hướng cùng giá EOD.",
        "trend_warning": group in {"Cảnh báo rủi ro / bán", "Cảnh báo không mua đuổi"},
        "sell_action": str(wb.get("sell_action") or "") if wb else "",
        "life_status": str(life.get("status", "CHƯA ĐỦ DỮ LIỆU")),
        "life_reason": str(life.get("note", "")),
        "ma_status": str(ma.get("status", "CHƯA ĐỦ DỮ LIỆU")),
        "ma_reason": str(ma.get("reason", "")),
        "stop_original": _number(signal.get("Cắt lỗ gốc", signal.get("Cắt lỗ tham khảo"))),
        "tp1_original": _number(signal.get("TP1 gốc", signal.get("Mục tiêu 1"))),
    }



# MIN_T2_ALERT_COMPARE_PRESENTATION_V2

def _lifecycle_display(data):
    """T+0 has no post-signal daily bar; keep the raw lifecycle unchanged."""
    status, reason = data["life_status"], data["life_reason"]
    if data["age"] == 0 and status == "CHƯA CHẠM CẮT LỖ/TP GỐC":
        return ("Chưa chạm cắt lỗ/TP gốc",
                "Ngày phát tín hiệu; chưa có phiên EOD sau tín hiệu để kiểm tra "
                "High–Low với cắt lỗ/TP gốc. Không kết luận mức gốc an toàn.")
    return status, reason


def _comparison_table_html(records):
    """Escape content; wrap long reasons without modifying source data."""
    import html
    heads = ("Nguồn", "Trạng thái", "Lý do")
    body = []
    for row in records:
        cells = ''.join('<td>' + html.escape(str(row[k]), quote=True) + '</td>' for k in heads)
        body.append('<tr>' + cells + '</tr>')
    style = """<style>
    .min-alert-compare-scroll{width:100%;overflow-x:auto;border:1px solid #315045;border-radius:8px;background:#0d221b}
    .min-alert-compare{width:100%;min-width:610px;table-layout:fixed;border-collapse:collapse;color:#eaf3ed;font-size:13px;line-height:1.55}
    .min-alert-compare th{background:#18372d;color:#f3fff7;text-align:left;font-weight:650}
    .min-alert-compare td,.min-alert-compare th{padding:10px 12px;border-bottom:1px solid #2a493e;vertical-align:top;white-space:normal;overflow-wrap:anywhere;word-break:normal}
    .min-alert-compare th:nth-child(1){width:26%}.min-alert-compare th:nth-child(2){width:24%}.min-alert-compare th:nth-child(3){width:50%}
    .min-alert-compare tr:last-child td{border-bottom:0}
    @media(max-width:700px){.min-alert-compare{font-size:12px}.min-alert-compare td,.min-alert-compare th{padding:8px}}
    </style>"""
    return (style + '<div class="min-alert-compare-scroll" role="region" aria-label="Đối chiếu cảnh báo" tabindex="0">'
            + '<table class="min-alert-compare"><thead><tr>'
            + ''.join('<th scope="col">' + html.escape(k) + '</th>' for k in heads)
            + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>')


def render_comparison(context, signal, daily):
    import streamlit as st
    with st.expander("Đối chiếu hai hệ thống cảnh báo · cùng mã và phiên EOD", expanded=False):
        data = compare(context, signal, daily)
        if data is None:
            st.warning("Không đủ dữ liệu EOD cùng phiên để đối chiếu; không ghép các kết quả lệch ngày hoặc lệch giá.")
            return
        st.caption(f"Mã {data['code']} · EOD {data['date']:%d/%m/%Y} · "
                   + (f"T+{data['age']}" if data['age'] is not None else "Không xác định tuổi tín hiệu")
                   + " · Dùng lại quy tắc từ các module hiện có")
        life_display_status, life_display_reason = _lifecycle_display(data)
        records = [
            {"Nguồn": "Cảnh báo xu hướng cổ phiếu", "Trạng thái": data["trend_status"],
             "Lý do": data["trend_reason"]},
            {"Nguồn": "Trading T+2 · mức gốc lịch sử", "Trạng thái": life_display_status,
             "Lý do": life_display_reason},
            {"Nguồn": "Cảnh báo MA20 · EOD hiện tại", "Trạng thái": data["ma_status"],
             "Lý do": data["ma_reason"]},
        ]
        st.markdown(_comparison_table_html(records), unsafe_allow_html=True)
        def fmt(v):
            return f"{v:.2f}" if np.isfinite(v) else "—"
        st.caption("Nguồn 1: waiting_buy (" + data["trend_group"] + "). "
                   "Nguồn 2: High–Low sau ngày tín hiệu và mức cắt lỗ/TP gốc. "
                   "Nguồn 3: MA20 = SMA20 và giá/khối lượng của EOD hiện tại.")
        st.write("Cắt lỗ gốc:", fmt(data["stop_original"]),
                 " · TP1 gốc:", fmt(data["tp1_original"]))
        if data["age"] is None or data["age"] > 15:
            st.info("Tín hiệu ngoài cửa sổ cảnh báo T+0–T+15; kết quả mức gốc chỉ là lịch sử, không phải cảnh báo giao dịch đang hiệu lực.")
        st.caption("Một cổ phiếu có thể có cảnh báo xu hướng hiện tại và tình trạng cắt lỗ gốc trong quá khứ đồng thời. "
                   "Thứ tự chạm mức trong cùng nến không xác định từ EOD; không suy ra đã khớp lệnh, "
                   "không giả định đang nắm giữ và không thay thế tư vấn cá nhân.")
