import glob
import html as htmllib
import inspect
import json
import math
import os
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import engine as E
import fund_guard as FG
import ichimoku_dual as IDU
import setups as SU
import supertrend as SPT
import hull_suite as HUL
import watchlist as WL
import wyckoff as WYK
import nav as NAV
import theme as TH
import brand as BR
import stock_tabs as ST
import mtf_levels as ML
import waiting_buy as WB
import action_summary as AS
import rsi_divergence as DV
import foreign_flow as FF
import sector_dashboard as SD
import sector_ranking as SR
import sector_rotation as SRT
import market_view as MV
import vnindex_view as VV
import cap_groups as CG
import market_overview as MO
import my_watchlist as MW
import my_portfolio as MP
import sell_card
import dry_supply as DS
import stock_map as SM
import crosshair as CH
import draw_tools as DT

st.set_page_config(page_title="Trạm Tín Hiệu | Min Trading", page_icon=BR.page_icon(), layout="wide")

TH.inject()
st.markdown(WYK.CSS, unsafe_allow_html=True)      # CSS khối ghi chú Wyckoff trong thẻ (wy-*)

st.markdown("""
<style>
 .ticket-buy{background:var(--tag-green-bg);border-left:5px solid var(--accent);padding:12px 15px;border-radius:8px;color:var(--tag-green-fg);margin-bottom:12px}
 .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:14px}
 .ct{font-weight:700;font-size:14px;margin-bottom:8px;color:var(--txt)}
 .row{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:3px 0;font-size:13px}
 .muted{color:var(--muted);font-size:12px;line-height:1.5}
 .big{font-size:24px;font-weight:800;line-height:1.2;margin:2px 0 6px}
 .mtf-top{display:flex;justify-content:space-between;align-items:stretch;gap:12px}
 .mtf-code{display:flex;align-items:center;font-size:56px;font-weight:800;line-height:1;letter-spacing:-.5px;color:var(--txt2)}
 .mtf-right{display:flex;align-items:center;justify-content:flex-end;gap:14px;flex-wrap:wrap}
 .mtf-px{display:flex;flex-direction:column;justify-content:center;line-height:1.2;text-align:right}
 .mtf-px b{font-size:30px;font-weight:800}.mtf-px span{font-size:12.5px;font-weight:600}
 .c-red{color:var(--red)}.c-green{color:var(--green)}.c-amber{color:var(--amber)}.c-gray{color:var(--muted)}
 .tag{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
 .tag-red{background:var(--tag-red-bg);color:var(--red)}.tag-green{background:var(--tag-green-bg);color:var(--tag-green-fg)}
 .tag-amber{background:var(--tag-amber-bg);color:var(--tag-amber-fg)}.tag-gray{background:var(--tag-gray-bg);color:var(--tag-gray-fg)}
 .box{background:var(--bg2);border-radius:8px;padding:8px 12px;margin:8px 0}
 .bar{height:7px;background:var(--bar);border-radius:99px;overflow:hidden;margin:6px 0 4px}
 .bar>div{height:100%;border-radius:99px}.bg-red{background:var(--red)}.bg-green{background:var(--green)}.bg-gray{background:#9CA3AF}
 .chip{display:inline-block;min-width:42px;text-align:center;padding:2px 6px;border-radius:6px;font-size:12px;font-weight:700;margin-right:8px}
 .chip-red{background:var(--tag-red-bg);color:var(--red)}.chip-green{background:var(--tag-green-bg);color:var(--tag-green-fg)}.chip-gray{background:var(--tag-gray-bg);color:var(--tag-gray-fg)}
 .item{padding:6px 0;border-bottom:1px solid var(--line2);font-size:13px}
 .multi-tf-title{font-weight:700;font-size:12px;color:var(--txt);margin:10px 0 6px}
 .multi-tf-container{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin:6px 0}
 .tf-subcard{background:var(--card2);border:1px solid var(--line);border-radius:6px;padding:8px 10px;min-width:0}
 .tf-title{font-size:11.5px;font-weight:700;text-transform:uppercase;color:var(--txt);border-bottom:1px solid var(--line);padding-bottom:3px;margin-bottom:5px;display:flex;justify-content:space-between;gap:4px}
 .tf-info{font-size:11px;color:var(--muted);margin-bottom:3px}
 .tf-info b{color:var(--txt2)}
 .tf-comment{font-size:10.5px;color:var(--txt);font-style:italic;background:var(--bg2);padding:3px 6px;border-radius:4px;margin-top:4px}
 .strategy-box{background:var(--tag-green-bg);border:1px solid var(--line);border-radius:6px;padding:8px 12px;font-size:11.5px;margin-top:8px;color:var(--tag-green-fg);line-height:1.6}
 .strategy-box.warn{background:var(--tag-amber-bg);color:var(--tag-amber-fg)}
 .strategy-box.bad{background:var(--tag-red-bg);color:var(--red)}
</style>
""", unsafe_allow_html=True)

st.markdown(f"<style>{DV.css()}</style>", unsafe_allow_html=True)   # cảnh báo phân kỳ RSI trong thẻ

st.markdown("""
<style>
/* Lưới hiển thị các thẻ cổ phiếu */
.stock-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-top:16px}
/* Thẻ cổ phiếu */
.stock-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:0 2px 6px var(--shadow);
 transition:transform .15s ease,box-shadow .15s ease;display:flex;flex-direction:column;justify-content:space-between;height:100%}
.stock-card:hover{transform:translateY(-2px);box-shadow:0 6px 16px var(--shadow);border-color:var(--muted)}
/* Header thẻ */
.stock-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.stock-code{font-size:22px;font-weight:800;color:var(--txt2);line-height:1}
.stock-company{font-size:11px;color:var(--muted);margin-top:4px;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}
/* Giá & biến động */
.price-box{display:flex;align-items:baseline;gap:10px;margin:10px 0;background:var(--card2);padding:8px 12px;border-radius:8px}
.price-val{font-size:20px;font-weight:800}
.price-chg{font-size:13px;font-weight:700}
/* Chỉ số cơ bản (lưới 2x2) */
.metrics-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;font-size:12px;color:var(--muted);margin-bottom:12px}
.metric-item b{color:var(--txt2)}
.ma-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:2px 0 10px}
.ma-item{background:var(--card2);border:1px solid var(--line2);border-radius:7px;padding:6px 7px;min-width:0}
.ma-label{font-size:10px;color:var(--muted);font-weight:700;letter-spacing:.2px}
.ma-value{font-size:13px;font-weight:800;color:var(--txt2);margin:2px 0;white-space:nowrap}
.ma-state{font-size:10px;font-weight:650;line-height:1.25;overflow-wrap:anywhere}
.ma-up{color:var(--green)}.ma-down{color:var(--red)}.ma-unknown{color:var(--muted)}
.ma-overview{margin:-3px 0 10px;padding:2px 0}
.ma-overview .ma-pills{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center}
.ma-overview .ma-pill{display:inline-block;border-radius:999px;padding:4px 12px;font-size:13px;font-weight:700;line-height:1.3}
.ma-overview .ma-pill.ma-positive{background:#DDF1EB;color:#08785E}
.ma-overview .ma-pill.ma-caution{background:#FDE6D6;color:#C2570C}
.ma-overview .ma-pill.ma-negative{background:#FCE4E8;color:#C02645}
.ma-overview .ma-pill.ma-neutral{background:#EEF1F5;color:#626B78}
.ma-overview .ma-note{margin-top:7px;font-size:13px;font-weight:500;color:var(--muted);line-height:1.4}
.stock-card.in-box{border:none;box-shadow:none;padding:2px 2px 0;background:transparent;transform:none}
.stock-title{display:flex;align-items:center;flex-wrap:wrap;gap:8px 10px}
.stock-card .price-box{margin:8px 0 10px}
.stock-card .metrics-grid{border-top:1px solid var(--line2);padding-top:10px;margin-bottom:10px}
.stock-card .tag-container{margin-bottom:6px}
/* Nhãn dự báo & chip */
.badge-forecast{padding:4px 8px;border-radius:6px;font-size:11px;font-weight:700;white-space:nowrap}
.tag-container{display:flex;flex-wrap:wrap;gap:4px;padding-top:10px;border-top:1px solid var(--line2)}
.tag-chip{background:var(--tag-green-bg);color:var(--tag-green-fg);font-size:10.5px;font-weight:600;padding:2px 8px;border-radius:12px}
/* Thẻ thống kê khu vực Kết quả lọc */
.kq-stat{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px 18px;box-shadow:0 2px 8px var(--shadow);height:100%}
.kq-l{font-size:11px;font-weight:700;letter-spacing:.5px;color:var(--muted);text-transform:uppercase}
.kq-v{font-size:30px;font-weight:800;color:var(--txt2);line-height:1.2;margin:4px 0 2px}
.kq-v.up{color:var(--green)}
.kq-s{font-size:12px;color:var(--muted)}
</style>
""", unsafe_allow_html=True)

_STRETCH = ({"width": "stretch"} if "width" in inspect.signature(st.plotly_chart).parameters
            else {"use_container_width": True})
_STRETCH_DF = ({"width": "stretch"} if "width" in inspect.signature(st.dataframe).parameters
               else {"use_container_width": True})
TF_LABEL = {"D": "Ngày (D)", "W": "Tuần (W)", "M": "Tháng (M)"}
BARS_SHOWN = {"D": 200, "W": 156, "M": 120}
LAYER_OPTS = ["Dự báo", "Tín hiệu quá khứ", "Dual Ichimoku", "Vùng giá", "Bollinger",
              "Wyckoff", "EMA 50/200", "Supertrend", "Hull Suite", "Khối lượng", "VNINDEX", "RS vs VNINDEX", "MACD", "RSI", "StochRSI"]
LAYER_DEFAULT = ["Dự báo", "Dual Ichimoku", "Supertrend", "Khối lượng", "RS vs VNINDEX", "MACD", "RSI", "StochRSI"]      # các lớp bật sẵn; lớp khác bấm vào mới hiện


# ------------------------------------------------------------------ DỮ LIỆU
@st.cache_data(show_spinner="Đang đọc file Excel...")
def load_raw(source) -> pd.DataFrame:
    return E.clean_raw(pd.read_excel(source, sheet_name=0))


EOD_CSV, EOD_META = "data/eod_prices.csv", "data/eod_meta.json"
MODE_EOD, MODE_XLS, MODE_LIVE = "Cuối phiên (tự cập nhật)", "Excel CafeF", "Vnstock tự động"


@st.cache_data(show_spinner="Đang đọc dữ liệu cuối phiên...")
def load_eod(path: str, mtime: float) -> pd.DataFrame:
    return E.clean_raw(pd.read_csv(path, dtype={"Mã": str}))


def read_eod_meta() -> dict:
    try:
        with open(EOD_META, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


@st.cache_data(show_spinner="Đang gộp nến Ngày/Tuần/Tháng và tính chỉ báo...")
def build_frames(raw: pd.DataFrame, ver: str = "") -> dict:
    parts = {"D": [], "W": [], "M": []}
    for _, g in raw.groupby("Mã"):
        base = g[["Mã", "Ngày"] + E.NUMERIC_COLS]
        for tf in parts:
            parts[tf].append(E.add_indicators(E.resample_ohlcv(base, tf)))
    frames = {tf: pd.concat(p, ignore_index=True) for tf, p in parts.items()}
    frames["D"] = E.mask_chg_gaps(frames["D"])     # % thay đổi chỉ tính so với phiên kề trước, thiếu phiên thì hiện "—"
    return frames


@st.cache_data(show_spinner="Đang phân tích...")
def analyze_cached(_frames: dict, code: str, tf: str, key: str) -> dict:
    g = _frames[tf]
    return E.analyze_frame(g[g["Mã"] == code], tf)


# ------------------------------------------------------------------ NGUỒN DỮ LIỆU
import realtime_data as RD

@st.cache_data(ttl=3600, show_spinner="Đang tải lịch sử OHLCV từ Vnstock...")
def load_vnstock_history(symbols_tuple: tuple[str, ...], start_date: str) -> pd.DataFrame:
    return RD.fetch_history(list(symbols_tuple), start=start_date)

@st.cache_data(ttl=10, show_spinner=False)
def load_vnstock_quotes(symbols_tuple: tuple[str, ...]):
    return RD.fetch_quote_board(list(symbols_tuple))

@st.cache_data(ttl=43200, show_spinner=False)
def load_vn30():
    return WL.fetch_vn30()

@st.cache_data(show_spinner="Đang nhận diện cấu trúc Wyckoff cho cả rổ...")
def wyckoff_table(_df: pd.DataFrame, key: str) -> dict:
    out = {}
    for code, g in _df.groupby("Mã"):
        try:
            w = WYK.analyze(g.reset_index(drop=True))
        except Exception:
            w = None
        out[code] = WYK.compact(w)
    return out

VN30_LIST, VN30_SRC = load_vn30()
MEMBER = WL.membership(VN30_LIST)

HAS_EOD = os.path.exists(EOD_CSV)

with st.sidebar:
    st.caption(f"Engine {E.ENGINE_VERSION}")
    st.header("📂 Dữ liệu")
    data_mode = st.radio("Nguồn dữ liệu", [MODE_EOD, MODE_XLS, MODE_LIVE], index=0 if HAS_EOD else 1,
                         help="Cuối phiên: file data/eod_prices.csv do lịch tự động cập nhật sau giờ đóng cửa (khuyến nghị). "
                              "Vnstock tự động: gọi nguồn liên tục khi mở app, dễ bị giới hạn tần suất.")
    source = None
    if data_mode == MODE_EOD:
        _meta = read_eod_meta()
        if HAS_EOD:
            st.caption("Dữ liệu cuối phiên, tự cập nhật sau 15:45 mỗi ngày giao dịch (GitHub Actions)."
                       + (f" Cập nhật lần cuối: {_meta['updated_at']}." if _meta.get("updated_at") else "")
                       + (f" Nguồn: {', '.join(_meta['sources'])}." if _meta.get("sources") else ""))
            if _meta.get("failed") or _meta.get("stopped"):
                st.warning(f"Lần chạy gần nhất chưa lấy đủ: {len(_meta.get('failed', []))} mã lỗi"
                           + (f"; dừng vì: {_meta['stopped']}" if _meta.get("stopped") else "") + ".")
            if _meta.get("adjusted"):
                st.caption("Đã tải lại lịch sử do điều chỉnh giá: " + ", ".join(_meta["adjusted"][:12]))
        else:
            st.info("Chưa có file data/eod_prices.csv. Chạy workflow ở tab Actions trên GitHub (xem README).")
    if data_mode == MODE_XLS:
        uploaded = st.file_uploader("Tải file Excel CafeF (.xlsx)", type=["xlsx"])
        repo_files = sorted(glob.glob("data/*.xlsx"))
        source = uploaded
        if source is None and repo_files:
            source = st.selectbox("Hoặc dùng file trong repo", repo_files, index=len(repo_files) - 1)
    if data_mode == MODE_LIVE:
        picked = st.multiselect("Rổ mã", WL.group_names(), default=WL.DEFAULT_PICK,
                                help="VN30 lấy từ nguồn dữ liệu; các nhóm ngành sửa trong watchlist.py. Một mã có thể thuộc nhiều nhóm.")
        extra_text = st.text_input("Mã thêm tay (phân cách bằng dấu phẩy)", "",
                                   help="Thêm các mã ngoài rổ đã chọn, ví dụ NTP,BVH.")
        extras = [x.strip().upper() for x in extra_text.split(",") if x.strip()]
        live_symbols = tuple(dict.fromkeys(WL.symbols_for(picked, VN30_LIST) + extras))
        st.caption(f"VN30: {len(VN30_LIST)} mã · nguồn: {VN30_SRC}")
        live_start = st.date_input("Lấy lịch sử từ ngày", value=pd.Timestamp("2024-01-01").date())
        refresh_seconds = st.select_slider("Chu kỳ làm mới bảng giá", options=[5, 10, 15, 30, 60], value=15,
                                           format_func=lambda x: f"{x} giây")
        st.caption(f"Đang chọn {len(live_symbols)} mã. Mỗi mã cần một yêu cầu lịch sử (cache 60 phút) nên lần tải đầu với rổ lớn có thể mất vài phút hoặc bị nguồn giới hạn tần suất; có thể chọn bớt nhóm để thử trước.")
        try:
            from streamlit_autorefresh import st_autorefresh
            st_autorefresh(interval=int(refresh_seconds * 1000), key="market_autorefresh")
        except ImportError:
            st.warning("Chưa có streamlit-autorefresh. Cài dependencies trong requirements.txt để tự làm mới giao diện.")

if data_mode == MODE_EOD:
    if not HAS_EOD:
        st.title("📈 Trạm Tín Hiệu Chứng Khoán Việt Nam")
        st.info("Chưa có dữ liệu cuối phiên. Vào GitHub → tab **Actions** → **Cập nhật dữ liệu cuối phiên** → "
                "**Run workflow** (chọn *Tải lại toàn bộ lịch sử*) để tạo file `data/eod_prices.csv`. "
                "Hoặc chọn **Excel CafeF** ở thanh bên.")
        st.stop()
    try:
        raw = load_eod(EOD_CSV, os.path.getmtime(EOD_CSV))
    except Exception as e:
        st.error(f"Không đọc được data/eod_prices.csv: {e}")
        st.stop()
elif data_mode == MODE_LIVE:
    if not live_symbols:
        st.warning("Nhập ít nhất một mã cổ phiếu.")
        st.stop()
    try:
        raw = load_vnstock_history(live_symbols, live_start.isoformat())
        quote_df, quote_source = load_vnstock_quotes(live_symbols)
        raw = RD.apply_live_quotes(raw, quote_df)
        with st.sidebar:
            st.caption(f"Nguồn bảng giá: {quote_source} · số mã trả về: {len(quote_df)}")
        errors = raw.attrs.get("provider_errors", [])
        if errors:
            st.warning("Một số mã không lấy được lịch sử: " + " | ".join(errors[:4]))
    except Exception as e:
        st.error(f"Không kết nối được Vnstock: {e}")
        st.info("Kiểm tra internet, phiên bản vnstock và hạn mức/nguồn được cấp quyền. Bạn vẫn có thể chuyển về Excel CafeF.")
        st.stop()
else:
    if source is None:
        st.title("📈 Trạm Tín Hiệu Chứng Khoán Việt Nam")
        st.info("👈 Hãy tải file Excel lên, đặt file `.xlsx` trong thư mục `data/`, hoặc chọn **Vnstock tự động** ở thanh bên.")
        st.stop()
    try:
        raw = load_raw(source)
    except Exception as e:
        st.error(f"Lỗi khi đọc hoặc xử lý dữ liệu: {e}")
        st.stop()

try:
    raw = E.clean_raw(raw)
    frames = build_frames(raw, E.ENGINE_VERSION)
except Exception as e:
    st.error(f"Lỗi khi xử lý dữ liệu: {e}")
    st.stop()

df = frames["D"]
latest_date = df["Ngày"].max()
n_sessions = int(df.groupby("Mã").size().min())
latest_df = df[df["Ngày"] == latest_date]
DATA_KEY = f"{latest_date:%Y%m%d}-{len(df)}"
WY_KEY = f"{DATA_KEY}-{float(latest_df['Giá đóng cửa'].sum()):.2f}"
WY_TABLE = wyckoff_table(df, WY_KEY)
if data_mode == "Vnstock tự động":
    st.caption(f"🟢 Chế độ tự động · lịch sử OHLCV được cache 60 phút · bảng giá polling mỗi {refresh_seconds} giây. Thời điểm chạy: {pd.Timestamp.now(tz='Asia/Ho_Chi_Minh'):%H:%M:%S %d/%m/%Y} (giờ VN). Giá đang chạy có thể chưa đồng bộ đầy đủ với OHLCV.")
elif data_mode == MODE_EOD:
    _stale = (pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None).normalize() - latest_date).days
    st.caption(f"🗓️ Dữ liệu cuối phiên đến ngày {latest_date:%d/%m/%Y}"
               + (" · ⚠ có vẻ chưa cập nhật phiên gần nhất, kiểm tra tab Actions trên GitHub" if _stale > 4 else ""))

# ------------------------------------------------------------------ BẢNG THEO DÕI
@st.cache_data(show_spinner=False)
def market_cached(_raw: pd.DataFrame, key: str):
    return E.market_series(_raw)


@st.cache_data(show_spinner="Đang tính Score, RS, MACD/Fisher, MA...")
def screener_cached(_frames: dict, mkt: pd.Series, key: str) -> pd.DataFrame:
    return E.build_screener(_frames, mkt)


mkt, mkt_src = market_cached(raw, WY_KEY)
res_df = screener_cached(frames, mkt, WY_KEY + "|" + E.ENGINE_VERSION).copy()
res_df["Nhóm"] = res_df["Mã"].map(lambda c_: ", ".join(MEMBER.get(c_, [])) or "Khác")
res_df["_wy"] = res_df["Mã"].map(WY_TABLE.get)
res_df["Wyckoff"] = res_df["_wy"].map(WYK.label)

# VNINDEX không nằm trong bảng lọc cổ phiếu (res_df) nhưng vẫn xem được ở trang Cổ phiếu / Đa khung: tính riêng một dòng cho chỉ số
INDEX_LIST = sorted({str(c_) for c_ in df["Mã"].unique() if str(c_).upper() in E.INDEX_CODES} - set(res_df["Mã"]))


@st.cache_data(show_spinner=False)
def index_row_cached(_frames: dict, _mkt: pd.Series, code: str, key: str):
    sub_ = {tf_: g_[g_["Mã"] == code] for tf_, g_ in _frames.items()}
    r_ = E.build_screener(sub_, _mkt, skip_index=False)
    return r_.iloc[0] if len(r_) else None


def stock_row(code):
    """Dòng thông tin của mã: cổ phiếu lấy từ bảng lọc, chỉ số (VNINDEX) tính riêng. Không có dữ liệu thì trả None."""
    r_ = res_df[res_df["Mã"] == code]
    if len(r_):
        return r_.iloc[0]
    return index_row_cached(frames, mkt, code, WY_KEY + "|" + E.ENGINE_VERSION) if code in INDEX_LIST else None


def _wy_note(code, compact_view: bool = False) -> str:
    """Khối Wyckoff (pha A–E + chú thích pha) dùng chung cho mọi thẻ cổ phiếu."""
    return WYK.note_html(WY_TABLE.get(str(code)), compact_view)

def _lean_html(code) -> str:
    """Dòng 'DỰ BÁO NGHIÊNG TĂNG / GIẢM' dùng chung cho mọi thẻ: cùng phép tính với biểu đồ (khung Ngày; |độ nghiêng| >= 1.0)."""
    try:
        a = analyze_cached(frames, str(code), "D", DATA_KEY)
        d = a.get("dir", 0) if a.get("enough") else 0
    except Exception:
        d = 0
    if d > 0:
        return ('<div class="lean-line" style="margin:6px 0 2px;font-size:12px;font-weight:800;letter-spacing:.3px;color:#08785E">'
                '▲ DỰ BÁO NGHIÊNG TĂNG</div>')
    if d < 0:
        return ('<div class="lean-line" style="margin:6px 0 2px;font-size:12px;font-weight:800;letter-spacing:.3px;color:#C02645">'
                '▼ DỰ BÁO NGHIÊNG GIẢM</div>')
    return ""


@st.cache_data(show_spinner=False)
def _wb_rows(key: str) -> dict:
    """Trạng thái chờ mua / lý do / vùng mua của từng mã (từ bảng Chờ mua), dùng cho khối Tóm tắt nhanh."""
    t = _wb_table()
    cols = [c for c in ("Trạng thái", "Lý do", "Vùng mua từ", "Vùng mua đến") if c in t.columns]
    return t.drop_duplicates("Mã", keep="first").set_index("Mã")[cols].to_dict("index")


def _action_html(code) -> str:
    """Khối 'Tóm tắt nhanh · Kết luận hành động' cuối thẻ: gom các tag của thẻ (MA, trạng thái, Dự báo, phân kỳ RSI, Wyckoff,
    hỗ trợ - kháng cự) thành hành động cho 3 vị thế: có cổ phiếu / cầm tiền mặt / đang margin. Quy tắc nằm ở action_summary.py."""
    try:
        code = str(code)
        g = df[df["Mã"] == code].sort_values("Ngày")
        c = pd.to_numeric(g["Giá đóng cửa"], errors="coerce")
        if c.empty:
            return ""
        ma = {n: (float(c.rolling(n).mean().iloc[-1]) if len(c) >= n else None) for n in (20, 50, 200)}
        w = _wb_rows(WY_KEY + "|" + E.ENGINE_VERSION + "|wb12").get(code, {})
        state, reason = str(w.get("Trạng thái", "")), str(w.get("Lý do", ""))
        a = analyze_cached(frames, code, "D", DATA_KEY)
        d = mtf_cached(frames, code, DATA_KEY)["D"]
        # ngày ở chân thẻ: ngày cập nhật dữ liệu; chế độ Vnstock trực tiếp thì nến cuối có thể là phiên đang giao dịch
        _date = f"Phiên ngày {pd.Timestamp(g['Ngày'].iloc[-1]):%d/%m/%Y} (đang cập nhật)" if data_mode == MODE_LIVE else latest_date
        ctx = dict(code=code, date=_date, close=float(c.iloc[-1]), ma20=ma[20], ma50=ma[50], ma200=ma[200],
                   label=WB.status_tag(state, reason)[0] if state else "", state=state, reason=reason,
                   lean=(a.get("dir", 0) if a.get("enough") else 0),
                   div=divergence_cached(frames, code, DATA_KEY + "|" + E.ENGINE_VERSION + "|dv1"),
                   wy=WY_TABLE.get(code), sup=d.get("sup") if d.get("ok") else None, res=d.get("res") if d.get("ok") else None,
                   zone=(w.get("Vùng mua từ"), w.get("Vùng mua đến")) if state in WB.STATE_GROUP and WB.STATE_GROUP[state] in WB.BUY_GROUPS else None)
        return AS.html(ctx)
    except Exception:
        return ""


TABLE_COLS = ["ST", "Mã", "Nhóm", "Giá", "Score", "RS vs VNI", "% Biên độ", "Position %", "Zone", "Lực mua/bán",
              "Giá tăng/giảm", "Vol vs tháng trước", "Vol/Avg10", "Nhận xét", "MACD D", "MACD W", "Fisher D",
              "Fisher W", "MA align", "Wyckoff", "Cảnh báo", "Lý do cảnh báo"]
ALERT_OPTS = ["MUA", "BÁN", "Crossover", "Đáy KT", "Không có"]
FLOW_OPTS = {"Vol tăng 3 phiên liên tiếp": "VolStep", "Dòng tiền sớm (gom ngầm)": "EarlyFlow",
             "Cạn cung": "DryUp", "NR4 (biên độ hẹp nhất 4 phiên)": "NR4", "NR7 (biên độ hẹp nhất 7 phiên)": "NR7"}
MA_OPTS = ["Tất cả", "Ngắn hạn - TĂNG (MA10 > MA20)", "Trung hạn - TĂNG (MA20 > MA50 > MA100)",
           "Dài hạn - TĂNG (MA50 > MA100 > MA200)"]
MA_COL = {MA_OPTS[1]: "Trend_NganHan", MA_OPTS[2]: "Trend_TrungHan", MA_OPTS[3]: "Trend_DaiHan"}
WY_OPTS = ["Tích lũy", "Phân phối", "Pha C", "Pha D", "Pha E"]


def header():
    st.caption(f"Dữ liệu đến ngày **{latest_date:%d/%m/%Y}** · {df['Mã'].nunique()} mã · "
               f"tối thiểu {n_sessions} phiên/mã · RS so với {mkt_src}")
    if n_sessions < 60:
        st.warning("Dữ liệu dưới 60 phiên/mã: Ichimoku, MA50/MA200, khung Tuần/Tháng và backtest sẽ thiếu hoặc không đáng tin.")
    elif n_sessions < 250:
        st.caption("ℹ️ Dưới 250 phiên/mã: 'đỉnh/đáy 52 tuần', MA200 và cấu trúc dài hạn chỉ tính trên phần dữ liệu có sẵn.")


def wy_match(w, sel):
    if not w:
        return False
    return any((s == "Tích lũy" and w["kind"] == "acc") or (s == "Phân phối" and w["kind"] == "dist")
               or (s.startswith("Pha ") and w["phase"] == s[-1]) for s in sel)


def filter_panel():
    with st.expander("🔍 Bộ lọc nâng cao", expanded=True):
        a1, a2, a3, a4 = st.columns(4)
        alerts = a1.multiselect("Cảnh báo / Tín hiệu", ALERT_OPTS, default=ALERT_OPTS,
                                help="MUA/BÁN: giá + khối lượng · Crossover: MACD/Fisher vừa cắt lên (3 phiên) · "
                                     "Đáy KT: WaveTrend quá bán + RS ổn định")
        zones = a2.multiselect("Zone", ["High", "Mid-Sell", "Low"], default=["High", "Mid-Sell", "Low"])
        min_score = a3.slider("Score tối thiểu (0-10)", 0.0, 10.0, 0.0, 0.5, help="≥ 5 = trung bình khá trở lên")
        min_rs = a4.slider("RS vs VNI tối thiểu", 0.80, 1.50, 0.80, 0.01,
                           help="RS = hiệu suất 20 phiên của mã / của thị trường. Đặt 1.00 để chỉ lấy mã mạnh hơn thị trường")
        b1, b2, b3, b4 = st.columns(4)
        min_vol = b1.slider("Vol/Avg10 tối thiểu", 0.0, 5.0, 0.0, 0.1, help="Ví dụ 1.2 = bắt đầu có dòng tiền tăng")
        align = b2.selectbox("MA Alignment (MA10>20>50>100>200)", ["Tất cả", "Đã align", "Chưa align"])
        ma_trend = b3.selectbox("Khung cấu trúc - MA", MA_OPTS)
        pos52 = b4.selectbox("Vị trí giá so với 52 tuần", ["Tất cả", "Gần Đỉnh 52 tuần (≤ 5%)", "Gần Đáy 52 tuần (≤ 10%)"])
        c1, c2, c3, c4 = st.columns(4)
        all_groups = [g_ for g_ in WL.group_names() if g_ != WL.OLD] + ["Khác"]
        groups = c1.multiselect("Nhóm ngành", all_groups, default=[], placeholder="Tất cả nhóm",
                                help="Một mã thuộc nhiều nhóm sẽ hiện nếu khớp bất kỳ nhóm nào được chọn.")
        wy = c2.multiselect("Wyckoff (pha / cấu trúc)", WY_OPTS, default=[], placeholder="Tất cả",
                            help="Chọn nhiều = khớp bất kỳ mục nào. Pha C/D/E = đã có Spring/UT hoặc SOS/SOW.")
        flow = c3.multiselect("Dòng tiền sớm & nén biến động", list(FLOW_OPTS), default=[],
                              help="Chọn nhiều mục = phải thoả tất cả")
        search = c4.text_input("Tìm mã", "").upper()
        above200 = c4.checkbox("Chỉ lấy mã nằm trên MA200")
    return dict(alerts=alerts, zones=zones, min_score=min_score, min_rs=min_rs, min_vol=min_vol, align=align,
                ma_trend=ma_trend, pos52=pos52, groups=groups, wy=wy, flow=flow, search=search, above200=above200)


def apply_filters(d: pd.DataFrame, p: dict) -> pd.DataFrame:
    f = d[d["Zone"].isin(p["zones"])]
    sel = set(p["alerts"])
    f = f[f["alerts"].apply(lambda a: bool(sel & set(a)) if a else "Không có" in sel).astype(bool)]
    if p["groups"]:
        f = f[f["Nhóm"].apply(lambda t_: any(g_ in [x.strip() for x in t_.split(",")] for g_ in p["groups"])).astype(bool)]
    if p["wy"]:
        f = f[f["_wy"].apply(lambda w: wy_match(w, p["wy"])).astype(bool)]
    if p["min_score"] > 0:
        f = f[f["Score"] >= p["min_score"]]
    if p["min_rs"] > 0.80:
        f = f[f["RS20"] >= p["min_rs"]]
    if p["min_vol"] > 0:
        f = f[f["Vol/Avg10"].fillna(0) >= p["min_vol"]]
    if p["align"] != "Tất cả":
        f = f[f["MA align"] == p["align"]]
    if p["ma_trend"] != "Tất cả":
        f = f[f[MA_COL[p["ma_trend"]]] == "TĂNG"]
    if p["pos52"].startswith("Gần Đỉnh"):
        f = f[f["Dist_High_52W"] <= 5.0]
    elif p["pos52"].startswith("Gần Đáy"):
        f = f[f["Dist_Low_52W"] <= 10.0]
    if p["above200"]:
        f = f[f["Giá"] > f["MA200"]]
    for k in p["flow"]:
        f = f[f[FLOW_OPTS[k]]]
    if p["search"]:
        f = f[f["Mã"].str.contains(p["search"], regex=False)]
    return f


def style_table(f: pd.DataFrame):
    zone = {"High": "background-color:#FF3B30;color:#fff;font-weight:600",
            "Low": "background-color:#DDF1EB;color:#0A6B54", "Mid-Sell": "background-color:#FADADD;color:#8A2B3A"}
    good, bad = "color:#0E8A6D;font-weight:600", "color:#C93A52;font-weight:600"
    colors = {"Lực mua mạnh": good, "Bị bán mạnh": bad, "Giá Tăng": good, "Giá Giảm": bad,
              "Vol Tăng": good, "Vol Giảm": bad, "Tăng": good, "Giảm": bad, "Đã align": good,
              "Cắt lên": "background-color:#DDF1EB;color:#0A6B54;font-weight:700",
              "Cắt xuống": "background-color:#FCE4E8;color:#C93A52;font-weight:700",
              "Tăng khỏe / Tiền vào": "background-color:#DDF1EB;color:#0A6B54;font-weight:600",
              "Còn tăng": "background-color:#B7F5A0;color:#14532D;font-weight:600",
              "Giảm mạnh / Áp lực xả": "background-color:#FFB3B3;color:#9B1C1C;font-weight:600",
              "Cầu đỡ / Rút chân": "background-color:#FADADD;color:#8A2B3A",
              "Giảm lành tính": "background-color:#FDECEC;color:#8A2B3A"}
    sty = f.style.format({"Giá": "{:,.2f}", "% Biên độ": "{:.1f}%", "Position %": "{:.1f}%", "Vol/Avg10": "{:.2f}",
                          "Score": "{:.1f}", "RS vs VNI": "{:.2f}"}, na_rep="-")
    ap = lambda x: x.map if hasattr(x, "map") else x.applymap
    sty = ap(sty)(lambda v: zone.get(v, ""), subset=["Zone"])
    sty = ap(sty)(lambda v: colors.get(v, ""),
                  subset=["Lực mua/bán", "Giá tăng/giảm", "Vol vs tháng trước", "Nhận xét", "MACD D", "MACD W",
                          "Fisher D", "Fisher W", "MA align"])
    wyc = lambda v: ("color:#0E8A6D;font-weight:600" if "Tích lũy" in str(v) else
                     "color:#C93A52;font-weight:600" if "Phân phối" in str(v) else "")
    sty = ap(sty)(wyc, subset=["Wyckoff"])

    def alert(v):
        v = str(v)
        return ("background-color:#0E8A6D;color:#fff;font-weight:700" if v.startswith("MUA") else
                "background-color:#C93A52;color:#fff;font-weight:700" if v.startswith("BÁN") else
                "background-color:#FDF1D6;color:#8A5A00;font-weight:700" if v != "-" else "")
    sty = ap(sty)(alert, subset=["Cảnh báo"])
    return ap(sty)(lambda v: "color:#0E8A6D;font-weight:700" if pd.notna(v) and v >= 1 else
                   "color:#C93A52" if pd.notna(v) else "", subset=["RS vs VNI"])


# ------------------------------------------------------------------ POPUP CHI TIẾT
def advice(r):
    """Danh sách (tiêu đề, màu, lời khuyên) từ góc nhìn định lượng."""
    c, atr = r["Giá"], r["ATR"] if pd.notna(r["ATR"]) else r["Giá"] * 0.02
    risk = 1.5 * atr
    sl, t1, t2 = c - risk, c + 2 * risk, c + 3 * risk
    vr = r["Vol/Avg10"] if pd.notna(r["Vol/Avg10"]) else 0
    out = []
    if r["PV_signal"] > 0:
        out.append(("MUA — giá + khối lượng", "green",
                    f"Vùng vào {fp(c - 0.25 * atr)}-{fp(c + 0.25 * atr)} · cắt lỗ {fp(sl)} ({risk / c * 100:.1f}%) · "
                    f"chốt 1: {fp(t1)} (R:R 1:2), chốt 2: {fp(t2)} (1:3). Nếu hôm sau mất {fp(c - 0.5 * atr)} với khối lượng "
                    "lớn thì nên thoát sớm."))
    if r["PV_signal"] < 0:
        out.append(("BÁN — giá + khối lượng", "red",
                    f"Nếu đang nắm giữ: cân nhắc giảm tỷ trọng hoặc dời cắt lỗ lên sát {fp(c - 0.5 * atr)}. Chưa mua mới cho đến "
                    f"khi giá đóng cửa lại trên MA20 ({fp(r['MA20'])}) kèm khối lượng ≥ 1.2×."))
    if "Đáy KT" in r["alerts"]:
        out.append(("Đáy KT — Cảnh báo sớm", "amber",
                    f"WaveTrend {r['WT1']:.0f} ở vùng quá bán, RS vẫn ổn định nên áp lực bán chưa phải kiểu xả cả thị trường. "
                    f"Đây mới là cảnh báo sớm, chưa phải điểm mua: chờ nến đóng cửa trên MA10 ({fp(r['MA10'])}) với Vol/Avg10 ≥ 1.2 "
                    f"(hiện {vr:.2f}). Nếu thăm dò thì tỷ trọng nhỏ, cắt lỗ {fp(sl)}, mục tiêu đầu MA20 ({fp(r['MA20'])})."))
    if "Crossover" in r["alerts"]:
        out.append(("Crossover Signal", "green",
                    f"MACD/Fisher vừa cắt lên: động lượng đang đảo chiều tăng. Ưu tiên khi giá đóng trên MA20 ({fp(r['MA20'])}); "
                    f"điểm vào khi vượt đỉnh phiên, cắt lỗ {fp(sl)}, mục tiêu {fp(t1)}. Tín hiệu yếu đi nếu Vol/Avg10 < 1.0 (hiện {vr:.2f})."))
    if not out:
        out.append(("Chưa có cảnh báo", "gray", "Chưa có điều kiện Mua/Bán/Crossover/Đáy KT: đứng ngoài và theo dõi."))
    return out


def swing_view(r):
    """(văn bản, màu, tooltip, dòng phụ) cho ô % của thẻ mã: giảm từ đỉnh hoặc tăng từ đáy."""
    kind, text = r.get("Swing_kind", ""), r.get("Swing_text", "—")
    chg = r.get("Chg_%", np.nan)
    day = f"Hôm nay {chg:+.2f}% so với phiên kề trước" if pd.notna(chg) else "Chưa đủ dữ liệu phiên kề trước"
    if kind not in ("down", "up") or text == "—":
        return "—", "#374151", day, ""
    ref, dt = r.get("Swing_ref", np.nan), r.get("Swing_date", pd.NaT)
    nm = "Đỉnh gần nhất" if kind == "down" else "Đáy gần nhất"
    tip = f"{nm} {ref:,.2f}" + (f" ({dt:%d/%m/%Y})" if pd.notna(dt) else "") + f" · {day}"
    wv = r.get("Swing_waves", "")
    if isinstance(wv, str) and wv:
        tip += " · " + wv
    hi52, lo52 = r.get("Hi52", np.nan), r.get("Lo52", np.nan)
    sub = f"Đỉnh 78 tuần {hi52:,.2f} · Đáy 78 tuần {lo52:,.2f}" if pd.notna(hi52) and pd.notna(lo52) else ""
    if r.get("Swing_bear", False):                 # hồi kỹ thuật trong xu hướng giảm: không dùng màu xanh của "đảo chiều"
        tr = r.get("Swing_trend_ref", np.nan)
        note = "⚠ Đang hồi trong xu hướng giảm, chưa xác nhận đảo chiều" + (
            f" (đường xu hướng giảm ~{tr:,.2f})" if pd.notna(tr) else "")
        sub = note + ("\n" + sub if sub else "")
        return text, ("#C02645" if kind == "down" else "#B45309"), tip, sub
    return text, ("#C02645" if kind == "down" else "#08785E"), tip, sub


@st.dialog("Chi tiết mã", width="large")
def show_detail(code):
    r = res_df[res_df["Mã"] == code].iloc[0]
    st.subheader(f"{code} · {r['Giá']:,.2f} ({swing_view(r)[0]})")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Score", f"{r['Score']:.1f}/10")
    m2.metric("RS vs VNI", f"{r['RS vs VNI']:.2f}" if pd.notna(r["RS vs VNI"]) else "-")
    m3.metric("MA Alignment", r["MA align"])
    m4.metric("Wyckoff", r["Wyckoff"])

    st.markdown("##### ⚡ Cảnh báo sớm & hành động")
    for title, k, txt in advice(r):
        st.markdown(card(f'{tag(title, k)}', f'<div class="muted" style="font-size:13px">{txt}</div>'),
                    unsafe_allow_html=True)

    st.markdown("##### 📈 Tín hiệu đa khung (MACD & Fisher)")
    st.dataframe(TH.style_df(pd.DataFrame({"Daily": [r["MACD D"], r["Fisher D"]], "Weekly": [r["MACD W"], r["Fisher W"]]},
                              index=["MACD (12-26-9)", "Fisher Transform (9)"])), **_STRETCH_DF)
    st.caption("Cắt lên/xuống = vừa cắt trong 3 nến gần nhất. Khung Tuần cần đủ ~35 tuần dữ liệu, thiếu thì hiện '-'.")

    st.markdown("##### 🏭 Trạng thái ngành & dòng tiền")
    left, right = st.columns(2)
    with left:
        groups = [g_ for g_ in MEMBER.get(code, []) if g_ != WL.OLD]
        if groups:
            for g_ in groups[:3]:
                peers = res_df[res_df["Nhóm"].apply(lambda t_: g_ in [x.strip() for x in t_.split(",")])]
                up, rs, strong = (peers["Giá tăng/giảm"] == "Giá Tăng").mean() * 100, peers["RS20"].mean(), (peers["Score"] >= 5).mean() * 100
                verdict = "Mạnh" if rs > 1 and up >= 50 else "Yếu" if rs < 1 and up < 50 else "Phân hóa"
                st.markdown(card(f'Nhóm: {g_} {tag(verdict, "green" if verdict == "Mạnh" else "red" if verdict == "Yếu" else "amber")}',
                                 row("Số mã trong dữ liệu", len(peers)) + row("% mã đang tăng", f"{up:.0f}%")
                                 + row("RS trung bình", f"{rs:.2f}") + row("% mã Score ≥ 5", f"{strong:.0f}%")),
                            unsafe_allow_html=True)
        else:
            st.info("Mã này chưa thuộc nhóm ngành nào trong watchlist.py.")
        st.markdown(_wy_note(code), unsafe_allow_html=True)
    with right:
        yn = lambda b: "✅" if b else "—"
        st.markdown(card("Dòng tiền nội tại",
                         row("Vol/Avg10", f"{r['Vol/Avg10']:.2f}" if pd.notna(r["Vol/Avg10"]) else "-")
                         + row("Vol tăng 3 phiên liên tiếp", yn(r["VolStep"])) + row("Dòng tiền sớm (gom ngầm)", yn(r["EarlyFlow"]))
                         + row("Cạn cung (vol thấp, giữ MA20)", yn(r["DryUp"])) + row("NR4 / NR7", f'{yn(r["NR4"])} / {yn(r["NR7"])}')
                         + row("MFI 14", f"{r['MFI14']:.0f}" if pd.notna(r["MFI14"]) else "-")
                         + row("A/D 5 phiên", "tăng" if r["AD_up"] else "giảm")), unsafe_allow_html=True)
    st.caption("Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")


# ------------------------------------------------------------------ TRANG 1: BỘ LỌC
def _stock_indicators(code: str) -> dict:
    """Tóm tắt trạng thái kỹ thuật từ dữ liệu OHLCV đã tải."""
    g = df[df["Mã"] == code].sort_values("Ngày").reset_index(drop=True)
    if len(g) < 2:
        return {}
    r, prev = g.iloc[-1], g.iloc[-2]
    close = g["Giá đóng cửa"]
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    rsi = (100 - 100/(1 + gain/loss.replace(0, np.nan))).where(loss != 0, 100.0)
    def state(condition, unknown=False):
        return "Chưa rõ" if unknown else ("Tốt" if condition else "Xấu")
    sa, sb = r.get("SpanA", np.nan), r.get("SpanB", np.nan)
    ichi_unknown = pd.isna(sa) or pd.isna(sb) or pd.isna(r.get("Tenkan", np.nan)) or pd.isna(r.get("Kijun", np.nan))
    ichi_good = not ichi_unknown and r["Giá đóng cửa"] > max(sa, sb) and r["Tenkan"] > r["Kijun"]
    macd_unknown = pd.isna(r.get("MACD", np.nan)) or pd.isna(r.get("MACD_sig", np.nan))
    vol_now, vol_prev = r.get(E.VOL, np.nan), prev.get(E.VOL, np.nan)
    vol_unknown = pd.isna(vol_now) or pd.isna(vol_prev)
    chg = r.get("Chg_%", np.nan)
    def trend(cols):
        vals = [r.get(f"MA{x}", np.nan) for x in cols]
        if any(pd.isna(v) for v in vals): return "Chưa rõ"
        return "Tốt" if all(vals[i] > vals[i+1] for i in range(len(vals)-1)) else "Xấu"
    rnow = rsi.iloc[-1] if len(rsi) else np.nan
    rprev = rsi.iloc[-2] if len(rsi) > 1 else np.nan
    return {
        "Vùng giá": "Tốt" if pd.notna(chg) and chg > 0 else "Xấu" if pd.notna(chg) and chg < 0 else "Chưa rõ",
        "Ichimoku": state(ichi_good, ichi_unknown),
        "MACD": state(not macd_unknown and r["MACD"] > r["MACD_sig"], macd_unknown),
        "Volume": state(not vol_unknown and vol_now > vol_prev, vol_unknown),
        "RSI": "Tốt" if pd.notna(rnow) and pd.notna(rprev) and rnow > rprev else "Xấu" if pd.notna(rnow) and pd.notna(rprev) else "Chưa rõ",
        "Ngắn hạn": trend((10, 20)), "Trung hạn": trend((20, 50, 100)), "Dài hạn": trend((50, 100, 200)),
    }


def _ma_summary_html(code: str) -> str:
    """Hiển thị MA20/50/200 theo giá đóng cửa ngày; thiếu lịch sử thì không đoán giá trị."""
    g = df[df["Mã"].astype(str).str.upper() == str(code).upper()].sort_values("Ngày")
    if g.empty or "Giá đóng cửa" not in g:
        close = np.nan
        mas = {20: np.nan, 50: np.nan, 200: np.nan}
    else:
        close_series = pd.to_numeric(g["Giá đóng cửa"], errors="coerce")
        close = close_series.iloc[-1] if len(close_series) else np.nan
        mas = {n: close_series.rolling(n, min_periods=n).mean().iloc[-1]
               if len(close_series) >= n else np.nan for n in (20, 50, 200)}
    items = []
    for n in (20, 50, 200):
        ma = mas[n]
        if pd.isna(close) or pd.isna(ma) or ma == 0:
            value, status, cls = "—", "Chưa đủ dữ liệu", "ma-unknown"
        else:
            diff = (float(close) / float(ma) - 1) * 100
            value = f"{float(ma):,.2f}"
            if abs(diff) < 0.05:
                status, cls = "Sát MA", "ma-unknown"
            elif diff > 0:
                status, cls = f"Trên MA +{diff:.1f}%", "ma-up"
            else:
                status, cls = f"Dưới MA {diff:.1f}%", "ma-down"
        items.append(f'<div class="ma-item"><div class="ma-label">MA{n}</div>'
                     f'<div class="ma-value">{value}</div><div class="ma-state {cls}">{status}</div></div>')
    # Tóm tắt trạng thái dựa trên vị trí giá đóng cửa so với MA ngày.
    # Đây chỉ là mô tả xu hướng, không phải tín hiệu mua/bán.
    pills, note = [], ""
    if any(pd.isna(mas[n]) for n in (20, 50, 200)) or pd.isna(close):
        pills.append('<span class="ma-pill ma-neutral">Trạng thái MA tổng hợp: Chưa đủ dữ liệu</span>')
    else:
        above = {n: float(close) >= float(mas[n]) for n in (20, 50, 200)}
        above20, above50, above200 = above[20], above[50], above[200]
        if not above20 and above50:
            short_text, short_cls = 'Ngắn hạn điều chỉnh', 'ma-caution'
        elif above20:
            short_text, short_cls = 'Ngắn hạn tích cực', 'ma-positive'
        else:
            short_text, short_cls = 'Ngắn hạn suy yếu', 'ma-negative'

        if above50 and above200:
            medium_text, medium_cls = 'Trung hạn tích cực', 'ma-positive'
        elif not above50 and not above200:
            medium_text, medium_cls = 'Trung hạn suy yếu', 'ma-negative'
        else:
            medium_text, medium_cls = 'Trung hạn hỗn hợp', 'ma-neutral'
        pills.append(f'<span class="ma-pill {short_cls}">{short_text}</span>')
        pills.append(f'<span class="ma-pill {medium_cls}">{medium_text}</span>')

        def _join(names):
            return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " và " + names[-1]
        up = [f"MA{n}" for n in (20, 50, 200) if above[n]]
        down = [f"MA{n}" for n in (20, 50, 200) if not above[n]]
        if not down:
            note = f"Giá trên {_join(up)}."
        elif not up:
            note = f"Giá dưới {_join(down)}."
        else:
            note = f"Giá dưới {_join(down)} nhưng trên {_join(up)}."
    overview_html = ('<div class="ma-overview" aria-label="Trạng thái MA tổng hợp">'
                     '<div class="ma-pills">' + ''.join(pills) + '</div>'
                     + (f'<div class="ma-note">{note}</div>' if note else '') + '</div>')
    return '<div class="ma-summary" aria-label="Giá trung bình động ngày">' + ''.join(items) + '</div>' + overview_html


# Chú thích khi rê chuột: 3 chip xu hướng chỉ đo cấu trúc đường MA (không phải khung Ngày/Tuần/Tháng bên dưới).
CHIP_TIPS = {"Ngắn hạn": "MA10 > MA20", "Trung hạn": "MA20 > MA50 > MA100", "Dài hạn": "MA50 > MA100 > MA200"}


def _status_chip(label: str, state: str) -> str:
    bg, fg = {"Tốt": ("#DDF1EB", "#08785E"), "Xấu": ("#FCE4E8", "#C02645"), "Chưa rõ": ("#EEF1F5", "#626B78")}.get(state, ("#EEF1F5", "#626B78"))
    tip = (htmllib.escape(CHIP_TIPS[label]) + f" · {state}") if label in CHIP_TIPS else state
    return f'<span title="{tip}" style="display:inline-block;background:{bg};color:{fg};border-radius:7px;padding:5px 8px;margin:3px 4px 3px 0;font-size:12px;font-weight:650;white-space:nowrap">{label}</span>'


def _forecast(states: dict) -> str:
    good, bad = list(states.values()).count("Tốt"), list(states.values()).count("Xấu")
    if good >= 6 and good - bad >= 4: return "Dự báo tăng mạnh"
    if bad >= 6 and bad - good >= 4: return "Dự báo giảm mạnh"
    if good > bad: return "Dự báo tăng"
    if bad > good: return "Dự báo giảm"
    return "Chưa rõ xu hướng"


def apply_manual_overrides(fund_map: dict, cap_map: dict, path: str = "data/nhap_tay.csv") -> None:
    """Số nhập tay trong data/nhap_tay.csv (Mã, Tên công ty, Vốn hóa TT, P/B, ROE) ưu tiên hơn dữ liệu tự động.
    Ô để trống thì dùng dữ liệu tự động. Số thập phân dùng dấu chấm (dấu phẩy cũng được chấp nhận)."""
    if not os.path.exists(path):
        return
    try:
        mt = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    except Exception:
        return
    mt.columns = [str(c).strip() for c in mt.columns]

    def num(v):
        if not isinstance(v, str) or not v.strip():
            return None
        try:
            return float(v.replace("%", "").replace(" ", "").replace(",", "."))
        except ValueError:
            return None

    for _, row in mt.iterrows():
        code = str(row.get("Mã", "")).strip().upper()
        if not code or code == "NAN":
            continue
        name = row.get("Tên công ty")
        if isinstance(name, str) and name.strip():
            fund_map.setdefault(code, {})["Tên công ty"] = name.strip()
        txt = row.get("Bảng xếp hạng")
        if isinstance(txt, str) and txt.strip():
            fund_map.setdefault(code, {})["Bảng xếp hạng"] = txt.strip()
        for col in ("P/B", "ROE", "P/E", "P/B TB 3N", "P/E TB 3N", "EPS", "Giá trị sổ sách", "KLGD MA20",
                    "Xếp hạng", "Xếp hạng tài chính", "Xếp hạng kinh doanh"):
            v = num(row.get(col))
            if v is not None:
                fund_map.setdefault(code, {})[col] = v
        cap = num(row.get("Vốn hóa TT"))
        if cap is not None:
            cap_map[code] = cap


_TF_HEAD = {"D": ("📅 D (Ngày)", "#10B981"), "W": ("🗓️ W (Tuần)", "#3B82F6"), "M": ("🏛️ M (Tháng)", "#8B5CF6")}


def sup_text(r):
    """Hỗ trợ: dạng khoảng 'thấp – cao' khi giá nằm trên mây (cả dải mây là vùng đỡ), ngược lại là một mức."""
    if r["sup"] is None:
        return "—"
    return f"{fp(r['sup'])} – {fp(r['sup_hi'])}" if r.get("sup_hi") is not None else fp(r["sup"])
def res_text(r):
    """Kháng cự 1 (đỉnh sóng gần giá nhất phía trên), kèm kháng cự 2 nếu có."""
    if r["res"] is None:
        return "—"
    return f"{fp(r['res'])} · {fp(r['res2'])}" if r.get("res2") is not None else fp(r["res"])
_TREND_CLS = {"Tăng": "c-green", "Giảm": "c-red"}      # còn lại (Tích lũy) màu vàng


@st.cache_data(show_spinner=False)
def divergence_cached(_frames: dict, code: str, key: str) -> list:
    """Phân kỳ RSI/giá khung D và W của một mã (xem rsi_divergence.py)."""
    return DV.analyze(_frames, code, ("M", "W", "D"))


@st.cache_data(show_spinner=False)
def mtf_cached(_frames: dict, code: str, key: str) -> dict:
    pick = lambda tf: _frames[tf][_frames[tf]["Mã"] == code]
    return ML.analyze_dwm_timeframe(pick("D"), pick("W"), pick("M"))


def _min_trading() -> str:
    """Dòng 'Min Trading dd/mm/yyyy' cuối khung Vùng mua: ngày cập nhật dữ liệu + 1 ngày (dữ liệu cập nhật chiều, hôm sau mới gửi khách)."""
    return f"Min Trading {(pd.Timestamp(latest_date) + pd.Timedelta(days=1)):%d/%m/%Y}"


def mtf_strategy_box(s: dict, code: str = "") -> str:
    """Bảng Vùng mua - Cắt lỗ - Mục tiêu dạng hàng ngang, cùng kiểu khối "Mua ngay" ở Cổ phiếu chờ mua
    (class wb-* lấy từ waiting_buy.card_css). Số liệu lấy nguyên từ ML._strategy, không đổi cách tính."""
    if not s["ok"]:
        return f'<div class="wb-box"><div class="wb-sec"><div class="wb-sub" style="margin:0">{htmllib.escape(s["msg"])}</div></div></div>'
    n = s["num"]
    px = lambda x: f"{x:,.1f}"
    pct = lambda x: f" ({(x / n['close'] - 1) * 100:+.1f}%)"
    go = n["close"] <= n["entry_hi"]
    pc = lambda x: (x / n["close"] - 1) * 100
    rr_cls = "wb-go" if s["rr_value"] >= 1.8 else "wb-wait"
    rr_tag = f'<small class="{rr_cls}" style="margin-left:8px">R:R 1:{s["rr_value"]} · {s["rr_label"]}</small>'
    notes = [s["status"]] + ["⚠ " + w for w in s["warn"] + ([s["tp_note"]] if s["tp_note"] else [])] + ([s["tp2_note"]] if s.get("tp2_note") else [])
    return WB.ladder_html(code, n["close"], n["entry_lo"], n["entry_hi"], go, n["sl"], pc(n["sl"]), n["tp"], pc(n["tp"]), rr_tag,
                          n.get("tp2"), pc(n["tp2"]) if n.get("tp2") is not None else None, "", " ".join(notes), _min_trading())


def mtf_block(res: dict, code: str = "", parts: bool = False):
    """Khối 'Phân tích đa khung D - W - M' + hộp chiến lược cho thẻ kết quả lọc (không có dòng trống / thụt lề để Markdown không vỡ)."""
    subs = []
    for tf in ("D", "W", "M"):
        title, accent = _TF_HEAD[tf]
        r = res[tf]
        if r["ok"]:
            sup = sup_text(r)
            rs = res_text(r)
            body = (f'<div class="tf-info">• Hỗ trợ: <b>{sup}</b></div><div class="tf-info">• Kháng cự: <b>{rs}</b></div>'
                    f'<div class="tf-comment">💬 {htmllib.escape(r["cmt"])}</div>')
            trend = f'<span class="{_TREND_CLS.get(r["trend"], "c-amber")}">{r["trend"]}</span>'
        else:
            body, trend = f'<div class="tf-comment">💬 {htmllib.escape(r["cmt"])}</div>', '<span class="c-gray">—</span>'
        subs.append(f'<div class="tf-subcard" style="border-top:3px solid {accent}"><div class="tf-title"><span>{title}</span>{trend}</div>{body}</div>')
    strat = mtf_strategy_box(res["strategy"], code)
    tf_html = ('<div class="multi-tf-title">📊 PHÂN TÍCH ĐA KHUNG (D - W - M):</div>'
               f'<div class="multi-tf-container">{"".join(subs)}</div>')
    if parts:     # thẻ kết quả lọc: tách khung Vùng mua (đặt lên trên) khỏi phần phân tích D-W-M (đặt dưới RSI/Wyckoff)
        return tf_html, strat
    return tf_html + strat


# ------------------------------------------------------------------ KẾT QUẢ LỌC: thống kê · tìm kiếm · lọc thời hạn · sắp xếp · bảng
KQ_TERMS = {"Tất cả": None, "Ngắn hạn": "Trend_NganHan", "Trung hạn": "Trend_TrungHan", "Dài hạn": "Trend_DaiHan"}
KQ_SORTS = ["Mã A → Z", "Mã Z → A", "Score cao → thấp", "Gần hỗ trợ nhất", "Gần kháng cự nhất"]
KQ_PER_PAGE = {"Thẻ": 12, "Bảng": 50}


def kq_apply(a: pd.DataFrame, query: str, term: str, sort_by: str, _frames=None, data_key: str = "") -> pd.DataFrame:
    """Tập B = Tập A + tìm mã + lọc thời hạn + sắp xếp; không thay đổi Tập A.
    Khoảng cách hỗ trợ/kháng cự tính theo % so với giá đóng cửa của đúng khung D/W/M."""
    b = a
    toks = [t for t in re.split(r"[,\s;]+", str(query or "").upper()) if t]
    if toks:
        up = b["Mã"].astype(str).str.upper()
        b = b[up.apply(lambda c: any(t in c for t in toks))]
    col = KQ_TERMS.get(term)
    if col and col in b.columns:
        b = b[b[col] == "TĂNG"]
    if sort_by == "Mã Z → A":
        b = b.sort_values("Mã", key=lambda x: x.astype(str).str.upper(), ascending=False)
    elif sort_by == "Score cao → thấp" and "Score" in b.columns:
        b = b.sort_values("Score", ascending=False, kind="stable")
    elif sort_by in ("Gần hỗ trợ nhất", "Gần kháng cự nhất") and _frames is not None:
        # Tất cả/Ngắn hạn dùng hỗ trợ-kháng cự Ngày; Trung hạn dùng Tuần; Dài hạn dùng Tháng.
        tf = {"Tất cả": "D", "Ngắn hạn": "D", "Trung hạn": "W", "Dài hạn": "M"}.get(term, "D")
        distances = {}
        for code in b["Mã"].astype(str).unique():
            try:
                levels = mtf_cached(_frames, code, data_key)[tf]
                close = levels.get("close")
                if not levels.get("ok") or close is None or float(close) <= 0:
                    distances[code] = np.nan
                    continue
                if sort_by == "Gần hỗ trợ nhất":
                    # Khi hỗ trợ là một vùng mây, lấy mép trên (gần giá nhất).
                    level = levels.get("sup_hi") if levels.get("sup_hi") is not None else levels.get("sup")
                    distance = (float(close) - float(level)) / float(close) * 100 if level is not None else np.nan
                else:
                    level = levels.get("res")
                    distance = (float(level) - float(close)) / float(close) * 100 if level is not None else np.nan
                distances[code] = distance if pd.notna(distance) and distance >= 0 else np.nan
            except Exception:
                distances[code] = np.nan
        b = b.assign(_level_distance=b["Mã"].astype(str).map(distances))
        b = b.sort_values("_level_distance", ascending=True, na_position="last", kind="stable").drop(columns=["_level_distance"])
    else:
        b = b.sort_values("Mã", key=lambda x: x.astype(str).str.upper())
    return b.reset_index(drop=True)


def kq_stat_card(label: str, value, sub: str, up: bool = False) -> str:
    return (f'<div class="kq-stat"><div class="kq-l">{htmllib.escape(label)}</div>'
            f'<div class="kq-v{" up" if up else ""}">{value}</div><div class="kq-s">{htmllib.escape(sub)}</div></div>')


def kq_table(b: pd.DataFrame):
    """Bảng dữ liệu thật từ kết quả lọc; cột nào dự án không có thì bỏ qua, ô thiếu hiện —."""
    names = {"Mã": "Mã CK", "Giá": "Giá", "Chg_%": "Thay đổi (%)", "RS vs VNI": "RS",
             "MA10": "MA10", "MA20": "MA20", "MA50": "MA50", "MA100": "MA100", "MA200": "MA200",
             "Trend_NganHan": "Ngắn hạn", "Trend_TrungHan": "Trung hạn", "Trend_DaiHan": "Dài hạn"}
    t = b[[c for c in names if c in b.columns]].rename(columns=names).copy()
    trend_cols = [c for c in ("Ngắn hạn", "Trung hạn", "Dài hạn") if c in t.columns]
    for c in trend_cols:
        t[c] = t[c].map({"TĂNG": "Tăng", "GIẢM": "Giảm", "LẪN LỘN": "Lẫn lộn"}).fillna("Chưa đủ dữ liệu")
    fmt = {c: "{:,.2f}" for c in ("Giá", "MA10", "MA20", "MA50", "MA100", "MA200") if c in t.columns}
    if "Thay đổi (%)" in t.columns: fmt["Thay đổi (%)"] = "{:+.2f}%"
    if "RS" in t.columns: fmt["RS"] = "{:.2f}"
    sty = t.style.format(fmt, na_rep="—")
    ap = lambda x: x.map if hasattr(x, "map") else x.applymap
    sty = ap(sty)(lambda v: "font-weight:800", subset=["Mã CK"])
    tcolor = {"Tăng": "color:#0E8A6D;font-weight:700", "Giảm": "color:#C93A52;font-weight:700",
              "Lẫn lộn": "color:#B7791F;font-weight:600", "Chưa đủ dữ liệu": "color:#8A93A0"}
    if trend_cols:
        sty = ap(sty)(lambda v: tcolor.get(v, ""), subset=trend_cols)
    if "Thay đổi (%)" in t.columns:
        sty = ap(sty)(lambda v: "color:#0E8A6D" if pd.notna(v) and v > 0 else "color:#C93A52" if pd.notna(v) and v < 0 else "", subset=["Thay đổi (%)"])
    return sty


def _kq_reset_page():
    st.session_state["kq_page"] = 1


def page_filter():
    st.title("🔍 Bộ lọc cổ phiếu")
    header()
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)      # CSS khối Vùng mua - Cắt lỗ - Mục tiêu (wb-*)
    st.caption("Giữ nguyên các điều kiện lọc hiện tại. Các mã đáp ứng điều kiện sẽ hiển thị thành từng thẻ ở phần Kết quả lọc bên dưới.")
    f = apply_filters(res_df, filter_panel()).sort_values("Score", ascending=False).drop_duplicates("Mã").reset_index(drop=True)   # Tập A
    st.divider()
    st.subheader("📋 Kết quả lọc")
    # ---- Tập B = Tập A + tìm mã + lọc thời hạn + sắp xếp (đọc trạng thái từ session_state để thẻ thống kê hiện đúng ngay lượt này)
    ss = st.session_state
    b = kq_apply(f, ss.get("kq_search", ""), ss.get("kq_term") or "Tất cả", ss.get("kq_sort", KQ_SORTS[0]), frames, DATA_KEY)
    view = ss.get("kq_view") or "Thẻ"
    per_page = KQ_PER_PAGE.get(view, 12)
    n_pages = max(1, math.ceil(len(b) / per_page))
    ss["kq_page"] = min(max(int(ss.get("kq_page", 1) or 1), 1), n_pages)      # gán TRƯỚC khi tạo widget nên không gây StreamlitWidgetAlreadyInstantiatedError
    cnt = lambda col: int((f[col] == "TĂNG").sum()) if col in f.columns else 0   # thẻ xu hướng đếm trên Tập A, không đổi theo ô tìm kiếm / tab
    sc = st.columns(4)
    sc[0].markdown(kq_stat_card("Tổng số mã", f"{len(f)}", f"Đang hiển thị {len(b)} mã"), unsafe_allow_html=True)
    sc[1].markdown(kq_stat_card("Ngắn hạn · Tăng", cnt("Trend_NganHan"), "MA10 > MA20", True), unsafe_allow_html=True)
    sc[2].markdown(kq_stat_card("Trung hạn · Tăng", cnt("Trend_TrungHan"), "MA20 > MA50 > MA100", True), unsafe_allow_html=True)
    sc[3].markdown(kq_stat_card("Dài hạn · Tăng", cnt("Trend_DaiHan"), "MA50 > MA100 > MA200", True), unsafe_allow_html=True)
    if f.empty:
        st.info("Không có mã nào thỏa bộ lọc hiện tại. Hãy nới lỏng một vài điều kiện.")
        return
    t1, t2, t3 = st.columns([2, 3.6, 1.8])
    t1.text_input("Tìm mã", placeholder="🔍 Tìm mã...", key="kq_search", label_visibility="collapsed", on_change=_kq_reset_page)
    with t2:
        st.segmented_control("Lọc theo thời hạn", list(KQ_TERMS), default="Tất cả", key="kq_term", label_visibility="collapsed", on_change=_kq_reset_page)
    t3.selectbox("Sắp xếp", KQ_SORTS, key="kq_sort", label_visibility="collapsed", on_change=_kq_reset_page)
    v1, v2, v3 = st.columns([2, 3.6, 1.8])
    with v1:
        st.segmented_control("Kiểu hiển thị", ["Thẻ", "Bảng"], default="Thẻ", key="kq_view", label_visibility="collapsed", on_change=_kq_reset_page)
    with v3:
        st.number_input("Trang", min_value=1, max_value=n_pages, step=1, key="kq_page", label_visibility="collapsed", disabled=n_pages == 1)
    lo, hi = (ss["kq_page"] - 1) * per_page, min(ss["kq_page"] * per_page, len(b))
    v2.caption(f"Hiển thị {lo + 1 if len(b) else 0}–{hi} / {len(b)} mã · trang {ss['kq_page']}/{n_pages}")
    if b.empty:
        st.info("Không có mã nào khớp tìm kiếm / bộ lọc thời hạn. Chọn \"Tất cả\" hoặc xóa từ khóa để xem lại toàn bộ kết quả lọc.")
        return
    page_df = b.iloc[lo:hi]
    if view == "Bảng":
        st.dataframe(kq_table(page_df), hide_index=True, use_container_width=True)
        return
    show_mtf = st.toggle("Hiện phân tích đa khung (D · W · M) và chiến lược trong từng thẻ", value=True, key="show_mtf")
    # Có thể bổ sung vốn hóa thực tế qua data/stock_metadata.csv (cột Mã,Vốn hóa TT; đơn vị tỷ đồng).
    cap_map = {}
    if os.path.exists("data/stock_metadata.csv"):
        try:
            meta = pd.read_csv("data/stock_metadata.csv", dtype={"Mã": str})
            if {"Mã", "Vốn hóa TT"}.issubset(meta.columns): cap_map = dict(zip(meta["Mã"].str.upper(), meta["Vốn hóa TT"]))
        except Exception: pass
    # Tên công ty, P/B, ROE: data/fundamentals.csv do update_fundamentals.py tự cập nhật; tên sửa tay ở data/ten_cong_ty_tay.csv
    fund_map = {}
    fund_map = FG.load_fund_map()   # đã chặn số mặc định / ngoài miền (fund_guard.py)
    if os.path.exists("data/ten_cong_ty_tay.csv"):
        try:
            _nt = pd.read_csv("data/ten_cong_ty_tay.csv", dtype=str)
            for _c, _n in zip(_nt["Mã"].str.upper().str.strip(), _nt["Tên công ty"]):
                if isinstance(_n, str) and _n.strip():
                    fund_map.setdefault(_c, {})["Tên công ty"] = _n.strip()
        except Exception: pass
    apply_manual_overrides(fund_map, cap_map)
    for _w in FG.warnings():
        st.warning("Dữ liệu cơ bản: " + _w)
    if f.empty:
        st.info("Không có mã nào thỏa bộ lọc hiện tại. Hãy nới lỏng một vài điều kiện.")
        return
    try:     # trạng thái chờ mua / cảnh báo của từng mã -> tag ở góc phải thẻ
        _wb_map = _wb_table().set_index("Mã")[["Trạng thái", "Lý do"]].to_dict("index")
    except Exception:
        _wb_map = {}
    CHIP_ONLY_GOOD = False                        # True: chỉ chip xanh "Tốt"; False: đủ 3 màu Tốt/Xấu/Chưa rõ
    # Số thẻ trên một hàng: 3; nhưng chỉ có 1–2 mã trên trang (ví dụ tìm đúng 1 mã) thì thẻ giãn ra hết khung.
    per_row = len(page_df) if len(page_df) <= 2 else 3
    rows = [page_df.iloc[i:i + per_row] for i in range(0, len(page_df), per_row)]
    for chunk in rows:
        cols = st.columns(per_row)
        for col, (_, r) in zip(cols, chunk.iterrows()):
            code = str(r["Mã"])
            with col:
                states = _stock_indicators(code)
                forecast = _forecast(states) if states else "Chưa rõ xu hướng"
                up = "tăng" in forecast.lower(); down = "giảm" in forecast.lower()
                bg, fg = ("#DDF1EB", "#08785E") if up else (("#FCE4E8", "#C02645") if down else ("#EEF1F5", "#626B78"))
                groups = MEMBER.get(code, [])
                sectors = [g for g in groups if g != WL.VN30]
                industry = htmllib.escape(", ".join(sectors)) if sectors else "Khác / chưa phân loại"
                vn30_badge = " · VN30" if WL.VN30 in groups else ""
                cap = cap_map.get(code.upper())
                try: cap_text = f"{float(cap):,.0f} tỷ" if pd.notna(cap) else "Chưa có"
                except (TypeError, ValueError): cap_text = htmllib.escape(str(cap)) if cap is not None else "Chưa có"
                fd = fund_map.get(code.upper(), {})
                cname = fd.get("Tên công ty")
                name_text = htmllib.escape(cname.strip()) if isinstance(cname, str) and cname.strip() else "Chưa có tên công ty"
                def _fmt(v, f_):
                    try: return f_.format(float(v)) if pd.notna(v) else "Chưa có"
                    except (TypeError, ValueError): return "Chưa có"
                pb_text, roe_text = _fmt(fd.get("P/B"), "{:.2f}"), _fmt(fd.get("ROE"), "{:.1f}%")
                chg = r.get("Chg_%", np.nan)
                chg_text, price_color, chg_tip, chg_sub = swing_view(r)     # "Đã giảm X% từ đỉnh" / "Đã tăng X% từ đáy"
                if CHIP_ONLY_GOOD:     # chỉ hiện các chỉ báo "Tốt" (chip xanh); đặt False để hiện đủ Tốt/Xấu/Chưa rõ
                    good = [lb for lb, v in states.items() if v == "Tốt"]
                    chips_html = "".join(f'<span class="tag-chip">{htmllib.escape(lb)}</span>' for lb in good) \
                        or '<span class="muted">Chưa có chỉ báo Tốt</span>'
                else:
                    chips_html = "".join(_status_chip(lb, v) for lb, v in states.items())
                mtf_html, strat_html = mtf_block(mtf_cached(frames, code, DATA_KEY), code, parts=True) if show_mtf else ("", "")
                div_html = DV.html(divergence_cached(frames, code, DATA_KEY + "|" + E.ENGINE_VERSION + "|dv1"))
                lean_html = _lean_html(code)
                _wb = _wb_map.get(code)
                if _wb:
                    _tl, _tbg, _tfg = WB.status_tag(_wb["Trạng thái"], _wb["Lý do"])
                    status_html = (f'<div style="flex-shrink:0;margin-left:8px"><span class="badge-forecast" title="{htmllib.escape(str(_wb["Lý do"]))}" '
                                   f'style="background:{_tbg};color:{_tfg}">{htmllib.escape(_tl)}</span></div>')
                else:
                    status_html = ""
                html = (f'<div class="stock-card in-box">'
                        f'<div class="stock-header"><div><div class="stock-title"><span class="stock-code">{code}</span>'
                        f'<span class="badge-forecast" style="background:{bg};color:{fg}">{forecast}</span></div>'
                        f'<div class="stock-company" title="{name_text}" style="margin-top:6px">{name_text}</div>{lean_html}</div>{status_html}</div>'
                        f'<div class="price-box" style="flex-wrap:wrap"><span class="price-val" style="color:{price_color}">{r["Giá"]:,.2f}</span>'
                        f'<span class="price-chg" style="color:{price_color}" title="{htmllib.escape(chg_tip)}">{chg_text}</span></div>'
                        + (f'<div class="muted" style="font-size:12px;margin:-4px 0 8px">{htmllib.escape(chg_sub).replace(chr(10), "<br>")}</div>' if chg_sub else "") +
                        f'<div class="metrics-grid">'
                        f'<div class="metric-item">Ngành: <b>{industry}{vn30_badge}</b></div>'
                        f'<div class="metric-item">Vốn hóa: <b>{cap_text}</b></div>'
                        f'<div class="metric-item">P/B: <b>{pb_text}</b></div>'
                        f'<div class="metric-item">ROE: <b>{roe_text}</b></div></div>'
                        + _ma_summary_html(code)
                        + f'<div class="tag-container">' + chips_html + '</div>' + (f'<div style="margin-bottom:12px">{strat_html}</div>' if strat_html else '') + div_html + _wy_note(code, True) + mtf_html + _action_html(code) + '</div>')
                with st.container(border=True):
                    st.markdown(html, unsafe_allow_html=True)
                    if st.button("📊 Xem biểu đồ", key=f"chart_{code}", use_container_width=True):
                        st.session_state["selected_code"] = code
                        # các selectbox có key riêng giữ giá trị cũ -> đồng bộ luôn để mở đúng mã vừa bấm
                        for _k in ("mtf_code", "tab_code"):
                            st.session_state[_k] = code
                        NAV.goto("Cổ phiếu", "Tổng quát")

# ------------------------------------------------------------------ TRANG: CỔ PHIẾU CHỜ MUA TRONG TUẦN
@st.cache_data(show_spinner="Đang nhận diện trạng thái chờ mua cho cả rổ...")
def waiting_cached(_frames: dict, _screener: pd.DataFrame, key: str) -> pd.DataFrame:
    return WB.build_waiting_buy(_frames, _screener)


WB_CHIP = {WB.G1: "tag-green", WB.G2: "tag-amber", WB.G3: "tag-gray"}
WB_HELP = {WB.G1: "Ra quyết định giải ngân ngay: đã có tín hiệu mua hoặc đang test hỗ trợ với khối lượng cạn.",
           WB.G2: "Chuẩn bị sức mua và canh lệnh trong phiên.",
           WB.G3: "Danh sách quan sát cho các tuần tiếp theo."}
WB_PER_GROUP = 24


def _wb_table() -> pd.DataFrame:
    return waiting_cached(frames, res_df, WY_KEY + "|" + E.ENGINE_VERSION + "|wb12")  # Chờ mua và Mua ngay dùng chung một bộ tính vùng mua; tăng version để làm mới cache


@st.cache_data(show_spinner=False)
def _wb_meta_maps(key: str) -> tuple[dict, dict]:
    """Vốn hóa (data/stock_metadata.csv), tên/P/B/ROE (data/fundamentals.csv) và số nhập tay - cùng nguồn với thẻ ở Bộ lọc."""
    cap_map, fund_map = {}, {}
    if os.path.exists("data/stock_metadata.csv"):
        try:
            meta = pd.read_csv("data/stock_metadata.csv", dtype={"Mã": str})
            if {"Mã", "Vốn hóa TT"}.issubset(meta.columns): cap_map = dict(zip(meta["Mã"].str.upper(), meta["Vốn hóa TT"]))
        except Exception: pass
    fund_map = FG.load_fund_map()   # đã chặn số mặc định / ngoài miền (fund_guard.py)
    apply_manual_overrides(fund_map, cap_map)
    return cap_map, fund_map


def _wb_meta(code: str) -> dict:
    cap_map, fund_map = _wb_meta_maps(WY_KEY)
    groups = MEMBER.get(code, [])
    sectors = [g for g in groups if g != WL.VN30]
    fd = fund_map.get(code.upper(), {})
    def fmt(v, f_):
        try: return f_.format(float(v)) if pd.notna(v) else "Chưa có"
        except (TypeError, ValueError): return "Chưa có"
    return {"Tên": (str(fd["Tên công ty"]).strip() if isinstance(fd.get("Tên công ty"), str) else ""),
            "Ngành": ", ".join(sectors) if sectors else "Khác / chưa phân loại",
            "Vốn hóa": fmt(cap_map.get(code.upper()), "{:,.0f} tỷ"),
            "P/B": fmt(fd.get("P/B"), "{:.2f}"), "ROE": fmt(fd.get("ROE"), "{:.1f}%"),
            "P/E": fmt(fd.get("P/E"), "{:.1f}"), "EPS": fmt(fd.get("EPS"), "{:,.0f}"),
            "BVPS": fmt(fd.get("Giá trị sổ sách"), "{:,.0f}"), "KLGD MA20": fmt(fd.get("KLGD MA20"), "{:,.0f}"),
            "Xếp hạng": (f"{int(fd['Xếp hạng'])} (TC {int(fd['Xếp hạng tài chính'])} · KD {int(fd['Xếp hạng kinh doanh'])}) · {fd.get('Bảng xếp hạng', '')}"
                         if pd.notna(fd.get("Xếp hạng")) and pd.notna(fd.get("Xếp hạng tài chính")) and pd.notna(fd.get("Xếp hạng kinh doanh")) else "")}


def _wb_ma_of(code: str) -> dict:
    """{20|50|200: (giá trị MA ngày, % giá đóng cửa so với MA)}; thiếu lịch sử thì bỏ qua."""
    g = df[df["Mã"].astype(str).str.upper() == str(code).upper()].sort_values("Ngày")
    c = pd.to_numeric(g["Giá đóng cửa"], errors="coerce").dropna()
    out = {}
    if c.empty:
        return out
    last = float(c.iloc[-1])
    for n in (20, 50, 200):
        if len(c) >= n and float(c.tail(n).mean()):
            m = float(c.tail(n).mean())
            out[n] = (m, (last / m - 1) * 100)
    return out


def _wb_scroll_to(code: str):
    """Cuộn tới thẻ của mã (sau khi bấm "Xem thêm" ở dạng Bảng) và viền sáng 4 giây."""
    import streamlit.components.v1 as components
    components.html("""<script>
const code=%s;let tries=0;
function go(){const d=window.parent.document;
 const el=[...d.querySelectorAll('[class*="st-key-wbcard-"]')].find(e=>[...e.classList].some(c=>c.startsWith('st-key-wbcard-')&&c.endsWith('-'+code)));
 if(el){el.scrollIntoView({behavior:'smooth',block:'center'});el.classList.add('wb-focus');setTimeout(()=>el.classList.remove('wb-focus'),4000);}
 else if(tries++<24)setTimeout(go,250);}
go();</script>""" % json.dumps(code), height=0)


def _wb_card(r, group):
    gi = WB.BUY_GROUPS.index(group)
    with st.container(key=f"wbcard-{gi}-{r['Mã']}"):
        div_html = DV.html(divergence_cached(frames, str(r["Mã"]), DATA_KEY + "|" + E.ENGINE_VERSION + "|dv1"))
        st.markdown(WB.card_html(r, group, _wb_meta(str(r["Mã"])), div_html, _ma_summary_html(str(r["Mã"])), _wy_note(r["Mã"]), _lean_html(r["Mã"]), _min_trading(), "", _action_html(r["Mã"])), unsafe_allow_html=True)
        if st.button("📊 Xem biểu đồ", key=f"wb_{group}_{r['Mã']}", use_container_width=True):
            st.session_state["selected_code"] = r["Mã"]
            for _k in ("mtf_code", "tab_code"):
                st.session_state[_k] = r["Mã"]
            NAV.goto("Cổ phiếu", "Tổng quát")


# ------------------------------------------------------------------ THẺ DÙNG CHUNG CHO CÁC TRANG DANH SÁCH
# Tăng mạnh / Giảm mạnh / Đang phục hồi / Danh sách cảnh báo / Bán - Chốt lời dùng đúng thẻ của Chờ mua, Mua ngay, Watchlist
# (waiting_buy.card_html + nút "Xem biểu đồ", lưới 3 cột, ô lọc, "Hiện tất cả"). Chỉ khác nhãn huy hiệu và một dòng ghi chú.
TONE_UI = {      # tone -> (nhãn trên huy hiệu, màu huy hiệu g/a/r/v/n, gợi ý hành động)
    "sell":    ("BÁN", "r", "Đang có lãi: chốt lời. Đang lỗ: cân nhắc cắt lỗ hoặc hạ tỷ trọng."),
    "tp":      ("CHỐT LỜI", "a", "Đang có lãi: chốt lời. Đang lỗ: cân nhắc cắt lỗ hoặc hạ tỷ trọng."),
    "risk":    ("THEO DÕI SUY YẾU", "r", sell_card.TONES["risk"]["hint"]),
    "over":    ("KHÔNG MUA ĐUỔI", "a", sell_card.TONES["over"]["hint"]),
    "surge":   ("TĂNG MẠNH", "g", sell_card.TONES["surge"]["hint"]),
    "plunge":  ("GIẢM MẠNH", "r", sell_card.TONES["plunge"]["hint"]),
    "recover": ("ĐANG PHỤC HỒI", "v", sell_card.TONES["recover"]["hint"]),
    "dry":     ("CẠN CUNG", "c", sell_card.TONES["dry"]["hint"]),
}


def _open_chart_of(code: str):
    st.session_state["selected_code"] = code
    for _k in ("mtf_code", "tab_code"):
        st.session_state[_k] = code
    NAV.goto("Cổ phiếu", "Tổng quát")


def _tone_card(r, tone: str, key: str):
    """Một thẻ ở các trang danh sách. tone = sell (tự tách BÁN / CHỐT LỜI theo cột 'Hành động bán'), tp, risk, over, surge, plunge, recover."""
    r = r.copy()
    code = str(r["Mã"])
    if tone == "sell" and str(r.get("Hành động bán")) == "CHỐT LỜI":
        tone = "tp"
    label, badge, hint = TONE_UI[tone]
    r["Trạng thái"] = label
    r["Lý do"] = re.sub(r"^\s*(BÁN|CHỐT LỜI)\s*:\s*", "", str(r.get("Lý do") or ""), flags=re.I)      # nhãn huy hiệu đã nói rõ, bỏ tiền tố
    if tone == "plunge":
        v, fmt = r.get("Giảm từ đỉnh %"), "Đã giảm {:.0f}% từ đỉnh"
    elif tone == "surge":
        v, fmt = r.get("Tăng từ đáy hiện tại %"), "Đã tăng {:.0f}% từ đáy"
    else:
        v, fmt = r.get("Tăng từ đáy %"), "Đã tăng {:.0f}% từ đáy"
    gain = fmt.format(float(v)) + ". " if v is not None and pd.notna(v) else ""
    if tone == "dry":      # thay dòng "Đã tăng ... từ đáy" bằng khối lượng phiên cuối và các nguồn báo cạn cung
        vr_ = r.get("Vol / MA20 Vol")
        gain = (f"Khối lượng phiên cuối = {float(vr_):.2f} lần MA20 Vol. " if vr_ is not None and pd.notna(vr_) else "") \
            + "Nguồn: " + " · ".join(r.get("Nguồn cạn cung") or []) + ". "
    ctx = f'<div class="wb-sub" style="margin:-4px 0 12px">{htmllib.escape(gain + hint)}</div>'
    with st.container(key=f"wbcard-{tone}-{code}"):          # tiền tố wbcard- để ăn CSS thẻ và cuộn tới thẻ (_wb_scroll_to)
        div_html = DV.html(divergence_cached(frames, code, DATA_KEY + "|" + E.ENGINE_VERSION + "|dv1"))
        st.markdown(WB.card_html(r, badge, _wb_meta(code), div_html, _ma_summary_html(code), _wy_note(code), _lean_html(code),
                                 _min_trading(), ctx, _action_html(code)), unsafe_allow_html=True)
        if st.button("📊 Xem biểu đồ", key=f"{key}_chart_{code}", use_container_width=True):
            _open_chart_of(code)


def _tone_limit(d: pd.DataFrame, key: str) -> pd.DataFrame:
    """Giống Mua ngay: hiện WB_PER_GROUP thẻ đầu, tick 'Hiện tất cả' để xem hết."""
    show_all = len(d) > WB_PER_GROUP and st.checkbox(f"Hiện tất cả {len(d)} mã", key=f"{key}_all")
    return d if show_all else d.head(WB_PER_GROUP)


def _tone_grid(shown: pd.DataFrame, total: int, tone, key: str):
    cols = st.columns(3)
    for i, (_, r) in enumerate(shown.iterrows()):
        with cols[i % 3]:
            _tone_card(r, tone(r) if callable(tone) else tone, key)
    if total > len(shown):
        st.caption(f"Đang hiển thị {len(shown)}/{total} mã có thứ tự ưu tiên cao nhất.")


def _tone_filters(d: pd.DataFrame, key: str) -> pd.DataFrame:
    """Ô Tìm mã + Nhóm ngành, cùng bố cục với Mua ngay."""
    f1, f2 = st.columns([1.2, 3])
    q = f1.text_input("Tìm mã", "", key=f"{key}_q", placeholder="🔍 Tìm mã...").upper().strip()
    inds = f2.multiselect("Nhóm ngành", sorted({x.strip() for t_ in d["Nhóm"] for x in str(t_).split(",") if x.strip()}),
                          key=f"{key}_ind", placeholder="Tất cả nhóm")
    if q:
        d = d[d["Mã"].astype(str).str.contains(q, regex=False)]
    if inds:
        d = d[d["Nhóm"].apply(lambda t_: any(i in [x.strip() for x in str(t_).split(",")] for i in inds))]
    return d


def _chip(code, color: str, linked) -> str:
    """Mã trong 'Danh sách tổng hợp': bấm để cuộn tới thẻ (chỉ khi thẻ đang hiển thị)."""
    c = htmllib.escape(str(code))
    if linked is not None and str(code) not in linked:
        return f'<span style="color:{color};font-weight:600;opacity:.7">{c}</span>'
    return (f'<a class="sc-jump" href="#sc-{c}" data-code="{c}" '
            f'style="color:{color};font-weight:600;text-decoration:none;cursor:pointer">{c}</a>')


def _chip_box(sub: str, chips: str) -> str:
    return (f'<div style="margin:6px 0 14px;padding:12px 14px;border:1px solid var(--line);border-radius:8px;background:var(--card);'
            f'line-height:1.9;font-size:15px"><div style="font-size:12px;color:var(--muted);margin-bottom:4px">{sub}</div>{chips}</div>')


def _wb_filters(d: pd.DataFrame, states: list[str]) -> pd.DataFrame:
    c1, c2, c3 = st.columns([1.2, 2, 2])
    q = c1.text_input("Tìm mã", "", key="wb_q", placeholder="🔍 Tìm mã...").upper().strip()
    inds = c2.multiselect("Nhóm ngành", sorted({x.strip() for t in d["Nhóm"] for x in str(t).split(",")}),
                          key="wb_ind", placeholder="Tất cả nhóm")
    sts = c3.multiselect("Trạng thái", states, key="wb_st", placeholder="Tất cả trạng thái")
    if q:
        d = d[d["Mã"].str.contains(q, regex=False)]
    if inds:
        d = d[d["Nhóm"].apply(lambda t: any(i in [x.strip() for x in str(t).split(",")] for i in inds))]
    if sts:
        d = d[d["Trạng thái"].isin(sts)]
    return d


def page_wait_buy():
    st.title("🛒 Chờ mua")
    header()
    st.caption("Danh sách theo dõi & khuyến nghị cho các cơ hội mua trong tuần. Độc lập với mục Lọc tất cả CP và Backtest. "
               "Chỉ gồm mã có xu hướng đủ khỏe; mã đang phục hồi nằm ở mục **Đang phục hồi**; mã tăng quá đà, suy yếu hoặc không có điểm mua nằm ở mục **Danh sách cảnh báo**.")
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)
    t = _wb_table()
    _now = set(_buy_now_table(t)["Mã"])      # mã "Vào được ngay" đã nằm ở mục Mua ngay, không lặp lại ở Chờ mua
    buy = t[t["Danh sách"].isin(WB.BUY_GROUPS) & ~t["Mã"].isin(_now)]
    if _now:
        st.caption(f"{len(_now)} mã đang ở trạng thái **✔ Vào được ngay** đã chuyển sang mục **Mua ngay**, không hiển thị ở đây.")
    m = st.columns(4)
    m[0].metric("TỔNG SỐ MÃ CHỜ MUA", f"{len(buy)} mã")
    for col, grp in zip(m[1:], WB.BUY_GROUPS):
        col.metric(grp.upper(), int((buy["Danh sách"] == grp).sum()))
    with st.expander("ℹ️ Quy tắc phân loại 9 trạng thái"):
        st.markdown(
            "- **Điểm mua đã xác nhận**: *Đã có tín hiệu mua* (thuật toán chính phát tín hiệu trong "
            f"{WB.CFG['buy_lookback']} phiên, giá chưa cao hơn {WB.CFG['buy_max_chase']:.0f}% so với giá phát tín hiệu) · "
            f"*Điểm mua đẹp* (uptrend, giá test EMA20 / MA50 / MA10-20 tuần / đáy nền trong {WB.CFG['support_touch']:.0f}%, "
            f"Vol 5 phiên ≤ {WB.CFG['dry_vol']:.1f} lần MA20 Vol, R:R ≥ {WB.CFG['min_rr']:.0f}; hoặc **bất kỳ mã nào ở nhóm Sắp có điểm mua / Theo dõi thêm** mà giá đã vào vùng mua "
            f"và RSI có phân kỳ ẩn tăng \"Xác nhận tiếp diễn\" thì tự nâng lên *Điểm mua đẹp*. Ngược lại, mã có phân kỳ RSI xấu (giảm) còn hiệu lực ở khung Ngày/Tuần không được nâng, và mã đang là *Điểm mua đẹp* / *Đã có tín hiệu mua* sẽ hạ xuống *Theo dõi điểm mua*).\n"
            "- **Sắp có điểm mua**: *Theo dõi điểm mua* (uptrend, điều chỉnh lành mạnh) · *Gần vùng mua, cần thêm xác nhận* "
            "(sát kháng cự / hỗ trợ, cần 1 phiên bứt phá hoặc đảo chiều) · *Chớm tăng giá* (dòng tiền sớm, chưa bứt nền) · "
            "*Tích lũy / Siết nền giá* (biên độ hẹp, Vol cạn, MA hội tụ).\n"
            "- **Theo dõi thêm**: *Có dấu hiệu cải thiện* (đáy sau cao hơn đáy trước) · *Chờ xác nhận* (mô hình đảo chiều chưa được MA/thanh khoản xác nhận) · "
            "*Chỉ đưa vào khi xu hướng không quá yếu* (điều kiện biên, có dòng tiền hỗ trợ).\n\n"
            "Hệ thống dùng EMA10/EMA20/MA50 ngày + MA10/MA20 tuần, Vol so với MA20 Vol, biên độ nền 5-10 phiên và hỗ trợ/kháng cự gần nhất. "
            "Ngưỡng nằm trong `CFG` của `waiting_buy.py`. Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
    if buy.empty:
        st.info("Hiện chưa có mã nào đạt điều kiện chờ mua.")
        return
    buy = _wb_filters(buy, [s for g_ in WB.BUY_GROUPS for s in WB.STATES_BY_GROUP[g_]])
    focus = st.session_state.pop("wb_focus", None)   # mã vừa bấm "Xem thêm" ở dạng Bảng
    st.session_state.setdefault("wb_view", "Thẻ")
    view = st.segmented_control("Kiểu hiển thị", ["Thẻ", "Bảng"], key="wb_view") or "Thẻ"
    for grp in WB.BUY_GROUPS:
        d = WB.sort_group(buy[buy["Danh sách"] == grp], grp)
        st.divider()
        st.subheader(f"{grp} ({len(d)})")
        st.caption(WB_HELP[grp])
        if d.empty:
            st.caption("Không có mã nào.")
            continue
        if view == "Bảng":
            _sec = lambda c_: ", ".join(g_ for g_ in MEMBER.get(c_, []) if g_ != WL.VN30) or "Khác"
            st.markdown(WB.table_html(d, grp, _sec, _wb_ma_of), unsafe_allow_html=True)
            st.caption("Giá, vùng mua, cắt lỗ, mục tiêu tính theo ATR (đơn vị nghìn đồng), % so với giá vào. "
                       "Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
            continue
        _codes = list(d["Mã"])
        need_all = bool(focus) and focus in _codes and _codes.index(focus) >= WB_PER_GROUP   # mã cần xem nằm ngoài 24 thẻ đầu
        show_all = need_all or (len(d) > WB_PER_GROUP and st.checkbox(f"Hiện tất cả {len(d)} mã", key=f"wb_all_{grp}"))
        cols = st.columns(3)
        for i, (_, r) in enumerate(d.head(len(d) if show_all else WB_PER_GROUP).iterrows()):
            with cols[i % 3]:
                _wb_card(r, grp)
        if len(d) > WB_PER_GROUP and not show_all:
            st.caption(f"Đang hiển thị {WB_PER_GROUP}/{len(d)} mã có thứ tự ưu tiên cao nhất.")
    if focus and view == "Thẻ":
        _wb_scroll_to(focus)


def _buy_now_table(t: pd.DataFrame) -> pd.DataFrame:
    """Mua ngay chỉ là bộ lọc trên bảng Chờ mua; tuyệt đối không tự tính lại vùng mua.
    Giữ nguyên Vùng mua từ/đến, Giá vào, Stop Loss và mục tiêu đã tính bởi waiting_buy.py.
    Chỉ lấy mã có hành động Vào ngay và không có tín hiệu BÁN / CHỐT LỜI."""
    d = t[t["Danh sách"].isin(WB.BUY_GROUPS) & (t["Hành động"] == "Vào ngay") & t["Vùng mua từ"].notna()].copy()
    if "Hành động bán" in d.columns:
        d = d[~d["Hành động bán"].isin(["BÁN", "CHỐT LỜI"])]
    return WB.sort_group(d, WB.G1)


def page_buy_now():
    st.title("⚡ Mua ngay")
    header()
    st.caption("Các mã có thể vào lệnh ngay: đã có tín hiệu mua hoặc đang test hỗ trợ với khối lượng cạn, và giá đang nằm trong vùng mua. "
               "Lọc từ mục **Chờ mua** (nhóm Điểm mua đã xác nhận), bỏ các mã đã có tín hiệu BÁN / CHỐT LỜI. "
               "Nên chia lệnh và tuân thủ mức cắt lỗ trên thẻ. Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)
    d = _buy_now_table(_wb_table())
    m = st.columns(3)
    m[0].metric("MÃ CÓ THỂ VÀO NGAY", f"{len(d)} mã")
    for col, stt in zip(m[1:], (WB.BUY_SIGNAL, WB.GOOD_ENTRY)):
        col.metric("MUA" if stt == WB.GOOD_ENTRY else stt.upper(), int((d["Trạng thái"] == stt).sum()))
    if d.empty:
        st.info("Hiện chưa có mã nào ở trạng thái Mua ngay. Xem mục **Chờ mua** để theo dõi các mã sắp có điểm mua.")
        return
    f1, f2 = st.columns([1.2, 3])
    q = f1.text_input("Tìm mã", "", key="bn_q", placeholder="🔍 Tìm mã...").upper().strip()
    inds = f2.multiselect("Nhóm ngành", sorted({x.strip() for t_ in d["Nhóm"] for x in str(t_).split(",") if x.strip()}),
                          key="bn_ind", placeholder="Tất cả nhóm")
    if q:
        d = d[d["Mã"].astype(str).str.contains(q, regex=False)]
    if inds:
        d = d[d["Nhóm"].apply(lambda t_: any(i in [x.strip() for x in str(t_).split(",")] for i in inds))]
    if d.empty:
        st.info("Không có mã nào phù hợp bộ lọc.")
        return
    show_all = len(d) > WB_PER_GROUP and st.checkbox(f"Hiện tất cả {len(d)} mã", key="bn_all")
    cols = st.columns(3)
    for i, (_, r) in enumerate(d.head(len(d) if show_all else WB_PER_GROUP).iterrows()):
        with cols[i % 3]:
            if r["Trạng thái"] in (WB.BUY_SIGNAL, WB.GOOD_ENTRY):      # nhãn trên thẻ Mua ngay: "MUA" (tên trạng thái trong dữ liệu giữ nguyên)
                r = r.copy()
                r["Trạng thái"] = "MUA"
            _wb_card(r, str(r["Danh sách"]))
    if len(d) > WB_PER_GROUP and not show_all:
        st.caption(f"Đang hiển thị {WB_PER_GROUP}/{len(d)} mã có thứ tự ưu tiên cao nhất.")
    _rt_focus_scroll()


def page_sector_ranking():
    """Ngành > Vị thế cổ phiếu ngành: dùng đúng thẻ MUA / CHỜ MUA, thêm khối Vị thế trong ngành."""
    header()
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)
    t = _wb_table()
    _now = set(_buy_now_table(t)["Mã"])      # cùng quy tắc nhãn MUA như mục Mua ngay
    _, fund_map = _wb_meta_maps(WY_KEY)

    def _card(r, ctx_html, vi):
        r = r.copy()
        if r["Mã"] in _now and r["Trạng thái"] in (WB.BUY_SIGNAL, WB.GOOD_ENTRY):
            r["Trạng thái"] = "MUA"
        code = str(r["Mã"])
        with st.container(key=f"wbcard-sr{vi}-{code}"):
            div_html = DV.html(divergence_cached(frames, code, DATA_KEY + "|" + E.ENGINE_VERSION + "|dv1"))
            st.markdown(WB.card_html(r, str(r["Danh sách"]), _wb_meta(code), div_html, _ma_summary_html(code),
                                     _wy_note(code), _lean_html(code), _min_trading(), ctx_html, _action_html(code)), unsafe_allow_html=True)
            if st.button("📊 Xem biểu đồ", key=f"sr_chart_{vi}_{code}", use_container_width=True):
                st.session_state["selected_code"] = code
                for _k in ("mtf_code", "tab_code"):
                    st.session_state[_k] = code
                NAV.goto("Cổ phiếu", "Tổng quát")

    SR.render(raw, DATA_KEY, res_df, t, WL.GROUPS, fund_map, _card, mkt)


def _wl_card(r, u, ver):
    """Thẻ Watchlist: cùng thẻ với mục Chờ mua (+ khối Vị thế của tôi, nút Xem biểu đồ / Bỏ theo dõi)."""
    code = str(r["Mã"])
    with st.container(key=f"wbcard-wl-{code}"):          # tiền tố wbcard- để ăn CSS thẻ của waiting_buy
        div_html = DV.html(divergence_cached(frames, code, DATA_KEY + "|" + E.ENGINE_VERSION + "|dv1"))
        st.markdown(WB.card_html(r, str(r["Danh sách"]), _wb_meta(code), div_html, _ma_summary_html(code), _wy_note(code), _lean_html(code), _min_trading(), "", _action_html(code)), unsafe_allow_html=True)
        pos = MW.position_html(u, r["Giá"])
        if pos:
            st.markdown(pos, unsafe_allow_html=True)
        b1, b2 = st.columns([3, 2])
        if b1.button("📊 Xem biểu đồ", key=f"wl_chart_{code}", use_container_width=True):
            st.session_state["selected_code"] = code
            for _k in ("mtf_code", "tab_code"):
                st.session_state[_k] = code
            NAV.goto("Cổ phiếu", "Tổng quát")
        if b2.button("🗑 Bỏ theo dõi", key=f"wl_rm_{code}", use_container_width=True):
            MW.remove_code(code)
            st.session_state["wl_ver"] = ver + 1
            st.rerun()


def page_watchlist():
    st.title("⭐ Watchlist")
    header()
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)

    def _open_chart(code: str):
        st.session_state["selected_code"] = code
        for _k in ("mtf_code", "tab_code"):
            st.session_state[_k] = code
        NAV.goto("Cổ phiếu", "Tổng quát")

    MW.render(_wb_table(), res_df, _open_chart, _wl_card)
    _rt_focus_scroll()


def page_my_portfolio():
    st.title("💼 Cổ phiếu của tôi")
    header()

    def _open_chart(code: str):
        st.session_state["selected_code"] = code
        for _k in ("mtf_code", "tab_code"):
            st.session_state[_k] = code
        NAV.goto("Cổ phiếu", "Tổng quát")

    MP.render(_wb_table(), res_df, _open_chart, latest_date)


def page_realtime_filter():
    """Bộ lọc Realtime: chọn ngành / mã -> sơ đồ tư duy: mã đang nằm ở mục nào, ý chính của mục, và nhánh cơ bản."""
    st.title("🧭 Bộ lọc Realtime")
    header()
    t = _wb_table()
    cap_map, fund_map = _wb_meta_maps(WY_KEY)
    now = set(_buy_now_table(t)["Mã"])
    vol = res_df.set_index("Mã")["Vol/Avg10"] if "Vol/Avg10" in res_df.columns else None
    try:
        _wl_df = MW.load()
        wl = set(_wl_df["Mã"].astype(str).str.upper())
        wl_pos = _wl_df.set_index("Mã").to_dict("index")
    except Exception:
        wl, wl_pos = set(), {}

    def _open_chart(code: str):
        st.session_state["selected_code"] = code
        for _k in ("mtf_code", "tab_code"):
            st.session_state[_k] = code
        NAV.goto("Cổ phiếu", "Tổng quát")

    def _mtf(code: str):
        try:
            A = {t_: analyze_cached(frames, code, t_, DATA_KEY) for t_ in ("M", "W", "D")}
            return E.mtf_conclusion(A), A
        except Exception:
            return None, None

    SM.render(t, cap_map, fund_map, now, wl, vol, _open_chart, _mtf, lambda c_: WY_TABLE.get(str(c_)), wl_pos, _action_html,
              {str(r_["Mã"]): r_["Nguồn cạn cung"] for _, r_ in _dry_table().iterrows()})


def _move_page(kind: str):
    """Tăng mạnh / Giảm mạnh. Hai chế độ: biến động trong phiên cuối, hoặc so với đáy (tăng) / đỉnh (giảm) trong 120 phiên."""
    up = kind == "surge"
    st.title("🚀 Tăng mạnh" if up else "💥 Giảm mạnh")
    header()
    lbl_ses = "Tăng trong phiên" if up else "Giảm trong phiên"
    lbl_leg = "Tăng từ đáy" if up else "Giảm từ đỉnh"
    st.session_state.setdefault(f"mv_mode_{kind}", lbl_ses)
    mode = st.segmented_control("Chế độ", [lbl_ses, lbl_leg], key=f"mv_mode_{kind}",
                                label_visibility="collapsed") or lbl_ses
    by_leg = mode == lbl_leg
    if by_leg:
        st.caption(("Các mã đã **tăng mạnh từ đáy** thấp nhất 120 phiên tới giá hiện tại, xếp theo % tăng giảm dần. "
                    "Đã chạy xa nên **không mua đuổi**: chờ nhịp lùi về hỗ trợ, hoặc xem trạng thái ở mục **Chờ mua** / **Bán / Chốt lời**. "
                    if up else
                    "Các mã đã **giảm mạnh từ đỉnh** cao nhất 120 phiên tới giá hiện tại, xếp theo % giảm sâu nhất trước. "
                    "Chưa nên bắt đáy sớm: chờ giá dừng giảm và lấy lại hỗ trợ; mã có dấu hiệu tích lũy nằm ở mục **Đang phục hồi**. ")
                   + "Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
    else:
        st.caption(("Các mã **tăng mạnh** ở phiên cuối, xếp theo % tăng giảm dần. " if up else
                    "Các mã **giảm mạnh** ở phiên cuối, xếp theo % giảm sâu nhất trước. ") +
                   "Nên kết hợp với khối lượng và trạng thái ở mục **Chờ mua**; chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
    t = _wb_table().copy()
    col = ("Tăng từ đáy hiện tại %" if up else "Giảm từ đỉnh %") if by_leg else "Chg %"
    t = t[t[col].notna()]
    vol = res_df.set_index("Mã")["Vol/Avg10"] if "Vol/Avg10" in res_df.columns else None
    t["Vol/Avg10"] = t["Mã"].map(vol) if vol is not None else np.nan
    c1, c2, c3 = st.columns([1.6, 1.2, 3])
    if by_leg:
        _def, _lo, _hi, _step = (30, 15, 100, 5) if up else (20, 10, 80, 5)
        _opts = [20, 30, 50] if up else [15, 20, 30]
        _k = f"mv_thr_leg_{kind}"
        st.session_state.setdefault(_k, _def)
        qc = st.columns(len(_opts) + 1)
        qc[0].caption("Chọn nhanh")
        for qcol, o in zip(qc[1:], _opts):
            if qcol.button(f"{o}%", key=f"mv_q_{kind}_{o}", use_container_width=True):
                st.session_state[_k] = o
        thr = c1.slider("Ngưỡng %", _lo, _hi, step=_step, key=_k)
    else:
        thr = c1.slider("Ngưỡng % thay đổi giá", 1.0, 15.0, 4.0, 0.5, key=f"mv_thr_{kind}")
    vmin = c2.selectbox("Khối lượng", ["Tất cả", "≥ 1.0× TB10", "≥ 1.5× TB10", "≥ 2.0× TB10"],
                        index=0 if by_leg else 1, key=f"mv_vol_{kind}_{int(by_leg)}")
    d = t[t[col] >= thr] if (up or by_leg) else t[t[col] <= -thr]
    if vmin != "Tất cả":
        d = d[d["Vol/Avg10"] >= float(vmin.split("≥ ")[1].split("×")[0])]
    inds = c3.multiselect("Nhóm ngành", sorted({x.strip() for t_ in d["Nhóm"] for x in str(t_).split(",") if x.strip()}),
                          key=f"mv_ind_{kind}", placeholder="Tất cả nhóm")
    q = st.text_input("Tìm mã", "", key=f"mv_q_{kind}", placeholder="🔍 Tìm mã...").upper().strip()
    if q:
        d = d[d["Mã"].astype(str).str.contains(q, regex=False)]
    if inds:
        d = d[d["Nhóm"].apply(lambda t_: any(i in [x.strip() for x in str(t_).split(",")] for i in inds))]
    d = d.sort_values(col, ascending=(not up and not by_leg))
    if by_leg and not up:
        d = d.sort_values(col, ascending=False)
    st.metric("Tổng số mã", len(d))
    if d.empty:
        st.info("Không có mã nào đạt ngưỡng.")
        return
    _, _fm = _wb_meta_maps(WY_KEY)
    _ma = {c_: _wb_ma_of(c_) for c_ in d["Mã"]}
    d = d.assign(**{"MA20": d["Mã"].map(lambda c_: _ma[c_].get(20, (None, None))[0]),
                    "MA20 %": d["Mã"].map(lambda c_: _ma[c_].get(20, (None, None))[1]),
                    "MA50": d["Mã"].map(lambda c_: _ma[c_].get(50, (None, None))[0]),
                    "MA50 %": d["Mã"].map(lambda c_: _ma[c_].get(50, (None, None))[1])})

    def _why(r):
        v = r.get("Vol/Avg10")
        vt = f", khối lượng {float(v):.1f} lần trung bình 10 phiên" if pd.notna(v) else ""
        if by_leg:
            head = (f'Giá hiện tại đã tăng {float(r[col]):.0f}% so với đáy 120 phiên' if up
                    else f'Giá hiện tại đã giảm {float(r[col]):.0f}% so với đỉnh 120 phiên')
            return f'{head}; phiên gần nhất {float(r["Chg %"]):+.2f}%{vt}. Trạng thái hiện tại: {r["Danh sách"]}' if pd.notna(r["Chg %"]) \
                else f'{head}{vt}. Trạng thái hiện tại: {r["Danh sách"]}'
        return f'{"Tăng" if up else "Giảm"} {abs(float(r["Chg %"])):.2f}% trong phiên gần nhất{vt}. Trạng thái hiện tại: {r["Danh sách"]}'
    d = d.assign(**{"Lý do": d.apply(_why, axis=1)})
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)
    shown = _tone_limit(d, f"mv_{kind}_{int(by_leg)}")
    _sc = set(shown["Mã"].astype(str))
    _chips = ", ".join(_chip(c_, "var(--green)" if up else "var(--red)", _sc) for c_ in d["Mã"])
    if not up:      # Giảm mạnh: chia danh sách theo cấu trúc Wyckoff (khung Ngày), bấm mã cuộn xuống thẻ bên dưới
        _chips = sell_card.chips_by_structure(list(d["Mã"]), WY_TABLE, "var(--red)", linked=_sc)
        _sub = (f'Danh sách tổng hợp ({len(d)} mã) · chia theo cấu trúc Wyckoff khung Ngày: Tích lũy, Đi ngang, Phân phối, Chưa rõ cấu trúc. '
                'Bấm vào mã để xuống thẻ bên dưới')
    else:
        _sub = f'Danh sách tổng hợp ({len(d)} mã)'
    st.markdown(_chip_box(_sub, _chips), unsafe_allow_html=True)
    _tone_grid(shown, len(d), kind, f"mv_{kind}")
    _sell_jump_js()
    _rt_focus_scroll()
    with st.expander("Xem dạng bảng"):
        st.dataframe(d[["Mã", "Giá", "Chg %", col, "Vol/Avg10", "Score", "RS20", "Nhóm", "Danh sách"]].loc[:, lambda x: ~x.columns.duplicated()]
                     .reset_index(drop=True), hide_index=True,
                     column_config={"Giá": st.column_config.NumberColumn(format="%.2f"),
                                    "Chg %": st.column_config.NumberColumn(format="%.2f"),
                                    col: st.column_config.NumberColumn(format="%.1f"),
                                    "Vol/Avg10": st.column_config.NumberColumn("Vol / TB10", format="%.2f"),
                                    "Score": st.column_config.NumberColumn(format="%.1f"),
                                    "RS20": st.column_config.NumberColumn("RS vs VNI", format="%.2f")},
                     **_STRETCH_DF)


def page_surge():
    _move_page("surge")


def page_plunge():
    _move_page("plunge")


def _dry_table() -> pd.DataFrame:
    """Bảng Cạn cung (dry_supply.py): gộp mọi mục đang nói mã cạn cung; dùng chung cho trang Cạn cung và Bộ lọc Realtime."""
    t = _wb_table()
    now = set(_buy_now_table(t)["Mã"])
    return DS.build(res_df, t, WY_TABLE, df, now)


def _lean_of(codes) -> dict:
    """{mã: +1 / -1 / 0}: dự báo nghiêng tăng / giảm của biểu đồ khung Ngày (cùng phép tính với _lean_html)."""
    out = {}
    for c_ in codes:
        try:
            a = analyze_cached(frames, str(c_), "D", DATA_KEY)
            out[str(c_)] = int(a.get("dir", 0)) if a.get("enough") else 0
        except Exception:
            out[str(c_)] = 0
    return out


def page_dry_supply():
    st.title("🧊 Cạn cung")
    header()
    st.caption("Các mã mà **bất kỳ mục nào của app** đang ghi là cạn cung / khối lượng cạn, gộp vào một danh sách: cờ **Cạn cung** ở Lọc tất cả CP, "
               "trạng thái **Điểm mua đẹp** và **Tích lũy / Siết nền giá** ở Chờ mua / Mua ngay, và sự kiện **Spring / Test / LPS volume thấp** của Wyckoff (tích lũy Pha C/D). "
               "Mã được nhiều nguồn cùng báo xếp trước. Cạn cung chỉ cho biết lực bán đã yếu, chưa phải tín hiệu mua: xem vùng mua và cắt lỗ ở mục **Chờ mua**. "
               "Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)
    d = _dry_table()
    m = st.columns(5)
    m[0].metric("Tổng số mã", len(d))
    for col, src in zip(m[1:], DS.SOURCES):
        col.metric(src, int(d["Nguồn cạn cung"].map(lambda L, s=src: s in L).sum()) if not d.empty else 0, help=DS.SRC_HELP[src])
    if d.empty:
        st.info("Hiện chưa có mã nào cạn cung.")
        return
    d = _tone_filters(d, "dry")
    srcs = st.multiselect("Nguồn", list(DS.SOURCES), key="dry_src", placeholder="Tất cả nguồn")
    if srcs:
        d = d[d["Nguồn cạn cung"].apply(lambda L: any(s in L for s in srcs))]
    if d.empty:
        st.info("Không có mã nào phù hợp bộ lọc.")
        return
    shown = _tone_limit(d, "dry")
    _sc = set(shown["Mã"].astype(str))
    st.markdown(_chip_box(f"Danh sách tổng hợp ({len(d)} mã) · chia theo dự báo nghiêng tăng / nghiêng giảm (khung Ngày) · bấm vào mã để xuống thẻ bên dưới",
                          DS.chips_html(d, lambda c_: _chip(c_, "var(--accent)", _sc), _lean_of(d["Mã"]))), unsafe_allow_html=True)
    _tone_grid(shown, len(d), "dry", "dry")
    _sell_jump_js()
    _rt_focus_scroll()
    with st.expander("Xem dạng bảng"):
        st.dataframe(d.assign(**{"Nguồn": d["Nguồn cạn cung"].map(" · ".join)})[["Mã", "Giá", "Chg %", "Vol / MA20 Vol", "Số nguồn", "Nguồn", "Score", "RS20", "Nhóm", "Danh sách"]]
                     .reset_index(drop=True), hide_index=True,
                     column_config={"Giá": st.column_config.NumberColumn(format="%.2f"),
                                    "Chg %": st.column_config.NumberColumn(format="%.2f"),
                                    "Vol / MA20 Vol": st.column_config.NumberColumn(format="%.2f"),
                                    "Score": st.column_config.NumberColumn(format="%.1f"),
                                    "RS20": st.column_config.NumberColumn("RS vs VNI", format="%.2f")},
                     **_STRETCH_DF)


def page_recovering():
    st.title("🌱 Đang phục hồi")
    header()
    st.caption("Các mã KHÔNG nằm trong **Chờ mua**: đang hồi phục hoặc có dấu hiệu tích lũy sau nhịp giảm. "
               "Chỉ chuyển sang tab Chờ mua khi vượt MA50 / kháng cự (xác nhận xu hướng). "
               "Mã có thêm tín hiệu **BÁN / CHỐT LỜI** vẫn hiện ở đây và đồng thời ở mục **Bán / Chốt lời**.")
    t = _wb_table()
    d = t[t["Danh sách"] == WB.L_RECOVER].sort_values("Score", ascending=False)
    st.metric("Tổng số mã", len(d))
    if d.empty:
        st.info("Không có mã nào.")
        return
    _, _fm = _wb_meta_maps(WY_KEY)
    _ma = {c_: _wb_ma_of(c_) for c_ in d["Mã"]}
    d = d.assign(**{"MA20": d["Mã"].map(lambda c_: _ma[c_].get(20, (None, None))[0]),
                    "MA20 %": d["Mã"].map(lambda c_: _ma[c_].get(20, (None, None))[1]),
                    "MA50": d["Mã"].map(lambda c_: _ma[c_].get(50, (None, None))[0]),
                    "MA50 %": d["Mã"].map(lambda c_: _ma[c_].get(50, (None, None))[1])})
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)      # CSS thẻ (wb-*)
    d = _tone_filters(d, "rc")
    if d.empty:
        st.info("Không có mã nào phù hợp bộ lọc.")
        return
    shown = _tone_limit(d, "rc")
    _tone_grid(shown, len(d), "recover", "rc")
    _rt_focus_scroll()
    with st.expander("Xem dạng bảng"):
        st.dataframe(d[["Mã", "Giá", "MA20", "MA50", "Score", "RS20", "Nhóm", "Lý do"]].reset_index(drop=True), hide_index=True,
                     column_config={"Giá": st.column_config.NumberColumn(format="%.2f"),
                                    "MA20": st.column_config.NumberColumn(format="%.2f"),
                                    "MA50": st.column_config.NumberColumn(format="%.2f"),
                                    "Score": st.column_config.NumberColumn(format="%.1f"),
                                    "RS20": st.column_config.NumberColumn("RS vs VNI", format="%.2f")},
                     **_STRETCH_DF)


def page_alert_lists():
    st.title("⚠️ Danh sách cảnh báo")
    header()
    st.caption("Các mã KHÔNG nằm trong **Chờ mua**: xu hướng suy yếu, tăng quá đà. Mã đang phục hồi có mục riêng **Đang phục hồi**. "
               "Mã có thêm tín hiệu **BÁN / CHỐT LỜI** vẫn hiện ở đây và đồng thời ở mục **Bán / Chốt lời**.")
    t_all = t = _wb_table()      # một mã có thể nằm ở nhiều mục: mã có tín hiệu BÁN / CHỐT LỜI vẫn hiện ở đây nếu Danh sách của nó là cảnh báo
    lists = [(WB.L_RISK, "Xu hướng suy yếu", "Xu hướng suy yếu, chưa có tín hiệu bán: không mua mới, theo dõi sát."),
             (WB.L_OVERBOUGHT, "Tăng quá đà", "Cảnh báo không mua đuổi (Overbought).")]
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)
    _TONE_OF = {WB.L_RISK: "risk", WB.L_OVERBOUGHT: "over"}
    _CHIP_COL = {WB.L_RISK: "var(--txt2)", WB.L_OVERBOUGHT: "#F5B942"}
    for tab, (key, title, note) in zip(st.tabs([f"{ttl} ({int((t['Danh sách'] == k).sum())})" for k, ttl, _ in lists]), lists):
        with tab:
            st.caption(note)
            d = t[t["Danh sách"] == key].sort_values("Score", ascending=False)
            if d.empty:
                st.info("Không có mã nào.")
                continue
            d = _tone_filters(d, f"alert_{key}")      # bộ lọc nằm ngay trên Danh sách tổng hợp (mỗi tab có bộ lọc riêng)
            if d.empty:
                st.info("Không có mã nào khớp bộ lọc.")
                continue
            shown = _tone_limit(d, f"alert_{key}")
            _sc = set(shown["Mã"].astype(str))
            _chips = ", ".join(_chip(c_, _CHIP_COL[key], _sc) for c_ in d["Mã"])
            st.markdown(_chip_box(f"Danh sách tổng hợp ({len(d)} mã)", _chips), unsafe_allow_html=True)
            _tone_grid(shown, len(d), _TONE_OF[key], f"alert_{key}")
            _sell_jump_js()
            with st.expander("Xem dạng bảng"):
                st.dataframe(d[["Mã", "Giá", "Score", "RS20", "Nhóm", "Lý do"]].reset_index(drop=True), hide_index=True,
                             column_config={"Giá": st.column_config.NumberColumn(format="%.2f"),
                                            "Score": st.column_config.NumberColumn(format="%.1f"),
                                            "RS20": st.column_config.NumberColumn("RS vs VNI", format="%.2f")},
                             **_STRETCH_DF)
    _rt_focus_scroll()
    st.caption(f"{int((t_all['Danh sách'] == WB.L_NONE).sum())} mã thuộc nhóm “Không có điểm mua / Bắt buộc đứng ngoài” đã bị loại khỏi mọi danh sách cơ hội.")


def _sell_jump_js():
    """Bấm mã ở Danh sách tổng hợp -> cuộn mượt tới thẻ của mã đó và viền sáng 2 giây (không tải lại trang)."""
    import streamlit.components.v1 as components
    components.html("""<script>
const d=window.parent.document;
if(!d.__scJump2){d.__scJump2=true;
 d.addEventListener('click',function(e){
  const a=e.target.closest&&e.target.closest('a.sc-jump');if(!a)return;
  e.preventDefault();
  const code=a.dataset.code;
  const el=[...d.querySelectorAll('[class*="st-key-wbcard-"]')].find(x=>[...x.classList].some(c=>c.startsWith('st-key-wbcard-')&&c.endsWith('-'+code)));
  if(!el)return;
  el.scrollIntoView({behavior:'smooth',block:'center'});
  el.classList.add('wb-focus');setTimeout(()=>el.classList.remove('wb-focus'),2000);
 });}
</script>""", height=0)


def page_sell_list():
    st.title("🔴 Bán / Chốt lời")
    header()
    st.caption("Các mã đang có tín hiệu **BÁN** hoặc **CHỐT LỜI** theo nến cuối phiên mới nhất. "
               "**CHỐT LỜI**: đã có lãi lớn từ đáy (từ 20%), giá còn trên MA50 nhưng đà đang yếu đi hoặc đã tăng từ 50% từ đáy. "
               "**BÁN**: có tín hiệu bán và xu hướng đã yếu (dưới MA50, nến xả mạnh, rơi nhanh). "
               "Mã đã giảm từ 20% so với đỉnh không nằm ở đây vì bán lúc này đã quá muộn.")
    t = _wb_table()
    if "Hành động bán" not in t.columns:
        st.info("Chưa có dữ liệu tín hiệu bán. Hãy tải lại trang.")
        return
    d = t[t["Hành động bán"].isin(["BÁN", "CHỐT LỜI"])]
    n_sell, n_tp = int((d["Hành động bán"] == "BÁN").sum()), int((d["Hành động bán"] == "CHỐT LỜI").sum())
    st.markdown(   # flex 1 hàng ngang, không bị Streamlit xếp chồng trên điện thoại (st.columns tự xuống dòng ở màn hẹp)
        "<style>.sell-m{display:flex;flex-wrap:nowrap;gap:10px;margin:4px 0 12px}"
        ".sell-m>div{flex:1 1 0;min-width:0}"
        ".sell-m .k{font-size:13px;color:var(--muted);white-space:nowrap}"
        ".sell-m .v{font-size:clamp(24px,7vw,36px);font-weight:400;line-height:1.2;color:var(--txt2)}</style>"
        f'<div class="sell-m"><div><div class="k">Tổng số mã</div><div class="v">{len(d)}</div></div>'
        f'<div><div class="k">BÁN</div><div class="v">{n_sell}</div></div>'
        f'<div><div class="k">CHỐT LỜI</div><div class="v">{n_tp}</div></div></div>', unsafe_allow_html=True)
    pick = st.segmented_control("Lọc", ["Tất cả", "BÁN", "CHỐT LỜI"], default="Tất cả", key="sell_list_filter",
                                label_visibility="collapsed") or "Tất cả"
    if pick != "Tất cả":
        d = d[d["Hành động bán"] == pick]
    f1, f2 = st.columns([1.2, 3])
    q = f1.text_input("Tìm mã", "", key="sell_q", placeholder="🔍 Tìm mã...").upper().strip()
    inds = f2.multiselect("Nhóm ngành", sorted({x.strip() for t_ in d["Nhóm"] for x in str(t_).split(",") if x.strip()}),
                          key="sell_ind", placeholder="Tất cả nhóm")
    if q:
        d = d[d["Mã"].astype(str).str.contains(q, regex=False)]
    if inds:
        d = d[d["Nhóm"].apply(lambda t_: any(i in [x.strip() for x in str(t_).split(",")] for i in inds))]
    if d.empty:
        st.info("Không có mã nào.")
        return
    d = (d.assign(_o=d["Hành động bán"].map({"BÁN": 0, "CHỐT LỜI": 1})).sort_values(["_o", "Score"], ascending=[True, False])
          .drop(columns="_o"))
    st.markdown(f"<style>{WB.card_css(TH.is_dark())}</style>", unsafe_allow_html=True)
    shown = _tone_limit(d, "sell")
    _sc = set(shown["Mã"].astype(str))
    _chips = ", ".join(_chip(c_, "var(--red)" if a_ == "BÁN" else "#F5B942", _sc) for c_, a_ in zip(d["Mã"], d["Hành động bán"]))
    st.markdown(_chip_box('Danh sách tổng hợp ({} mã) · <span style="color:var(--red)">BÁN</span> · '
                          '<span style="color:#F5B942">CHỐT LỜI</span>'.format(len(d)), _chips), unsafe_allow_html=True)
    _tone_grid(shown, len(d), "sell", "sell")
    _sell_jump_js()
    _rt_focus_scroll()
    with st.expander("Xem dạng bảng"):
        st.dataframe(d[["Mã", "Hành động bán", "Giá", "Chg %", "Score", "RS20", "Nhóm", "Lý do"]].rename(columns={"Hành động bán": "Tín hiệu"})
                     .reset_index(drop=True), hide_index=True,
                     column_config={"Giá": st.column_config.NumberColumn(format="%.2f"),
                                    "Chg %": st.column_config.NumberColumn(format="%.2f"),
                                    "Score": st.column_config.NumberColumn(format="%.1f"),
                                    "RS20": st.column_config.NumberColumn("RS vs VNI", format="%.2f")},
                     **_STRETCH_DF)


# ------------------------------------------------------------------ HTML CARDS
def fp(x):
    """Giá giao dịch hiển thị 1 chữ số thập phân; không đổi giá trị tính toán."""
    try:
        value = round(float(x), 1)
        return f"{value:,.1f}"
    except (TypeError, ValueError):
        return "—"


def card(title, inner):
    return f'<div class="card"><div class="ct">{title}</div>{inner}</div>'


def row(label, value):
    return f'<div class="row"><span>{label}</span><b>{value}</b></div>'


def tag(text, kind):
    return f'<span class="tag tag-{kind}">{text}</span>'


def dir_kind(d):
    return "green" if d > 0 else "red" if d < 0 else "gray"


def _mtf_price_html(price, chg) -> str:
    """Giá phiên gần nhất cạnh mã: xanh nếu tăng so với phiên trước, đỏ nếu giảm, xám nếu đứng giá / chưa có phiên so sánh."""
    try:
        price = float(price)
    except (TypeError, ValueError):
        return ""
    if pd.isna(price):
        return ""
    chg = float(chg) if chg is not None and pd.notna(chg) else None
    if chg is None:
        col, sub = "var(--muted)", ""
    elif chg > 1e-9:
        col, sub = "var(--green)", f"▲ {price - price / (1 + chg / 100):+,.2f} ({chg:+.2f}%)"
    elif chg < -1e-9:
        col, sub = "var(--red)", f"▼ {price - price / (1 + chg / 100):+,.2f} ({chg:+.2f}%)"
    else:
        col, sub = "var(--muted)", "— 0.00 (0.00%)"
    return (f'<div class="mtf-px" style="color:{col}"><b>{price:,.2f}</b>' + (f"<span>{sub}</span>" if sub else "") + "</div>")


def mtf_card(conc, A, code="", price=None, chg=None):
    code_html = f'<div class="mtf-code">{htmllib.escape(str(code))}</div>' if code else ""
    if code_html:       # giá hiện tại nằm cạnh mã
        code_html = f'<div class="mtf-right">{code_html}{_mtf_price_html(price, chg)}</div>'
    if conc is None:
        return card("Kết luận đa khung", f'<div class="mtf-top"><div class="muted">Chưa đủ dữ liệu ở cả 3 khung để kết luận.</div>{code_html}</div>')
    k = conc["kind"]
    # Tên mã nằm bên phải, cao bằng 2 hàng: tiêu đề "Kết luận đa khung" + kết luận (ƯU TIÊN MUA...)
    html = [f'<div class="mtf-top"><div><div class="ct">Kết luận đa khung</div><div class="big c-{k}" style="margin-bottom:0">{conc["verdict"]}</div></div>{code_html}</div>',
            f'<div class="muted" style="margin-top:6px">{conc["text"]}</div>',
            f'<div class="box">Nếu nến đóng ngay lúc này: <b class="c-{k}">{conc["verdict"]}</b></div>',
            row("Điểm đa khung (-100 đến +100)", f'{conc["score"]:+.0f}'), "<hr style='margin:8px 0'>"]
    for t in ("M", "W", "D"):
        a = A[t]
        head = f'<span><b>{E.TF_NAME[t]}</b> · <span class="muted">{E.TF_ROLE[t]}</span></span>'
        if a["enough"]:
            lab = "Tăng" if a["dir"] > 0 else "Giảm" if a["dir"] < 0 else "Ngang"
            right = f'{abs(a["bias"]):.0f}/100' + (" ⚠" if a["partial"] else " ✓")
            html.append(f'<div class="row">{head}<span>{tag(lab, dir_kind(a["dir"]))} &nbsp;<b>{right}</b></span></div>')
        else:
            html.append(f'<div class="row">{head}<span class="muted">thiếu dữ liệu ({a["n"]} nến)</span></div>')
    html.append('<div class="muted" style="margin-top:8px">Quy tắc: khung lớn (Tháng, Tuần) quyết định hướng đi, khung Ngày '
                'chọn điểm vào. Hai khung lớn cùng giảm thì không mua; khung lớn ngược nhau thì CHỜ. ⚠ = chưa đủ nến '
                'cho Ichimoku/EMA200 nên các chỉ báo đó chưa được tính điểm. Đây là xác suất, không phải chắc chắn: '
                'luôn đặt cắt lỗ.</div>')
    return f'<div class="card" id="mtf-conclusion">{"".join(html)}</div>'


def rsi_card(a, tf, code):
    """Thẻ Phân tích RSI: giá trị RSI(14) khung đang xem + phân kỳ RSI/giá khung M, W và D (cùng quy tắc thẻ ở mục Lọc tất cả CP)."""
    rsi = DV.rsi14(a["g"]["Giá đóng cửa"]).dropna()
    if rsi.empty:
        head = '<div class="muted">Chưa đủ dữ liệu để tính RSI(14).</div>'
    else:
        v, prev = float(rsi.iloc[-1]), float(rsi.iloc[-2]) if len(rsi) > 1 else float("nan")
        zone, kind = (("Quá mua (≥ 70)", "red") if v >= 70 else ("Quá bán (≤ 30)", "green") if v <= 30
                      else ("Vùng mạnh (50-70)", "green") if v >= 50 else ("Vùng yếu (30-50)", "amber"))
        slope = "" if pd.isna(prev) else (" · đang tăng" if v > prev else " · đang giảm" if v < prev else "")
        head = row(f"RSI(14) khung {E.TF_NAME[tf]}", f"<b>{v:.1f}</b>") + f'<div style="margin:6px 0 4px">{tag(zone, kind)}{slope}</div>'
    sigs = divergence_cached(frames, code, DATA_KEY + "|" + E.ENGINE_VERSION + "|dv1")
    body = (DV.html(sigs) if sigs else
            '<div class="muted" style="margin-top:6px">Chưa có tín hiệu phân kỳ RSI còn hiệu lực ở khung Tháng, Tuần và Ngày (khung Tháng cần khoảng 31 nến tháng trở lên).</div>')
    note = ('<div class="muted" style="margin-top:8px">Quy tắc: RSI(14) Wilder; so 2 đỉnh / 2 đáy giá gần nhất (pivot) với RSI tại đúng nến đó. '
            'Phân kỳ thường (giá HH/RSI LH, giá LL/RSI HL) và phóng đại (2 đỉnh/đáy bằng nhau) là cảnh báo đảo chiều; '
            'phân kỳ ẩn (giá HL/RSI LL, giá LH/RSI HH) là xác nhận tiếp diễn. Tín hiệu hết hạn khi giá vượt đỉnh / thủng đáy của pivot sau; '
            'pivot cần vài nến để xác nhận nên luôn trễ. Hiển thị cả khung M, W và D; chỉ để tham khảo, không phải khuyến nghị đầu tư.</div>')
    return card("Phân tích RSI", head + body + note)


SETUP_BT = {        # backtest 147 mã 2019-2026, vào mở cửa phiên sau, đã trừ phí 0,15%/chiều + thuế 0,1% + trượt giá 0,1%/chiều, T+2,
                    # thoát khi chạm cắt lỗ hoặc đóng cửa dưới Supertrend, tối đa 60 phiên: (số lệnh, lãi TB %, thắng %, R/lệnh)
    "BOTTOM": (603, 4.1, 37, 0.53), "BASE_HL": (1309, 2.8, 34, 0.36), "BREAKOUT": (3074, 1.5, 30, 0.25), "TREND": (3629, 3.0, 34, 0.50)}
SETUP_BASE = (5880, 2.1, 34, 0.31)      # vào ngẫu nhiên, cùng cách cắt lỗ và thoát


def setup_card(g_day):
    """Thẻ Phân loại trạng thái (khung Ngày): trạng thái giá, điểm vào, cắt lỗ, mục tiêu. Logic ở setups.py."""
    p = SU.plan(g_day)
    if p is None:
        return card("Phân loại trạng thái · khung Ngày", '<div class="muted">Chưa đủ dữ liệu (cần từ 130 phiên để tính Kijun 129).</div>')
    s_ = p["state"]
    head = tag(p["label"], p["tag"]) + (f' <span class="muted">báo cách đây {p["bars_ago"]} phiên</span>' if p["bars_ago"] else "")
    html = [head, f'<div class="muted" style="margin-top:8px">{p["text"]}</div>']
    box = []
    if p["entry"] is not None:
        lab = {"WATCH": "Giá kích hoạt (chờ vượt)", "TREND": "Giá hiện tại"}.get(s_, "Đỉnh nền vừa vượt")
        risk = (p["entry"] - p["stop"]) / p["entry"] * 100
        box += [row(lab, f'<b>{fp(p["entry"])}</b>'),
                row("Cắt lỗ", f'<span class="c-red">{fp(p["stop"])}</span> <span class="muted">−{risk:.1f}%</span>'),
                row("Mục tiêu 1 (2R)", f'<span class="c-green">{fp(p["t1"])}</span>'),
                row("Mục tiêu 2 (3R)", f'<span class="c-green">{fp(p["t2"])}</span>')]
        if p["st_line"] and p["st_up"]:
            box.append(row("Thoát khi đóng cửa dưới Supertrend", fp(p["st_line"])))
        if s_ in ("BOTTOM", "BASE_HL", "BREAKOUT") and p["ext"] is not None and p["ext"] > 0.05:
            html.append(f'<div class="muted" style="margin-top:6px;color:#F5B942">Giá hiện tại đã cao hơn điểm vào {p["ext"] * 100:.1f}%: đã chạy xa, tránh đuổi; chờ nhịp lùi về gần đỉnh nền.</div>')
    elif s_ == "RANGE":
        box += [row("Kháng cự (đường trên)", f'<span class="c-red">{fp(p["res"])}</span>'),
                row("Hỗ trợ (đường dưới)", f'<span class="c-green">{fp(p["sup"])}</span>')]
    box += [row("Tenkan 65 / Kijun 129", f'{fp(p["tenkan"])} / {fp(p["kijun"])}'),
            row("Mây Kumo (9-17-26)", f'{fp(p["cloud_bot"])} – {fp(p["cloud_top"])}'),
            row("RSI(14)", f'{p["rsi"]:.0f}')]
    html.append('<div class="box">' + "".join(box) + "</div>")
    html.append(f'<div class="muted" style="margin-top:6px">{tag("Động lượng RSI", p["rsi_kind"])} {p["rsi_note"]}</div>')
    if p["div_note"]:
        html.append(f'<div class="muted" style="margin-top:6px">{tag("Phân kỳ tăng", "green" if p["div"]["state"] == "confirmed" else "amber")} {p["div_note"]}</div>')
    if s_ in SETUP_BT:
        n, rt, w, rr = SETUP_BT[s_]
        bn, brt, bw, brr = SETUP_BASE
        html.append(f'<div class="muted" style="margin-top:8px">Backtest kiểu này ({n:,} lệnh, 147 mã, 2019-2026, đã trừ phí, thuế, trượt giá, T+2): '
                    f'lãi trung bình {rt:+.1f}%/lệnh, thắng {w}%, {rr:+.2f}R/lệnh. Vào ngẫu nhiên với cùng cách thoát: {brt:+.1f}%, thắng {bw}%, {brr:+.2f}R. '
                    'Tức là tỷ lệ thắng chỉ khoảng một phần ba; lợi nhuận đến từ vài lệnh lớn, và kết quả âm ở các năm 2019, 2022, 2024, 2026. '
                    'Chia nhỏ vốn, luôn đặt cắt lỗ; đây là công cụ lọc, không phải lệnh chắc thắng.</div>')
    elif s_ == "WEAK":
        html.append('<div class="muted" style="margin-top:6px">Trạng thái yếu nhất trong backtest: +0,8%/lệnh, 0,06R, thấp hơn nhiều so với vào ngẫu nhiên.</div>')
    elif s_ == "RANGE":
        html.append('<div class="muted" style="margin-top:6px">Mua sát hỗ trợ giữa Tenkan và Kijun cho kỳ vọng gần 0 và 50% lần bị quét cắt lỗ trong 10 phiên; '
                    'vượt đường trên kèm khối lượng mới có lợi thế (+2,3% sau 20 phiên so với mức nền +1,7%).</div>')
    html.append('<div class="muted" style="margin-top:6px">Cắt lỗ = mức thấp hơn giữa giá vào − 2 ATR và đáy nền − 1% (kẹp trong 3–12% rủi ro); với Xu hướng tăng lấy thêm đường Supertrend nếu chặt hơn.</div>')
    return card("Phân loại trạng thái · khung Ngày", "".join(html))


def forecast_card(a, tf):
    d, bias, total, fc = a["dir"], a["bias"], a["total"], a["fc"]
    last_ts = a["g"]["Ngày"].iat[-1]
    word = "nghiêng tăng" if d > 0 else "nghiêng giảm" if d < 0 else "đi ngang / chưa rõ"
    k = dir_kind(d)
    html = [f'<div class="row"><div class="big c-{k}">Dự báo: {word}</div>'
            f'<span class="muted">sau {E.TF_UNIT[tf]} {last_ts:%d/%m/%Y}</span></div>',
            f'<div class="bar"><div class="bg-{k}" style="width:{min(abs(bias), 100):.0f}%"></div></div>',
            f'<div class="muted">{abs(bias):.0f}/100 độ nghiêng của chỉ báo</div>']
    if fc:
        lbl = "Mục tiêu" if d > 0 else "Mục tiêu (kịch bản giảm)"
        html.append('<div class="box">'
                    + row("Vùng vào dự kiến", f'{fp(min(fc["lo"], fc["hi"]))}-{fp(max(fc["lo"], fc["hi"]))}')
                    + row(f"{lbl} 1", f'<span class="c-green">{fp(fc["t1"])}</span> <span class="muted">R:R 1:2</span>')
                    + row(f"{lbl} 2", f'<span class="c-green">{fp(fc["t2"])}</span> <span class="muted">R:R 1:3</span>')
                    + row("Cắt lỗ nếu sai", f'<span class="c-red">{fp(fc["sl"])}</span> <span class="muted">{fc["sl_pct"]:.2f}%</span>')
                    + "</div>")
        html.append(f'<div class="muted">Kịch bản cho khoảng {E.HORIZON} {E.TF_UNIT[tf]} tới. Đây là ước tính từ trạng thái hiện tại '
                    'của các chỉ báo (cắt lỗ = 1,5 ATR), chưa phải kết quả đã xảy ra; giá có thể đi ngược dự báo nên luôn cần cắt lỗ.</div>')
    else:
        html.append('<div class="box">Độ nghiêng dưới ngưỡng ±1.0: chưa có lợi thế rõ ràng, nên đứng ngoài và chờ.</div>')
    html.append('<div class="ct" style="margin-top:12px">Các chỉ báo đang nghiêng thế nào</div>')
    for name, s, mx, txt in a["items"]:
        ck = "green" if s > 0.04 else "red" if s < -0.04 else "gray"
        val = f"{s:+.1f}" if abs(s) > 0.04 else "0.0"
        html.append(f'<div class="item"><span class="chip chip-{ck}">{val}</span><b>{name}</b>'
                    f'<div class="muted" style="margin-left:50px">{txt}</div></div>')
    html.append(row("Tổng độ nghiêng", f'<span class="c-{k}">{total:+.1f} / {E.MAX_SCORE}</span>'))
    return card("Dự báo", "".join(html))


def backtest_card(a, tf, code, include_short):
    s = E.backtest_stats(a["trades"], a["n"], include_short)
    title = f"Backtest {code} khung {E.TF_NAME[tf]}"
    if s is None:
        return card(title, '<div class="muted">Chưa có lệnh mô phỏng nào đã đóng ở khung này.</div>')
    enough = s["n"] >= 20
    rec_ok = pd.notna(s["rec_exp"]) and s["rec_exp"] > 0
    if not enough:
        badge = tag("Chưa đủ lệnh để kết luận (cần ≥ 20)", "gray")
    elif s["exp"] > 0 and rec_ok:
        badge = tag("Kỳ vọng dương, đáng để theo dõi", "green")
    elif s["exp"] > 0:
        badge = tag("Kỳ vọng dương nhưng phần mới nhất chưa xác nhận", "amber")
    else:
        badge = tag("Kỳ vọng âm, không nên theo", "red")
    pf = "∞" if s["pf"] == float("inf") else f'{s["pf"]:.2f}'
    cnt = f'{s["n"]} (mua {s["buy"]}' + (f', bán {s["sell"]})' if include_short else ")")
    rec = f'{s["rec_n"]} lệnh, {s["rec_exp"]:+.2f}R' if s["rec_n"] else "chưa có lệnh"
    ideal = E.backtest_stats(a.get("trades_ideal", pd.DataFrame()), a["n"], include_short) if "trades_ideal" in a else None
    extra = []
    if ideal is not None:
        extra.append(row("Kỳ vọng lý tưởng (không phí, không T+2)", f'{ideal["exp"]:+.2f}R'))
        extra.append(row("Chênh lệch do thực tế giao dịch", f'{s["exp"] - ideal["exp"]:+.2f}R'))
    if s.get("skipped"):
        extra.append(row("Tín hiệu không mua được (khóa trần)", f'{s["skipped"]}'))
    html = [badge, '<div style="height:6px"></div>', row("Số lệnh", cnt), row("Tỷ lệ thắng", f'{s["win"]:.0f}%'),
            row("Kỳ vọng mỗi lệnh", f'{s["exp"]:+.2f}R'), row("Profit factor", pf),
            row("Sụt giảm tối đa", f'{s["mdd"]:.1f}R'), row("30% dữ liệu mới nhất", rec), *extra,
            '<div class="muted" style="margin-top:6px">Kỳ vọng = tỷ lệ thắng × lãi trung bình − tỷ lệ thua × lỗ trung bình, '
            'tính theo R (1R = mức rủi ro mỗi lệnh). Thắng nhiều chưa chắc có lời. Cần từ 20 lệnh trở lên và kỳ vọng '
            'dương ở cả phần dữ liệu mới nhất mới đáng tin. Tín hiệu Mua theo giá + khối lượng; vào ở giá mở cửa phiên kế tiếp, cắt lỗ 1,5 ATR, chốt 2R, giữ tối đa '
            '20 nến. Đã tính phí môi giới 0,15%/chiều, thuế bán 0,1%, trượt giá 0,1%/chiều, bước giá, T+2 (khung Ngày), gap qua cắt lỗ và phiên khóa trần/sàn '
            '(chỉnh ở BT_COST trong engine.py). Chưa tính thanh khoản thực tế và thiên lệch sống sót của rổ mã.' + ('' if include_short else ' Chỉ tính lệnh Mua (thị trường VN không bán khống).') + '</div>']
    return card(title, "".join(html))


def elliott_card(a):
    e = a["elliott"]
    return card("Sóng Elliott", tag(e["title"], e["tag"]) + f'<div class="muted" style="margin-top:8px">{e["text"]}</div>')


def wyckoff_card(a):
    w = a.get("wy")
    if not w:
        return card("Phân tích Wyckoff", '<div class="muted">Chưa thấy vùng đi ngang đủ rõ (tối thiểu 30 nến trong khung biên độ không quá 10%, chạm cả hai biên từ 2 lần). '
                                         'Giá đang ở trạng thái xu hướng hoặc biên quá rộng.</div>').replace('<div class="card">', '<div class="card" id="wyckoff-detail">', 1)
    k = {"buy": "green", "sell": "red"}.get(w["lean"], "gray")
    head = tag(WYK.label(w), k) + f' <span class="muted">khớp mẫu {w["score"]}%</span>'
    html = [head, f'<div class="muted" style="margin-top:8px">{w["summary"]}</div>']
    if w["kind"] != "unk" or w["trigger"]:
        html.append('<div class="box">' + row("Biên trên / dưới", f'{fp(w["tr"]["top"])} / {fp(w["tr"]["bot"])}')
                    + row("Số nến đi ngang · biên độ", f'{w["tr"]["L"]} nến · {(w["tr"]["top"] / w["tr"]["bot"] - 1) * 100:.1f}%')
                    + row(w["trigger"]["txt"], f'<b>{fp(w["trigger"]["p"])}</b>')
                    + row(w["inval"]["txt"], f'<b>{fp(w["inval"]["p"])}</b>') + "</div>")
    for e in sorted(w["events"], key=lambda x: -x["i"]):
        html.append(f'<div class="item"><span class="chip chip-{k}">{e["label"]}</span><b>{e["date"]:%d/%m/%Y}</b> · {fp(e["p"])}'
                    f'<div class="muted" style="margin-left:50px">{e["txt"]}</div></div>')
    if w["notes"]:
        html.append(f'<div class="muted" style="margin-top:6px">{" ".join(w["notes"])}</div>')
    html.append('<div class="muted" style="margin-top:6px">Wyckoff đọc cấu trúc giá và volume nên mang tính chủ quan. Vùng đi ngang chỉ tính khi biên độ không quá 10%; phiên đóng cửa vượt khung rồi quay lại khung cũ được ghi là breakout giả. '
                'Vùng còn cần biên chạm nhiều lần và giá cắt đường giữa nhiều lần; sự kiện dò theo volume và biên độ nến. Máy có thể gắn nhãn khác cách bạn đọc, '
                'và vẫn có thể thấy "cấu trúc" ngay trên dữ liệu ngẫu nhiên, nên chỉ dùng để quan sát cùng các chỉ báo khác, không tính vào điểm tín hiệu và backtest.</div>')
    return card("Phân tích Wyckoff", "".join(html)).replace('<div class="card">', '<div class="card" id="wyckoff-detail">', 1)


def zones_card(a):
    if not a["zones"]:
        return card("Vùng giá gần nhất", '<div class="muted">Chưa xác định được vùng hỗ trợ/kháng cự.</div>')
    html = []
    for z in a["zones"]:
        cls = "c-red" if z["kind"] == "Kháng cự" else "c-green"
        html.append(f'<div class="row"><span class="{cls}">{z["kind"]} ({z["n"]} lần chạm)</span>'
                    f'<b>{fp(z["lo"])}-{fp(z["hi"])}</b></div>')
    return card("Vùng giá gần nhất", "".join(html))


def signals_card(a, include_short):
    t = a["trades"]
    if t.empty:
        return card("Tín hiệu gần đây", '<div class="muted">Chưa có cảnh báo Mua/Bán nào ở khung này.</div>')
    html = []
    for _, r in t.tail(8).iloc[::-1].iterrows():
        buy = r["dir"] == 1
        ref = "" if (buy or include_short) else ' <span class="muted">(tham khảo)</span>'
        val = '<span class="muted">không mua được (khóa trần)</span>' if bool(r.get("skip", False)) else '<span class="muted">đang mở</span>' if r["open"] else (
            f'<span class="{"c-green" if r["R"] > 0 else "c-red"}">{r["R"]:+.2f}R</span>')
        html.append(f'<div class="row"><span class="{"c-green" if buy else "c-red"}"><b>{"Mua" if buy else "Bán"}</b> '
                    f'{r["Ngày"]:%d/%m/%Y}{ref}<br><span class="muted">{E.PV_LABEL.get(r["code"], "")}</span></span>'
                    f'<b>{val}</b></div>')
    html.append('<div class="muted" style="margin-top:6px">Mua/Bán theo giá + khối lượng. "Bán" là tín hiệu thoát/tránh mua; '
                'kết quả R của lệnh Bán chỉ là mô phỏng bán khống.</div>')
    return card("Tín hiệu gần đây", "".join(html))


def alert_banner(a, tf):
    now, prev = a["pv_now"], a["pv_prev"]
    unit = E.TF_UNIT[tf]
    if now:
        msg = f'**{"🟢 CẢNH BÁO MUA" if now["side"] > 0 else "🔴 CẢNH BÁO BÁN"}** ({E.PV_LABEL[now["code"]]}) · {now["text"]}'
        (st.success if now["side"] > 0 else st.error)(msg)
    else:
        extra = ""
        if prev:
            extra = (f' Cảnh báo gần nhất: **{"Mua" if prev["side"] > 0 else "Bán"}** ngày {prev["date"]:%d/%m/%Y} '
                     f'({prev["ago"]} {unit} trước): {E.PV_LABEL[prev["code"]]}.')
        st.info(f"Chưa có cảnh báo Mua/Bán ở {unit} mới nhất.{extra}")


# ------------------------------------------------------------------ BIỂU ĐỒ
def future_date(last, tf, k):
    if tf == "D":
        return last + pd.offsets.BDay(k)
    return last + (pd.Timedelta(weeks=k) if tf == "W" else pd.DateOffset(months=k))


DATE_GAP_PX = 34       # khe (px) giữa biểu đồ nến và khung bên dưới: chứa dải nhãn ngày + nhãn ngày của đường gióng
# Định dạng nhãn trục ngày chỉ dùng mã số (không cần ngôn ngữ), Plotly tự chọn theo bước chia khi zoom:
# ngày/tuần -> 24/10 · mỗi tháng -> Tháng 10 · mỗi 2-11 tháng -> T10/2026 · từ 1 năm -> 2026
DATE_TICK_STOPS = [
    dict(dtickrange=[None, 2500000000], value="%-d/%-m"),
    dict(dtickrange=[2500000000, 2700000000], value="Tháng %-m"),
    dict(dtickrange=[2700000000, 31000000000], value="T%-m/%Y"),
    dict(dtickrange=[31000000000, None], value="%Y"),
]

def _chart_name(code: str) -> str:
    """Tên công ty (data/fundamentals.csv, sửa tay ở nhap_tay.csv / ten_cong_ty_tay.csv); chỉ số thì ghi tên chỉ số."""
    if str(code).upper() in E.INDEX_CODES:
        return "Chỉ số VN-Index"
    try:
        name = _wb_meta(str(code)).get("Tên", "") or ""
    except Exception:  # noqa: BLE001
        return ""
    # "Công ty cổ phần" (không phân biệt hoa/thường) -> "CTCP"
    return re.sub(r"công\s+ty\s+cổ\s+phần", "CTCP", str(name), flags=re.IGNORECASE)


def _ohlc_header(code: str, tf: str, g: pd.DataFrame) -> str:
    """Dòng nhỏ dưới tên công ty: khung + O/H/L/C và thay đổi của nến cuối, kiểu TradingView (tên công ty vẽ riêng, cỡ chữ bằng giá)."""
    if g is None or len(g) == 0:
        return ""
    r = g.iloc[-1]
    prev = float(g["Giá đóng cửa"].iloc[-2]) if len(g) > 1 else float("nan")
    o, h, l_, c = (float(r[k]) for k in ("Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa"))
    up = (c >= prev) if pd.notna(prev) else (c >= o)
    col = "#2BD6A2" if up else "#F2506E"
    head = f'<span style="color:#8B95A5;font-size:14px">{ {"D": "1D", "W": "1W", "M": "1M"}.get(tf, tf) }</span>'
    pct = r.get("Chg_%", float("nan")) if tf == "D" else ((c / prev - 1) * 100 if pd.notna(prev) and prev else float("nan"))
    chg = ""
    if pd.notna(pct) and pd.notna(prev):
        chg = f' {c - prev:+,.2f} ({f"{pct:+.2f}".replace(".", ",")}%)'
    ohlc = f'<span style="color:{col};font-size:14px">  O{o:,.2f} H{h:,.2f} L{l_:,.2f} C{c:,.2f}{chg}</span>'
    return head + ohlc


_CODE_PX = {"I": 16, "J": 22, "L": 26, "M": 40, "W": 46, "Q": 34, "G": 32, "O": 33, "D": 32, "N": 32, "H": 32, "U": 31, "V": 30,
            "A": 31, "C": 29, "B": 28, "S": 27, "R": 28, "E": 25, "F": 24, "P": 27, "T": 25, "K": 30, "X": 29, "Y": 29, "Z": 26}


def _code_px(code: str) -> int:
    """Chiều ngang ước lượng (px) của chữ mã ở cỡ 56 đậm, để đặt giá ngay bên phải mã."""
    return int(sum(_CODE_PX.get(ch, 28) for ch in str(code).upper()))


def _brand_tag() -> str:
    """Dòng thương hiệu trên biểu đồ: TRẠM TÍN HIỆU | MIN TRADING (tên lấy từ brand.py)."""
    return (f'<b style="color:#E6EDF3">{BR.TITLE.upper()}</b> <span style="color:#6B7686">|</span> '
            f'<b style="color:#E8C47C">{BR.BRAND.upper()}</b>')


def make_chart(a, code, tf, layers, metrics=None, mobile=False, bars=None, drag="pan"):
    g = a["g"]
    t = g.tail(bars or BARS_SHOWN[tf])
    x = t["Ngày"]
    subs = [s for s in ("Khối lượng", "VNINDEX", "RS vs VNINDEX", "MACD", "RSI", "StochRSI") if s in layers]
    if str(code).upper() in E.INDEX_CODES:
        subs = [s for s in subs if s not in ("VNINDEX", "RS vs VNINDEX")]   # đang xem chính VNINDEX thì không cần 2 khung này
    elif len(mkt) == 0:
        subs = [s for s in subs if s != "RS vs VNINDEX"]
    _w = [0.6 if s == "Khối lượng" else 1.0 for s in subs]          # khung khối lượng thấp hơn các chỉ báo khác
    heights = [0.56] + [0.44 * w_ / sum(_w) for w_ in _w] if subs else [1.0]
    height = (440 + 140 * len(subs)) if mobile else (540 + 180 * len(subs))    # điện thoại: thấp hơn để dễ vuốt qua biểu đồ
    # khe giữa các khung cố định theo px (không theo %) để luôn đủ chỗ cho dải nhãn ngày dưới biểu đồ nến
    fig = make_subplots(rows=1 + len(subs), cols=1, shared_xaxes=True, vertical_spacing=DATE_GAP_PX / height, row_heights=heights)
    # hộp thông tin khi rê chuột vào nến: "T6, 24/10/2026" + Mở / Cao / Thấp / Đóng (giống biểu đồ VNINDEX)
    _kl = pd.to_numeric(t["Khối lượng khớp lệnh"], errors="coerce").fillna(0).to_numpy()
    _tip = [f"<b>{VV._cross_label(pd.Timestamp(d_), tf)}</b><br>Mở {o_:,.2f} · Cao {h_:,.2f}<br>Thấp {l_:,.2f} · Đóng {c_:,.2f}<br>KL {v_ / 1e6:,.2f} triệu cp"
            for d_, o_, h_, l_, c_, v_ in zip(x, t["Giá mở cửa"], t["Giá cao nhất"], t["Giá thấp nhất"], t["Giá đóng cửa"], _kl)]
    fig.add_trace(go.Candlestick(x=x, open=t["Giá mở cửa"], high=t["Giá cao nhất"], low=t["Giá thấp nhất"],
                                 close=t["Giá đóng cửa"], name=code, whiskerwidth=0, text=_tip, hoverinfo="text",      # thân nến đặc, cùng màu với biểu đồ VNINDEX
                                 increasing=dict(line=dict(color=VV.UP, width=1), fillcolor=VV.UP),
                                 decreasing=dict(line=dict(color=VV.DN, width=1), fillcolor=VV.DN)), row=1, col=1)

    def line(col, name, color, w=1.2, dash=None):
        return go.Scatter(x=x, y=t[col], name=name, line=dict(width=w, color=color, dash=dash))

    if "EMA 50/200" in layers:
        fig.add_trace(line("EMA50", "EMA50", "#8B5CF6"), row=1, col=1)
        fig.add_trace(line("EMA200", "EMA200", "#6B7280"), row=1, col=1)
    if "Dual Ichimoku" in layers:      # bộ 1 (9-26-52) chỉ mây, bộ 2 (65-129) chỉ Tenkan và Kijun; chi tiết ở ichimoku_dual.py
        _last = pd.Timestamp(g["Ngày"].iloc[-1])
        for _tr in IDU.traces(g, len(t), lambda k_: future_date(_last, tf, k_)):
            fig.add_trace(_tr, row=1, col=1)
        _cloud_end = IDU.cloud_end(g, lambda k_: future_date(_last, tf, k_))
    if "Bollinger" in layers:
        fig.add_trace(go.Scatter(x=x, y=t["BB_up"], line=dict(width=0.8, color="rgba(59,130,246,.7)"),
                                 name="Bollinger", legendgroup="bb"), row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=t["BB_lo"], line=dict(width=0.8, color="rgba(59,130,246,.7)"), fill="tonexty",
                                 fillcolor="rgba(59,130,246,0.06)", showlegend=False, legendgroup="bb"), row=1, col=1)
        fig.add_trace(line("BB_mid", "BB giữa", "rgba(59,130,246,.6)", 0.8, "dot"), row=1, col=1)

    enough = a["enough"]
    fc = a["fc"] if enough and "Dự báo" in layers else None
    fx = future_date(x.iloc[-1], tf, E.HORIZON)
    ys = [t["Giá thấp nhất"].min(), t["Giá cao nhất"].max()]

    if enough and "Vùng giá" in layers:
        for z in a["zones"]:
            red = z["kind"] == "Kháng cự"
            fig.add_hrect(y0=z["lo"], y1=z["hi"], row=1, col=1, line_width=0,
                          fillcolor="rgba(242,80,110,.10)" if red else "rgba(43,214,162,.12)",
                          annotation_text=f'{z["kind"]} {z["n"]}x', annotation_position="top left",
                          annotation_font=dict(size=9, color="#F2506E" if red else "#2BD6A2"))
    if enough and "Elliott" in layers and a["elliott"]["points"]:
        pts = a["elliott"]["points"]
        fig.add_trace(go.Scatter(x=[g["Ngày"].iat[i] for i, _, _ in pts], y=[p for _, p, _ in pts],
                                 mode="lines+markers+text", text=[w for _, _, w in pts], textposition="top center",
                                 line=dict(width=1.5, color="#7C3AED"), name="Elliott"), row=1, col=1)
    wy = a.get("wy") if enough and "Wyckoff" in layers else None
    if wy and wy["tr"]["e_date"] >= x.iloc[0]:
        tr_ = wy["tr"]
        wc = {"acc": "43,214,162", "dist": "242,80,110"}.get(wy["kind"], "107,114,128")
        xs0 = max(tr_["s_date"], x.iloc[0])
        fig.add_shape(type="rect", x0=xs0, x1=tr_["e_date"], y0=tr_["bot"], y1=tr_["top"], row=1, col=1,
                      line=dict(width=1.3, color=f"rgb({wc})"), fillcolor=f"rgba({wc},0.07)", layer="below")
        for y_, dash_ in ((tr_["top"], "dash"), (tr_["bot"], "dash"), (tr_["mid"], "dot")):
            fig.add_trace(go.Scatter(x=[tr_["e_date"], fx], y=[y_, y_], mode="lines", showlegend=False, hoverinfo="skip",
                                     line=dict(width=1, dash=dash_, color=f"rgba({wc},0.7)")), row=1, col=1)
        fig.add_annotation(x=xs0, y=tr_["top"], text=f"Wyckoff · {WYK.label(wy)}", showarrow=False, xanchor="left",
                           yanchor="bottom", font=dict(size=11, color=f"rgb({wc})"), row=1, col=1)
        evs = [e for e in wy["events"] if e["date"] >= x.iloc[0]]
        if evs:
            fig.add_trace(go.Scatter(x=[e["date"] for e in evs], y=[e["p"] for e in evs], mode="markers+text", name="Wyckoff",
                                     text=[e["label"] for e in evs],
                                     textposition=["bottom center" if e["pos"] == "lo" else "top center" for e in evs],
                                     textfont=dict(size=10, color=f"rgb({wc})"),
                                     marker=dict(symbol="diamond", size=8, color=f"rgb({wc})"),
                                     hovertext=[f'{e["label"]}: {e["txt"]}' for e in evs], hoverinfo="text+x"), row=1, col=1)
    if "Tín hiệu quá khứ" in layers:
        for d, sym, color, col, off, nm in ((1, "triangle-up", "#2BD6A2", "Giá thấp nhất", 0.985, "Mua"),
                                            (-1, "triangle-down", "#F2506E", "Giá cao nhất", 1.015, "Bán")):
            s_ = t[t["PV_signal"] == d]
            if not s_.empty:
                fig.add_trace(go.Scatter(x=s_["Ngày"], y=s_[col] * off, mode="markers", name=nm,
                                         marker=dict(symbol=sym, size=11, color=color),
                                         hovertext=[f"{nm}: {E.PV_LABEL[c]}<br>Vol {v:.1f}x MA10"
                                                    for c, v in zip(s_["PV_code"], s_["Vol_vs_MA10"])],
                                         hoverinfo="text+x"), row=1, col=1)
    if fc:
        lx, col_ = x.iloc[-1], ("#F2506E" if fc["dir"] < 0 else "#2BD6A2")
        for name, y, color, dash in (("Vào lệnh", fc["entry"], "#6B7280", "dot"), ("Cắt lỗ", fc["sl"], "#F2506E", "dash"),
                                     ("Mục tiêu 1", fc["t1"], "#2BD6A2", "dash"), ("Mục tiêu 2", fc["t2"], "#2BD6A2", "dot")):
            fig.add_trace(go.Scatter(x=[lx, fx], y=[y, y], mode="lines+text", text=["", f"{name} {y:,.2f}"],
                                     textposition="top left", textfont=dict(size=9, color=color),
                                     line=dict(width=1, dash=dash, color=color), showlegend=False, hoverinfo="skip"),
                          row=1, col=1)
            ys.append(y)
        fig.add_annotation(x=fx, y=fc["t1"], ax=lx, ay=fc["entry"], axref="x", ayref="y", xref="x", yref="y",
                           showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=col_,
                           text="Dự báo " + ("tăng" if fc["dir"] > 0 else "giảm"), font=dict(size=11, color="#fff"),
                           bgcolor=col_)

    # Hull Suite + Supertrend vẽ SAU các lớp giá khác để nằm trên cùng, không bị mây / vùng giá che; tính trên toàn bộ lịch sử rồi cắt phần hiển thị
    if "Hull Suite" in layers:
        for _tr in HUL.traces(x, HUL.compute(g).iloc[-len(t):]):
            fig.add_trace(_tr, row=1, col=1)
    if "Supertrend" in layers:
        _stv = SPT.compute(g).iloc[-len(t):]
        for _tr in SPT.traces(x, _stv):
            fig.add_trace(_tr, row=1, col=1)
        for _an in SPT.annotations(x, _stv):
            fig.add_annotation(**_an, row=1, col=1)

    r = 2
    if "Khối lượng" in subs:
        vol_all = pd.to_numeric(g["Khối lượng khớp lệnh"], errors="coerce")
        vol_ma20 = vol_all.rolling(20, min_periods=1).mean().loc[t.index]     # MA20 tính trên toàn lịch sử rồi cắt theo vùng hiển thị
        vol = vol_all.loc[t.index]
        up_ = (t["Giá đóng cửa"] >= t["Giá mở cửa"]).to_numpy()
        fig.add_trace(go.Bar(x=x, y=vol, name="Khối lượng", showlegend=False,
                             marker_color=np.where(up_, "#2BD6A2", "#F2506E")), row=r, col=1)
        fig.add_trace(go.Scatter(x=x, y=vol_ma20, name="MA20 KL", line=dict(width=1.4, color="#F59E0B")), row=r, col=1)
        fig.update_yaxes(title_text="Khối lượng · MA20", title_font_size=10, row=r, col=1)
        r += 1
    if "VNINDEX" in subs:
        _fi = frames[tf]
        _vi = _fi[_fi["Mã"].astype(str).str.upper().isin(E.INDEX_CODES)]
        _vi = _vi[(_vi["Ngày"] >= x.iloc[0]) & (_vi["Ngày"] <= x.iloc[-1])]
        if len(_vi):
            _vtip = [f"<b>VNINDEX · {VV._cross_label(pd.Timestamp(d_), tf)}</b><br>Mở {o_:,.2f} · Cao {h_:,.2f}<br>Thấp {l_:,.2f} · Đóng {c_:,.2f}"
                     for d_, o_, h_, l_, c_ in zip(_vi["Ngày"], _vi["Giá mở cửa"], _vi["Giá cao nhất"], _vi["Giá thấp nhất"], _vi["Giá đóng cửa"])]
            fig.add_trace(go.Candlestick(x=_vi["Ngày"], open=_vi["Giá mở cửa"], high=_vi["Giá cao nhất"], low=_vi["Giá thấp nhất"],
                                         close=_vi["Giá đóng cửa"], name="VNINDEX", whiskerwidth=0, text=_vtip, hoverinfo="text", showlegend=False,
                                         increasing=dict(line=dict(color=VV.UP, width=1), fillcolor=VV.UP),
                                         decreasing=dict(line=dict(color=VV.DN, width=1), fillcolor=VV.DN)), row=r, col=1)
            _vc = _vi["Giá đóng cửa"]
            _vlast = float(_vc.iloc[-1])
            _vchg = (_vlast / float(_vc.iloc[-2]) - 1) * 100 if len(_vc) > 1 else 0.0
        else:
            _vlast = _vchg = float("nan")
        fig.update_yaxes(title_text="VNINDEX", title_font_size=10, row=r, col=1)
        r += 1
    if "RS vs VNINDEX" in subs:
        # RS = giá mã / VNINDEX, tính trên toàn lịch sử rồi chuẩn hoá về 100 tại nến đầu vùng hiển thị; MA20 để lọc nhiễu
        _dates = pd.DatetimeIndex(g["Ngày"])
        _m = mkt.copy(); _m.index = pd.DatetimeIndex(_m.index)
        _m = _m[~_m.index.duplicated(keep="last")].sort_index()
        _mk = _m.reindex(_m.index.union(_dates)).ffill().reindex(_dates).to_numpy()      # tuần/tháng: lấy VNINDEX tại ngày của nến
        rs_all = pd.Series(g["Giá đóng cửa"].to_numpy() / _mk, index=g.index)
        rs_ma = rs_all.rolling(20, min_periods=5).mean().loc[t.index]
        rs_t = rs_all.loc[t.index]
        _base = rs_t.dropna().iloc[0] if rs_t.notna().any() else 1.0
        rs_t, rs_ma = rs_t / _base * 100, rs_ma / _base * 100
        _above = (rs_t >= rs_ma).to_numpy()
        fig.add_hline(y=100, line_dash="dot", line_color="#9CA3AF", line_width=1, row=r, col=1)
        fig.add_trace(go.Scatter(x=x, y=rs_t, name="RS vs VNINDEX", line=dict(width=1.6, color="#2BD6A2" if _above[-1] else "#F2506E"),
                                 hovertemplate="RS %{y:.1f}<extra></extra>"), row=r, col=1)
        fig.add_trace(go.Scatter(x=x, y=rs_ma, name="MA20 RS", line=dict(width=1.2, color="#F59E0B"),
                                 hovertemplate="MA20 RS %{y:.1f}<extra></extra>"), row=r, col=1)
        fig.update_yaxes(title_text="RS vs VNINDEX", title_font_size=10, row=r, col=1)
        r += 1
    if "MACD" in subs:
        fig.add_trace(go.Bar(x=x, y=t["MACD_hist"], name="Hist", showlegend=False,
                             marker_color=np.where(t["MACD_hist"] >= 0, "#2BD6A2", "#F2506E")), row=r, col=1)
        fig.add_trace(line("MACD", "MACD", "#3B82F6", 1), row=r, col=1)
        fig.add_trace(line("MACD_sig", "Tín hiệu", "#F59E0B", 1), row=r, col=1)
        fig.update_yaxes(title_text="MACD 12-26-9", title_font_size=10, row=r, col=1)
        r += 1
    if "RSI" in subs:
        rsi_t = DV.rsi14(g["Giá đóng cửa"]).loc[t.index]            # RSI(14) Wilder, cùng công thức với phân tích phân kỳ
        fig.add_hrect(y0=30, y1=70, row=r, col=1, line_width=0, fillcolor="rgba(120,130,150,.08)")
        fig.add_trace(go.Scatter(x=x, y=rsi_t, name="RSI(14)", line=dict(width=1.4, color="#8B5CF6")), row=r, col=1)
        for y in (30, 70):
            fig.add_hline(y=y, line_dash="dot", line_color="#9CA3AF", line_width=1, row=r, col=1)
        # nối 2 pivot của tín hiệu phân kỳ (cùng quy tắc thẻ Phân tích RSI) trên RSI và trên giá
        if tf in ("D", "W", "M"):
            for s_ in DV.detect(g, tf):
                if pd.Timestamp(s_["d2"]) < x.iloc[0]:
                    continue
                cl_ = "#2BD6A2" if s_["dir"] == "up" else "#F2506E"
                fig.add_trace(go.Scatter(x=[s_["d1"], s_["d2"]], y=[s_["r1"], s_["r2"]], mode="lines+markers", showlegend=False,
                                         line=dict(width=1.6, color=cl_), marker=dict(size=6, color=cl_),
                                         hovertext=s_["name"], hoverinfo="text"), row=r, col=1)
                fig.add_trace(go.Scatter(x=[s_["d1"], s_["d2"]], y=[s_["p1"], s_["p2"]], mode="lines+markers", showlegend=False,
                                         line=dict(width=1.4, dash="dot", color=cl_), marker=dict(size=5, color=cl_),
                                         hovertext=s_["name"], hoverinfo="text"), row=1, col=1)
        fig.update_yaxes(title_text="RSI 14", title_font_size=10, range=[0, 100], row=r, col=1)
        r += 1
    if "StochRSI" in subs:
        fig.add_trace(line("SRSI_K", "%K", "#F59E0B", 1), row=r, col=1)
        fig.add_trace(line("SRSI_D", "%D", "#3B82F6", 1), row=r, col=1)
        for y in (20, 80):
            fig.add_hline(y=y, line_dash="dot", line_color="#9CA3AF", line_width=1, row=r, col=1)
        fig.update_yaxes(title_text="StochRSI", title_font_size=10, row=r, col=1)

    pad = (max(ys) - min(ys)) * 0.04
    fig.update_yaxes(range=[min(ys) - pad, max(ys) + pad], row=1, col=1)

    # ---- Cột giá / chỉ số nằm bên PHẢI, thẻ giá hiện tại và giá trị mới nhất của từng khung chỉ báo (kiểu Finpath)
    fig.update_yaxes(side="right", title_text=None)
    last_c = float(t["Giá đóng cửa"].iloc[-1])
    prev_c = float(t["Giá đóng cửa"].iloc[-2]) if len(t) > 1 else last_c
    tag_col = "#2BD6A2" if last_c >= prev_c else "#F2506E"
    fig.add_hline(y=last_c, line_dash="dot", line_color=tag_col, line_width=1, row=1, col=1)
    fig.add_annotation(xref="paper", yref="y", x=1, y=last_c, xanchor="left", yanchor="middle", showarrow=False,
                       text=f"<b>{last_c:,.2f}</b>", font=dict(size=11, color="#FFFFFF"), bgcolor=tag_col, borderpad=3)

    def _fv(v):                                   # 8.97M / 125K / 950
        return "-" if pd.isna(v) else (f"{v / 1e6:,.2f}M" if abs(v) >= 1e6 else f"{v / 1e3:,.1f}K" if abs(v) >= 1e4 else f"{v:,.0f}")

    def _hdr(sub, html_):                         # dòng giá trị ở góc trên trái của khung chỉ báo
        if sub in subs:
            dom = fig.get_subplot(2 + subs.index(sub), 1).yaxis.domain
            fig.add_annotation(xref="paper", yref="paper", x=0.004, y=dom[1], xanchor="left", yanchor="top", showarrow=False,
                               align="left", text=html_, font=dict(size=11, color="#8B95A5"))
    lr = t.iloc[-1]
    if "Khối lượng" in subs:
        _hdr("Khối lượng", f'VOL: <b style="color:#CBD2DC">{_fv(vol.iloc[-1])}</b>  MA20: <span style="color:#F59E0B">{_fv(vol_ma20.iloc[-1])}</span>')
    if "VNINDEX" in subs:
        _vcol = "#2BD6A2" if _vchg >= 0 else "#F2506E"
        _hdr("VNINDEX", f'VNINDEX  <b style="color:#CBD2DC">{_vlast:,.2f}</b>  <span style="color:{_vcol}">{_vchg:+.2f}%</span>' if _vlast == _vlast
             else "VNINDEX: chưa có dữ liệu trong vùng đang xem")
    if "RS vs VNINDEX" in subs:
        _st = "mạnh hơn thị trường" if _above[-1] else "yếu hơn thị trường"
        _hdr("RS vs VNINDEX", f'RS = {code}/VNINDEX (=100 đầu vùng)  <b style="color:#CBD2DC">{rs_t.iloc[-1]:.1f}</b>  '
                              f'MA20: <span style="color:#F59E0B">{rs_ma.iloc[-1]:.1f}</span>  · {_st}')
    if "MACD" in subs:
        _hdr("MACD", f'MACD(12,26,9)  DIF: <span style="color:#3B82F6">{lr["MACD"]:.2f}</span>  '
                     f'DEA: <span style="color:#F59E0B">{lr["MACD_sig"]:.2f}</span>  MACD: <b style="color:#CBD2DC">{lr["MACD_hist"]:.2f}</b>')
    if "RSI" in subs:
        _hdr("RSI", f'RSI(14): <b style="color:#8B5CF6">{rsi_t.iloc[-1]:.2f}</b>')
    if "StochRSI" in subs:
        _hdr("StochRSI", f'StochRSI  %K: <span style="color:#F59E0B">{lr["SRSI_K"]:.1f}</span>  %D: <span style="color:#3B82F6">{lr["SRSI_D"]:.1f}</span>')
    if "Dual Ichimoku" in layers:                  # kéo trục tới hết phần mây tương lai (25 nến) như TradingView, không cắt cụt ở nến dự báo
        fx = max(fx, _cloud_end)
    fig.update_xaxes(range=[x.iloc[0], fx], rangeslider_visible=False)
    if tf == "D":
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    # Trục ngày: hiện ngay dưới biểu đồ nến (trên khung khối lượng), không chỉ ở đáy cùng; nhãn tự đổi theo mức zoom
    fig.update_xaxes(hoverformat="%d/%m/%Y")        # ngày trong hộp rê chuột của các đường chỉ báo luôn đầy đủ, không theo nhãn tháng của trục
    fig.update_xaxes(tickformatstops=DATE_TICK_STOPS, tickangle=0, ticks="outside", ticklen=4, tickfont=dict(size=11))
    fig.update_xaxes(showticklabels=True, row=1, col=1)
    if metrics:
        # Bên trái: MÃ + GIÁ cạnh nhau (bỏ nhãn "Giá"), dòng phụ của giá nằm dưới mã. Bên phải mã: tên công ty (cỡ chữ bằng giá, hiện
        # đủ, tự xuống dòng) rồi O/H/L/C. Các chỉ số còn lại nằm ngay trên biểu đồ.
        import textwrap
        price_m = next((m for m in metrics if m["label"] == "Giá"), None)
        others = [m for m in metrics if m is not price_m]
        NAME_PX, NAME_LH = 26, 34                       # cỡ chữ tên = cỡ chữ giá; 34px mỗi dòng
        NAME_WRAP = 60                                  # số ký tự tối đa mỗi dòng tên (vùng bên phải mã rộng ~80% biểu đồ, đủ chứa ~60-65 ký tự cỡ 26px)
        name_lines = textwrap.wrap(_chart_name(code) or "", NAME_WRAP)
        top, bot = 150, 10
        code_w = 0.20                                  # phần bên trái dành cho mã + giá
        step = (1 - code_w) / max(1, len(others))
        fig.add_annotation(xref="paper", yref="paper", x=0, y=1, xanchor="left", yanchor="bottom", yshift=34, showarrow=False,
                           text=f"<b>{htmllib.escape(str(code))}</b>", font=dict(size=56))
        if price_m:
            fig.add_annotation(xref="paper", yref="paper", x=0, y=1, xanchor="left", yanchor="bottom", xshift=_code_px(code) + 18,
                               yshift=40, showarrow=False, text=f'<b>{price_m["value"]}</b>', font=dict(size=NAME_PX),
                               hovertext=price_m.get("tip"))
            if price_m.get("sub"):
                fig.add_annotation(xref="paper", yref="paper", x=0, y=1, xanchor="left", yanchor="top", yshift=32, showarrow=False,
                                   align="left", text="<br>".join(textwrap.wrap(str(price_m["sub"]), 34)),
                                   font=dict(size=11, color=price_m.get("color", "#8B95A5")), hovertext=price_m.get("tip"))
        # Mỗi chỉ số = 3 chú thích riêng (nhãn / giá trị / dòng phụ) xếp bằng yshift (px) để không đè nhau khi khác cỡ chữ
        for i, m in enumerate(others):
            base = dict(xref="paper", yref="paper", x=code_w + i * step, y=1, xanchor="left", showarrow=False, align="left")
            fig.add_annotation(**base, yanchor="bottom", yshift=66, text=m["label"], font=dict(size=12, color="#8B95A5"),
                               hovertext=m.get("tip"))
            fig.add_annotation(**base, yanchor="bottom", yshift=36, text=f'<b>{m["value"]}</b>', font=dict(size=26),
                               hovertext=m.get("tip"))
            if m.get("sub"):
                fig.add_annotation(**base, yanchor="top", yshift=32, text="<br>".join(textwrap.wrap(str(m["sub"]), 34)),
                                   font=dict(size=11, color=m.get("color", "#8B95A5")), hovertext=m.get("tip"))
        # Chồng từ dưới lên: chỉ số -> O/H/L/C (86) -> tên công ty (106, mỗi dòng 34px) -> dòng thương hiệu
        brand_y = 106 + NAME_LH * len(name_lines) + (6 if name_lines else 0)
        BRAND_H = 80 + (brand_y - 122)                 # chừa chỗ cho tên nhiều dòng + thương hiệu (mốc cũ: thương hiệu ở 122px, BRAND_H 80)
        top += BRAND_H
        height += BRAND_H - 80                         # cao thêm đúng phần đã chiếm để vùng vẽ nến không bị thu nhỏ
        ph = height - top - bot
        fig.add_annotation(xref="paper", yref="paper", x=0, y=1, xanchor="left", yanchor="bottom", yshift=brand_y, showarrow=False,
                           text=_brand_tag(), font=dict(size=22))
        if name_lines:
            fig.add_annotation(xref="paper", yref="paper", x=code_w, y=1, xanchor="left", yanchor="bottom", yshift=106, showarrow=False,
                               align="left", text="<br>".join(htmllib.escape(x_) for x_ in name_lines),
                               font=dict(size=NAME_PX, color="#E6EDF3"))
        fig.add_annotation(xref="paper", yref="paper", x=code_w, y=1, xanchor="left", yanchor="bottom", yshift=86, showarrow=False,
                           align="left", text=_ohlc_header(code, tf, g))
        fig.update_layout(height=height, template=TH.plotly_template(), margin=dict(l=10, r=62, t=top, b=bot),
                          legend=dict(orientation="h", yanchor="bottom", y=1 + (104 + BRAND_H) / ph, font=dict(size=10)))
    elif mobile:
        # điện thoại: chú thích xuống dưới đáy biểu đồ (nhiều dòng cũng không đè lên chỉ số / thanh công cụ)
        fig.update_layout(height=height, template=TH.plotly_template(), margin=dict(l=10, r=54, t=20, b=130),
                          legend=dict(orientation="h", yanchor="top", y=-0.035, font=dict(size=10)))
    else:
        fig.add_annotation(xref="paper", yref="paper", x=0, y=1, xanchor="left", yanchor="bottom", yshift=58, showarrow=False,
                           text=_brand_tag(), font=dict(size=22))
        fig.update_layout(height=height, template=TH.plotly_template(), margin=dict(l=10, r=62, t=96, b=10),
                          legend=dict(orientation="h", y=1.04, font=dict(size=10)))
    TH.style_fig(fig)
    if "Dual Ichimoku" in layers:
        # Nhãn giá của Tenkan / Kijun / Span B / Lead 1 ở cột giá bên phải; tự đẩy lệch (px) để các nhãn gần giá nhau không đè lên nhau
        _yr = fig.layout.yaxis.range
        _ph = (fig.layout.height - fig.layout.margin.t - fig.layout.margin.b) * heights[0]
        _ppu = _ph / (_yr[1] - _yr[0]) if _yr else 0
        if _ppu > 0:
            _cur, _gap = last_c * _ppu, 15.0
            _pos = []
            for _v, _bg, _fg in IDU.price_tags(g, len(t), lambda k_: future_date(_last, tf, k_)):
                if _yr[0] <= _v <= _yr[1]:
                    _pos.append([_v * _ppu, _v, _bg, _fg])
            _prev = _cur                                  # nhãn giá hiện tại đứng yên; các nhãn phía trên xếp dần lên, phía dưới xếp dần xuống
            for _r in sorted((r_ for r_ in _pos if r_[0] >= _cur), key=lambda r_: r_[0]):
                _r[0] = _prev = max(_r[0], _prev + _gap)
            _prev = _cur
            for _r in sorted((r_ for r_ in _pos if r_[0] < _cur), key=lambda r_: -r_[0]):
                _r[0] = _prev = min(_r[0], _prev - _gap)
            for _p, _v, _bg, _fg in _pos:
                fig.add_annotation(xref="paper", yref="y", x=1, y=_v, xanchor="left", yanchor="middle", showarrow=False,
                                   yshift=_p - _v * _ppu, text=f"{_v:,.2f}", font=dict(size=11, color=_fg), bgcolor=_bg, borderpad=3)
    if mobile:
        fig.update_layout(dragmode=drag)
        if drag is False:                      # chế độ "Cuộn trang": khóa mọi thao tác kéo/zoom để biểu đồ không giữ cử chỉ vuốt
            fig.update_xaxes(fixedrange=True)
            fig.update_yaxes(fixedrange=True)
    return fig


MOBILE_MODES = ["Cuộn trang", "Kéo & zoom"]


def mobile_chart_opts(mode: str):
    """Điện thoại. 'Cuộn trang': khóa kéo/zoom, vuốt trang không bị biểu đồ giữ lại (dùng thanh 'Số nến hiển thị' để phóng to).
    'Kéo & zoom': một ngón kéo ngang để xem, có thanh công cụ phóng to / thu nhỏ / đặt lại, chạm đúp để đặt lại."""
    if mode == "Kéo & zoom":
        return "pan", {"displayModeBar": True, "displaylogo": False, "scrollZoom": True, "doubleClick": "reset",
                       "modeBarButtonsToRemove": ["zoom2d", "select2d", "lasso2d", "toImage", "hoverClosestCartesian",
                                                  "hoverCompareCartesian", "toggleSpikelines"]}
    return False, {"displayModeBar": False, "scrollZoom": False}


def is_mobile() -> bool:
    """Nhận diện điện thoại qua User-Agent (Streamlit >= 1.37); không nhận diện được thì coi là máy tính."""
    try:
        ua = (st.context.headers.get("User-Agent") or "").lower()
    except Exception:  # noqa: BLE001
        return False
    return any(k in ua for k in ("iphone", "android", "mobile", "ipad"))


def metrics_html(metrics, code="", name="") -> str:
    """Điện thoại: mã + giá cạnh nhau, tên công ty (cỡ chữ bằng giá, hiện đủ) rồi lưới chỉ số 2 cột."""
    price_m = next((m for m in metrics if m["label"] == "Giá"), None)
    cells = []
    for m in metrics:
        if m is price_m:
            continue
        sub = (f'<div class="cm-sub" style="color:{m.get("color", "#8B95A5")}">{htmllib.escape(str(m["sub"]))}</div>' if m.get("sub") else "")
        cells.append(f'<div class="cm-item"><div class="cm-lab">{htmllib.escape(m["label"])}</div>'
                     f'<div class="cm-val">{htmllib.escape(str(m["value"]))}</div>{sub}</div>')
    head = ""
    if code:
        price = f'<span class="cm-price">{htmllib.escape(str(price_m["value"]))}</span>' if price_m else ""
        head = f'<div class="cm-head"><span class="cm-code">{htmllib.escape(str(code))}</span>{price}</div>'
        if name:
            head += f'<div class="cm-name">{htmllib.escape(str(name))}</div>'
        if price_m and price_m.get("sub"):
            head += f'<div class="cm-sub" style="color:{price_m.get("color", "#8B95A5")};margin-bottom:6px">{htmllib.escape(str(price_m["sub"]))}</div>'
    return ('<style>.cm-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 14px;margin:4px 0 6px}'
            '.cm-lab{font-size:12px;color:var(--muted)}.cm-val{font-size:24px;font-weight:800;line-height:1.25;color:var(--txt2)}'
            '.cm-sub{font-size:11.5px;line-height:1.35}.cm-code{font-size:56px;font-weight:800;line-height:1.1;color:var(--txt2)}'
            '.cm-head{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin:2px 0 2px}'
            '.cm-price{font-size:24px;font-weight:800;color:var(--txt2)}'
            '.cm-name{font-size:24px;line-height:1.3;color:var(--txt);margin:0 0 4px}</style>'
            + head + '<div class="cm-grid">' + "".join(cells) + '</div>')


def pick_layers():
    if hasattr(st, "pills"):
        sel = st.pills("Lớp hiển thị", LAYER_OPTS, selection_mode="multi", default=LAYER_DEFAULT,
                       label_visibility="collapsed")
        return sel or []
    return st.multiselect("Lớp hiển thị", LAYER_OPTS, default=LAYER_DEFAULT)


# ------------------------------------------------------------------ TRANG 2: CỔ PHIẾU
def page_stock():
    st.title("📊 Cổ phiếu")
    header()

    codes = sorted(list(res_df["Mã"].unique()) + INDEX_LIST)      # gồm cả VNINDEX
    saved = st.session_state.get("selected_code")
    c1, c2, c3 = st.columns([1.2, 2, 1.8])
    code = c1.selectbox("Mã cổ phiếu", codes, index=codes.index(saved) if saved in codes else 0)
    st.session_state["selected_code"] = code
    tf = c2.radio("Khung thời gian", ["D", "W", "M"], format_func=TF_LABEL.get, horizontal=True)
    include_short = c3.toggle("Mô phỏng cả lệnh Bán (short)", value=False,
                              help="Thị trường VN không bán khống được, mặc định chỉ tính lệnh Mua.")
    layers = pick_layers()

    A = {t: analyze_cached(frames, code, t, DATA_KEY) for t in ("M", "W", "D")}
    info = stock_row(code)
    if info is None:
        st.warning(f"Chưa đủ dữ liệu để phân tích {code}.")
        return
    a = A[tf]

    d_chg = df[df["Mã"] == code]["Chg_%"].iloc[-1]
    _sw_text, _, _sw_tip, _ = swing_view(info)
    _sw_col = "#E5586A" if info.get("Swing_kind") == "down" else ("#8B95A5" if info.get("Swing_bear", False) else "#25A879")
    chart_metrics = [
        {"label": "Giá", "value": f"{info['Giá']:,.2f}", "sub": (_sw_text if _sw_text != "—" else ""), "color": _sw_col, "tip": _sw_tip},
        {"label": "Vol vs MA10", "value": f"{info['Vol/Avg10']:.1f}x" if pd.notna(info["Vol/Avg10"]) else "-"},
        {"label": "Position %", "value": f"{info['Position %']:.0f}%" if pd.notna(info["Position %"]) else "-"},
        {"label": "Cảnh báo (phiên mới nhất)", "value": info["Cảnh báo"] if info["Cảnh báo"] != "-" else "Không có"},
        {"label": f"Độ nghiêng {E.TF_NAME[tf]}", "value": f"{a['bias']:+.0f}/100" if a["enough"] else "-"},
    ]

    alert_banner(a, tf)
    col_main, col_side = st.columns([2.2, 1])
    with col_main:
        if not a["enough"]:
            st.warning(f"Khung {E.TF_NAME[tf]} chỉ có {a['n']} nến (< {E.MIN_BARS}): chưa đủ để tính điểm, dự báo "
                       "và backtest. Hãy chọn khung nhỏ hơn hoặc tải dữ liệu lịch sử dài hơn.")
        _mob = is_mobile()
        _drag, _cfg, _bars = "pan", {"displayModeBar": True}, None
        if _mob:
            st.markdown(metrics_html(chart_metrics, code, _chart_name(code)), unsafe_allow_html=True)
            _mode = st.radio("Thao tác trên biểu đồ", MOBILE_MODES, horizontal=True, key="mob_chart_mode",
                             help="Cuộn trang: vuốt để cuộn trang bình thường, biểu đồ không bị kéo/zoom ngoài ý muốn. "
                                  "Kéo & zoom: kéo ngang để xem, dùng nút +/- và nút nhà (đặt lại) trên thanh công cụ; chạm đúp để đặt lại.")
            _nmax = min(BARS_SHOWN[tf], len(a["g"]))
            if _nmax > 30:
                _bars = st.slider("Số nến hiển thị (ít nến = phóng to)", 30, _nmax, min(90, _nmax), key=f"mob_bars_{tf}")
            _drag, _cfg = mobile_chart_opts(_mode)
        st.plotly_chart(make_chart(a, code, tf, layers, None if _mob else chart_metrics, _mob, _bars, _drag),
                        config=_cfg, **_STRETCH)
        if not _mob:
            CH.inject()                # đường gióng dọc/ngang + nhãn Thứ, Ngày Tháng Năm và nhãn giá khi rê chuột
            DT.inject(code, tf)        # thanh công cụ vẽ kiểu TradingView (đường, mũi tên, hình, đo giá/ngày, chữ...), lưu theo mã + khung

    with col_side:
        st.markdown(mtf_card(E.mtf_conclusion(A), A, code, info["Giá"], d_chg), unsafe_allow_html=True)
        try:
            st.markdown(setup_card(A["D"]["g"]), unsafe_allow_html=True)
        except Exception as _e:        # thẻ phụ không được làm hỏng cả trang
            st.caption(f"Không tính được phân loại trạng thái: {_e}")
        if a["enough"]:
            st.markdown(forecast_card(a, tf), unsafe_allow_html=True)
        st.markdown(backtest_card(a, tf, code, include_short), unsafe_allow_html=True)
        st.markdown(rsi_card(a, tf, code), unsafe_allow_html=True)
        if a["enough"]:
            st.markdown(wyckoff_card(a), unsafe_allow_html=True)
            st.markdown(zones_card(a), unsafe_allow_html=True)
        st.markdown(signals_card(a, include_short), unsafe_allow_html=True)

        with st.expander("📋 Thẻ lý do Wyckoff · Volume (khung Ngày)"):
            if info["Tín hiệu"] != "WAIT":
                st.markdown(f'<div class="ticket-buy"><b>{info["Tín hiệu"]}</b> · Điểm {info["Điểm số"]}/6.0<br>'
                            f'📍 Entry: {fp(info["Entry"])} · 🛑 Stoploss: {fp(info["Stoploss"])} · '
                            f'🎯 TakeProfit: {fp(info["TakeProfit"])}</div>', unsafe_allow_html=True)
            else:
                st.warning("ĐỨNG NGOÀI (WAIT) – chưa đủ điểm đồng thuận")
            for cat, pts, txt in info["reasons"] or []:
                st.write(f"• **{cat} (+{pts}đ):** {txt}")
            if not info["reasons"]:
                st.write("Chưa có chỉ báo nào đóng góp điểm.")

    _rt_focus_scroll()
    st.caption("Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")


def page_stock_tab(sub):
    st.title(f"📊 Cổ phiếu · {sub}")
    header()
    fm = {}
    fm = FG.load_fund_map()   # đã chặn số mặc định / ngoài miền (fund_guard.py)
    cap = {}
    if os.path.exists("data/stock_metadata.csv"):
        try:
            _m = pd.read_csv("data/stock_metadata.csv", dtype={"Mã": str})
            if {"Mã", "Vốn hóa TT"}.issubset(_m.columns): cap = dict(zip(_m["Mã"].str.upper(), _m["Vốn hóa TT"]))
        except Exception: pass
    apply_manual_overrides(fm, cap)
    for _c, _v in cap.items():
        if pd.notna(_v): fm.setdefault(_c, {})["Vốn hóa TT"] = _v
    ST.render(sub, df, sorted(res_df["Mã"].unique()), fm, WL.GROUPS)


# ------------------------------------------------------------------ ĐA KHUNG NGÀY · TUẦN · THÁNG
def mtf_level_card(tf, r):
    title = f"Khung {ML.TF_LABEL[tf]}"
    if not r["ok"]:
        return card(title, f'<div class="muted">{htmllib.escape(r["cmt"])}</div>')
    kind = {"Tăng": "green", "Giảm": "red"}.get(r["trend"], "amber")
    lo, hi = r["cloud"]
    return card(title, f'<div class="big c-{kind}">{r["trend"]}</div>'
                + row("Giá đóng cửa", fp(r["close"]))
                + row("Hỗ trợ", sup_text(r))
                + row("Kháng cự", res_text(r))
                + row("Mây Kumo", f"{fp(lo)} – {fp(hi)}")
                + f'<div class="muted" style="margin-top:8px">{htmllib.escape(r["cmt"])}</div>')


def mtf_strategy_card(s):
    title = "Chiến lược giao dịch (theo khung Ngày)"
    if not s["ok"]:
        return card(title, f'<div class="muted">{htmllib.escape(s["msg"])}</div>')
    kind = "green" if s["rr_value"] >= 1.8 else "amber" if s["rr_value"] > 0 else "red"
    body = (row("Vùng gom", s["entry"]) + row("Cắt lỗ (SL)", s["sl"]) + row("Chốt lời (TP)", s["tp"])
            + row("R:R", f'<span class="tag tag-{kind}">{s["rr"]}</span>')
            + f'<div class="box">{htmllib.escape(s["status"])}</div>')
    for w in s["warn"] + ([s["tp_note"]] if s["tp_note"] else []):
        body += f'<div class="muted c-amber">⚠ {htmllib.escape(w)}</div>'
    body += (f'<div class="muted" style="margin-top:8px">Vùng gom = hỗ trợ đến hỗ trợ +2%. Cắt lỗ = hỗ trợ −{s["sl_pct"]}%. '
             'Chốt lời = kháng cự gần nhất. R:R tính từ giữa vùng gom. Đây là kế hoạch tham khảo, không phải khuyến nghị.</div>')
    return card(title, body)


def page_mtf_levels():
    st.title("📐 Đa khung Ngày · Tuần · Tháng")
    header()
    codes = sorted(list(res_df["Mã"].unique()) + INDEX_LIST)      # gồm cả VNINDEX
    saved = st.session_state.get("selected_code")
    code = st.selectbox("Mã cổ phiếu", codes, index=codes.index(saved) if saved in codes else 0, key="mtf_code")
    st.session_state["selected_code"] = code
    res = mtf_cached(frames, code, DATA_KEY)
    for col, tf in zip(st.columns(3), ("D", "W", "M")):
        col.markdown(mtf_level_card(tf, res[tf]), unsafe_allow_html=True)
    st.markdown(mtf_strategy_card(res["strategy"]), unsafe_allow_html=True)
    st.caption("Mỗi khung cần ≥ 52 nến để có mây Ichimoku (khung Tháng cần khoảng 4,5 năm lịch sử). "
               "Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")


# ------------------------------------------------------------------ LIÊN KẾT TỪ SƠ ĐỒ (Bộ lọc Realtime)
_RT_JS = """<script>
const f=%s;let tries=0;
function find(d){
 if(f.kind==='wb')return [...d.querySelectorAll('[class*="st-key-wbcard-"]')].find(e=>[...e.classList].some(c=>c.startsWith('st-key-wbcard-')&&c.endsWith('-'+f.code)));
 return d.getElementById(f.id);}
function go(){const d=window.parent.document;
 if(f.tab){const t=[...d.querySelectorAll('[role="tab"]')].find(b=>b.textContent.trim().startsWith(f.tab));
  if(t&&t.getAttribute('aria-selected')!=='true')t.click();}
 const el=find(d);
 if(el&&el.offsetParent!==null){el.scrollIntoView({behavior:'smooth',block:'center'});
  if(f.kind==='wb'){el.classList.add('wb-focus');setTimeout(()=>el.classList.remove('wb-focus'),4000);}
  else if(f.kind==='sc'){el.classList.add('sc-flash');setTimeout(()=>el.classList.remove('sc-flash'),3000);}
  else{el.style.boxShadow='0 0 0 2px #2DD4A7';setTimeout(()=>{el.style.boxShadow=''},3000);}}
 else if(tries++<32)setTimeout(go,250);}
go();</script>"""


def _rt_focus_scroll():
    """Trang đích gọi sau khi vẽ xong thẻ: cuộn tới thẻ của mã vừa bấm ở sơ đồ Bộ lọc Realtime (chỉ một lần)."""
    f = st.session_state.pop("rt_focus", None)
    if f:
        import streamlit.components.v1 as components
        components.html(_RT_JS % json.dumps(f), height=0)


def _rt_go(target: str, code: str):
    """Đặt trang đích + mã cần cuộn tới theo liên kết ?rtgo=<đích>~<mã> ở sơ đồ Bộ lọc Realtime."""
    code = code.upper().strip()
    BT = "Bộ lọc & Backtest"
    if target == "wait":      # trang Chờ mua đã có sẵn cơ chế wb_focus
        st.session_state["_nav_pending"] = (BT, "Chờ mua")
        st.session_state["wb_view"], st.session_state["wb_focus"] = "Thẻ", code
    elif target == "buynow":
        st.session_state["_nav_pending"] = (BT, "Mua ngay")
        st.session_state["bn_all"] = True
        st.session_state["rt_focus"] = {"kind": "wb", "code": code}
    elif target == "watch":
        st.session_state["_nav_pending"] = (BT, "Watchlist")
        st.session_state["wl_view"] = "Thẻ"
        st.session_state["rt_focus"] = {"kind": "wb", "code": code}
    elif target == "dry":
        st.session_state["_nav_pending"] = (BT, "Cạn cung")
        st.session_state["rt_focus"] = {"kind": "wb", "code": code}
    elif target in ("recover", "risk", "over", "sell"):
        sub = {"recover": "Đang phục hồi", "risk": "Danh sách cảnh báo", "over": "Danh sách cảnh báo", "sell": "Bán / Chốt lời"}[target]
        st.session_state["_nav_pending"] = (BT, sub)
        st.session_state["rt_focus"] = {"kind": "sc", "id": f"sc-{code}", "tab": {"risk": "Xu hướng suy yếu", "over": "Tăng quá đà"}.get(target, "")}
    elif target in ("surge-s", "surge-l", "plunge-s", "plunge-l"):
        up = target.startswith("surge")
        kind = "surge" if up else "plunge"
        st.session_state["_nav_pending"] = (BT, "Tăng mạnh" if up else "Giảm mạnh")
        by_leg = target.endswith("-l")
        st.session_state[f"mv_mode_{kind}"] = ((("Tăng từ đáy" if up else "Giảm từ đỉnh")) if by_leg else ("Tăng trong phiên" if up else "Giảm trong phiên"))
        st.session_state["rt_focus"] = {"kind": "sc", "id": f"sc-{code}", "tab": ""}
    elif target in ("chart", "wyckoff"):
        st.session_state["selected_code"] = code
        for _k in ("mtf_code", "tab_code"):
            st.session_state[_k] = code
        st.session_state["_nav_pending"] = ("Biểu đồ", None)
        st.session_state["rt_focus"] = {"kind": "id", "id": "mtf-conclusion" if target == "chart" else "wyckoff-detail", "tab": ""}


# ------------------------------------------------------------------ ĐIỀU HƯỚNG (Mega Navigation Bar)
def _route_inner():
    BR.render_header(f"Dữ liệu EOD · {latest_date:%d/%m/%Y}")
    _go = st.query_params.get("wbgo")      # liên kết "Xem thêm" ở bảng Cổ phiếu chờ mua -> mở thẻ của mã đó
    if _go:
        st.query_params.clear()
        st.session_state["_nav_pending"] = ("Bộ lọc & Backtest", "Chờ mua")
        st.session_state["wb_view"] = "Thẻ"
        st.session_state["wb_focus"] = str(_go).upper().strip()
    _rt = st.query_params.get("rtgo")      # liên kết ở sơ đồ Bộ lọc Realtime -> mở thẻ của mã ở đúng trang
    if _rt:
        st.query_params.clear()
        if "~" in str(_rt):
            _rt_go(*str(_rt).split("~", 1))
    main, sub = NAV.render_nav()
    if main == "Cổ phiếu" and sub == "Đa khung D-W-M":
        return page_mtf_levels()
    if main == "Thị trường" and sub == "Tổng quan":
        try:
            _waiting_overview = _wb_table()
            _buy_overview = _buy_now_table(_waiting_overview)
            _wait_n = int(_waiting_overview["Mã"].nunique()) if "Mã" in _waiting_overview else len(_waiting_overview)
            _buy_n = int(_buy_overview["Mã"].nunique()) if "Mã" in _buy_overview else len(_buy_overview)
        except Exception:
            _buy_n, _wait_n = None, None
        return MO.render(raw, DATA_KEY, buy_n=_buy_n, wait_n=_wait_n)
    if main == "Thị trường" and sub == "Góc nhìn thị trường":
        return MV.render()
    if main == "Thị trường" and sub == "Nhận định VNINDEX":
        return VV.render(raw, DATA_KEY)
    if main == "Thị trường" and sub == "Nhóm vốn hóa":
        return CG.render(raw, DATA_KEY, vn30=VN30_LIST, on_open=_cap_open, openable=set(res_df["Mã"]))
    if main == "Thị trường" and sub == "Dòng tiền khối ngoại":
        return FF.render()
    if main == "Ngành" and sub == "Tổng quan ngành":
        return SD.render(raw)
    if main == "Ngành" and sub == "Cảnh báo luân chuyển dòng tiền":
        header()
        return SRT.render(raw, mkt, WL.GROUPS, mkt_src)
    if main == "Ngành" and sub == "Vị thế cổ phiếu ngành":
        return page_sector_ranking()
    if main == "Bộ lọc & Backtest":
        if sub == "Mua ngay": return page_buy_now()
        if sub == "Lọc tất cả CP": return page_filter()
        if sub == "Bộ lọc Realtime": return page_realtime_filter()
        if sub == "Chờ mua": return page_wait_buy()
        if sub == "Tăng mạnh": return page_surge()
        if sub == "Giảm mạnh": return page_plunge()
        if sub == "Cạn cung": return page_dry_supply()
        if sub == "Đang phục hồi": return page_recovering()
        if sub == "Watchlist": return page_watchlist()
        if sub == "Cổ phiếu của tôi": return page_my_portfolio()
        if sub == "Danh sách cảnh báo": return page_alert_lists()
        if sub == "Bán / Chốt lời": return page_sell_list()
        return NAV.placeholder("🧪 Backtest chiến lược",
                               ["Backtest theo từng mã (Win Rate) hiện có trong Cổ phiếu > Tổng quát.",
                                "Công cụ backtest hàng loạt theo bộ lọc: đang xây dựng."])
    if main in ("Biểu đồ", "Cổ phiếu") and (main == "Biểu đồ" or sub in ("Tổng quát", "Chỉ báo kỹ thuật")):
        return page_stock()
    if main == "Cổ phiếu" and sub in ST.TABS:
        return page_stock_tab(sub)
    NAV.placeholder(f"{NAV.ICON[main]} {main}" + (f" · {sub}" if sub else ""),
                    NAV.MARKET_DESC.get(sub) if main == "Thị trường" else None)


def _cap_open(code):
    """Mở thẻ chi tiết của mã từ tab Nhóm vốn hóa (giống nút \"Xem biểu đồ\" ở các mục khác)."""
    st.session_state["selected_code"] = code
    for _k in ("mtf_code", "tab_code"):
        st.session_state[_k] = code
    NAV.goto("Cổ phiếu", "Tổng quát")


def route():
    _route_inner()
    st.session_state.pop("rt_focus", None)      # trang đích không có thẻ của mã (rỗng / bị lọc): bỏ yêu cầu cuộn còn sót


route()
