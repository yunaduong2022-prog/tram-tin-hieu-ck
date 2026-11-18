"""Read-only technical commentary for the left column of the Livestream tab.

Uses existing engine D/W/M calculations. Never changes trading decisions or price data.
Price-state commentary compares the most recent daily EOD close with prior-20-bar
support/resistance and never treats a one-day breach as a confirmed trend reversal.
"""
from __future__ import annotations

import html
import math

import pandas as pd

TF_LABELS = {"D": "Ngày (D)", "W": "Tuần (W)", "M": "Tháng (M)"}
DIR_LABELS = {1: "Nghiêng tăng", -1: "Nghiêng giảm", 0: "Chưa rõ xu hướng"}


def _number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _last(g, column):
    if g is None or getattr(g, "empty", True) or column not in g.columns:
        return None
    return _number(g[column].iloc[-1])


def _price(value):
    return "—" if value is None else f"{value:,.2f}"


def _valid_level(v):
    n = _number(v)
    return n if n is not None and n > 0 else None


def summary_frame(analysis, tf="D"):
    """Present fields that already exist in the engine; W/M volumes are provisional."""
    if not isinstance(analysis, dict) or not analysis.get("enough"):
        return {"ready": False, "trend": "Chưa đủ dữ liệu", "details": "Chưa đủ nến để chấm điểm"}
    g = analysis.get("g")
    close = _valid_level(_last(g, "Giá đóng cửa"))
    if close is None:
        return {"ready": False, "trend": "Chưa đủ dữ liệu", "details": "Thiếu giá đóng cửa hợp lệ"}
    direction = analysis.get("dir", 0)
    if direction not in (-1, 0, 1):
        direction = 0
    ma20 = _valid_level(_last(g, "MA20"))
    vol_ratio = _number(_last(g, "Vol_vs_MA10"))
    if vol_ratio is not None and vol_ratio < 0:
        vol_ratio = None
    notes = []
    if ma20 is not None:
        comparison = "trên" if close > ma20 else "dưới" if close < ma20 else "bằng"
        notes.append(f"Giá {comparison} MA20 ({_price(ma20)})")
    if vol_ratio is not None:
        provisional = " (tạm tính, nến chưa chắc hoàn tất)" if tf in ("W", "M") else ""
        notes.append(f"Vol/MA10: {vol_ratio:.2f}x{provisional}")
    if not notes:
        notes.append("Chưa đủ MA/khối lượng")
    return {
        "ready": True, "trend": DIR_LABELS[direction], "dir": direction,
        "close": close, "ma20": ma20, "vol_ratio": vol_ratio,
        "support": _valid_level(_last(g, "Support_20")),
        "resistance": _valid_level(_last(g, "Resistance_20")),
        "details": " · ".join(notes),
    }


def _classify(close, support, resistance):
    """Conservative EOD location, not a technical buy/sell signal."""
    if support is not None and resistance is not None and support >= resistance:
        return "invalid"
    if resistance is not None and close > resistance:
        return "above"
    if support is not None and close < support:
        return "below"
    if support is not None and resistance is not None:
        return "inside"  # Inclusive: touching a level is not a confirmed break
    return "unknown"


def build_commentary(code, analyses):
    """Generate scenarios and spoken commentary from latest daily EOD and existing scores."""
    analyses = analyses if isinstance(analyses, dict) else {}
    frames = {tf: summary_frame(analyses.get(tf), tf) for tf in ("D", "W", "M")}
    daily, weekly, monthly = (frames[tf] for tf in ("D", "W", "M"))
    if not daily["ready"]:
        return {"frames": frames, "state": "unknown", "state_label": "Thiếu dữ liệu khung ngày",
                "scenarios": [], "script": None,
                "note": "Thiếu dữ liệu khung ngày; chưa tạo kịch bản giá hoặc lời dẫn."}

    support, resistance, close = daily["support"], daily["resistance"], daily["close"]
    state = _classify(close, support, resistance)
    if state == "invalid":
        support = resistance = None
        state = "unknown"

    weak_big = any(frames[tf]["ready"] and frames[tf]["dir"] < 0 for tf in ("W", "M"))
    big_risk = (" Khung tuần/tháng còn nghiêng giảm; chưa thể coi đây là đảo chiều dài hạn."
                if weak_big else " Chưa thể xác nhận đảo chiều chỉ bằng một phiên vượt mốc.")
    if daily["vol_ratio"] is None:
        vol_note = "Chưa đủ dữ liệu xác nhận khối lượng."
    elif daily["vol_ratio"] >= 1.2:
        vol_note = f"Vol/MA10 đạt {daily['vol_ratio']:.2f}x; cần quan sát sự duy trì của dòng tiền."
    else:
        vol_note = f"Vol/MA10 mới {daily['vol_ratio']:.2f}x, chưa cho thấy khối lượng vượt 1,2 lần trung bình."

    if state == "above":
        state_label = "Giá đã đóng cửa trên kháng cự 20 phiên"
        positive = (f"Giá đóng cửa {_price(close)} đã trên kháng cự {_price(resistance)} "
                    f"({(close / resistance - 1) * 100:+.1f}%). {vol_note} "
                    f"Theo dõi giữ giá trên {_price(resistance)} và phản ứng khi kiểm định lại vùng vừa vượt."
                    + big_risk)
        neutral = (f"Giá hiện đã nằm trên biên trên {_price(resistance)}, không còn trong vùng dao động cũ. "
                   "Chỉ quay về trạng thái tích lũy trong biên nếu giá trở lại dưới mốc này.")
        negative = (f"Nếu giá mất lại vùng {_price(resistance)}, rủi ro bứt phá không bền tăng lên; "
                    + (f"theo dõi hỗ trợ {_price(support)}." if support is not None
                       else "chưa có hỗ trợ 20 phiên hợp lệ để xác định mốc tiếp theo."))
    elif state == "below":
        state_label = "Giá đã đóng cửa dưới hỗ trợ 20 phiên"
        positive = (f"Giá hiện dưới hỗ trợ {_price(support)}. Trước khi cân nhắc kịch bản hồi phục, "
                    f"cần lấy lại vùng {_price(support)} và kiểm tra lực cầu; chưa có xác nhận đảo chiều.")
        neutral = (f"Giá {_price(close)} đã thấp hơn biên dưới {_price(support)}, "
                   "không còn nằm trong vùng tích lũy trước đó. Theo dõi khả năng lấy lại hỗ trợ.")
        negative = (f"Giá đã đóng cửa dưới hỗ trợ {_price(support)} "
                    f"({(close / support - 1) * 100:+.1f}%). Rủi ro suy yếu tăng, "
                    "ưu tiên quản trị rủi ro và chờ tín hiệu ổn định trở lại.")
    elif state == "inside":
        state_label = "Giá còn trong biên hỗ trợ–kháng cự"
        positive = (f"Chờ đóng cửa vượt {_price(resistance)} cùng sự cải thiện khối lượng "
                    "và duy trì trên vùng vừa vượt; hiện chưa có bứt phá xác nhận.")
        neutral = (f"Giá {_price(close)} còn trong vùng {_price(support)}–{_price(resistance)}. "
                   "Quan sát phản ứng khi kiểm định hai biên; chạm biên chưa đồng nghĩa phá vỡ.")
        negative = (f"Nếu đóng cửa dưới {_price(support)}, rủi ro suy yếu tăng; "
                    "chờ tín hiệu ổn định trở lại.")
    else:
        state_label = "Chưa đủ mốc kỹ thuật hợp lệ"
        positive = (f"Chờ hệ thống có kháng cự 20 phiên hợp lệ trước khi đánh giá bứt phá."
                    if resistance is None else f"Chờ đóng cửa vượt kháng cự {_price(resistance)} và xác nhận thanh khoản.")
        neutral = "Chưa đủ cặp hỗ trợ/kháng cự hợp lệ để xác định vùng dao động."
        negative = (f"Chờ hệ thống có hỗ trợ 20 phiên hợp lệ để đánh giá rủi ro phá đáy."
                    if support is None else f"Nếu đóng cửa dưới hỗ trợ {_price(support)}, cần đánh giá lại rủi ro.")

    scenarios = [("Tích cực", positive), ("Trung tính", neutral), ("Tiêu cực", negative)]
    weekly_text = weekly["trend"].lower() if weekly["ready"] else "chưa đủ dữ liệu"
    monthly_text = monthly["trend"].lower() if monthly["ready"] else "chưa đủ dữ liệu"
    level_text = (f"Hỗ trợ 20 phiên {_price(support)}, kháng cự 20 phiên {_price(resistance)}. "
                  if support is not None and resistance is not None else
                  "Hỗ trợ/kháng cự 20 phiên chưa đủ dữ liệu hợp lệ. ")
    state_script = {"above": positive, "inside": neutral, "below": negative, "unknown": neutral}[state]
    script = (f"Đang theo dõi {code} theo dữ liệu cuối phiên, giá đóng cửa gần nhất {_price(close)}. "
              f"Khung ngày {daily['trend'].lower()}, tuần {weekly_text}, tháng {monthly_text}. "
              f"{daily['details']}. {level_text}Trạng thái giá: {state_label.lower()}. "
              f"{state_script} "
              "Đây là kịch bản theo điều kiện, không phải khuyến nghị mua bán hay kết quả chắc chắn.")
    return {"frames": frames, "state": state, "state_label": state_label,
            "scenarios": scenarios, "script": script, "note": ""}


def render(code, analyses, data_date=None):
    """Append below weekly chart; never mutates charts, trading logic or source data."""
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
    st.caption("Xu hướng lấy từ D/W/M hiện có. Vol/MA10 ở khung tuần/tháng chỉ tạm tính khi nến chưa hoàn tất; không dùng để xác nhận bứt phá ngày.")
    st.markdown("<div class='live-card-title' style='margin-top:14px'>🎯 BA KỊCH BẢN DIỄN BIẾN GIÁ</div>", unsafe_allow_html=True)
    st.caption(f"Trạng thái theo giá đóng cửa EOD: **{model['state_label']}**.")
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
    st.caption("Hỗ trợ/kháng cự tính theo đáy/đỉnh 20 phiên trước, không bao gồm phiên hiện tại. Vượt một mốc chưa đủ xác nhận đảo chiều.")
    with st.expander("🎤 LỜI DẪN TỰ ĐỘNG · SAO CHÉP ĐỂ LIVESTREAM", expanded=False):
        if model["script"]:
            st.code(model["script"], language=None, wrap_lines=True)
            st.caption("Nhấn biểu tượng sao chép trên khung lời dẫn; kiểm tra số liệu EOD trước khi phát.")
        else:
            st.info(model["note"])
        if data_date is not None:
            st.caption(f"Dữ liệu tham chiếu: {data_date:%d/%m/%Y}. Không phải giá trực tiếp trong phiên.")
