"""NHNN FX intelligence with explicit evidence levels and a limited live news watch.

Never upgrade an RSS headline or published purchase offer to executed turnover.
Verified historical items remain dated, even when new news is fetched.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import escape as escape_html, unescape as unescape_html
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
                    "date": published, "kind": classify_headline(title, source),
                    "excerpt": _rss_excerpt(node.findtext("description") or "", title)})
    return out


# MIN_NHNN_NEWS_IMPACT_CARDS_V1: verified highlights + RSS excerpt + conditional impact.

def _rss_excerpt(description: str, title: str) -> str:
    """Only use text RSS actually supplied; don't invent missing article body."""
    content = unescape_html(description or "")
    content = re.sub(r"<[^>]*>", " ", content)
    content = re.sub(r"\s+", " ", content).strip()
    if not content:
        return ""
    # Google News descriptions frequently contain only a repeat of the title
    # and publisher. Such a field is NOT the original article's summary.
    norm_content, norm_title = normalized(content), normalized(title)
    if norm_title and norm_title in norm_content:
        # Discard rather than claiming to know the article body.
        if len(norm_content) <= len(norm_title) + 90:
            return ""
    if len(content) < 70:
        return ""
    return content[:340].rstrip() + ("…" if len(content) > 340 else "")


def _conditional_impact(kind: str) -> str:
    """Topic-level potential mechanism; no unverified policy execution claims."""
    if kind == "TIN HOÁN ĐỔI":
        return ("Nếu nghiệp vụ hoán đổi được thực hiện, VND có thể hỗ trợ "
                "thanh khoản trong kỳ hạn; cần theo dõi giá trị thực hiện "
                "và nghĩa vụ hoàn trả khi đáo hạn.")
    if kind == "TIN MUA / BÁN NGOẠI TỆ":
        return ("Mua USD thực tế có thể cung ứng VND; bán USD thực tế có thể "
                "hút VND. Chỉ tiêu đề không đủ xác minh hướng giao dịch hay quy mô.")
    if kind == "TIN ĐỀ CẬP THỰC HIỆN · CẦN ĐỐI CHIẾU":
        return ("Có thể ảnh hưởng trực tiếp đến thanh khoản, nhưng cần đọc "
                "nguồn gốc để xác nhận loại nghiệp vụ, giá trị và thời điểm.")
    if kind == "NGHIÊN CỨU / NHẬN ĐỊNH":
        return ("Đây có thể là quan điểm của đơn vị phân tích, không phải "
                "quyết định NHNN hay dự báo chắc chắn về lãi suất/VNINDEX.")
    return ("Theo dõi thêm tỷ giá liên ngân hàng, lãi suất và thanh khoản; "
            "chưa đủ dữ liệu để kết luận tác động lên cổ phiếu.")


def render_nhnn_quick_box() -> None:
    """Dated NHNN summary, shown once below the USD/VND mini-chart."""
    # Static policy history is dated on purpose. New RSS items appear below.
    st.markdown("""
<style>
.nhnn-impact-brief{border:1.5px solid #27d49b;border-radius:12px;
 background:rgba(23,133,92,.07);padding:11px 16px 13px;
 margin:14px 0 17px;color:var(--txt,#e6efe9);font-size:13px;line-height:1.55}
.nhnn-impact-title{display:inline-block;background:#36dca0;color:#08281c;
 font-weight:850;font-size:13px;padding:5px 11px;border-radius:6px;
 margin:-3px 0 8px}
.nhnn-impact-brief p{margin:3px 0 6px!important;color:var(--txt,#e6efe9)!important}
.nhnn-impact-brief .nhnn-green{color:#39d5a1!important;font-weight:750}
.nhnn-impact-brief .nhnn-gold{color:#f5bf54!important;font-weight:750}
.nhnn-impact-brief .nhnn-muted{font-size:11px;opacity:.85;margin-top:6px!important}
.nhnn-impact-brief a{color:#77c6ef!important;text-decoration:underline}
</style>
<section class="nhnn-impact-brief">
  <div class="nhnn-impact-title">NHNN MUA USD · TÁC ĐỘNG THANH KHOẢN</div>
  <p>• <strong>Thông báo 10/11:</strong> dự kiến mua USD giao ngay giá
    <strong>25.500 VND/USD</strong> từ 11/11, thứ Hai và thứ Tư hằng tuần.</p>
  <p>• <strong>Hoán đổi USD/VND:</strong> VnEconomy ngày 11/11 dẫn đại diện NHNN
    cho biết đã cung ứng <strong>gần 50.000 tỷ VND</strong> qua nghiệp vụ ngày 09/11;
    <strong>khác với mua USD giao ngay</strong> và có kỳ hạn hoàn trả.</p>
  <p class="nhnn-green">⇒ Nếu NHNN thực mua USD giao ngay, ngân hàng bán USD sẽ
    nhận VND; có thể hỗ trợ thanh khoản và giảm áp lực chi phí vốn.</p>
  <p class="nhnn-green">⇒ <strong>NGÂN HÀNG HƯỞNG LỢI TRỰC TIẾP VỀ THANH KHOẢN</strong>
    nếu thực tế bán USD cho NHNN và nhận VND. Điều này không đồng nghĩa
    mọi ngân hàng hay cổ phiếu ngân hàng chắc chắn hưởng lợi.</p>
  <p class="nhnn-gold">⇒ Chưa có khối lượng mua USD giao ngay được xác minh;
    không kết luận đã bơm thêm VND qua kênh này hoặc lãi suất/VNINDEX chắc chắn giảm/tăng.</p>
  <p class="nhnn-muted">Tin có ngày gốc, không phải báo giá hay số liệu hôm nay ·
    <a href="https://vnexpress.net/ngan-hang-nha-nuoc-se-dinh-ky-mua-usd-tu-cac-nha-bang-5142801.html" target="_blank">VnExpress 10/11</a>
    · <a href="https://vneconomy.vn/phan-ung-cua-thi-truong-sau-khi-hoan-doi-va-mo-kenh-mua-ngoai-te.htm" target="_blank">VnEconomy 11/11</a></p>
</section>
""", unsafe_allow_html=True)

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
    # The green quick box is rendered beside the USD/VND chart, not repeated here.

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

    st.markdown("**Tin mới về NHNN · Nội dung & tác động có điều kiện**")
    monitor = fetch_updates()
    stamp = monitor["checked_at"].astimezone(TZ).strftime("%d/%m/%Y %H:%M")
    st.caption(f"Kiểm tra RSS: {stamp} (giờ VN) · cập nhật mỗi 30 phút khi trang mở. "
               "Trích yếu chỉ lấy từ RSS, không thay thế bài viết gốc hay xác nhận giao dịch.")
    if not monitor["available"]:
        st.warning("Không kết nối được nguồn tin. Các nội dung có ngày ở trên vẫn là "
                   "dữ liệu lịch sử; không thể suy ra NHNN không có giao dịch mới.")
    elif not monitor["items"]:
        st.info("Chưa tìm được tin phù hợp trong 14 ngày qua. Không đồng nghĩa "
                "NHNN không có hoạt động mua/bán ngoại tệ.")
    else:
        if monitor["some_sources_failed"]:
            st.caption("Một số nguồn đang giới hạn truy cập; danh sách có thể thiếu tin.")
        recent = monitor["items"][:4]
        extra = monitor["items"][4:]

        def news_card(news: dict) -> None:
            when = news["date"].astimezone(TZ).strftime("%d/%m/%Y %H:%M")
            with st.container(border=True):
                st.markdown(f"**{news['kind']} · {when}**")
                st.markdown(f"[{_safe_md(news['title'])}]({news['url']})")
                snippet = news.get("excerpt", "")
                if snippet:
                    st.write("**Nội dung RSS:** " + _safe_md(snippet))
                else:
                    st.caption("Nguồn RSS chưa có trích yếu độc lập từ nội dung bài; "
                               "mở đường dẫn để đọc chi tiết. Không tự tạo bản tóm tắt.")
                st.write("**Tác động tiềm năng:** " + _conditional_impact(news["kind"]))
                st.caption("Nguồn tổng hợp: " + _safe_md(news["publisher"]) + " · "
                           "Chưa đối chiếu toàn văn và số liệu giao dịch.")

        for news in recent:
            news_card(news)
        if extra:
            with st.expander(f"Xem thêm {len(extra)} tin cùng chủ đề", expanded=False):
                for news in extra:
                    news_card(news)
    st.caption("Tin tổng hợp và nhận định có điều kiện, không phải xác nhận thực hiện "
               "giao dịch NHNN hay khuyến nghị mua bán cổ phiếu.")
