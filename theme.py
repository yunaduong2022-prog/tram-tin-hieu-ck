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
    "bg": "#F6F9F7", "bg2": "#EBF3EF", "card": "#FFFFFF",
    "card2": "#F0F6F2", "line": "#C9DCD1", "line2": "#E1ECE5",
    "txt": "#172B23", "txt2": "#10251B", "muted": "#526C60",
    "accent": "#087C5C", "red": "#C52945", "green": "#087C5C",
    "amber": "#975A06", "gold": "#93621B", "cream": "#FCF8DF",
    "hero": "#1A3B32", "tag-red-bg": "#FCE8EC",
    "tag-green-bg": "#DFF3E9", "tag-amber-bg": "#FEF1D5",
    "tag-gray-bg": "#E9EDF0", "tag-green-fg": "#086748",
    "tag-amber-fg": "#8E5708", "tag-gray-fg": "#4C5B67",
    "bar": "#D9E8DF", "shadow": "rgba(21,49,35,.10)",
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
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
