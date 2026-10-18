"""Chọn nền Sáng / Tối cho app (Streamlit). Toàn bộ màu tuỳ biến đi qua biến CSS."""
import streamlit as st

OPTIONS = ["☀️ Sáng", "🌙 Tối"]
DEFAULT = OPTIONS[0]

# Bảng màu: tên biến -> (sáng, tối)
PALETTE = {
    "bg":      ("#FFFFFF", "#0D1117"),   # nền trang
    "bg2":     ("#F4F6F9", "#161B22"),   # nền sidebar / thanh nav / ô phụ
    "card":    ("#FFFFFF", "#161B22"),   # nền thẻ
    "card2":   ("#F8FAFC", "#1C222B"),   # nền phụ trong thẻ
    "line":    ("#E3E8EF", "#2A313C"),   # viền
    "line2":   ("#F0F2F5", "#232A34"),   # viền mờ
    "txt":     ("#1F2937", "#E6EDF3"),   # chữ chính
    "txt2":    ("#0F172A", "#F0F6FC"),   # chữ đậm (mã CP, số liệu)
    "muted":   ("#6B7280", "#8B949E"),   # chữ phụ
    "accent":  ("#0E8A6D", "#2DD4A7"),
    "red":     ("#C93A52", "#FF6B81"),
    "green":   ("#0E8A6D", "#2DD4A7"),
    "amber":   ("#B7791F", "#F5B942"),
    "tag-red-bg":   ("#FCE4E8", "#3A1A22"),
    "tag-green-bg": ("#DDF1EB", "#0F2E26"),
    "tag-amber-bg": ("#FDF1D6", "#3A2E12"),
    "tag-gray-bg":  ("#EEF1F5", "#262D38"),
    "tag-green-fg": ("#0A6B54", "#5EE6C0"),
    "tag-amber-fg": ("#8A5A00", "#F5B942"),
    "tag-gray-fg":  ("#4B5563", "#B1BAC4"),
    "bar":     ("#E5E7EB", "#2A313C"),
    "shadow":  ("rgba(0,0,0,.06)", "rgba(0,0,0,.5)"),
}


def mode() -> str:
    """'light' hoặc 'dark' theo lựa chọn hiện tại."""
    return "dark" if st.session_state.get("theme_mode") == OPTIONS[1] else "light"


def is_dark() -> bool:
    return mode() == "dark"


def toggle(container=None):
    """Nút chọn nền. Gọi 1 lần ở đầu sidebar (hoặc truyền container khác)."""
    (container or st).radio("Nền giao diện", OPTIONS, key="theme_mode", horizontal=True)


def plotly_template() -> str:
    return "plotly_dark" if is_dark() else "plotly_white"


def style_fig(fig):
    """Làm biểu đồ Plotly trong suốt để ăn theo nền trang."""
    fig.update_layout(template=plotly_template(), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def style_df(df):
    """Bảng st.dataframe: nền tối thì tô ô cùng màu nền trang (không đảo màu)."""
    if not is_dark():
        return df
    bg, txt = PALETTE["bg"][1], PALETTE["txt"][1]
    return df.style.set_properties(**{"background-color": bg, "color": txt})


def inject():
    """Chèn biến màu + ghi đè giao diện Streamlit. Gọi sau toggle(), trước khi vẽ nội dung."""
    i = 1 if is_dark() else 0
    vars_ = ";".join(f"--{k}:{v[i]}" for k, v in PALETTE.items())
    css = f":root{{{vars_};color-scheme:{mode()}}}"
    if is_dark():
        css += """
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--bg)!important;color:var(--txt)!important}
[data-testid="stHeader"]{background:var(--bg)!important}
[data-testid="stSidebar"],[data-testid="stSidebar"]>div{background:var(--bg2)!important}
.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp h5,.stApp h6,.stApp p,.stApp li,.stApp label,
.stApp [data-testid="stMarkdownContainer"],.stApp [data-testid="stWidgetLabel"] *,
.stApp [data-testid="stMetricValue"],.stApp [data-testid="stMetricLabel"] *{color:var(--txt)!important}
.stApp [data-testid="stCaptionContainer"],.stApp small{color:var(--muted)!important}
.stApp [data-baseweb="select"]>div,.stApp [data-baseweb="input"],.stApp [data-baseweb="base-input"],
.stApp input,.stApp textarea,.stApp [data-baseweb="textarea"]{background:var(--card2)!important;color:var(--txt)!important;border-color:var(--line)!important}
.stApp [data-baseweb="popover"] *,.stApp [role="listbox"],.stApp [role="option"]{background:var(--card)!important;color:var(--txt)!important}
.stApp [data-baseweb="tag"]{background:var(--line)!important}
.stApp .stButton>button,.stApp .stDownloadButton>button{background:var(--card2);color:var(--txt);border:1px solid var(--line)}
.stApp [data-testid="stExpander"],.stApp [data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--line)!important}
.stApp [data-testid="stAlert"]{background:var(--card2)!important;color:var(--txt)!important}
.stApp hr{border-color:var(--line)!important}
.stApp [data-testid="stDataFrame"]{background:var(--bg)!important}
"""
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
