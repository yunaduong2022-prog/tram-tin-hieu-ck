"""NHNN FX intelligence with explicit evidence levels and a limited live news watch.

Never upgrade an RSS headline or published purchase offer to executed turnover.
Verified historical items remain dated, even when new news is fetched.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape as escape_html
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
import re
import unicodedata
import xml.etree.ElementTree as ET

import streamlit as st

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
FEED_TTL_SECONDS = 1800
HEADLINE_WINDOW_DAYS = 14
FED_CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"

# Sources and observations are locked to their publication dates. These are NOT
# live measurements and must not be reused as today's executions or forecasts.
EVIDENCE = (
    {
        "date": date(2026, 11, 10), "kind": "THÔNG BÁO CHÍNH SÁCH",
        "text": "NHNN công bố mua USD giao ngay 25.500 VND/USD từ 11/11, dự kiến vào thứ Hai và thứ Tư. Đây là giá mua theo phương án, không chứng minh đã mua được USD.",
        "source": "VnExpress · 10/11/2026",
        "url": "https://vnexpress.net/ngan-hang-nha-nuoc-se-dinh-ky-mua-usd-tu-cac-nha-bang-5142801.html",
    },
    {
        "date": date(2026, 11, 11), "kind": "THÔNG TIN THỰC HIỆN · HOÁN ĐỔI",
        "text": "VnEconomy dẫn đại diện NHNN cho biết ngày 09/11 gần 50.000 tỷ VND được cung ứng qua nghiệp vụ hoán đổi. Đây là thông tin báo chí dẫn nguồn, KHÔNG phải khối lượng mua USD giao ngay từ 11/11.",
        "source": "VnEconomy · 11/11/2026",
        "url": "https://vneconomy.vn/phan-ung-cua-thi-truong-sau-khi-hoan-doi-va-mo-kenh-mua-ngoai-te.htm",
    },
    {
        "date": date(2026, 11, 11), "kind": "DIỄN BIẾN TỶ GIÁ",
        "text": "VnEconomy ghi nhận tỷ giá liên ngân hàng khoảng 25.634 VND/USD lúc 11h ngày 11/11; cao hơn giá mua giao ngay 25.500 khoảng 134 đồng. Là mức giá nội ngày, không phải giá chốt hoặc số USD đã giao dịch với NHNN.",
        "source": "VnEconomy · 11/11/2026",
        "url": "https://vneconomy.vn/phan-ung-cua-thi-truong-sau-khi-hoan-doi-va-mo-kenh-mua-ngoai-te.htm",
    },
    {
        "date": date(2026, 11, 12), "kind": "NGHIÊN CỨU LỊCH SỬ",
        "text": "Theo bài báo dẫn VNDIRECT: 13 đợt NHNN mua ngoại tệ giai đoạn 2016–2023, VNINDEX tăng 11/13 lần sau 1 tháng và 12/13 lần sau 3 tháng. Mẫu nhỏ, có yếu tố trùng chu kỳ tăng; không phải xác suất hoặc dự báo cho đợt hiện tại.",
        "source": "CafeF dẫn VNDIRECT · 12/11/2026",
        "url": "https://cafef.vn/nhnn-bat-dau-mua-ngoai-te-vndirect-chi-ra-tin-hieu-dang-chu-y-voi-vn-index-188261111190240006.chn",
    },
    {
        "date": date(2026, 11, 12), "kind": "KỊCH BẢN PHÂN TÍCH",
        "text": "VNDIRECT lưu ý cuối 2026–2027 có thể xuất hiện biện pháp trung hòa thanh khoản như tín phiếu trong một số kịch bản. Đây là khả năng được phân tích, không phải quyết định chính sách đã công bố.",
        "source": "CafeF dẫn VNDIRECT · 12/11/2026",
        "url": "https://cafef.vn/nhnn-bat-dau-mua-ngoai-te-vndirect-chi-ra-tin-hieu-dang-chu-y-voi-vn-index-188261111190240006.chn",
    },
)

SEARCHES = (
    '"Ngân hàng Nhà nước" ("mua USD" OR "bán USD" OR "hoán đổi ngoại tệ") when:14d',
    '("VNDIRECT" OR "HSC" OR "ACBS") ("NHNN" OR "thanh khoản" OR "ngoại tệ") when:14d',
)


def normalized(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value).replace("đ", "d").replace("Đ", "D"))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def classify_headline(title: str, publisher: str = "") -> str:
    """A headline/topic label, NEVER a fact verification."""
    content = normalized(title + " " + publisher)
    if any(k in content for k in ("vndirect", "hsc", "acbs", "du bao", "nhan dinh", "phan tich", "trien vong")):
        return "NGHIÊN CỨU / NHẬN ĐỊNH"
    if any(k in content for k in ("da trung thau", "trung thau", "da thuc hien", "da cung ung", "da mua")):
        return "TIN ĐỀ CẬP THỰC HIỆN · CẦN ĐỐI CHIẾU"
    if any(k in content for k in ("hoan doi", "swap")):
        return "TIN HOÁN ĐỔI"
    if any(k in content for k in ("mua usd", "ban usd", "mua ngoai te", "ban ngoai te")):
        return "TIN MUA / BÁN NGOẠI TỆ"
    return "TIN LIÊN QUAN"


def _relevant(title: str, publisher: str) -> bool:
    text = normalized(title + " " + publisher)
    return (any(x in text for x in ("ngan hang nha nuoc", "nhnn", "vndirect", "hsc", "acbs"))
            and any(x in text for x in ("ngoai te", "usd", "hoan doi", "thanh khoan", "ty gia", "lai suat")))


def _safe_md(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value))[:230]
    return re.sub(r"([\\`*\[\]()_])", r"\\\1", escape_html(value))


def _parse_rss(data: bytes, now: datetime) -> list[dict]:
    root = ET.fromstring(data)
    out: list[dict] = []
    for node in root.findall(".//item"):
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        source = (node.findtext("source") or "Nguồn tổng hợp").strip()
        published_text = node.findtext("pubDate") or ""
        if not title or not link or not _relevant(title, source):
            continue
        parsed_url = urlsplit(link)
        if parsed_url.scheme != "https" or parsed_url.hostname not in {"news.google.com", "www.google.com"}:
            continue
        try:
            published = parsedate_to_datetime(published_text)
            if published.tzinfo is None:
                continue
            published = published.astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
        if published < now - timedelta(days=HEADLINE_WINDOW_DAYS) or published > now + timedelta(days=1):
            continue
        out.append({"title": title[:230], "publisher": source[:90], "url": link,
                    "date": published, "kind": classify_headline(title, source)})
    return out


@st.cache_data(ttl=FEED_TTL_SECONDS, show_spinner=False)
def fetch_updates() -> dict:
    """Aggregated headline discovery. An RSS failure is NOT 'no NHNN activity'."""
    now = datetime.now(timezone.utc)
    all_items: list[dict] = []
    failures = 0
    for query in SEARCHES:
        url = ("https://news.google.com/rss/search?q=" + quote_plus(query)
               + "&hl=vi&gl=VN&ceid=VN%3Avi")
        request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml"})
        try:
            with urlopen(request, timeout=5) as response:
                data = response.read(700_000)
            all_items.extend(_parse_rss(data, now))
        except (HTTPError, URLError, TimeoutError, OSError, ET.ParseError, ValueError):
            failures += 1
    unique: dict[str, dict] = {}
    for entry in all_items:
        key = normalized(entry["title"])
        if key not in unique or entry["date"] > unique[key]["date"]:
            unique[key] = entry
    items = sorted(unique.values(), key=lambda item: item["date"], reverse=True)[:8]
    return {"checked_at": now, "items": items, "available": failures < len(SEARCHES),
            "some_sources_failed": failures > 0}


def render_nhnn_briefing() -> None:
    """Append research / monitoring below the existing SBV purchase/swap card."""
    st.markdown("##### NHNN & THANH KHOẢN · BẢN TIN KIỂM CHỨNG")
    st.caption("Phân biệt: thông báo chính sách / số liệu được báo chí dẫn nguồn / nghiên cứu lịch sử / dự báo. "
               "Không suy ra lượng USD đã thực mua từ biến động tỷ giá.")

    with st.container(border=True):
        a, b = st.columns(2, gap="medium")
        with a:
            st.markdown("**HOÁN ĐỔI · SỐ LIỆU ĐƯỢC BÁO CHÍ DẪN NGUỒN**")
            st.markdown("**Gần 50.000 tỷ VND · nghiệp vụ ngày 09/11/2026**")
            st.write("VnEconomy dẫn đại diện NHNN cho biết số VND trên đã được cung ứng "
                     "thông qua **hoán đổi USD/VND**. Khác với hạn mức 2 tỷ USD và "
                     "khác với hoạt động mua USD giao ngay.")
            st.caption("[VnEconomy · 11/11/2026](https://vneconomy.vn/phan-ung-cua-thi-truong-sau-khi-hoan-doi-va-mo-kenh-mua-ngoai-te.htm) "
                       "· Số liệu dẫn lời, chưa đối chiếu bảng giao dịch gốc.")
        with b:
            st.markdown("**MUA GIAO NGAY · MỨC THỰC HIỆN CHƯA XÁC MINH**")
            st.write("**Khối lượng USD thực mua:** chưa có số liệu xác minh trong nguồn hiện tại. "
                     "Công bố mua giao ngay giá 25.500 không đồng nghĩa ngân hàng đã bán USD cho NHNN.")
            st.write("**Tham chiếu 11/11 lúc 11h:** tỷ giá liên ngân hàng khoảng 25.634, "
                     "cao hơn giá mua can thiệp khoảng 134 đồng. Không dùng một thời điểm tỷ giá "
                     "để kết luận số lượng giao dịch của cả phiên.")
            st.caption("[VnEconomy · 11/11/2026](https://vneconomy.vn/phan-ung-cua-thi-truong-sau-khi-hoan-doi-va-mo-kenh-mua-ngoai-te.htm)")
        st.info("**Đánh giá tác động:** Có kênh hỗ trợ thanh khoản nhưng tác động tới lãi suất và VNINDEX "
                "phụ thuộc khối lượng thực tế, tỷ giá liên ngân hàng và các biện pháp hút/bơm tiền khác. "
                "Chưa đủ căn cứ khẳng định mua giao ngay đã tạo lượng VND đáng kể.")
        if datetime.now(TZ).date() > date(2026, 11, 26):
            st.warning("Số liệu và diễn biến trên là mốc 09–12/11/2026, không phải kết quả giao dịch hôm nay. "
                       "Kiểm tra tin mới và thông báo chính thức bên dưới.")

    with st.expander("Bằng chứng có ngày & nghiên cứu lịch sử (không phải số liệu realtime)", expanded=False):
        for item in EVIDENCE:
            st.markdown(f"**{item['kind']} · {item['date']:%d/%m/%Y}**")
            st.write(item["text"])
            st.caption(f"[{item['source']}]({item['url']})")
        now = datetime.now(TZ).date()
        if now <= date(2026, 12, 9):
            st.markdown("**LỊCH FED · 08–09/12/2026**")
            st.write("Lịch họp FOMC được công bố trước; chưa phải quyết định lãi suất. "
                     "Xem kết quả chính thức sau kỳ họp.")
        else:
            st.markdown("**LỊCH FED / QUYẾT ĐỊNH MỚI**")
            st.write("Kiểm tra lịch và tuyên bố mới trực tiếp từ Fed; không lặp lại lịch tháng 12/2026 đã qua.")
        st.caption(f"[Nguồn chính thức: Federal Reserve FOMC calendar]({FED_CALENDAR})")

    st.markdown("**Tin mới liên quan · tự kiểm tra mỗi 30 phút khi trang được mở**")
    monitor = fetch_updates()
    stamp = monitor["checked_at"].astimezone(TZ).strftime("%d/%m/%Y %H:%M")
    st.caption(f"Lần kiểm tra nguồn RSS: {stamp} (giờ VN). "
               "Đây là tiêu đề và phân loại chủ đề, không xác minh các con số trong bài.")
    if not monitor["available"]:
        st.warning("Không kết nối được nguồn tổng hợp tin. Giữ thông tin có ngày ở trên; "
                   "không có nghĩa là NHNN không thực hiện giao dịch mới.")
    elif not monitor["items"]:
        st.info("Chưa tìm được tiêu đề phù hợp trong 14 ngày qua. "
                "Không kết luận NHNN không hoạt động.")
    else:
        if monitor["some_sources_failed"]:
            st.caption("Một số nguồn tin đang lỗi hoặc bị giới hạn; kết quả có thể chưa đầy đủ.")
        for news in monitor["items"]:
            when = news["date"].astimezone(TZ).strftime("%d/%m/%Y %H:%M")
            st.markdown(f"- **{news['kind']} · {when}** · "
                        f"[{_safe_md(news['title'])}]({news['url']}) "
                        f"· {_safe_md(news['publisher'])}")
    st.caption("Muốn xác nhận lượng USD/VND thực hiện hoặc nhận định nguyên bản HSC/VNDIRECT: "
               "cần tài liệu gốc hay thông báo NHNN; tiêu đề RSS không đủ bằng chứng. "
               "Không phải khuyến nghị giao dịch.")
