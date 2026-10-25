"""Mega Navigation Bar (Top-Down) + Dark Theme cho Trạm Tín Hiệu Chứng Khoán VN."""
import streamlit as st

# Menu chính -> danh sách tab phụ (rỗng = không có sub-menu)
MENU = {
    "Vĩ mô": [],
    "Thị trường": ["Tổng quan", "Góc nhìn thị trường", "Nhận định VNINDEX", "Nhóm vốn hóa", "Dòng tiền khối ngoại", "Dòng tiền tự doanh", "Thanh khoản & độ rộng",
                   "Nhóm ngành", "Kết quả kinh doanh"],
    "Ngành": ["Tổng quan ngành", "Cảnh báo luân chuyển dòng tiền", "Vị thế cổ phiếu ngành", "Xếp hạng cổ phiếu", "Tác động ngành", "Định giá ngành"],
    "Cổ phiếu": ["Tổng quát", "Thông tin chung", "Định giá", "Cơ bản", "Biến động giá", "Phạm vi giá",
                 "Thanh khoản", "Chỉ báo kỹ thuật", "Đa khung D-W-M", "Ghi chú", "Tin tức"],
    "Bộ lọc & Backtest": ["Mua ngay", "Chờ mua", "Tăng mạnh", "Lọc tất cả CP", "Bộ lọc Realtime", "Giảm mạnh", "Cạn cung", "Đang phục hồi",
                          "Watchlist", "Cổ phiếu của tôi", "Danh sách cảnh báo",
                          "Bán / Chốt lời", "Backtest chiến lược"],
    "Biểu đồ": [],
}
DEFAULT_MAIN = "Thị trường"   # trang mở đầu khi vào app (muốn như cũ thì đổi thành "Bộ lọc & Backtest")
ICON = {"Vĩ mô": "🌐", "Thị trường": "🏛️", "Ngành": "🏭", "Cổ phiếu": "📊", "Bộ lọc & Backtest": "🔍", "Biểu đồ": "📈"}

# Mô tả nội dung từng tab phụ của mục "Thị trường" (hiển thị ở trang chờ cho tới khi có nội dung thật)
MARKET_DESC = {
    "Tổng quan": ["Xu hướng, độ rộng, dòng tiền, mức độ rủi ro", "Bản đồ sức mạnh ngành", "Số cổ phiếu phát tín hiệu MUA / CHỜ MUA"],
    "Góc nhìn thị trường": ["Bản tin nhận định thị trường theo ngày"],
    "Nhận định VNINDEX": ["Biểu đồ nến VNINDEX kèm khối lượng, đường MA", "Nhận định tự động: tin tức, dòng tiền, hành động"],
    "Nhóm vốn hóa": ["Tỷ số VNSmallcap/VN30 và VNSmallcap/VN-Index: dòng tiền chấp nhận rủi ro hay co về cổ phiếu lớn", "Nến VN30, VNMidcap, VNSmallcap", "Hiệu suất so sánh các nhóm"],
    "Dòng tiền khối ngoại": ["Mua/bán ròng", "Top cổ phiếu được mua/bán ròng", "Lũy kế 5–20 phiên"],
    "Dòng tiền tự doanh": ["Theo dõi giao dịch tự doanh (chỉ hiển thị khi có dữ liệu)"],
    "Thanh khoản & độ rộng": ["Giá trị giao dịch", "Số mã tăng / giảm"],
    "Nhóm ngành": ["Luân chuyển dòng tiền", "Sức mạnh ngành"],
    "Kết quả kinh doanh": ["Tổng hợp tình hình doanh nghiệp"],
}

DARK_CSS = """
<style>
/* ===== MEGA NAV BAR ===== */
.st-key-mega-nav{position:sticky;top:0;z-index:999;margin:0 -1rem 14px;background:var(--bg2);
  border-bottom:1px solid var(--line);padding:6px 1rem 0}
.st-key-mega-nav [data-testid="stVerticalBlock"]{gap:0}
.st-key-mega-nav [data-testid="stButtonGroup"]{gap:0}
.st-key-mega-nav button{background:transparent!important;border:none!important;border-radius:0!important;
  box-shadow:none!important;color:var(--muted)!important;font-weight:600;padding:10px 18px;
  border-bottom:2px solid transparent!important;transition:color .15s,background .15s,border-color .15s}
.st-key-mega-nav button:hover{color:var(--txt)!important;background:var(--line2)!important}
.st-key-mega-nav button[aria-checked="true"],.st-key-mega-nav button[aria-pressed="true"],
.st-key-mega-nav button[data-testid*="Active"]{color:var(--accent)!important;border-bottom-color:var(--accent)!important;background:transparent!important}
/* hàng sub-menu: trượt xuống mượt */
.st-key-nav-sub{background:var(--bg);margin:0 -1rem;padding:2px 1rem;border-top:1px solid var(--line);
  animation:subslide .22s ease-out}
.st-key-nav-sub button{font-size:13px;padding:8px 14px}
@keyframes subslide{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:none}}
</style>
"""


def _reset_sub():
    st.session_state["nav_sub"] = (MENU[st.session_state["nav_main"]] or [None])[0]


def goto(main: str, sub: str | None = None):
    """Chuyển trang bằng code (thay cho st.switch_page).

    Không được gán thẳng st.session_state["nav_main"] ở đây: lúc này widget segmented_control
    cùng key đã được tạo trong lượt chạy hiện tại (render_nav chạy đầu route) nên Streamlit báo
    StreamlitWidgetAlreadyInstantiatedError. Ta chỉ ghi "yêu cầu chuyển trang", rồi rerun;
    render_nav() ở đầu lượt sau sẽ áp dụng TRƯỚC khi tạo widget.
    """
    st.session_state["_nav_pending"] = (main, sub or (MENU[main] or [None])[0])
    st.rerun()


def render_nav():
    st.markdown(DARK_CSS, unsafe_allow_html=True)
    pending = st.session_state.pop("_nav_pending", None)  # áp dụng yêu cầu goto() trước khi tạo widget
    if pending:
        st.session_state["nav_main"], st.session_state["nav_sub"] = pending
    st.session_state.setdefault("nav_main", DEFAULT_MAIN)
    if st.session_state.get("nav_main") not in MENU:
        st.session_state["nav_main"] = DEFAULT_MAIN
    st.session_state.setdefault("nav_sub", (MENU[st.session_state["nav_main"]] or [None])[0])

    with st.container(key="mega-nav"):
        main = st.segmented_control("Menu", list(MENU), key="nav_main", label_visibility="collapsed",
                                    format_func=lambda m: f"{ICON[m]} {m}", on_change=_reset_sub)
        if main is None:  # bấm lại mục đang chọn -> giữ nguyên mục vừa xem
            main = st.session_state.get("_nav_last_main", DEFAULT_MAIN)
            st.session_state["nav_main"] = main
        st.session_state["_nav_last_main"] = main
        subs = MENU[main]
        sub = None
        if subs:
            with st.container(key="nav-sub"):
                if st.session_state.get("nav_sub") not in subs:
                    st.session_state["nav_sub"] = subs[0]
                sub = st.segmented_control("Tab phụ", subs, key="nav_sub", label_visibility="collapsed")
                sub = sub or subs[0]
    return main, sub


def placeholder(title: str, bullets: list[str] | None = None):
    st.title(title)
    st.info("Mục này đã có chỗ trong thanh điều hướng, nội dung đang được xây dựng.")
    for b in bullets or []:
        st.markdown(f"- {b}")
