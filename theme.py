"""Trạm Tín Hiệu: giao diện Sáng/Tối, mặc định tối cho mỗi phiên mới.

Giữ API cũ (PALETTE, toggle, mode, is_dark, inject, style_fig, style_df,
plotly_template) để các phần còn lại tiếp tục hoạt động.
"""
import streamlit as st

DARK = {
    "bg": "#0E1C18", "bg2": "#14261F", "card": "#162B24",
    "card2": "#1B332B", "line": "#26433A", "line2": "#1F382F",
    "txt": "#E6EFE9", "txt2": "#F3F8F5", "muted": "#8FA89D",
    "accent": "#2DD4A7", "red": "#FF6B81", "green": "#2DD4A7",
    "amber": "#F5B942", "gold": "#E0B565", "cream": "#FCF8DF",
    "hero": "#1A3B32", "tag-red-bg": "#3A1A22",
    "tag-green-bg": "#0F2E26", "tag-amber-bg": "#3A2E12",
    "tag-gray-bg": "#262D38", "tag-green-fg": "#5EE6C0",
    "tag-amber-fg": "#F5B942", "tag-gray-fg": "#B1BAC4",
    "bar": "#26433A", "shadow": "rgba(0,0,0,.5)",
}
LIGHT = {
    "bg": "#EDF3EF", "bg2": "#E1EBE5", "card": "#FAFDFB",
    "card2": "#F0F6F2", "line": "#BED0C5", "line2": "#D5E2D9",
    "txt": "#19342C", "txt2": "#102820", "muted": "#4C665A",
    "accent": "#0B6B53", "red": "#C2354A", "green": "#087A58",
    "amber": "#95600F", "gold": "#B48127", "cream": "#FCF8DF",
    "hero": "#163D31", "tag-red-bg": "#F8E6E9",
    "tag-green-bg": "#D9EDE2", "tag-amber-bg": "#F6EACF",
    "tag-gray-bg": "#E4EBE6", "tag-green-fg": "#086A4A",
    "tag-amber-fg": "#89580F", "tag-gray-fg": "#405B4E",
    "bar": "#CCDDD2", "shadow": "rgba(17,47,35,.12)",
}
# Tương thích các module chỉ đọc PALETTE ở thời điểm import.
PALETTE = DARK


def mode() -> str:
    return st.session_state.get("min_theme_mode", "dark") if st.session_state.get("min_theme_mode", "dark") in ("dark", "light") else "dark"


def is_dark() -> bool:
    return mode() == "dark"


def palette() -> dict:
    return DARK if is_dark() else LIGHT


def toggle(container=None):
    """Chọn Sáng/Tối; không tự ghi cookie để giữ mặc định tối khi mở phiên mới."""
    target = container if container is not None else st
    choice = target.segmented_control(
        "Giao diện", ["dark", "light"],
        key="min_theme_mode", default="dark",
        format_func=lambda item: "🌙 Tối" if item == "dark" else "☀️ Sáng",
        label_visibility="collapsed",
    )
    if choice is None:
        st.session_state["min_theme_mode"] = "dark"


def plotly_template() -> str:
    return "plotly_dark" if is_dark() else "plotly_white"


def style_fig(fig):
    """Nền trong suốt và màu chữ theo bảng màu đang chọn."""
    p = palette()
    fig.update_layout(
        template=plotly_template(),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=p["txt"]),
        hoverlabel=dict(bgcolor=p["card"], font=dict(color=p["txt"])),
    )
    return fig


def style_df(df):
    p = palette()
    return df.style.set_properties(**{"background-color": p["card"], "color": p["txt"]})


FINANCE_LIGHT_CSS = '''
/* MIN_FINANCE_LIGHT_V2 — broker/terminal light theme; dark theme untouched. */
:root{--min-finance-header:#173E32;--min-finance-selected:#D7E9DD;--min-finance-gold:#B48127}
.stApp [data-testid="stMain"]{background:linear-gradient(180deg,#EDF3EF 0%,#F2F6F2 75%)!important}
.stApp [data-testid="stSidebar"]{border-right:1px solid var(--line)!important}
.stApp .brand-hero{box-shadow:0 7px 24px rgba(20,57,44,.15);border:1px solid #426552}
/* The global Markdown text override had made the dark hero tagline unreadable. */
.stApp .brand-hero .brand-ttl p{color:#EDF5EB!important;opacity:.91!important}
.stApp .brand-hero .brand-pill{color:#F7F8E7!important}
/* Three-layer market navigation: distinguish active tab without large solid blocks. */
.stApp .st-key-mega-nav{background:#E3ECE6!important;border-bottom:1px solid #BFD2C6!important}
.stApp .st-key-nav-filter-groups{background:#EAF1EC!important;border-top:1px solid #CADACF!important}
.stApp .st-key-nav-sub{background:#F4F7F3!important;border-top:1px solid #D0DFD4!important}
.stApp .st-key-mega-nav button{color:#244B3C!important;font-weight:700!important}
.stApp .st-key-mega-nav button:hover{background:#D9E8DE!important;color:#0B5B44!important}
.stApp .st-key-mega-nav button[aria-checked="true"],
.stApp .st-key-mega-nav button[aria-pressed="true"]{color:#075D45!important;border-bottom-color:#08795A!important;background:#DDEDE2!important}
.stApp .st-key-nav-filter-groups button[aria-checked="true"],
.stApp .st-key-nav-filter-groups button[aria-pressed="true"]{background:#D7E9DD!important}
/* Streamlit's base config is still dark; pill buttons need explicit light surfaces.
   This avoids dark pills with dark text after selecting the light UI. */
.stApp [data-testid="stPills"] button,
.stApp [data-testid="stSegmentedControl"] button,
.stApp [data-testid="stButtonGroup"] button{
  color:#183E30!important;background:#F5FAF5!important;
  border:1px solid #BFD4C7!important;box-shadow:none!important;
}
.stApp [data-testid="stPills"] button *,
.stApp [data-testid="stSegmentedControl"] button *,
.stApp [data-testid="stButtonGroup"] button *{color:inherit!important}
.stApp [data-testid="stPills"] button[aria-checked="true"],
.stApp [data-testid="stPills"] button[aria-pressed="true"],
.stApp [data-testid="stSegmentedControl"] button[aria-checked="true"],
.stApp [data-testid="stSegmentedControl"] button[aria-pressed="true"],
.stApp [data-testid="stButtonGroup"] button[aria-checked="true"],
.stApp [data-testid="stButtonGroup"] button[aria-pressed="true"]{
  color:#075E43!important;background:#D6EEE0!important;
  border-color:#1E9975!important;font-weight:800!important;
}
/* Re-apply the nav's flat market tabs after generic widget buttons. */
.stApp .st-key-mega-nav [data-testid="stButtonGroup"] button,
.stApp .st-key-nav-filter-groups [data-testid="stButtonGroup"] button,
.stApp .st-key-nav-sub [data-testid="stButtonGroup"] button{
  border:0!important;border-bottom:2px solid transparent!important;
  border-radius:0!important;background:transparent!important;
}
.stApp .st-key-mega-nav [data-testid="stButtonGroup"] button[aria-checked="true"],
.stApp .st-key-mega-nav [data-testid="stButtonGroup"] button[aria-pressed="true"],
.stApp .st-key-nav-filter-groups [data-testid="stButtonGroup"] button[aria-checked="true"],
.stApp .st-key-nav-filter-groups [data-testid="stButtonGroup"] button[aria-pressed="true"],
.stApp .st-key-nav-sub [data-testid="stButtonGroup"] button[aria-checked="true"],
.stApp .st-key-nav-sub [data-testid="stButtonGroup"] button[aria-pressed="true"]{
  color:#08664C!important;border-bottom-color:#08795A!important;
  background:#DCECE1!important;
}
.stApp .stButton>button,.stApp .stDownloadButton>button{
  background:#EEF5F0!important;border:1px solid #BDD2C4!important;
  color:#17382B!important;font-weight:650!important;
}
.stApp .stButton>button:hover,.stApp .stDownloadButton>button:hover{
  background:#DCEDE1!important;border-color:#16815E!important;color:#075B43!important;
}
.stApp [data-baseweb="select"]>div,.stApp [data-baseweb="base-input"],
.stApp input,.stApp textarea{background:#F5F9F5!important;color:#183C2D!important;
  border-color:#BDD2C4!important}
.stApp input::placeholder,.stApp textarea::placeholder{color:#657E70!important}
.stApp [data-testid="stTabs"] button[aria-selected="true"]{
  color:#087657!important;border-bottom:3px solid #087657!important;font-weight:800!important}
.stApp [data-testid="stTabs"] button[aria-selected="false"]{color:#4E685A!important}
.stApp [data-testid="stMetric"]{background:#F7FAF7;border:1px solid #D5E1D9;border-radius:12px;padding:10px 13px}
.stApp [data-testid="stDataFrame"]{border:1px solid #90B0A0!important;border-radius:11px;overflow:hidden}
/* Native dataframes keep Streamlit's dark canvas: intentional terminal inset. */
.stApp [data-testid="stExpander"]{background:#F4F8F4!important;border-color:#CCDBD0!important}
.stApp [data-testid="stAlert"]{background:#E7F0E9!important;border:1px solid #C6D9CB!important}
/* Brand title shown above the sector terminal uses static light text by default. */
.stApp .dd-topbar .dd-brand-name{color:#163B2C!important}
.stApp .dd-topbar .dd-brand-gold{color:#A47422!important}
.stApp .dd-chip.lead,.stApp .dd-tag{color:#8B631D;border-color:#D4B467;background:#F8EDD4}
/* Professional table surfaces retain row separation, muted header, and trading colors. */
.stApp .stock-card,.stApp .card,.stApp .kq-stat,.stApp .dd-card,
.stApp .bk-wrap,.stApp .nn-wrap{box-shadow:0 3px 12px rgba(13,58,34,.06)}
.stApp .tp-tb thead th{letter-spacing:.15px}
.stApp .st-key-min-theme-selector button{border-radius:8px!important}
'''

def inject():
    """CSS theo phiên Streamlit; config.toml vẫn để dark làm mặc định."""
    p = palette()
    vars_ = ";".join(f"--{k}:{v}" for k, v in p.items())
    scheme = "dark" if is_dark() else "light"
    css = f":root{{{vars_};color-scheme:{scheme}}}" + """
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--bg)!important;color:var(--txt)!important}
[data-testid="stHeader"]{background:var(--bg)!important}
[data-testid="stSidebar"],[data-testid="stSidebar"]>div{background:var(--bg2)!important;color:var(--txt)!important}
.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6,.stApp p,.stApp li,.stApp label,
.stApp [data-testid="stMarkdownContainer"],.stApp [data-testid="stWidgetLabel"] *,
.stApp [data-testid="stMetricValue"],.stApp [data-testid="stMetricLabel"] *{color:var(--txt)!important}
.stApp [data-testid="stCaptionContainer"],.stApp small{color:var(--muted)!important}
.stApp [data-baseweb="select"]>div,.stApp [data-baseweb="input"],.stApp [data-baseweb="base-input"],
.stApp input,.stApp textarea,.stApp [data-baseweb="textarea"]{background:var(--card2)!important;color:var(--txt)!important;border-color:var(--line)!important}
.stApp input::placeholder,.stApp textarea::placeholder{color:var(--muted)!important}
.stApp [data-baseweb="popover"] *,.stApp [role="listbox"],.stApp [role="option"]{background:var(--card)!important;color:var(--txt)!important}
.stApp [data-baseweb="tag"]{background:var(--line)!important}
.stApp .stButton>button,.stApp .stDownloadButton>button{background:var(--card2);color:var(--txt);border:1px solid var(--line)}
.stApp .stButton>button:hover{border-color:var(--accent);color:var(--accent)}
.stApp [data-testid="stExpander"],.stApp [data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--line)!important}
.stApp [data-testid="stAlert"]{background:var(--card2)!important;color:var(--txt)!important}
.stApp hr{border-color:var(--line)!important}
.stApp [data-testid="stDataFrame"]{background:var(--card)!important}
.stApp [data-testid="stDataFrame"] canvas{color-scheme:normal}
.stApp [data-testid="stTabs"] button{color:var(--muted)!important}
.stApp [data-testid="stTabs"] button[aria-selected="true"]{color:var(--accent)!important}
.stApp [data-testid="stMetricDelta"]{color:var(--txt)}
.st-key-min-theme-selector{display:flex;justify-content:flex-end;margin:-4px 0 8px}
.st-key-min-theme-selector button{border-color:var(--line)!important;color:var(--txt)!important;background:var(--card)!important}
.st-key-min-theme-selector button[aria-checked="true"],.st-key-min-theme-selector button[aria-pressed="true"]{border-color:var(--accent)!important;color:var(--accent)!important;background:var(--card2)!important}
"""
    if not is_dark():
        css += FINANCE_LIGHT_CSS
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
