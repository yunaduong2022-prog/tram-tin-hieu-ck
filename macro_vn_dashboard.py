"""Verified, date-scoped Vietnam macro dashboard for Trạm Tín Hiệu.

Phase 1: manually curated source-checked observations; no silent real-time claims.
Does not alter pricing, signals, EOD, DNSE, VIP or backtest logic.
"""
from __future__ import annotations

from html import escape
from pathlib import Path
from datetime import date
import math

import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).resolve().parent / "data" / "macro_vn.csv"
COLS = ["id", "group", "label", "period", "asof", "value", "unit",
        "comparison", "source", "source_url", "note"]
SECTIONS = ["Tổng quan", "Chu kỳ & Lạm phát", "Tiền tệ & Thanh khoản",
            "Tài khóa", "Quốc tế", "Tác động ngành"]

CSS = """
<style>
.mvn-head{border:1px solid var(--line,#355044);border-radius:15px;padding:19px 22px;
 background:var(--card,#13271e);margin:6px 0 15px}
.mvn-kicker{font-size:11px;letter-spacing:1.4px;color:var(--muted,#91a99f);font-weight:800}
.mvn-title{font-size:24px;color:var(--txt,#e7f1ec);font-weight:850;margin:7px 0}
.mvn-sub{color:var(--muted,#a0b4a9);font-size:13px;line-height:1.65}
.mvn-card{border:1px solid var(--line,#355044);border-radius:12px;
 background:var(--card,#13271e);padding:14px 16px;min-height:142px}
.mvn-label{font-size:12px;color:var(--muted,#9fb5aa);font-weight:650}
.mvn-value{font-size:27px;color:var(--txt,#e7f1ec);font-weight:850;margin:7px 0}
.mvn-period{font-size:11px;color:var(--muted,#91a99f);line-height:1.45}
.mvn-note{font-size:12px;color:var(--muted,#91a99f);line-height:1.65}
.mvn-tag{display:inline-block;border-radius:5px;padding:3px 8px;background:var(--bg2,#20342c);
 color:var(--txt2,#dcece3);font-size:11px;font-weight:650}
.mvn-alert{border-left:3px solid #d5aa54;padding:10px 12px;background:var(--card2,#182d25);
 border-radius:7px;font-size:12px;color:var(--txt,#e7f1ec);line-height:1.7}
@media(max-width:720px){.mvn-title{font-size:19px}.mvn-value{font-size:23px}}
</style>
"""


def read_data(path: Path = DATA_PATH) -> pd.DataFrame:
    """Load only source-attested records. Duplicates/invalid values fail closed."""
    if not path.is_file():
        return pd.DataFrame(columns=COLS)
    try:
        df = pd.read_csv(path, dtype={"id": str, "period": str, "asof": str}, encoding="utf-8-sig")
    except (OSError, ValueError, UnicodeError):
        return pd.DataFrame(columns=COLS)
    if not all(col in df.columns for col in COLS):
        return pd.DataFrame(columns=COLS)
    df = df.loc[:, COLS].copy()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["asof"] = pd.to_datetime(df["asof"], format="%Y-%m-%d", errors="coerce")
    df["source_url"] = df["source_url"].fillna("").astype(str)
    df["source"] = df["source"].fillna("").astype(str)
    df = df.dropna(subset=["id", "value", "asof"])
    df = df[df["value"].map(math.isfinite)]
    df = df[df["source_url"].str.startswith("https://") & df["source"].str.len().gt(0)]
    df = df.drop_duplicates(subset=["id", "period", "asof"], keep=False)
    return df.sort_values(["id", "asof"]).reset_index(drop=True)


def latest(df: pd.DataFrame, key: str) -> dict | None:
    part = df.loc[df["id"].eq(key)] if "id" in df.columns else pd.DataFrame()
    if part.empty:
        return None
    return part.sort_values("asof").iloc[-1].to_dict()


def value_text(record: dict | None) -> str:
    if not record:
        return "Chưa có số liệu"
    val = float(record["value"])
    raw = f"{val:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{raw} {record['unit']}"


def stale(record: dict | None, now: date | None = None) -> bool:
    if not record:
        return True
    now = now or date.today()
    d = pd.Timestamp(record["asof"]).date()
    # Period-based thresholds: annual/quarterly/monthly observations are NOT daily prices.
    threshold = 115 if record["id"].startswith("GDP") else 55
    return (now - d).days > threshold


def _src(row: dict | None) -> None:
    if not row:
        st.caption("Chưa có dữ liệu đã kiểm chứng để hiển thị. Không tự tạo giá trị.")
        return
    p = pd.Timestamp(row["asof"]).strftime("%d/%m/%Y")
    status = " · ⚠ Đã quá kỳ cập nhật dự kiến" if stale(row) else ""
    st.caption(f"Kỳ: {escape(str(row['period']))} · kết thúc {p}{status} · "
               f"[Nguồn: {escape(str(row['source']))}]({row['source_url']})")
    if pd.notna(row.get("note")) and str(row["note"]).strip():
        st.caption(str(row["note"]))


def _card(row: dict | None, fallback: str) -> None:
    if row:
        label = str(row["label"])
        period = f"{row['period']} · đến {pd.Timestamp(row['asof']):%d/%m/%Y}"
        value = value_text(row)
        note = "⚠ Cần đối chiếu kỳ mới" if stale(row) else "Số liệu theo kỳ công bố"
    else:
        label, value, period, note = fallback, "—", "Chưa xác minh nguồn", "Không suy diễn từ dữ liệu khác"
    st.markdown('<div class="mvn-card">'
                f'<div class="mvn-label">{escape(label)}</div>'
                f'<div class="mvn-value">{escape(value)}</div>'
                f'<div class="mvn-period">{escape(period)}</div>'
                f'<div class="mvn-note">{escape(note)}</div></div>',
                unsafe_allow_html=True)


def _cards(df: pd.DataFrame, ids: list[tuple[str, str]]) -> None:
    for first in range(0, len(ids), 4):
        cols = st.columns(min(4, len(ids) - first), gap="small")
        for col, (key, label) in zip(cols, ids[first:first+4]):
            with col:
                _card(latest(df, key), label)


def _source_table(df: pd.DataFrame, keys: list[str]) -> None:
    rows = []
    for key in keys:
        item = latest(df, key)
        if not item:
            continue
        rows.append({"Chỉ tiêu": item["label"], "Giá trị": value_text(item),
                     "Kỳ dữ liệu": item["period"], "Đến ngày": f'{item["asof"]:%d/%m/%Y}',
                     "Đối chiếu": item["comparison"], "Nguồn": item["source"],
                     "Link gốc": item["source_url"]})
    if not rows:
        st.info("Chưa có bản ghi có nguồn đã xác minh.")
        return
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True,
                 column_config={"Link gốc": st.column_config.LinkColumn("Link gốc")})


def _section_heading(title: str, subtitle: str) -> None:
    st.subheader(title)
    st.caption(subtitle)


def _summary(df: pd.DataFrame) -> None:
    _section_heading("Tổng quan vĩ mô Việt Nam", "Chỉ hiển thị dữ liệu có nguồn và kỳ công bố; không phải bảng tin thời gian thực.")
    _cards(df, [("GDP_Q", "GDP quý mới nhất"), ("CPI_OCT_YOY", "CPI cùng kỳ"),
                ("IIP_10M", "Tăng trưởng IIP"), ("PUBLIC_INV_10M", "Giải ngân đầu tư công")])
    st.markdown("#### Nhận định nền tảng · không phải tín hiệu giao dịch")
    growth, cpi, inv = latest(df, "GDP_Q"), latest(df, "CPI_OCT_YOY"), latest(df, "PUBLIC_INV_10M")
    if growth and cpi:
        st.markdown("<div class='mvn-alert'>"
                    "<b>Tăng trưởng và lạm phát phải được đọc cùng nhau.</b> "
                    "GDP quý III tăng so cùng kỳ, trong khi CPI tháng Mười cùng kỳ ở mức đáng theo dõi. "
                    "Chỉ từ các số này chưa đủ xác định chu kỳ kinh tế hoặc dự báo VNINDEX; "
                    "cần bổ sung PMI, tín dụng, lãi suất, tỷ giá và dòng tiền trên thị trường."
                    "</div>", unsafe_allow_html=True)
    else:
        st.info("Chưa đủ hai trụ cột tăng trưởng và CPI để đưa ra nhận định nền tảng.")
    if inv:
        st.caption("Đầu tư công đã có dữ liệu giải ngân đến 31/10; tác động đến cổ phiếu xây dựng, vật liệu "
                   "còn phụ thuộc tiến độ dự án và lợi nhuận từng doanh nghiệp.")
    st.markdown("#### Tình trạng dữ liệu")
    available = df["id"].nunique() if not df.empty else 0
    st.caption(f"Có {available} nhóm chỉ tiêu nguồn gốc rõ ràng trong kho macro thủ công. "
               "Chưa có dữ liệu đủ chuẩn cho PMI, OMO, tín dụng, lãi suất liên ngân hàng, "
               "tỷ giá liên ngân hàng và báo cáo chu kỳ tự động; không tự điền số.")
    with st.expander("Kiểm tra nguồn và kỳ dữ liệu", expanded=False):
        _source_table(df, ["GDP_Q", "CPI_OCT_YOY", "IIP_10M", "PUBLIC_INV_10M"])


def _growth(df: pd.DataFrame) -> None:
    _section_heading("Chu kỳ kinh tế & Lạm phát", "So sánh đúng kỳ: GDP theo quý, CPI theo tháng hoặc bình quân lũy kế.")
    _cards(df, [("GDP_Q", "GDP quý"), ("GDP_9M", "GDP 9 tháng"),
                ("CPI_OCT_YOY", "CPI tháng 10 cùng kỳ"), ("CORE_CPI_10M", "CPI lõi bình quân")])
    st.markdown("#### GDP theo quý")
    q = df.loc[df["id"].eq("GDP_Q")].sort_values("asof")
    if len(q) >= 2:
        table = q[["period", "value"]].rename(columns={"period": "Quý", "value": "GDP (% YoY)"})
        st.line_chart(table.set_index("Quý"), height=240)
        st.caption("Mỗi điểm là tăng trưởng so với cùng quý năm trước, không phải tốc độ tăng so với quý liền trước.")
    else:
        st.info("Cần ít nhất hai quý có nguồn để vẽ diễn biến GDP.")
    st.markdown("#### Các thước đo lạm phát")
    _source_table(df, ["CPI_OCT_MOM", "CPI_OCT_YOY", "CPI_10M", "CORE_CPI_10M"])
    st.markdown("#### Nhận diện giai đoạn chu kỳ")
    st.info("**Chưa đủ bằng chứng để gắn nhãn chu kỳ.** GDP tăng tốc chưa đủ kết luận đang 'phục hồi' "
            "hay 'cuối chu kỳ'. Cần PMI, tín dụng, lãi suất thực, cầu nội địa và xu hướng lạm phát nhiều kỳ.")
    with st.expander("Khung đọc 4 giai đoạn kinh tế", expanded=False):
        st.write("**Phục hồi:** hoạt động sản xuất cải thiện từ nền yếu, lạm phát thường bớt căng thẳng.\n\n"
                 "**Mở rộng:** tăng trưởng và nhu cầu lan rộng, cần đánh giá chất lượng tín dụng.\n\n"
                 "**Cuối chu kỳ:** áp lực giá hoặc chi phí vốn cao có thể hạn chế tăng trưởng.\n\n"
                 "**Suy giảm:** sản lượng và nhu cầu yếu, chính sách phản ứng tùy bối cảnh.")


def _monetary(df: pd.DataFrame) -> None:
    _section_heading("Tiền tệ & Thanh khoản", "Tách rõ lãi suất điều hành, thị trường liên ngân hàng, OMO, tín dụng và tỷ giá.")
    _cards(df, [("POLICY_RATE", "Lãi suất điều hành"), ("INTERBANK_ON", "Liên ngân hàng O/N"),
                ("CREDIT_YTD", "Tăng trưởng tín dụng"), ("USDVND", "USD/VND liên ngân hàng")])
    st.warning("Các thước đo tiền tệ trên **chưa được đưa vào kho macro có nguồn kiểm chứng**. "
               "Không suy ra 'NHNN bơm/hút tiền' chỉ từ biến động USD/VND hoặc tin tức.")
    st.markdown("#### Kênh truyền dẫn cần theo dõi")
    st.write("OMO và lãi suất liên ngân hàng → chi phí vốn → tín dụng và định giá; "
             "USD/VND và lợi suất Mỹ → áp lực tỷ giá → không gian chính sách. "
             "Đây là quan hệ điều kiện, không phải tín hiệu giá cổ phiếu tức thời.")
    st.markdown("[Dữ liệu, thông cáo NHNN](https://www.sbv.gov.vn/)")
    st.caption("Mục **Thị trường → Nhận định VNINDEX** đã có bảng USD/VND và hồ sơ NHNN riêng. "
               "Dữ liệu này chưa được trộn với CPI/GDP để tạo điểm số.")
    if st.toggle("Xem hồ sơ chính sách ngoại hối NHNN hiện có", value=False, key="mvn_nhnn_details"):
        try:
            from vnindex_nhnn_fx import render_fx_interventions
            render_fx_interventions()
        except (ImportError, AttributeError, ValueError, OSError) as exc:
            st.info(f"Hồ sơ NHNN chưa tải được: {type(exc).__name__}")


def _fiscal(df: pd.DataFrame) -> None:
    _section_heading("Chính sách tài khóa", "Dùng tỷ lệ giải ngân với đúng mẫu số kế hoạch và số lũy kế được công bố.")
    _cards(df, [("PUBLIC_INV_10M", "Giải ngân / kế hoạch"),
                ("PUBLIC_INV_AMOUNT_10M", "Giải ngân lũy kế"),
                ("BUDGET_REV_10M", "Thu ngân sách"), ("BUDGET_EXP_10M", "Chi ngân sách")])
    inv = latest(df, "PUBLIC_INV_10M")
    if inv:
        st.markdown("#### Tiến độ giải ngân vốn đầu tư công")
        st.progress(min(1.0, max(0.0, float(inv["value"]) / 100.0)),
                    text=f"{value_text(inv)} · so với kế hoạch Thủ tướng Chính phủ giao")
        _src(inv)
        st.caption("Có cách tính tỷ lệ khác khi điều chỉnh mẫu số; không trộn 74,1% với 76,6% "
                   "vì khác phần vốn trong kế hoạch tính toán.")
    st.markdown("#### Tác động đến ngành · có điều kiện")
    st.write("Giải ngân thực tế có thể tạo nhu cầu cho **xây dựng hạ tầng, đá, nhựa đường, thép, xi măng**. "
             "Muốn xác nhận cổ phiếu hưởng lợi cần kiểm tra dự án, backlog, biên lợi nhuận, "
             "công nợ và dòng tiền của từng doanh nghiệp.")
    _source_table(df, ["PUBLIC_INV_10M", "PUBLIC_INV_AMOUNT_10M", "BUDGET_REV_10M"])


def _sector_impact(df: pd.DataFrame) -> None:
    _section_heading("Bản đồ truyền dẫn Vĩ mô → Ngành", "Kịch bản có điều kiện; không gắn nhãn 'ngành dẫn sóng' khi chưa đối chiếu giá và thanh khoản.")
    pathways = [
        {"Yếu tố": "GDP / IIP tăng tốc", "Ngành liên quan": "Công nghiệp, thép, khu công nghiệp",
         "Điều kiện xác nhận": "Đơn hàng, sản lượng, giá bán, biên lợi nhuận và dòng tiền cổ phiếu"},
        {"Yếu tố": "Áp lực CPI tăng", "Ngành liên quan": "Bán lẻ, tiêu dùng, doanh nghiệp vay nợ",
         "Điều kiện xác nhận": "Giá đầu vào, khả năng chuyển giá, lãi suất thực và sức mua"},
        {"Yếu tố": "Lãi suất / tín dụng thuận lợi (chưa có số)", "Ngành liên quan": "Ngân hàng, chứng khoán, bất động sản",
         "Điều kiện xác nhận": "Chất lượng tín dụng, NIM, thanh khoản giao dịch và dòng tiền"},
        {"Yếu tố": "Giải ngân đầu tư công", "Ngành liên quan": "Xây dựng, vật liệu, hạ tầng",
         "Điều kiện xác nhận": "Hợp đồng trúng thầu, backlog, công nợ và tiến độ thực tế"},
        {"Yếu tố": "Biến động USD/VND / Fed", "Ngành liên quan": "Xuất khẩu, nhập khẩu, ngân hàng",
         "Điều kiện xác nhận": "Tỷ giá thực tế, cơ cấu doanh thu/chi phí ngoại tệ và dòng vốn"},
    ]
    st.dataframe(pd.DataFrame(pathways), hide_index=True, use_container_width=True)
    st.caption("Ưu tiên nghiên cứu ngành: phải đồng thời kiểm tra dữ liệu **Thị trường → Nhóm ngành** "
               "và **Ngành → Dòng dẫn sóng**; chưa tính sức mạnh giá từ các chỉ tiêu vĩ mô này.")
    with st.expander("Nguồn số liệu nền", expanded=False):
        _source_table(df, ["GDP_Q", "IIP_10M", "CPI_OCT_YOY", "PUBLIC_INV_10M"])


def render(international_render) -> None:
    """Mount phase-1 macro VN around existing 9-instrument international page."""
    # MIN_MACRO_MINDMAP_20261123
    import macro_vn_mindmap as MVN_MAP
    MVN_MAP.consume_navigation(SECTIONS, widget_key="mvn_section_v1")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown("<div class='mvn-head'><div class='mvn-kicker'>TRẠM TÍN HIỆU · MIN TRADING</div>"
                "<div class='mvn-title'>VĨ MÔ VIỆT NAM & THẾ GIỚI</div>"
                "<div class='mvn-sub'>Chu kỳ kinh tế · Lạm phát · Tiền tệ · Tài khóa "
                "→ bối cảnh VNINDEX và ngành. Dữ liệu trong nước có nguồn và kỳ công bố riêng.</div></div>",
                unsafe_allow_html=True)
    if hasattr(st, "pills"):
        selected = st.pills("Chuyên mục Vĩ mô", SECTIONS, selection_mode="single",
                            default=None if "mvn_section_v1" in st.session_state else "Tổng quan", key="mvn_section_v1")
    else:
        selected = st.radio("Chuyên mục Vĩ mô", SECTIONS, horizontal=True, key="mvn_section_v1")
    selected = selected or "Tổng quan"
    if selected == "Quốc tế":
        st.caption("Giữ nguyên 9 chỉ số thị trường Mỹ/hàng hóa và chức năng phân tích chi tiết hiện có.")
        return international_render()
    df = read_data()
    if df.empty:
        st.error("Chưa đọc được data/macro_vn.csv hợp lệ; không hiển thị số liệu không có nguồn.")
    elif df["asof"].max().date() > date.today():
        st.warning("Dữ liệu có kỳ trong tương lai so với ngày hệ thống; cần kiểm tra nguồn trước khi dùng.")
    if selected == "Tổng quan":
        MVN_MAP.render_mindmap()
        _summary(df)
    elif selected == "Chu kỳ & Lạm phát":
        _growth(df)
    elif selected == "Tiền tệ & Thanh khoản":
        _monetary(df)
    elif selected == "Tài khóa":
        _fiscal(df)
    else:
        _sector_impact(df)
    st.caption("Bản dữ liệu nền là snapshot nguồn chính thức, **không tự cập nhật theo phiên cổ phiếu**. "
               "Số liệu kinh tế cần cập nhật theo báo cáo mới và theo cùng phương pháp đo lường; "
               "không phải khuyến nghị giao dịch.")
