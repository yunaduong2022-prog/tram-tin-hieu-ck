"""Giao diện CỐ ĐỊNH nền tối xanh rêu (theo ảnh đại diện Min Trading). Không còn nút chọn Sáng/Tối.
Giữ nguyên tên các hàm cũ (toggle, mode, is_dark, inject, style_fig, style_df, plotly_template)
để app.py / stock_tabs.py không phải sửa."""
import streamlit as st

# Bảng màu duy nhất: tên biến -> mã màu
PALETTE = {
    "bg":      "#0E1C18",   # nền trang
    "bg2":     "#14261F",   # nền sidebar / thanh nav / ô phụ
    "card":    "#162B24",   # nền thẻ
    "card2":   "#1B332B",   # nền phụ trong thẻ
    "line":    "#26433A",   # viền
    "line2":   "#1F382F",   # viền mờ
    "txt":     "#E6EFE9",   # chữ chính
    "txt2":    "#F3F8F5",   # chữ đậm (mã CP, số liệu)
    "muted":   "#8FA89D",   # chữ phụ
    "accent":  "#2DD4A7",
    "red":     "#FF6B81",
    "green":   "#2DD4A7",
    "amber":   "#F5B942",
    "gold":    "#E0B565",   # điểm nhấn thương hiệu (màu tóc)
    "cream":   "#FCF8DF",   # viền kem của ảnh đại diện
    "hero":    "#1A3B32",   # nền thanh thương hiệu
    "tag-red-bg":   "#3A1A22",
    "tag-green-bg": "#0F2E26",
    "tag-amber-bg": "#3A2E12",
    "tag-gray-bg":  "#262D38",
    "tag-green-fg": "#5EE6C0",
    "tag-amber-fg": "#F5B942",
    "tag-gray-fg":  "#B1BAC4",
    "bar":     "#26433A",
    "shadow":  "rgba(0,0,0,.5)",
}


def mode() -> str:
    return "dark"


def is_dark() -> bool:
    return True


def toggle(container=None):
    """Không còn nút chọn nền (giữ lại hàm rỗng để code cũ gọi không lỗi)."""
    return None


def plotly_template() -> str:
    return "plotly_dark"


def style_fig(fig):
    """Làm biểu đồ Plotly trong suốt để ăn theo nền trang."""
    fig.update_layout(template=plotly_template(), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    return fig


def style_df(df):
    """Bảng st.dataframe: tô ô cùng màu nền trang."""
    return df.style.set_properties(**{"background-color": PALETTE["bg"], "color": PALETTE["txt"]})


def inject():
    """Chèn biến màu + ghi đè giao diện Streamlit. Gọi trước khi vẽ nội dung."""
    vars_ = ";".join(f"--{k}:{v}" for k, v in PALETTE.items())
    css = f":root{{{vars_};color-scheme:dark}}" + """
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
.stApp .stButton>button:hover{border-color:var(--accent);color:var(--accent)}
.stApp [data-testid="stExpander"],.stApp [data-testid="stVerticalBlockBorderWrapper"]{border-color:var(--line)!important}
.stApp [data-testid="stAlert"]{background:var(--card2)!important;color:var(--txt)!important}
.stApp hr{border-color:var(--line)!important}
.stApp [data-testid="stDataFrame"]{background:var(--bg)!important}
"""
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
