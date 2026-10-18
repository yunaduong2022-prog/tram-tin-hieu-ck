import glob
import html as htmllib
import inspect
import json
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import engine as E
import watchlist as WL
import wyckoff as WYK

st.set_page_config(page_title="Trạm Tín Hiệu Chứng Khoán Việt Nam", page_icon="📈", layout="wide")

st.markdown("""
<style>
 .ticket-buy{background:#DDF1EB;border-left:5px solid #0E8A6D;padding:12px 15px;border-radius:8px;color:#0A6B54;margin-bottom:12px}
 .card{background:#fff;border:1px solid #E3E8EF;border-radius:12px;padding:14px 16px;margin-bottom:14px}
 .ct{font-weight:700;font-size:14px;margin-bottom:8px;color:#1F2937}
 .row{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:3px 0;font-size:13px}
 .muted{color:#6B7280;font-size:12px;line-height:1.5}
 .big{font-size:24px;font-weight:800;line-height:1.2;margin:2px 0 6px}
 .c-red{color:#C93A52}.c-green{color:#0E8A6D}.c-amber{color:#B7791F}.c-gray{color:#6B7280}
 .tag{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600}
 .tag-red{background:#FCE4E8;color:#C93A52}.tag-green{background:#DDF1EB;color:#0A6B54}
 .tag-amber{background:#FDF1D6;color:#8A5A00}.tag-gray{background:#EEF1F5;color:#4B5563}
 .box{background:#F4F6F9;border-radius:8px;padding:8px 12px;margin:8px 0}
 .bar{height:7px;background:#E5E7EB;border-radius:99px;overflow:hidden;margin:6px 0 4px}
 .bar>div{height:100%;border-radius:99px}.bg-red{background:#C93A52}.bg-green{background:#0E8A6D}.bg-gray{background:#9CA3AF}
 .chip{display:inline-block;min-width:42px;text-align:center;padding:2px 6px;border-radius:6px;font-size:12px;font-weight:700;margin-right:8px}
 .chip-red{background:#FCE4E8;color:#C93A52}.chip-green{background:#DDF1EB;color:#0A6B54}.chip-gray{background:#EEF1F5;color:#4B5563}
 .item{padding:6px 0;border-bottom:1px solid #F0F2F5;font-size:13px}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* Lưới hiển thị các thẻ cổ phiếu */
.stock-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:16px;margin-top:16px}
/* Thẻ cổ phiếu */
.stock-card{background:#fff;border:1px solid #E2E8F0;border-radius:12px;padding:16px;box-shadow:0 2px 6px rgba(0,0,0,.04);
 transition:transform .15s ease,box-shadow .15s ease;display:flex;flex-direction:column;justify-content:space-between;height:100%}
.stock-card:hover{transform:translateY(-2px);box-shadow:0 6px 16px rgba(0,0,0,.08);border-color:#CBD5E1}
/* Header thẻ */
.stock-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px}
.stock-code{font-size:22px;font-weight:800;color:#0F172A;line-height:1}
.stock-company{font-size:11px;color:#64748B;margin-top:4px;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}
/* Giá & biến động */
.price-box{display:flex;align-items:baseline;gap:10px;margin:10px 0;background:#F8FAFC;padding:8px 12px;border-radius:8px}
.price-val{font-size:20px;font-weight:800}
.price-chg{font-size:13px;font-weight:700}
/* Chỉ số cơ bản (lưới 2x2) */
.metrics-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;font-size:12px;color:#475569;margin-bottom:12px}
.metric-item b{color:#0F172A}
.stock-card.in-box{border:none;box-shadow:none;padding:2px 2px 0;background:transparent;transform:none}
.stock-title{display:flex;align-items:center;flex-wrap:wrap;gap:8px 10px}
.stock-card .price-box{margin:8px 0 10px}
.stock-card .metrics-grid{border-top:1px solid #F1F5F9;padding-top:10px;margin-bottom:10px}
.stock-card .tag-container{margin-bottom:6px}
/* Nhãn dự báo & chip */
.badge-forecast{padding:4px 8px;border-radius:6px;font-size:11px;font-weight:700;white-space:nowrap}
.tag-container{display:flex;flex-wrap:wrap;gap:4px;padding-top:10px;border-top:1px solid #F1F5F9}
.tag-chip{background:#E6F4EA;color:#137333;font-size:10.5px;font-weight:600;padding:2px 8px;border-radius:12px}
</style>
""", unsafe_allow_html=True)

_STRETCH = ({"width": "stretch"} if "width" in inspect.signature(st.plotly_chart).parameters
            else {"use_container_width": True})
_STRETCH_DF = ({"width": "stretch"} if "width" in inspect.signature(st.dataframe).parameters
               else {"use_container_width": True})
TF_LABEL = {"D": "Ngày (D)", "W": "Tuần (W)", "M": "Tháng (M)"}
BARS_SHOWN = {"D": 200, "W": 156, "M": 120}
LAYER_OPTS = ["Dự báo", "Tín hiệu quá khứ", "Ichimoku", "Fibonacci", "Vùng giá", "Bollinger",
              "Elliott", "Wyckoff", "EMA 50/200", "MACD", "KDJ", "StochRSI"]
LAYER_DEFAULT = ["Dự báo", "Tín hiệu quá khứ", "Ichimoku", "Vùng giá", "Wyckoff", "EMA 50/200", "MACD", "KDJ", "StochRSI"]


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
def build_frames(raw: pd.DataFrame) -> dict:
    parts = {"D": [], "W": [], "M": []}
    for _, g in raw.groupby("Mã"):
        base = g[["Mã", "Ngày"] + E.NUMERIC_COLS]
        for tf in parts:
            parts[tf].append(E.add_indicators(E.resample_ohlcv(base, tf)))
    return {tf: pd.concat(p, ignore_index=True) for tf, p in parts.items()}


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
        out[code] = None if w is None else {k: w[k] for k in ("kind", "re", "phase", "lean", "score", "title")}
    return out

VN30_LIST, VN30_SRC = load_vn30()
MEMBER = WL.membership(VN30_LIST)

HAS_EOD = os.path.exists(EOD_CSV)

with st.sidebar:
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
    frames = build_frames(raw)
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
res_df = screener_cached(frames, mkt, WY_KEY).copy()
res_df["Nhóm"] = res_df["Mã"].map(lambda c_: ", ".join(MEMBER.get(c_, [])) or "Khác")
res_df["_wy"] = res_df["Mã"].map(WY_TABLE.get)
res_df["Wyckoff"] = res_df["_wy"].map(WYK.label)

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


@st.dialog("Chi tiết mã", width="large")
def show_detail(code):
    r = res_df[res_df["Mã"] == code].iloc[0]
    st.subheader(f"{code} · {r['Giá']:,.2f} ({r['Chg_%']:+.2f}%)")
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
    st.dataframe(pd.DataFrame({"Daily": [r["MACD D"], r["Fisher D"]], "Weekly": [r["MACD W"], r["Fisher W"]]},
                              index=["MACD (12-26-9)", "Fisher Transform (9)"]), **_STRETCH_DF)
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
        w = r["_wy"]
        if w:
            st.markdown(card("Wyckoff", f'{tag(r["Wyckoff"], "green" if w["kind"] == "acc" else "red" if w["kind"] == "dist" else "gray")}'
                             f' <span class="muted">khớp mẫu {w["score"]}%</span>'), unsafe_allow_html=True)
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
        "Sóng ngắn": trend((10, 20)), "Sóng trung": trend((20, 50, 100)), "Trục chính": trend((50, 100, 200)),
    }


def _status_chip(label: str, state: str) -> str:
    bg, fg = {"Tốt": ("#DDF1EB", "#08785E"), "Xấu": ("#FCE4E8", "#C02645"), "Chưa rõ": ("#EEF1F5", "#626B78")}.get(state, ("#EEF1F5", "#626B78"))
    return f'<span title="{state}" style="display:inline-block;background:{bg};color:{fg};border-radius:7px;padding:5px 8px;margin:3px 4px 3px 0;font-size:12px;font-weight:650;white-space:nowrap">{label}</span>'


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
        for col in ("P/B", "ROE"):
            v = num(row.get(col))
            if v is not None:
                fund_map.setdefault(code, {})[col] = v
        cap = num(row.get("Vốn hóa TT"))
        if cap is not None:
            cap_map[code] = cap


def page_filter():
    st.title("🔍 Bộ lọc cổ phiếu")
    header()
    st.caption("Giữ nguyên các điều kiện lọc hiện tại. Các mã đáp ứng điều kiện sẽ hiển thị thành từng thẻ ở phần Kết quả lọc bên dưới.")
    f = apply_filters(res_df, filter_panel()).sort_values("Score", ascending=False).reset_index(drop=True)
    st.divider()
    st.subheader("📋 Kết quả lọc")
    st.caption(f"{len(f)} mã phù hợp với điều kiện lọc hiện tại.")
    # Có thể bổ sung vốn hóa thực tế qua data/stock_metadata.csv (cột Mã,Vốn hóa TT; đơn vị tỷ đồng).
    cap_map = {}
    if os.path.exists("data/stock_metadata.csv"):
        try:
            meta = pd.read_csv("data/stock_metadata.csv", dtype={"Mã": str})
            if {"Mã", "Vốn hóa TT"}.issubset(meta.columns): cap_map = dict(zip(meta["Mã"].str.upper(), meta["Vốn hóa TT"]))
        except Exception: pass
    # Tên công ty, P/B, ROE: data/fundamentals.csv do update_fundamentals.py tự cập nhật; tên sửa tay ở data/ten_cong_ty_tay.csv
    fund_map = {}
    if os.path.exists("data/fundamentals.csv"):
        try:
            _fd = pd.read_csv("data/fundamentals.csv", dtype={"Mã": str})
            _fd["Mã"] = _fd["Mã"].str.upper().str.strip()
            fund_map = _fd.drop_duplicates("Mã", keep="last").set_index("Mã").to_dict("index")
        except Exception: pass
    if os.path.exists("data/ten_cong_ty_tay.csv"):
        try:
            _nt = pd.read_csv("data/ten_cong_ty_tay.csv", dtype=str)
            for _c, _n in zip(_nt["Mã"].str.upper().str.strip(), _nt["Tên công ty"]):
                if isinstance(_n, str) and _n.strip():
                    fund_map.setdefault(_c, {})["Tên công ty"] = _n.strip()
        except Exception: pass
    apply_manual_overrides(fund_map, cap_map)
    if f.empty:
        st.info("Không có mã nào thỏa bộ lọc hiện tại. Hãy nới lỏng một vài điều kiện.")
        return
    CHIP_ONLY_GOOD = False                        # True: chỉ chip xanh "Tốt"; False: đủ 3 màu Tốt/Xấu/Chưa rõ
    per_row = 3                                   # số thẻ trên một hàng (màn hình hẹp Streamlit tự xếp thành 1 cột)
    rows = [f.iloc[i:i + per_row] for i in range(0, len(f), per_row)]
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
                price_color = "#08785E" if pd.notna(chg) and chg > 0 else "#C02645" if pd.notna(chg) and chg < 0 else "#374151"
                chg_text = f"{chg:+.2f}%" if pd.notna(chg) else "—"
                if CHIP_ONLY_GOOD:     # chỉ hiện các chỉ báo "Tốt" (chip xanh); đặt False để hiện đủ Tốt/Xấu/Chưa rõ
                    good = [lb for lb, v in states.items() if v == "Tốt"]
                    chips_html = "".join(f'<span class="tag-chip">{htmllib.escape(lb)}</span>' for lb in good) \
                        or '<span class="muted">Chưa có chỉ báo Tốt</span>'
                else:
                    chips_html = "".join(_status_chip(lb, v) for lb, v in states.items())
                html = (f'<div class="stock-card in-box">'
                        f'<div class="stock-header"><div><div class="stock-title"><span class="stock-code">{code}</span>'
                        f'<span class="badge-forecast" style="background:{bg};color:{fg}">{forecast}</span></div>'
                        f'<div class="stock-company" title="{name_text}" style="margin-top:6px">{name_text}</div></div></div>'
                        f'<div class="price-box"><span class="price-val" style="color:{price_color}">{r["Giá"]:,.2f}</span>'
                        f'<span class="price-chg" style="color:{price_color}">{chg_text}</span></div>'
                        f'<div class="metrics-grid">'
                        f'<div class="metric-item">Ngành: <b>{industry}{vn30_badge}</b></div>'
                        f'<div class="metric-item">Vốn hóa: <b>{cap_text}</b></div>'
                        f'<div class="metric-item">P/B: <b>{pb_text}</b></div>'
                        f'<div class="metric-item">ROE: <b>{roe_text}</b></div></div>'
                        f'<div class="tag-container">' + chips_html + '</div></div>')
                with st.container(border=True):
                    st.markdown(html, unsafe_allow_html=True)
                    if st.button("📊 Xem biểu đồ", key=f"chart_{code}", use_container_width=True):
                        st.session_state["selected_code"] = code
                        st.switch_page(stock_page)

# ------------------------------------------------------------------ TRANG: KHUNG CẤU TRÚC MA (cards)

def page_ma():
    st.title("🧱 Khung cấu trúc - MA")
    header()
    st.caption("Vị trí giá so với MA10 · MA20 · MA50 · MA100 · MA200 và cấu trúc ngắn, trung, dài hạn.")
    f = apply_filters(res_df, filter_panel()).sort_values("Score", ascending=False)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("TỔNG SỐ MÃ", f"{len(f)} mã")
    c2.metric("NGẮN HẠN · TĂNG", int((f["Trend_NganHan"] == "TĂNG").sum()), "MA10 > MA20", delta_color="off")
    c3.metric("TRUNG HẠN · TĂNG", int((f["Trend_TrungHan"] == "TĂNG").sum()), "MA20 > MA50 > MA100", delta_color="off")
    c4.metric("DÀI HẠN · TĂNG", int((f["Trend_DaiHan"] == "TĂNG").sum()), "MA50 > MA100 > MA200", delta_color="off")
    st.divider()
    if len(f) > 60:
        st.caption("Hiển thị 60 mã có Score cao nhất; dùng bộ lọc để thu hẹp.")
    cols = st.columns(3)
    for i, (_, r) in enumerate(f.head(60).iterrows()):
        with cols[i % 3], st.container(border=True):
            h1, h2 = st.columns([2, 1])
            h1.subheader(r["Mã"])
            h1.caption(f"Giá: {r['Giá']:,.2f} · Score {r['Score']:.1f}")
            st_ = r["Trend_NganHan"]
            h2.markdown(f":{'green' if st_ == 'TĂNG' else 'red' if st_ == 'GIẢM' else 'orange'}[**{st_}**]")
            t1, t2, t3 = st.columns(3)
            t1.caption(f"Ngắn hạn: **{r['Trend_NganHan']}**")
            t2.caption(f"Trung hạn: **{r['Trend_TrungHan']}**")
            t3.caption(f"Dài hạn: **{r['Trend_DaiHan']}**")
            st.markdown("**GIÁ SO VỚI MA**")
            for n in (10, 20, 50, 100, 200):
                v = r[f"MA{n}"]
                if pd.isna(v) or not v:
                    st.text(f"MA{n:<3}: chưa đủ dữ liệu")
                    continue
                dp = (r["Giá"] - v) / v * 100
                st.text(f"MA{n:<3}: {v:>8.2f} ({dp:+6.2f}%) {'🟢' if dp >= 0 else '🔴'}")


# ------------------------------------------------------------------ HTML CARDS
def fp(x):
    return f"{x:,.2f}"


def card(title, inner):
    return f'<div class="card"><div class="ct">{title}</div>{inner}</div>'


def row(label, value):
    return f'<div class="row"><span>{label}</span><b>{value}</b></div>'


def tag(text, kind):
    return f'<span class="tag tag-{kind}">{text}</span>'


def dir_kind(d):
    return "green" if d > 0 else "red" if d < 0 else "gray"


def mtf_card(conc, A):
    if conc is None:
        return card("Kết luận đa khung", '<div class="muted">Chưa đủ dữ liệu ở cả 3 khung để kết luận.</div>')
    k = conc["kind"]
    html = [f'<div class="big c-{k}">{conc["verdict"]}</div>',
            f'<div class="muted">{conc["text"]}</div>',
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
    return card("Kết luận đa khung", "".join(html))


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
    html = [badge, '<div style="height:6px"></div>', row("Số lệnh", cnt), row("Tỷ lệ thắng", f'{s["win"]:.0f}%'),
            row("Kỳ vọng mỗi lệnh", f'{s["exp"]:+.2f}R'), row("Profit factor", pf),
            row("Sụt giảm tối đa", f'{s["mdd"]:.1f}R'), row("30% dữ liệu mới nhất", rec),
            '<div class="muted" style="margin-top:6px">Kỳ vọng = tỷ lệ thắng × lãi trung bình − tỷ lệ thua × lỗ trung bình, '
            'tính theo R (1R = mức rủi ro mỗi lệnh). Thắng nhiều chưa chắc có lời. Cần từ 20 lệnh trở lên và kỳ vọng '
            'dương ở cả phần dữ liệu mới nhất mới đáng tin. Tín hiệu Mua theo giá + khối lượng; vào tại giá đóng cửa, cắt lỗ 1,5 ATR, chốt 2R, giữ tối đa '
            '20 nến.' + ('' if include_short else ' Chỉ tính lệnh Mua (thị trường VN không bán khống).') + '</div>']
    return card(title, "".join(html))


def elliott_card(a):
    e = a["elliott"]
    return card("Sóng Elliott", tag(e["title"], e["tag"]) + f'<div class="muted" style="margin-top:8px">{e["text"]}</div>')


def wyckoff_card(a):
    w = a.get("wy")
    if not w:
        return card("Phân tích Wyckoff", '<div class="muted">Chưa thấy vùng đi ngang đủ rõ (tối thiểu 30 nến, chạm cả hai biên từ 2 lần). '
                                         'Giá đang ở trạng thái xu hướng hoặc biên quá rộng.</div>')
    k = {"buy": "green", "sell": "red"}.get(w["lean"], "gray")
    head = tag(WYK.label(w), k) + f' <span class="muted">khớp mẫu {w["score"]}%</span>'
    html = [head, f'<div class="muted" style="margin-top:8px">{w["summary"]}</div>']
    if w["kind"] != "unk" or w["trigger"]:
        html.append('<div class="box">' + row("Biên trên / dưới", f'{fp(w["tr"]["top"])} / {fp(w["tr"]["bot"])}')
                    + row(w["trigger"]["txt"], f'<b>{fp(w["trigger"]["p"])}</b>')
                    + row(w["inval"]["txt"], f'<b>{fp(w["inval"]["p"])}</b>') + "</div>")
    for e in sorted(w["events"], key=lambda x: -x["i"]):
        html.append(f'<div class="item"><span class="chip chip-{k}">{e["label"]}</span><b>{e["date"]:%d/%m/%Y}</b> · {fp(e["p"])}'
                    f'<div class="muted" style="margin-left:50px">{e["txt"]}</div></div>')
    if w["notes"]:
        html.append(f'<div class="muted" style="margin-top:6px">{" ".join(w["notes"])}</div>')
    html.append('<div class="muted" style="margin-top:6px">Wyckoff đọc cấu trúc giá và volume nên mang tính chủ quan. Vùng đi ngang được tìm bằng quy tắc '
                '(biên chạm nhiều lần, giá cắt đường giữa nhiều lần), sự kiện dò theo volume và biên độ nến. Máy có thể gắn nhãn khác cách bạn đọc, '
                'và vẫn có thể thấy "cấu trúc" ngay trên dữ liệu ngẫu nhiên, nên chỉ dùng để quan sát cùng các chỉ báo khác, không tính vào điểm tín hiệu và backtest.</div>')
    return card("Phân tích Wyckoff", "".join(html))


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
        val = '<span class="muted">đang mở</span>' if r["open"] else (
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


def make_chart(a, code, tf, layers):
    g = a["g"]
    t = g.tail(BARS_SHOWN[tf])
    x = t["Ngày"]
    subs = [s for s in ("MACD", "KDJ", "StochRSI") if s in layers]
    heights = [0.56] + [0.44 / len(subs)] * len(subs) if subs else [1.0]
    fig = make_subplots(rows=1 + len(subs), cols=1, shared_xaxes=True, vertical_spacing=0.025, row_heights=heights)
    fig.add_trace(go.Candlestick(x=x, open=t["Giá mở cửa"], high=t["Giá cao nhất"], low=t["Giá thấp nhất"],
                                 close=t["Giá đóng cửa"], name=code, increasing_line_color="#0E8A6D",
                                 decreasing_line_color="#C93A52"), row=1, col=1)

    def line(col, name, color, w=1.2, dash=None):
        return go.Scatter(x=x, y=t[col], name=name, line=dict(width=w, color=color, dash=dash))

    if "EMA 50/200" in layers:
        fig.add_trace(line("EMA50", "EMA50", "#8B5CF6"), row=1, col=1)
        fig.add_trace(line("EMA200", "EMA200", "#6B7280"), row=1, col=1)
    if "Ichimoku" in layers:
        fig.add_trace(line("Tenkan", "Tenkan", "#E4572E", 1), row=1, col=1)
        fig.add_trace(line("Kijun", "Kijun", "#1D4ED8", 1), row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=t["SpanA"], line=dict(width=0.6, color="rgba(14,138,109,.5)"),
                                 showlegend=False, hoverinfo="skip"), row=1, col=1)
        fig.add_trace(go.Scatter(x=x, y=t["SpanB"], line=dict(width=0.6, color="rgba(201,58,82,.5)"), fill="tonexty",
                                 fillcolor="rgba(100,150,200,0.18)", name="Mây Kumo", hoverinfo="skip"), row=1, col=1)
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

    if enough and "Fibonacci" in layers and a["fib"]:
        (ia, _, pa), (ib, _, pb) = a["fib"]["A"], a["fib"]["B"]
        x0 = max(g["Ngày"].iat[ia], x.iloc[0])
        lv = [(f"{r * 100:.1f}%", pb - (pb - pa) * r) for r in (0, 0.236, 0.382, 0.5, 0.618, 0.786, 1)]
        lv += [("Fib 127.2%", pa + (pb - pa) * 1.272), ("Fib 161.8%", pa + (pb - pa) * 1.618)]
        for name, y in lv:
            fig.add_trace(go.Scatter(x=[x0, x.iloc[-1]], y=[y, y], mode="lines+text", text=["", name],
                                     textposition="middle right", textfont=dict(size=9, color="#B7791F"),
                                     line=dict(width=0.8, dash="dot", color="rgba(183,121,31,.7)"),
                                     showlegend=False, hoverinfo="skip"), row=1, col=1)
        ys += [pa, pb]
    if enough and "Vùng giá" in layers:
        for z in a["zones"]:
            red = z["kind"] == "Kháng cự"
            fig.add_hrect(y0=z["lo"], y1=z["hi"], row=1, col=1, line_width=0,
                          fillcolor="rgba(201,58,82,.10)" if red else "rgba(14,138,109,.12)",
                          annotation_text=f'{z["kind"]} {z["n"]}x', annotation_position="top left",
                          annotation_font=dict(size=9, color="#C93A52" if red else "#0E8A6D"))
    if enough and "Elliott" in layers and a["elliott"]["points"]:
        pts = a["elliott"]["points"]
        fig.add_trace(go.Scatter(x=[g["Ngày"].iat[i] for i, _, _ in pts], y=[p for _, p, _ in pts],
                                 mode="lines+markers+text", text=[w for _, _, w in pts], textposition="top center",
                                 line=dict(width=1.5, color="#7C3AED"), name="Elliott"), row=1, col=1)
    wy = a.get("wy") if enough and "Wyckoff" in layers else None
    if wy and wy["tr"]["e_date"] >= x.iloc[0]:
        tr_ = wy["tr"]
        wc = {"acc": "14,138,109", "dist": "201,58,82"}.get(wy["kind"], "107,114,128")
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
        for d, sym, color, col, off, nm in ((1, "triangle-up", "#0E8A6D", "Giá thấp nhất", 0.985, "Mua"),
                                            (-1, "triangle-down", "#C93A52", "Giá cao nhất", 1.015, "Bán")):
            s_ = t[t["PV_signal"] == d]
            if not s_.empty:
                fig.add_trace(go.Scatter(x=s_["Ngày"], y=s_[col] * off, mode="markers", name=nm,
                                         marker=dict(symbol=sym, size=11, color=color),
                                         hovertext=[f"{nm}: {E.PV_LABEL[c]}<br>Vol {v:.1f}x MA10"
                                                    for c, v in zip(s_["PV_code"], s_["Vol_vs_MA10"])],
                                         hoverinfo="text+x"), row=1, col=1)
    if fc:
        lx, col_ = x.iloc[-1], ("#C93A52" if fc["dir"] < 0 else "#0E8A6D")
        for name, y, color, dash in (("Vào lệnh", fc["entry"], "#6B7280", "dot"), ("Cắt lỗ", fc["sl"], "#C93A52", "dash"),
                                     ("Mục tiêu 1", fc["t1"], "#0E8A6D", "dash"), ("Mục tiêu 2", fc["t2"], "#0E8A6D", "dot")):
            fig.add_trace(go.Scatter(x=[lx, fx], y=[y, y], mode="lines+text", text=["", f"{name} {y:,.2f}"],
                                     textposition="top left", textfont=dict(size=9, color=color),
                                     line=dict(width=1, dash=dash, color=color), showlegend=False, hoverinfo="skip"),
                          row=1, col=1)
            ys.append(y)
        fig.add_annotation(x=fx, y=fc["t1"], ax=lx, ay=fc["entry"], axref="x", ayref="y", xref="x", yref="y",
                           showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=col_,
                           text="Dự báo " + ("tăng" if fc["dir"] > 0 else "giảm"), font=dict(size=11, color="#fff"),
                           bgcolor=col_)

    r = 2
    if "MACD" in subs:
        fig.add_trace(go.Bar(x=x, y=t["MACD_hist"], name="Hist", showlegend=False,
                             marker_color=np.where(t["MACD_hist"] >= 0, "#0E8A6D", "#C93A52")), row=r, col=1)
        fig.add_trace(line("MACD", "MACD", "#3B82F6", 1), row=r, col=1)
        fig.add_trace(line("MACD_sig", "Tín hiệu", "#F59E0B", 1), row=r, col=1)
        fig.update_yaxes(title_text="MACD 12-26-9", title_font_size=10, row=r, col=1)
        r += 1
    if "KDJ" in subs:
        for col, nm, cl in (("KDJ_K", "K", "#F59E0B"), ("KDJ_D", "D", "#3B82F6"), ("KDJ_J", "J", "#8B5CF6")):
            fig.add_trace(line(col, nm, cl, 1), row=r, col=1)
        for y in (20, 80):
            fig.add_hline(y=y, line_dash="dot", line_color="#9CA3AF", line_width=1, row=r, col=1)
        fig.update_yaxes(title_text="KDJ 9-3-3", title_font_size=10, row=r, col=1)
        r += 1
    if "StochRSI" in subs:
        fig.add_trace(line("SRSI_K", "%K", "#F59E0B", 1), row=r, col=1)
        fig.add_trace(line("SRSI_D", "%D", "#3B82F6", 1), row=r, col=1)
        for y in (20, 80):
            fig.add_hline(y=y, line_dash="dot", line_color="#9CA3AF", line_width=1, row=r, col=1)
        fig.update_yaxes(title_text="StochRSI", title_font_size=10, row=r, col=1)

    pad = (max(ys) - min(ys)) * 0.04
    fig.update_yaxes(range=[min(ys) - pad, max(ys) + pad], row=1, col=1)
    fig.update_xaxes(range=[x.iloc[0], fx], rangeslider_visible=False)
    if tf == "D":
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    fig.update_layout(height=540 + 180 * len(subs), template="plotly_white", margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.04, font=dict(size=10)))
    return fig


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

    codes = sorted(res_df["Mã"].unique())
    saved = st.session_state.get("selected_code")
    c1, c2, c3 = st.columns([1.2, 2, 1.8])
    code = c1.selectbox("Mã cổ phiếu", codes, index=codes.index(saved) if saved in codes else 0)
    st.session_state["selected_code"] = code
    tf = c2.radio("Khung thời gian", ["D", "W", "M"], format_func=TF_LABEL.get, horizontal=True)
    include_short = c3.toggle("Mô phỏng cả lệnh Bán (short)", value=False,
                              help="Thị trường VN không bán khống được, mặc định chỉ tính lệnh Mua.")
    layers = pick_layers()

    A = {t: analyze_cached(frames, code, t, DATA_KEY) for t in ("M", "W", "D")}
    info = res_df[res_df["Mã"] == code].iloc[0]
    a = A[tf]

    m1, m2, m3, m4, m5 = st.columns(5)
    d_chg = df[df["Mã"] == code]["Chg_%"].iloc[-1]
    m1.metric("Giá", f"{info['Giá']:,.2f}", f"{d_chg:+.2f}%" if pd.notna(d_chg) else None)
    m2.metric("Vol vs MA10", f"{info['Vol/Avg10']:.1f}x" if pd.notna(info["Vol/Avg10"]) else "-")
    m3.metric("Position %", f"{info['Position %']:.0f}%" if pd.notna(info["Position %"]) else "-")
    m4.metric("Cảnh báo (phiên mới nhất)", info["Cảnh báo"] if info["Cảnh báo"] != "-" else "Không có")
    m5.metric(f"Độ nghiêng {E.TF_NAME[tf]}", f"{a['bias']:+.0f}/100" if a["enough"] else "-")

    alert_banner(a, tf)
    col_main, col_side = st.columns([2.2, 1])
    with col_main:
        if not a["enough"]:
            st.warning(f"Khung {E.TF_NAME[tf]} chỉ có {a['n']} nến (< {E.MIN_BARS}): chưa đủ để tính điểm, dự báo "
                       "và backtest. Hãy chọn khung nhỏ hơn hoặc tải dữ liệu lịch sử dài hơn.")
        st.plotly_chart(make_chart(a, code, tf, layers), **_STRETCH)

    with col_side:
        st.markdown(mtf_card(E.mtf_conclusion(A), A), unsafe_allow_html=True)
        if a["enough"]:
            st.markdown(forecast_card(a, tf), unsafe_allow_html=True)
        st.markdown(backtest_card(a, tf, code, include_short), unsafe_allow_html=True)
        if a["enough"]:
            st.markdown(elliott_card(a), unsafe_allow_html=True)
            st.markdown(wyckoff_card(a), unsafe_allow_html=True)
            st.markdown(zones_card(a), unsafe_allow_html=True)
        st.markdown(signals_card(a, include_short), unsafe_allow_html=True)

        with st.expander("📋 Thẻ lý do Wyckoff · Volume (khung Ngày)"):
            if info["Tín hiệu"] != "WAIT":
                st.markdown(f'<div class="ticket-buy"><b>{info["Tín hiệu"]}</b> · Điểm {info["Điểm số"]}/6.0<br>'
                            f'📍 Entry: {info["Entry"]:,.2f} · 🛑 Stoploss: {info["Stoploss"]:,.2f} · '
                            f'🎯 TakeProfit: {info["TakeProfit"]:,.2f}</div>', unsafe_allow_html=True)
            else:
                st.warning("ĐỨNG NGOÀI (WAIT) – chưa đủ điểm đồng thuận")
            for cat, pts, txt in info["reasons"] or []:
                st.write(f"• **{cat} (+{pts}đ):** {txt}")
            if not info["reasons"]:
                st.write("Chưa có chỉ báo nào đóng góp điểm.")

    st.caption("Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")


# ------------------------------------------------------------------ ĐIỀU HƯỚNG
filter_page = st.Page(page_filter, title="Bộ lọc", icon="🔍", url_path="bo-loc", default=True)
stock_page = st.Page(page_stock, title="Cổ phiếu", icon="📊", url_path="co-phieu")
ma_page = st.Page(page_ma, title="Khung cấu trúc MA", icon="🧱", url_path="khung-ma")
st.navigation([filter_page, stock_page, ma_page]).run()
