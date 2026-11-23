"""CPI lịch sử Việt Nam, phiên bản snapshot theo nguồn Cục Thống kê.

Only reads data/macro_cpi_history.csv. Does not scrape sites, update Git, touch
market data, or infer a core CPI *monthly* rate from a cumulative average.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

DATA_PATH = Path(__file__).resolve().parent / "data" / "macro_cpi_history.csv"
COLUMNS = ("year_month", "cpi_yoy_pct", "cpi_mom_pct", "cpi_ytd_avg_yoy_pct",
           "core_ytd_avg_yoy_pct", "source", "source_url")
METRICS = ("cpi_yoy_pct", "cpi_mom_pct", "cpi_ytd_avg_yoy_pct", "core_ytd_avg_yoy_pct")


def vietnam_today() -> date:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def decimal_value(raw: str, name: str) -> Decimal:
    try:
        val = Decimal(str(raw).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"INVALID_NUMBER_{name}") from exc
    if not val.is_finite():
        raise ValueError(f"NONFINITE_{name}")
    lower, upper = (Decimal("-15"), Decimal("25")) if name == "cpi_mom_pct" else (Decimal("-20"), Decimal("40"))
    if not lower <= val <= upper:
        raise ValueError(f"OUTLIER_{name}")
    return val


def parse_row(raw: dict[str, str], today: date | None = None) -> dict[str, Any]:
    if set(COLUMNS) != set(raw):
        raise ValueError("CPI_SCHEMA_MISMATCH")
    now = today or vietnam_today()
    month_str = str(raw["year_month"]).strip()
    if len(month_str) != 7:
        raise ValueError("CPI_INVALID_MONTH")
    try:
        month = datetime.strptime(month_str, "%Y-%m").date()
    except ValueError as exc:
        raise ValueError("CPI_INVALID_DATE") from exc
    next_month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    month_end = next_month - timedelta(days=1)
    if month_end > now:
        raise ValueError("CPI_FUTURE_MONTH")
    url = str(raw["source_url"]).strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in ("www.nso.gov.vn", "nso.gov.vn"):
        raise ValueError("CPI_UNVERIFIED_SOURCE_DOMAIN")
    if str(raw["source"]).strip() != "Cục Thống kê":
        raise ValueError("CPI_SOURCE_MISSING")
    row = {"month": month, "month_end": month_end,
           "source": raw["source"], "url": url}
    for key in METRICS:
        row[key] = decimal_value(raw[key], key)
    return row


def read_history(path: Path = DATA_PATH, today: date | None = None) -> list[dict[str, Any]]:
    """Fail closed on invalid, duplicated, skipped or out-of-order monthly data."""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames is None or set(reader.fieldnames) != set(COLUMNS):
                raise ValueError("CPI_SCHEMA_MISMATCH")
            records = [parse_row(r, today) for r in reader]
    except (OSError, UnicodeError, csv.Error, TypeError) as exc:
        raise ValueError("CPI_HISTORY_UNREADABLE") from exc
    if len(records) < 2:
        raise ValueError("CPI_TOO_FEW_MONTHS")
    months = [r["month"] for r in records]
    if len(months) != len(set(months)):
        raise ValueError("CPI_DUPLICATE_MONTH")
    if months != sorted(months):
        raise ValueError("CPI_UNSORTED_MONTHS")
    for previous, current in zip(months, months[1:]):
        if current.year * 12 + current.month != previous.year * 12 + previous.month + 1:
            raise ValueError("CPI_GAP_IN_MONTHLY_SERIES")
    return records


def change_pp(current: Decimal, prior: Decimal) -> Decimal:
    """Percentage-point difference; not CPI index change or percent-of-percent."""
    return current - prior


def fmt(v: Decimal) -> str:
    return f"{v:.2f}".replace(".", ",")


def render_cpi_history() -> None:
    """Three distinct panels, each with consistent numerator and time basis."""
    import streamlit as st
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.info("Thiếu thư viện Plotly để vẽ CPI lịch sử.")
        return

    st.markdown("#### Lịch sử CPI Việt Nam theo tháng")
    try:
        rows = read_history()
    except ValueError as exc:
        st.error(f"Chưa thể hiển thị chuỗi CPI đáng tin cậy ({exc}). Không nội suy số liệu.")
        return
    start = rows[0]["month"]
    last = rows[-1]
    st.caption(f"Dữ liệu từ {start:%m/%Y} đến {last['month']:%m/%Y} · "
               "Theo các công bố của Cục Thống kê, có nguồn riêng cho từng kỳ. "
               "Đây là snapshot theo tháng, không phải dữ liệu CPI thời gian thực.")

    tabs = st.tabs(["CPI so cùng kỳ (YoY)", "CPI so tháng trước (MoM)",
                    "CPI & CPI lõi bình quân lũy kế"])
    x = [r["month"] for r in rows]

    def chart(series: list[tuple[str, str]], *, zero_line: bool = False) -> Any:
        fig = go.Figure()
        for label, key in series:
            fig.add_trace(go.Scatter(x=x, y=[float(r[key]) for r in rows],
                                     mode="lines+markers", name=label,
                                     hovertemplate="%{x|%m/%Y}: %{y:.2f}%<extra>" + label + "</extra>"))
        fig.update_layout(height=350, margin=dict(l=8, r=8, t=12, b=5),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          hovermode="x unified", legend=dict(orientation="h", y=1.16),
                          xaxis=dict(tickformat="%m/%Y", dtick="M1", showgrid=False),
                          yaxis=dict(title="%", zeroline=zero_line))
        return fig

    with tabs[0]:
        st.plotly_chart(chart([("CPI YoY", "cpi_yoy_pct")]), use_container_width=True, theme="streamlit")
        st.caption("Mỗi điểm so CPI tháng này với CÙNG tháng năm trước; "
                   "không phải tăng giá so với tháng liền trước.")
    with tabs[1]:
        st.plotly_chart(chart([("CPI MoM", "cpi_mom_pct")], zero_line=True),
                        use_container_width=True, theme="streamlit")
        st.caption("Mỗi điểm so CPI với THÁNG trước. Giá trị âm là mức giá giảm so tháng liền trước, "
                   "không đồng nghĩa giảm phát kéo dài.")
    with tabs[2]:
        st.plotly_chart(chart([("CPI bình quân từ đầu năm", "cpi_ytd_avg_yoy_pct"),
                               ("Lạm phát cơ bản bình quân từ đầu năm", "core_ytd_avg_yoy_pct")]),
                        use_container_width=True, theme="streamlit")
        st.caption("Hai đường là bình quân LŨY KẾ từ tháng 1 tới từng tháng so với cùng kỳ năm trước; "
                   "không phải CPI lõi riêng từng tháng.")

    yoy_diff = change_pp(last["cpi_yoy_pct"], rows[-2]["cpi_yoy_pct"])
    mom_diff = change_pp(last["cpi_mom_pct"], rows[-2]["cpi_mom_pct"])
    msg = (f"**Đọc dữ liệu {last['month']:%m/%Y}:** CPI YoY {fmt(last['cpi_yoy_pct'])}%, "
           f"thay đổi {fmt(yoy_diff)} điểm phần trăm so với kỳ trước; "
           f"CPI MoM {fmt(last['cpi_mom_pct'])}%, "
           f"thay đổi {fmt(mom_diff)} điểm phần trăm so với kỳ trước. "
           "Cần đối chiếu nhóm hàng đóng góp và điều hành tiền tệ; "
           "đây không phải dự báo lãi suất hay tín hiệu VN-Index.")
    st.info(msg)
    if (vietnam_today() - last["month_end"]).days > 65:
        st.warning("Chuỗi CPI đã quá 65 ngày so với kỳ gần nhất: cần cập nhật báo cáo mới; "
                   "không xem là bức tranh lạm phát hiện tại.")
    with st.expander("Kiểm tra lịch sử và nguồn CPI theo từng tháng", expanded=False):
        import pandas as pd
        display = [{"Tháng": r["month"].strftime("%m/%Y"),
                    "CPI YoY (%)": float(r["cpi_yoy_pct"]),
                    "CPI MoM (%)": float(r["cpi_mom_pct"]),
                    "CPI bình quân YTD (%)": float(r["cpi_ytd_avg_yoy_pct"]),
                    "CPI lõi bình quân YTD (%)": float(r["core_ytd_avg_yoy_pct"]),
                    "Nguồn chính thức": r["url"]} for r in rows]
        st.dataframe(pd.DataFrame(display), hide_index=True, use_container_width=True,
                     column_config={"Nguồn chính thức": st.column_config.LinkColumn("Báo cáo Cục Thống kê")})
    st.caption("Dữ liệu này được ghi nhận theo các báo cáo đã công bố; không tự cập nhật theo phiên cổ phiếu. "
               "Không trộn CPI YoY, MoM, bình quân lũy kế hoặc CPI lõi thành một tín hiệu đơn lẻ.")
