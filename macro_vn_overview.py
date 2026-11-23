"""Vĩ mô thông minh: evidence-aware overview derived ONLY from macro_vn.csv.

No external fetch, financial scoring, cycle labelling or trading recommendations.
This module is UI-only; existing data ingestion, market signals, and NHNN Actions
remain untouched. Functions building the view-model use standard Python only.
"""
from __future__ import annotations

from datetime import date, datetime
from html import escape
from math import isfinite
from typing import Any, Iterable
from zoneinfo import ZoneInfo

CORE = (
    ("GDP_Q", "GDP theo quý"),
    ("IIP_10M", "IIP lũy kế"),
    ("CPI_OCT_YOY", "CPI cùng kỳ"),
    ("CORE_CPI_10M", "Lạm phát cơ bản"),
    ("INTERBANK_ON", "Lãi suất qua đêm"),
    ("CREDIT_YTD", "Tăng trưởng tín dụng"),
    ("USDVND_CENTRAL", "Tỷ giá trung tâm"),
    ("PUBLIC_INV_10M", "Giải ngân đầu tư công"),
)

# Approximate monitoring windows, not assertions about mandatory release cycles.
MAX_AGE_DAYS = {
    "GDP_Q": 115,
    "IIP_10M": 55,
    "CPI_OCT_YOY": 55,
    "CORE_CPI_10M": 55,
    "INTERBANK_ON": 7,
    "CREDIT_YTD": 45,
    "USDVND_CENTRAL": 5,
    "PUBLIC_INV_10M": 55,
}


def vietnam_today() -> date:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def as_date(raw: Any) -> date | None:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if raw is None:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _valid(row: dict[str, Any], today: date) -> bool:
    d = as_date(row.get("asof"))
    if d is None or d > today:
        return False
    try:
        val = float(row["value"])
    except (TypeError, ValueError, KeyError):
        return False
    return (isfinite(val) and bool(str(row.get("source", "")).strip())
            and str(row.get("source_url", "")).startswith("https://"))


def last(rows: Iterable[dict[str, Any]], key: str, today: date) -> dict[str, Any] | None:
    matching = [r for r in rows if r.get("id") == key and _valid(r, today)]
    if not matching:
        return None
    latest_day = max(as_date(r["asof"]) for r in matching)
    newest = [r for r in matching if as_date(r["asof"]) == latest_day]
    # Conflicting or duplicate same-day records are not silently picked.
    return newest[0] if len(newest) == 1 else None


def old(row: dict[str, Any] | None, today: date) -> bool:
    if row is None:
        return True
    d = as_date(row["asof"])
    return d is None or (today - d).days > MAX_AGE_DAYS.get(row["id"], 55)


def fmt(row: dict[str, Any] | None, decimals: int = 2) -> str:
    if row is None:
        return "—"
    n = float(row["value"])
    num = f"{n:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    if row["id"] == "USDVND_CENTRAL":
        return f"{n:,.0f}".replace(",", ".") + " VND/USD"
    return f"{num} {row.get('unit', '')}".strip()


def period_text(row: dict[str, Any] | None, today: date) -> str:
    if not row:
        return "Chưa có bản ghi đủ nguồn"
    d = as_date(row["asof"])
    flag = " · cần đối chiếu kỳ mới" if old(row, today) else ""
    return f"{str(row.get('period', ''))} · {d:%d/%m/%Y}{flag}"


def gdp_yoy_trend(rows: Iterable[dict[str, Any]], today: date) -> str:
    """Only compare three consecutive quarters from one year, same GDP YoY ID."""
    import re
    cleaned = {}
    for row in rows:
        if row.get("id") != "GDP_Q" or not _valid(row, today):
            continue
        m = re.fullmatch(r"Q([1-4])/([0-9]{4})", str(row.get("period", "")))
        if not m:
            continue
        quarter, year = int(m.group(1)), int(m.group(2))
        d = as_date(row["asof"])
        if d.year != year:
            continue
        cleaned[(year, quarter)] = (float(row["value"]), d)
    if len(cleaned) < 3:
        return "Chưa đủ 3 quý GDP YoY cùng phương pháp để nhận xét đà tăng trưởng."
    keys = sorted(cleaned)[-3:]
    if (len(set(k[0] for k in keys)) != 1
            or [k[1] for k in keys] != list(range(keys[0][1], keys[0][1] + 3))):
        return "Chưa có 3 quý liên tiếp cùng năm để đánh giá GDP YoY."
    if (today - cleaned[keys[-1]][1]).days > MAX_AGE_DAYS["GDP_Q"]:
        return "Chuỗi GDP đã quá kỳ theo dõi; không gán nhãn xu hướng hiện tại."
    values = [cleaned[k][0] for k in keys]
    if values[0] < values[1] < values[2]:
        return "Tốc độ tăng GDP (% YoY) tăng qua 3 quý liên tiếp; chưa đủ xác định pha chu kỳ."
    if values[0] > values[1] > values[2]:
        return "Tốc độ tăng GDP (% YoY) giảm qua 3 quý liên tiếp; chưa đủ xác định pha chu kỳ."
    return "GDP YoY biến động qua 3 quý; chưa đủ xác định pha chu kỳ."


def build_overview(rows: list[dict[str, Any]], today: date | None = None) -> dict[str, Any]:
    now = today or vietnam_today()
    records = {key: last(rows, key, now) for key, _ in CORE}
    gdp, iip = records["GDP_Q"], records["IIP_10M"]
    cpi, core = records["CPI_OCT_YOY"], records["CORE_CPI_10M"]
    on, credit = records["INTERBANK_ON"], records["CREDIT_YTD"]
    fx, invest = records["USDVND_CENTRAL"], records["PUBLIC_INV_10M"]

    def status(*keys: str) -> str:
        subset = [records[k] for k in keys]
        if any(x is None for x in subset):
            return "Thiếu chỉ tiêu"
        if any(old(x, now) for x in subset):
            return "Cần cập nhật kỳ mới"
        return "Có dữ liệu theo kỳ"

    pillars = [
        {
            "name": "Tăng trưởng kinh tế", "status": status("GDP_Q", "IIP_10M"),
            "metrics": [("GDP quý", fmt(gdp), period_text(gdp, now)),
                        ("IIP lũy kế", fmt(iip), period_text(iip, now))],
            "evidence": gdp_yoy_trend(rows, now),
            "limit": "Cần PMI, tiêu dùng và cầu tín dụng nhiều kỳ trước khi định danh chu kỳ.",
        },
        {
            "name": "Lạm phát", "status": status("CPI_OCT_YOY", "CORE_CPI_10M"),
            "metrics": [("CPI tháng (YoY)", fmt(cpi), period_text(cpi, now)),
                        ("CPI lõi bình quân", fmt(core), period_text(core, now))],
            "evidence": "CPI theo tháng và CPI lõi bình quân lũy kế là hai cách đo khác nhau.",
            "limit": "Chưa có chuỗi CPI theo tháng đủ dài để kết luận đang tăng hay giảm áp lực.",
        },
        {
            "name": "Tiền tệ & thanh khoản", "status": status("INTERBANK_ON", "CREDIT_YTD"),
            "metrics": [("Lãi suất O/N", fmt(on), period_text(on, now)),
                        ("Tín dụng từ đầu năm", fmt(credit), period_text(credit, now))],
            "evidence": "O/N là mức theo ngày; tín dụng là tăng trưởng lũy kế so cuối năm trước.",
            "limit": "Thiếu OMO và chuỗi lãi suất liên ngân hàng để kết luận nới lỏng/thắt chặt.",
        },
        {
            "name": "Quốc tế & tỷ giá", "status": ("Chờ liên kết nguồn quốc tế"
                                                      if fx else "Thiếu tỷ giá trung tâm"),
            "metrics": [("Tỷ giá trung tâm NHNN", fmt(fx, 0), period_text(fx, now)),
                        ("Fed · DXY · lợi suất Mỹ", "Ở chuyên mục Quốc tế", "Chưa đồng bộ vào kho vĩ mô Việt Nam")],
            "evidence": "Tỷ giá trung tâm khác với giá USD/VND giao dịch trên liên ngân hàng.",
            "limit": "Chưa có chuỗi đối chiếu Fed, DXY và tỷ giá giao dịch cùng kỳ để đánh giá áp lực.",
        },
    ]
    missing = [name for key, name in CORE if records[key] is None]
    outdated = [name for key, name in CORE if records[key] is not None and old(records[key], now)]
    return {"pillars": pillars, "records": records, "missing": missing,
            "outdated": outdated, "asof": now,
            "gdp_evidence": gdp_yoy_trend(rows, now),
            "fiscal": (fmt(invest), period_text(invest, now)),
            "source_rows": [records[k] for k, _ in CORE if records[k] is not None]}


CSS = """
<style>
.mvn-smart-eyebrow{font-size:11px;letter-spacing:1.1px;font-weight:800;color:var(--muted,#a0b4a9)}
.mvn-smart-card{min-height:240px;border:1px solid var(--line,#355044);
 background:var(--card,#13271e);border-radius:13px;padding:16px 18px;margin:5px 0 14px}
.mvn-smart-title{font-size:16px;font-weight:800;color:var(--txt,#e7f1ec);line-height:1.45}
.mvn-smart-status{display:inline-block;margin:8px 0 11px;padding:4px 9px;
 border:1px solid var(--line,#355044);border-radius:7px;color:var(--txt2,#dcece3);
 background:var(--bg2,#20342c);font-size:11px}
.mvn-smart-metrics{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.mvn-smart-metric{border-top:1px solid var(--line,#355044);padding-top:9px;min-width:0}
.mvn-smart-lbl{font-size:11px;color:var(--muted,#b4c7bd);line-height:1.6}
.mvn-smart-num{font-size:18px;font-weight:850;color:var(--txt,#e7f1ec);line-height:1.4;overflow-wrap:anywhere}
.mvn-smart-date{font-size:10.5px;color:var(--muted,#b4c7bd);line-height:1.5}
.mvn-smart-ev{margin-top:12px;color:var(--txt2,#dcece3);font-size:12px;line-height:1.65}
.mvn-smart-limit{margin-top:6px;color:var(--muted,#b4c7bd);font-size:11.5px;line-height:1.55}
@media(max-width:720px){.mvn-smart-card{min-height:0}.mvn-smart-metrics{grid-template-columns:1fr}}
</style>
"""


def _card_html(pillar: dict[str, Any]) -> str:
    bits = [f'<section class="mvn-smart-card"><div class="mvn-smart-title">{escape(pillar["name"])}</div>',
            f'<div class="mvn-smart-status">{escape(pillar["status"])}</div>',
            '<div class="mvn-smart-metrics">']
    for label, value, period in pillar["metrics"]:
        bits.append('<div class="mvn-smart-metric">'
                    f'<div class="mvn-smart-lbl">{escape(label)}</div>'
                    f'<div class="mvn-smart-num">{escape(value)}</div>'
                    f'<div class="mvn-smart-date">{escape(period)}</div></div>')
    bits.extend(['</div>', f'<div class="mvn-smart-ev">{escape(pillar["evidence"])}</div>',
                 f'<div class="mvn-smart-limit">Cần xác nhận: {escape(pillar["limit"])}</div>',
                 '</section>'])
    return ''.join(bits)


def render_smart_overview(rows: list[dict[str, Any]]) -> None:
    """Render verified, period-bound evidence; leave all existing macro tabs intact."""
    import pandas as pd
    import streamlit as st

    view = build_overview(rows)
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("### Bảng điều khiển 4 trụ cột vĩ mô")
    st.caption("Mỗi con số đi kèm kỳ dữ liệu. Trạng thái phản ánh mức đầy đủ/độ mới của nguồn, "
               "không phải xếp hạng thị trường hay tín hiệu giao dịch.")
    for i in range(0, 4, 2):
        left, right = st.columns(2, gap="small")
        for col, item in zip((left, right), view["pillars"][i:i + 2]):
            with col:
                st.markdown(_card_html(item), unsafe_allow_html=True)

    fiscal_value, fiscal_period = view["fiscal"]
    st.markdown("#### Tài khóa · Đầu tư công")
    st.caption(f"**Giải ngân:** {fiscal_value} · {fiscal_period}. "
               "Đây là tỷ lệ so kế hoạch Thủ tướng giao; hiệu quả với cổ phiếu "
               "còn tùy dự án, doanh thu, biên lợi nhuận và dòng tiền thực tế.")

    st.markdown("#### Kết luận vĩ mô dựa trên bằng chứng")
    st.info(f"**Điều có thể quan sát:** {view['gdp_evidence']} "
            "**Điều chưa thể xác định:** trạng thái nới lỏng/thắt chặt của chính sách tiền tệ "
            "và dòng tiền vào chứng khoán. Cần thêm OMO, lãi suất liên ngân hàng nhiều kỳ, PMI "
            "và xác nhận bằng dữ liệu thị trường. Không tự chấm điểm hoặc dự báo VN-Index từ các snapshot.")
    if view["outdated"]:
        st.warning("**Cần đối chiếu kỳ mới:** " + ", ".join(view["outdated"]) + ".")
    if view["missing"]:
        st.caption("Chưa có bản ghi đủ nguồn cho: " + ", ".join(view["missing"]) + ".")
    st.caption("Nguồn/chỉ tiêu chưa được kết nối đồng bộ: PMI, OMO, tỷ giá giao dịch USD/VND liên ngân hàng; "
               "Fed/DXY/lợi suất Mỹ xem tại chuyên mục Quốc tế.")

    st.markdown("#### Kênh tác động cần xác nhận")
    impacts = [
        {"Yếu tố": "GDP / IIP", "Kênh liên hệ": "Công nghiệp, thép, khu công nghiệp",
         "Điều kiện xác nhận": "Đơn hàng, sản lượng, lợi nhuận và sức mạnh giá/khối lượng của ngành"},
        {"Yếu tố": "OMO / O/N / tín dụng", "Kênh liên hệ": "Ngân hàng, chứng khoán, bất động sản",
         "Điều kiện xác nhận": "Bơm/hút ròng xác minh, chi phí vốn, tín dụng, thanh khoản cổ phiếu"},
        {"Yếu tố": "Giải ngân đầu tư công", "Kênh liên hệ": "Hạ tầng, xây dựng, vật liệu",
         "Điều kiện xác nhận": "Khối lượng dự án, doanh thu, backlog và dòng tiền doanh nghiệp"},
        {"Yếu tố": "Fed / DXY / tỷ giá", "Kênh liên hệ": "Chi phí vốn, tỷ giá và định giá",
         "Điều kiện xác nhận": "Chuỗi tỷ giá đúng loại, chính sách công bố và diễn biến giá/khối lượng"},
    ]
    st.dataframe(pd.DataFrame(impacts), hide_index=True, use_container_width=True)
    st.caption("Đây là kênh truyền dẫn có điều kiện, không phải bảng xếp hạng ngành dẫn sóng, "
               "không tạo lệnh mua/bán. Cần xác nhận từ mục Thị trường và Ngành.")

    with st.expander("Nguồn và kỳ dữ liệu của các trụ cột", expanded=False):
        evidence = []
        for row in view["source_rows"]:
            evidence.append({
                "Chỉ tiêu": str(row["label"]), "Giá trị": fmt(row),
                "Kỳ": str(row["period"]), "Ngày": f"{as_date(row['asof']):%d/%m/%Y}",
                "Trạng thái": "Cần đối chiếu kỳ mới" if old(row, view["asof"]) else "Theo kỳ công bố",
                "Nguồn": str(row["source"]), "Liên kết": str(row["source_url"]),
            })
        if evidence:
            st.dataframe(pd.DataFrame(evidence), hide_index=True, use_container_width=True,
                         column_config={"Liên kết": st.column_config.LinkColumn("Liên kết")})
        else:
            st.info("Chưa có bản ghi có nguồn được kiểm chứng.")
