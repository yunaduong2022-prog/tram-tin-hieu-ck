"""Read-only technical commentary for the left column of the Livestream tab.

Uses existing engine's D/W/M results. Never changes signals or price data.
"""
from __future__ import annotations

import html
import math

import pandas as pd


TF_LABELS = {"D": "Ngày (D)", "W": "Tuần (W)", "M": "Tháng (M)"}
DIR_LABELS = {1: "Nghiêng tăng", -1: "Nghiêng giảm", 0: "Chưa rõ xu hướng"}


def _number(value):
    """Ignore absent, non-numeric or non-finite inputs; never invent levels."""
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _last(g, column):
    if g is None or getattr(g, "empty", True) or column not in g.columns:
        return None
    return _number(g[column].iloc[-1])


def _price(value):
    return "—" if value is None else f"{value:,.2f}"


def summary_frame(analysis):
    """Return factual display fields, respecting engine MIN_BARS/enough."""
    if not isinstance(analysis, dict) or not analysis.get("enough"):
        return {"ready": False, "trend": "Chưa đủ dữ liệu", "details": "Chưa đủ nến để chấm điểm"}
    g = analysis.get("g")
    close = _last(g, "Giá đóng cửa")
    if close is None:
        return {"ready": False, "trend": "Chưa đủ dữ liệu", "details": "Thiếu giá đóng cửa hợp lệ"}
    direction = analysis.get("dir", 0)
    if direction not in (-1, 0, 1):
        direction = 0
    ma20 = _last(g, "MA20")
    vol_ratio = _last(g, "Vol_vs_MA10")
    notes = []
    if ma20 is not None:
        comparison = "trên" if close > ma20 else "dưới" if close < ma20 else "bằng"
        notes.append(f"Giá {comparison} MA20 ({_price(ma20)})")
    if vol_ratio is not None:
        notes.append(f"Vol/MA10: {vol_ratio:.2f}x")
    if not notes:
        notes.append("Chưa đủ MA/khối lượng")
    return {"ready": True, "trend": DIR_LABELS[direction], "dir": direction,
            "close": close, "ma20": ma20, "vol_ratio": vol_ratio,
            "support": _last(g, "Support_20"), "resistance": _last(g, "Resistance_20"),
            "details": " · ".join(notes)}


def build_commentary(code, analyses):
    """Generate conditional scenarios & spoken commentary from valid EOD indicators."""
    frames = {tf: summary_frame(analyses.get(tf)) for tf in ("D", "W", "M")}
    daily, weekly, monthly = (frames[tf] for tf in ("D", "W", "M"))
    if not daily["ready"]:
        return {"frames": frames, "scenarios": [], "script": None,
                "note": "Thiếu dữ liệu khung ngày; chưa tạo kịch bản giá hoặc lời dẫn."}
    support, resistance = daily["support"], daily["resistance"]
    if support is not None and resistance is not None and support >= resistance:
        support = resistance = None
    close = daily["close"]
    positive = (f"Nếu đóng cửa vượt {_price(resistance)} với khối lượng xác nhận, "
                "theo dõi khả năng duy trì đà tăng." if resistance is not None
                else "Chờ hệ thống có kháng cự 20 phiên hợp lệ trước khi đánh giá bứt phá.")
    neutral = (f"Khi giá còn dao động giữa {_price(support)} và {_price(resistance)}, "
               "ưu tiên quan sát phản ứng tại hai biên." if support is not None and resistance is not None
               else "Chưa có đủ cặp hỗ trợ/kháng cự hợp lệ để xác định vùng dao động.")
    negative = (f"Nếu đóng cửa dưới {_price(support)}, rủi ro suy yếu tăng; "
                "chờ tín hiệu ổn định trở lại." if support is not None
                else "Chờ hệ thống có hỗ trợ 20 phiên hợp lệ để đánh giá rủi ro phá đáy.")
    scenarios = [("Tích cực", positive), ("Trung tính", neutral), ("Tiêu cực", negative)]
    weekly_text = weekly["trend"].lower() if weekly["ready"] else "chưa đủ dữ liệu"
    monthly_text = monthly["trend"].lower() if monthly["ready"] else "chưa đủ dữ liệu"
    vol_text = (f"Khối lượng bằng {daily['vol_ratio']:.2f} lần trung bình 10 phiên trước đó. "
                if daily["vol_ratio"] is not None else "Khối lượng chưa đủ dữ liệu để so sánh. ")
    level_text = (f"Vùng cần theo dõi là hỗ trợ {_price(support)} và kháng cự {_price(resistance)}. "
                  if support is not None and resistance is not None else
                  "Vùng hỗ trợ và kháng cự chưa được xác nhận đầy đủ. ")
    script = (f"Đang theo dõi {code} theo dữ liệu cuối phiên, giá đóng cửa gần nhất {_price(close)}. "
              f"Khung ngày {daily['trend'].lower()}, khung tuần {weekly_text}, khung tháng {monthly_text}. "
              f"{daily['details']}. {vol_text}{level_text}"
              "Kịch bản tích cực cần giá vượt kháng cự kèm xác nhận khối lượng; "
              "nếu thủng hỗ trợ thì ưu tiên quản trị rủi ro. "
              "Đây là các điều kiện theo dõi, không phải dự báo chắc chắn hay khuyến nghị mua bán.")
    return {"frames": frames, "scenarios": scenarios, "script": script, "note": ""}


def render(code, analyses, data_date=None):
    """Append below weekly chart; isolated from charts, trading engines and right column."""
    import streamlit as st

    model = build_commentary(code, analyses)
    safe_code = html.escape(str(code))
    st.markdown(f"<div class='live-card-title' style='margin-top:16px'>🧭 TỔNG HỢP KỸ THUẬT ĐA KHUNG · {safe_code}</div>", unsafe_allow_html=True)
    rows = []
    for tf in ("D", "W", "M"):
        snapshot = model["frames"][tf]
        rows.append({"Khung": TF_LABELS[tf], "Xu hướng": snapshot["trend"],
                     "Tín hiệu xác nhận": snapshot["details"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=143)
    st.caption("Xu hướng lấy từ bộ chấm điểm D/W/M hiện có. MA20 và Vol/MA10 lấy theo từng khung; thiếu nến sẽ ghi rõ, không tự suy đoán.")
    st.markdown("<div class='live-card-title' style='margin-top:14px'>🎯 BA KỊCH BẢN DIỄN BIẾN GIÁ</div>", unsafe_allow_html=True)
    if model["scenarios"]:
        for title, body in model["scenarios"]:
            tone = {"Tích cực": "#39d6a0", "Trung tính": "#f7bd55", "Tiêu cực": "#f07f88"}[title]
            st.markdown(
                f"<div style='border:1px solid #29384d;border-left:3px solid {tone};background:#111b2b;"
                f"border-radius:9px;padding:9px 12px;margin:5px 0'>"
                f"<b style='color:{tone}'>{title}</b> · <span style='color:#dce5f0'>{html.escape(body)}</span></div>",
                unsafe_allow_html=True,
            )
    else:
        st.info(model["note"])
    st.caption("Mốc kỹ thuật dùng đỉnh/đáy 20 phiên trước (không tính phiên hiện tại), không phải mức giá đảm bảo đạt được.")
    with st.expander("🎤 LỜI DẪN TỰ ĐỘNG · SAO CHÉP ĐỂ LIVESTREAM", expanded=False):
        if model["script"]:
            st.code(model["script"], language=None, wrap_lines=True)
            st.caption("Nhấn biểu tượng sao chép trên khung lời dẫn. Nội dung tự cập nhật theo mã đang chọn và dữ liệu EOD; kiểm tra trước khi phát.")
        else:
            st.info(model["note"])
        if data_date is not None:
            st.caption(f"Dữ liệu tham chiếu: {data_date:%d/%m/%Y}. Không phải giá trực tiếp trong phiên.")
