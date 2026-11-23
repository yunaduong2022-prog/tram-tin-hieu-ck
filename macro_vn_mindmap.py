"""Interactive, theme-aware macro mind map for Trạm Tín Hiệu.

UI only. No macro data downloads, EOD writes, trading signals, or external JS.
Each branch navigates to an *existing* Vietnam/international macro section
using Streamlit query parameters and preserves all underlying analysis.
"""
from __future__ import annotations

from html import escape
from urllib.parse import urlencode

import streamlit as st

NAV_PARAM = "mvn_section"
NAV_KEY = "mvn_section_v1"

# Each branch routes to its own relevant macro view. Cycle and inflation are
# separate views to avoid showing a GDP chart before CPI when opening Lạm phát.
BRANCHES = (
    ("01", "Chu kỳ kinh tế", "GDP · PMI · IIP · Pha kinh tế", "Chu kỳ kinh tế"),
    ("02", "Lạm phát", "CPI · CPI lõi · Giá hàng hóa", "Lạm phát"),
    ("03", "Chính sách tiền tệ", "Lãi suất · OMO · Tín dụng · Tỷ giá · TPCP", "Tiền tệ & Thanh khoản"),
    ("04", "Chính sách tài khóa", "Thuế · Đầu tư công · Ngân sách · Nợ công", "Tài khóa"),
    ("05", "Vĩ mô quốc tế", "Fed · DXY · Lợi suất Mỹ · Hàng hóa", "Quốc tế"),
    ("06", "Tác động thị trường & ngành", "VN-Index · Dòng tiền · Bank · CK · Thép · BĐS", "Tác động ngành"),
)

CSS = """
<style>
.mvn-mm-wrap{--mm-line:#1aa38c;--mm-hi:#35d9b6;--mm-ink:var(--txt,#e8f2ec);
 --mm-muted:var(--muted,#a4b7ae);--mm-card:var(--card,#132b23);
 border:1px solid var(--line,#355044);border-radius:16px;
 background:var(--card2,rgba(23,47,38,.55));padding:21px 22px;margin:12px 0 22px;
 color:var(--mm-ink);font-family:inherit}
.mvn-mm-kicker{font-size:11px;font-weight:850;letter-spacing:1.5px;
 color:var(--mm-hi);text-transform:uppercase;margin-bottom:5px}
.mvn-mm-heading{font-size:20px;line-height:1.3;font-weight:800;color:var(--mm-ink);margin:0}
.mvn-mm-hint{font-size:12px;color:var(--mm-muted);margin-top:5px;margin-bottom:16px}
.mvn-mm-layout{display:grid;grid-template-columns:minmax(185px,29%) minmax(0,1fr);
 gap:32px;align-items:center}
.mvn-mm-hub{border:2px solid var(--mm-line);border-radius:14px;
 background:linear-gradient(120deg,rgba(33,165,140,.14),rgba(31,91,79,.08));
 min-height:146px;display:flex;align-items:center;justify-content:center;
 flex-direction:column;padding:16px 12px;position:relative;text-align:center}
.mvn-mm-hub::after{content:"";position:absolute;right:-33px;top:50%;
 width:33px;height:2px;background:var(--mm-line)}
.mvn-mm-hub-core{font-size:24px;font-weight:900;letter-spacing:1.1px;color:var(--mm-ink)}
.mvn-mm-hub-sub{font-size:12px;line-height:1.7;color:var(--mm-muted);margin-top:7px}
.mvn-mm-branches{border-left:2px solid var(--mm-line);padding-left:29px;
 display:flex;flex-direction:column;gap:9px;position:relative}
.mvn-mm-node{display:flex;align-items:center;gap:12px;position:relative;
 padding:11px 13px;min-height:62px;text-decoration:none !important;
 color:var(--mm-ink) !important;border:1px solid var(--line,#355044);
 background:var(--mm-card);border-radius:11px;
 transition:border-color .12s, background .12s, transform .12s}
.mvn-mm-node::before{content:"";position:absolute;left:-31px;top:50%;
 width:31px;height:2px;background:var(--mm-line)}
.mvn-mm-node:hover,.mvn-mm-node:focus-visible{border-color:var(--mm-hi);
 background:var(--card2,rgba(39,74,62,.95));transform:translateX(2px);
 outline:2px solid transparent}
.mvn-mm-number{display:flex;justify-content:center;align-items:center;flex:none;
 border-radius:8px;width:35px;height:35px;background:rgba(26,163,140,.16);
 color:var(--mm-hi);font-size:13px;font-weight:800}
.mvn-mm-detail{min-width:0;flex:1}
.mvn-mm-name{font-size:14px;line-height:1.45;font-weight:800;color:var(--mm-ink)}
.mvn-mm-desc{font-size:11.5px;line-height:1.5;color:var(--mm-muted);margin-top:2px}
.mvn-mm-arrow{font-size:17px;color:var(--mm-hi);flex:none}
.mvn-mm-outcome{display:flex;justify-content:space-between;gap:10px;align-items:center;
 margin-top:16px;padding:11px 13px;border:1px dashed var(--mm-line);border-radius:10px;
 background:rgba(26,163,140,.055)}
.mvn-mm-outcome-title{font-size:12px;font-weight:800;color:var(--mm-ink)}
.mvn-mm-outcome-note{font-size:11px;color:var(--mm-muted);margin-top:3px;line-height:1.5}
.mvn-mm-action{font-size:12px;font-weight:800;color:var(--mm-hi) !important;
 text-decoration:none !important;white-space:nowrap}
.mvn-mm-action:hover{text-decoration:underline !important}
@media(max-width:760px){
.mvn-mm-wrap{padding:16px 12px}.mvn-mm-layout{display:block}
.mvn-mm-hub{min-height:90px;margin-bottom:13px}.mvn-mm-hub::after{display:none}
.mvn-mm-branches{border-left:0;padding-left:0;gap:8px}
.mvn-mm-node::before{display:none}.mvn-mm-outcome{align-items:flex-start;flex-direction:column}
.mvn-mm-hub-core{font-size:20px}.mvn-mm-name{font-size:13px}}
@media(prefers-reduced-motion:reduce){.mvn-mm-node{transition:none}}
</style>
"""


def navigation_url(section: str) -> str:
    """Relative href; never navigates to a new domain or mutates other data."""
    return "?" + urlencode({NAV_PARAM: section})


def consume_navigation(sections: list[str], widget_key: str = NAV_KEY) -> None:
    """Consume a map click *before* the existing st.pills widget is instantiated.

    Clearing the one-time URL parameter prevents it from forcing subsequent
    manual tab changes. Unknown values are ignored rather than injecting keys.
    """
    try:
        requested = st.query_params.get(NAV_PARAM)
    except (AttributeError, KeyError):
        return
    if isinstance(requested, list):
        requested = requested[-1] if requested else None
    if not requested:
        return
    if requested in sections:
        st.session_state[widget_key] = requested
    try:
        del st.query_params[NAV_PARAM]
    except (AttributeError, KeyError):
        pass


def build_markup() -> str:
    """No live claims. Navigation and topic structure only."""
    rows = []
    for number, title, details, section in BRANCHES:
        href = escape(navigation_url(section), quote=True)
        rows.append(
            '<a class="mvn-mm-node" href="' + href + '" '
            'title="Mở ' + escape(section, quote=True) + '">'
            '<span class="mvn-mm-number">' + escape(number) + '</span>'
            '<span class="mvn-mm-detail">'
            '<span class="mvn-mm-name">' + escape(title) + '</span>'
            '<span class="mvn-mm-desc" style="display:block">' + escape(details) + '</span>'
            '</span><span class="mvn-mm-arrow" aria-hidden="true">›</span></a>'
        )
    link = escape(navigation_url("Tác động ngành"), quote=True)
    return (
        '<div class="mvn-mm-wrap" role="region" aria-label="Sơ đồ tư duy vĩ mô">'
        '<div class="mvn-mm-kicker">TRẠM TÍN HIỆU · BẢN ĐỒ VĨ MÔ</div>'
        '<div class="mvn-mm-heading">Từ kinh tế đến dòng tiền thị trường</div>'
        '<div class="mvn-mm-hint">Chọn một nhánh để mở dữ liệu, nguồn công bố và phân tích hiện có.</div>'
        '<div class="mvn-mm-layout">'
        '<div class="mvn-mm-hub"><div class="mvn-mm-hub-core">VĨ MÔ</div>'
        '<div class="mvn-mm-hub-sub">Chu kỳ · Lạm phát<br>Chính sách · Quốc tế</div></div>'
        '<div class="mvn-mm-branches">' + ''.join(rows) + '</div></div>'
        '<div class="mvn-mm-outcome">'
        '<div><div class="mvn-mm-outcome-title">VĨ MÔ → VN-INDEX → DÒNG TIỀN → NHÓM NGÀNH</div>'
        '<div class="mvn-mm-outcome-note">Liên hệ có điều kiện; cần xác nhận thêm bằng giá, thanh khoản và sức mạnh ngành.</div></div>'
        '<a class="mvn-mm-action" target="_self" href="' + link + '">Xem tác động ngành →</a>'
        '</div></div>'
    )


def render_mindmap() -> None:
    """Mount only inside Tổng quan, preserving all original dashboard sections."""
    st.markdown(CSS + build_markup(), unsafe_allow_html=True)
