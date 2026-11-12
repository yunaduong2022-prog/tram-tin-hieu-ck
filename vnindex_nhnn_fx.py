"""NHNN FX intervention context, with dated sourced policy and automatic news watch.

Do NOT infer FX interventions from USD/VND rates. A policy announcement is NOT
proof that any given USD amount actually traded. News updates are headlines only.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import re
import unicodedata
import xml.etree.ElementTree as ET

import streamlit as st

# Verified contemporary reporting of NHNN announcement, not executed turnover.
SOURCES = (
    ("VnExpress · 10/11/2026",
     "https://vnexpress.net/ngan-hang-nha-nuoc-se-dinh-ky-mua-usd-tu-cac-nha-bang-5142801.html"),
    ("Dân trí · 10/11/2026",
     "https://dantri.com.vn/kinh-doanh/ngan-hang-nha-nuoc-mua-usd-giao-ngay-ho-tro-thanh-khoan-he-thong-20261110100211695.htm"),
)
EVENT_DATE = date(2026, 11, 10)
EFFECTIVE_DATE = date(2026, 11, 11)
VNN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _plain(value: str) -> str:
    """Normalize titles only to find relevant news; never infer trade execution."""
    s = unicodedata.normalize("NFKD", value.lower().replace("đ", "d"))
    return "".join(c for c in s if not unicodedata.combining(c))


def _relevant(title: str) -> bool:
    title = _plain(title)
    has_authority = any(k in title for k in ("ngan hang nha nuoc", "nhnn"))
    has_operation = any(k in title for k in
                        ("mua usd", "ban usd", "mua ngoai te", "ban ngoai te",
                         "hoan doi ngoai te", "hoan doi usd", "swap usd"))
    return has_authority and has_operation


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_policy_headlines() -> list[dict]:
    """Fetch *headlines*, not intervention volumes, from Google News RSS.

    Google News is an aggregator and can be unavailable in Streamlit Cloud. All
    entries retain publication dates; never transform titles into confirmed trades.
    """
    query = '"Ngân hàng Nhà nước" ("mua USD" OR "bán USD" OR "hoán đổi ngoại tệ") when:14d'
    url = ("https://news.google.com/rss/search?q=" + quote_plus(query)
           + "&hl=vi&gl=VN&ceid=VN%3Avi")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml"})
    try:
        with urlopen(request, timeout=6) as response:
            payload = response.read(750_000)
        root = ET.fromstring(payload)
        now = datetime.now(timezone.utc)
        results = []
        seen = set()
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            href = (item.findtext("link") or "").strip()
            date_text = (item.findtext("pubDate") or "").strip()
            if not _relevant(title) or not href or not date_text or len(title) > 250:
                continue
            try:
                published = parsedate_to_datetime(date_text).astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
            if published > now + timedelta(days=1) or now - published > timedelta(days=14):
                continue
            if (urlsplit(href).scheme != "https" or
                    urlsplit(href).hostname not in ("news.google.com", "www.google.com")):
                continue
            dedup_key = _plain(title)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            results.append({"title": title, "url": href, "date": published})
            if len(results) >= 4:
                break
        return sorted(results, key=lambda item: item["date"], reverse=True)
    except (HTTPError, URLError, TimeoutError, OSError, ET.ParseError, ValueError):
        return []


def render_fx_interventions() -> None:
    """Render NHNN policy context separate from daily USD/VND prices."""
    st.markdown("#### NHNN · MUA / BÁN USD & THANH KHOẢN VND")
    with st.container(border=True):
        a, b = st.columns(2, gap="medium")
        with a:
            st.markdown("**MUA USD GIAO NGAY · TIN NGÀY 09–10/11/2026**")
            st.metric("Tỷ giá mua can thiệp được công bố", "25.500 VND/USD")
            st.write("Phương án bắt đầu **11/11/2026**, giao dịch dự kiến vào **thứ Hai và thứ Tư hằng tuần**, áp dụng cho tổ chức tín dụng đủ điều kiện.")
            st.caption("Đây là mức giá của thông báo ngày 10/11; không phải báo giá thời gian thực và chưa xác nhận lượng USD thực mua.")
        with b:
            st.markdown("**BÁN USD / HOÁN ĐỔI · THEO DÕI**")
            st.write("Chưa có **số liệu thực hiện bán USD giao ngay** được xác minh trong các nguồn của bảng này. Không có thông tin **không đồng nghĩa** NHNN không giao dịch.")
            st.write("Nghiệp vụ **hoán đổi USD/VND** công bố **06/11/2026**: hạn mức tối đa **2 tỷ USD**, kỳ hạn **182 ngày**; khác với mua/bán USD giao ngay không kỳ hạn.")
        st.info("**Tác động nếu giao dịch mua thực sự phát sinh:** NHNN thanh toán VND cho USD mua vào, có thể bổ sung thanh khoản hệ thống. **Chưa có khối lượng khớp lệnh xác nhận**, vì vậy không ghi số tiền đã bơm.")
        today = datetime.now(VNN_TZ).date()
        if (today - EVENT_DATE).days > 14:
            st.warning("Thông báo đang hiển thị là dữ liệu lịch sử; cần kiểm tra xem chính sách đã thay đổi hay chưa.")
        st.caption("Nguồn thông báo được dẫn lại: " + " · ".join(f"[{label}]({url})" for label, url in SOURCES))
    with st.expander("Tin mới về hoạt động ngoại tệ NHNN · tự kiểm tra 30 phút/lần", expanded=False):
        items = fetch_policy_headlines()
        if not items:
            st.caption("Chưa lấy được tin mới phù hợp từ nguồn tổng hợp RSS. Không suy diễn từ tỷ giá USD/VND.")
        else:
            st.caption("Tin từ Google News RSS; tiêu đề và ngày đăng, **không phải dữ liệu giao dịch NHNN đã xác nhận**.")
            for item in items:
                when = item["date"].astimezone(VNN_TZ).strftime("%d/%m/%Y %H:%M")
                title = escape(item["title"]).replace("[", "\\[").replace("]", "\\]")
                st.markdown(f"- **{when}** · [{title}]({item['url']})")
