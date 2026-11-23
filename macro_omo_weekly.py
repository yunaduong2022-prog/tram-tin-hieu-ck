"""Conservative, source-scoped OMO weekly snapshots for Trạm Tín Hiệu.

No crawling, auto-pricing, or live-data claims. The repo/collateral lending
channel and SBV bill channel are separate; missing bill amounts are UNKNOWN,
not zero. Weekly rows are not transaction-level daily OMO facts.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

DATA_PATH = Path(__file__).resolve().parent / "data" / "macro_omo_weekly.csv"
COLUMNS = ("start_date", "end_date", "repo_awarded_bn", "repo_matured_bn",
           "repo_rate_pct", "bills_issued_bn", "bills_matured_bn", "source",
           "source_url", "crosscheck_url", "source_date", "note")
MAX_DAYS = 14  # monitoring threshold only; not a mandatory publication cycle


def vn_today() -> date:
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def money(raw: str | None, required: bool = False) -> Decimal | None:
    s = str(raw or "").strip()
    if s == "":
        if required:
            raise ValueError("REQUIRED_COMPONENT_MISSING")
        return None
    try:
        x = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError("COMPONENT_NOT_NUMERIC") from exc
    if not x.is_finite() or not (Decimal("0") <= x <= Decimal("5000000")):
        raise ValueError("COMPONENT_OUT_OF_BOUNDS")
    return x


def parse(row: dict[str, str], today: date | None = None) -> dict[str, Any]:
    now = today or vn_today()
    if set(COLUMNS) - set(row):
        raise ValueError("CSV_COLUMNS_MISSING")
    try:
        start = date.fromisoformat(row["start_date"])
        end = date.fromisoformat(row["end_date"])
        source_date = date.fromisoformat(row["source_date"])
    except (ValueError, TypeError) as exc:
        raise ValueError("INVALID_DATES") from exc
    if start > end or (end - start).days > 6 or end > now or source_date > now or source_date < end:
        raise ValueError("PERIOD_OR_PUBLICATION_INVALID")
    source = str(row["source"]).strip()
    url = str(row["source_url"]).strip()
    crosscheck_url = str(row["crosscheck_url"]).strip()
    if not source or not url.startswith("https://") or (crosscheck_url and not crosscheck_url.startswith("https://")):
        raise ValueError("MISSING_OR_INVALID_SOURCE")
    awarded = money(row["repo_awarded_bn"], required=True)
    matured = money(row["repo_matured_bn"], required=True)
    rate = money(row["repo_rate_pct"], required=True)
    if rate > Decimal("30"):
        raise ValueError("RATE_OUT_OF_BOUNDS")
    bills_issued = money(row["bills_issued_bn"])
    bills_matured = money(row["bills_matured_bn"])
    repo_net = awarded - matured
    # Full net: repo injections minus repo maturities minus bill issuance plus bill maturities.
    full_net = (repo_net - bills_issued + bills_matured
                if bills_issued is not None and bills_matured is not None else None)
    return {"start": start, "end": end, "source_date": source_date,
            "awarded": awarded, "matured": matured, "rate": rate,
            "bills_issued": bills_issued, "bills_matured": bills_matured,
            "repo_net": repo_net, "full_net": full_net,
            "source": source, "source_url": url, "crosscheck_url": crosscheck_url,
            "note": str(row.get("note", "")).strip(),
            "stale": (now - end).days > MAX_DAYS}


def latest_verified_week(path: Path = DATA_PATH, today: date | None = None) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)
            if reader.fieldnames is None or set(reader.fieldnames) != set(COLUMNS):
                return None
            rows = list(reader)
        if not rows:
            return None
        observations = [parse(row, today) for row in rows]
    except (OSError, UnicodeError, ValueError, csv.Error):
        return None  # fail closed, never silently use partial/conflicting data
    keys = [(r["start"], r["end"]) for r in observations]
    if len(keys) != len(set(keys)):
        return None
    return sorted(observations, key=lambda r: r["end"])[-1]


def fmt_bn(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " tỷ"


def fmt_pct(v: Decimal | None) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}".replace(".", ",") + "%/năm"


def repo_direction(v: Decimal) -> str:
    return "Bơm ròng" if v > 0 else "Hút ròng" if v < 0 else "Cân bằng"


def render_omo_weekly() -> None:
    """Render below interbank yield curve without modifying SBV O/N workflow."""
    import streamlit as st

    st.markdown("#### OMO · Bơm/hút tiền qua thị trường mở")
    st.caption("Theo dõi **kênh cầm cố** riêng biệt với **tín phiếu NHNN**. "
               "Số liệu tuần không được trình bày như kết quả giao dịch từng phiên.")
    row = latest_verified_week()
    if row is None:
        st.info("Chưa có bảng OMO hợp lệ và đủ nguồn để hiển thị. Không tự suy đoán lượng bơm/hút ròng.")
        return
    period = f"{row['start']:%d/%m}–{row['end']:%d/%m/%Y}"
    st.caption(f"**Kỳ theo dõi:** {period} · **Công bố:** {row['source_date']:%d/%m/%Y} "
               f"· **Nguồn:** {row['source']} (tổng hợp thứ cấp, không phải feed trực tiếp của NHNN).")
    cols = st.columns(4, gap="small")
    indicators = [
        ("Bơm mới · cầm cố", fmt_bn(row["awarded"])),
        ("Đáo hạn · cầm cố", fmt_bn(row["matured"])),
        (f"{repo_direction(row['repo_net'])} · cầm cố", fmt_bn(abs(row["repo_net"]))),
        ("Lãi suất đấu thầu cầm cố", fmt_pct(row["rate"])),
    ]
    for col, (label, value) in zip(cols, indicators):
        with col:
            st.metric(label, value)
    if row["full_net"] is None:
        st.info("**Bơm/hút ròng toàn bộ OMO: —** Chưa đủ hai cấu phần tín phiếu "
                "(phát hành **và** đáo hạn). Việc không chào thầu tín phiếu mới "
                "không chứng minh được không có tín phiếu đáo hạn.")
    else:
        st.metric("Bơm/hút ròng toàn OMO (đủ cả hai kênh)", fmt_bn(row["full_net"]))
    if row["stale"]:
        st.warning("Bản ghi OMO đã quá 14 ngày tính từ cuối kỳ. Chỉ tham khảo lịch sử, "
                   "không dùng như số liệu hiện tại.")
    st.caption("**Cách tính ròng kênh cầm cố:** trúng thầu mới − đáo hạn. "
               "**Cách tính ròng toàn OMO:** ròng cầm cố − tín phiếu phát hành + tín phiếu đáo hạn. "
               "Số dư lưu hành không được cộng vào dòng tiền giao dịch theo tuần.")
    st.markdown(f"[Xem nguồn báo cáo tuần]({row['source_url']})"
                + (f" · [Nguồn đối chiếu]({row['crosscheck_url']})" if row["crosscheck_url"] else ""))
    st.caption("**Giới hạn phân tích:** Ròng OMO không đồng nghĩa dòng tiền trực tiếp vào cổ phiếu. "
               "Cần kiểm tra lãi suất O/N, thanh khoản hệ thống, tỷ giá và dữ liệu ngành.")
