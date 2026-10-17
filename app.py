import glob
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Trạm Tín Hiệu Chứng Khoán Việt Nam", page_icon="📈", layout="wide")

st.markdown("""
<style>
    .ticket-buy {background-color:#DDF1EB;border-left:5px solid #0E8A6D;padding:15px;border-radius:8px;color:#0A6B54;margin-bottom:15px;}
</style>
""", unsafe_allow_html=True)

st.title("📈 Trạm Tín Hiệu Chứng Khoán Việt Nam")

NUMERIC_COLS = ["Giá mở cửa", "Giá cao nhất", "Giá thấp nhất", "Giá đóng cửa", "Khối lượng khớp lệnh"]


# ------------------------------------------------------------------ DỮ LIỆU
def indicators(g: pd.DataFrame) -> pd.DataFrame:
    g = g.copy()
    c, h, l, v = g["Giá đóng cửa"], g["Giá cao nhất"], g["Giá thấp nhất"], g["Khối lượng khớp lệnh"]
    for n in (9, 20, 50, 200):
        g[f"MA{n}"] = c.rolling(n).mean()
    g["Vol_MA10"] = v.shift(1).rolling(10).mean()
    g["Vol_vs_MA10"] = v / g["Vol_MA10"]
    rng = h - l
    g["Position_%"] = np.where(rng > 0, (c - l) / rng.replace(0, np.nan) * 100, 50.0)
    tenkan = (h.rolling(9).max() + l.rolling(9).min()) / 2
    kijun = (h.rolling(26).max() + l.rolling(26).min()) / 2
    g["SpanA"] = ((tenkan + kijun) / 2).shift(26)
    g["SpanB"] = ((h.rolling(52).max() + l.rolling(52).min()) / 2).shift(26)
    g["Resistance_20"] = h.shift(1).rolling(20).max()
    g["Support_20"] = l.shift(1).rolling(20).min()
    return g


@st.cache_data(show_spinner="Đang xử lý dữ liệu...")
def load_and_process(source) -> pd.DataFrame:
    df = pd.read_excel(source, sheet_name=0)
    df.columns = [str(c).strip() for c in df.columns]
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["Ngày"] = pd.to_datetime(df["Ngày"], format="%d/%m/%Y", errors="coerce")
    df = df.dropna(subset=["Mã", "Ngày", "Giá đóng cửa"]).sort_values(["Mã", "Ngày"])
    parts = [indicators(g) for _, g in df.groupby("Mã")]
    return pd.concat(parts).reset_index(drop=True)


# ------------------------------------------------------------------ TÍN HIỆU
def analyze_signal(row, stop_buffer=0.03, target_r=2.0):
    c, l = row["Giá đóng cửa"], row["Giá thấp nhất"]
    v_ratio, pos = row["Vol_vs_MA10"], row["Position_%"]
    res, sup = row["Resistance_20"], row["Support_20"]
    score, reasons = 0.0, []

    if pd.notna(res) and pd.notna(pos) and c > res and pos >= 70:
        score += 2.0
        reasons.append(("Wyckoff", 2.0, f"Phá kháng cự 20 phiên ({res:.2f}), đóng cửa sát đỉnh (Position {pos:.0f}%)"))
    elif pd.notna(sup) and pd.notna(pos) and l < sup and c >= sup and pos >= 50:
        score += 1.5
        reasons.append(("Wyckoff", 1.5, f"Quét thủng hỗ trợ ({sup:.2f}) rồi đóng cửa trên hỗ trợ (Spring/Test)"))

    if pd.notna(v_ratio):
        if v_ratio >= 1.5:
            score += 1.5
            reasons.append(("Volume", 1.5, f"Khối lượng gấp {v_ratio:.1f} lần MA10 Vol"))
        elif v_ratio >= 1.2:
            score += 1.0
            reasons.append(("Volume", 1.0, f"Khối lượng gấp {v_ratio:.1f} lần MA10 Vol"))

    sa, sb = row["SpanA"], row["SpanB"]
    if pd.notna(sa) and pd.notna(sb) and c > max(sa, sb):
        score += 1.5
        reasons.append(("Ichimoku", 1.5, f"Giá nằm trên mây Kumo ({max(sa, sb):.2f})"))

    if pd.notna(row["MA9"]) and c > row["MA9"]:
        score += 0.5
        reasons.append(("MA Trend", 0.5, "Giá trên MA9"))

    if score >= 3.5:
        signal = "MUA MỚI (BREAKOUT)" if (pd.notna(pos) and pos >= 70) else "MUA GOM (SPRING)"
    else:
        signal = "WAIT"

    entry = c
    stoploss = l * (1 - stop_buffer)
    risk = entry - stoploss
    takeprofit = entry + target_r * risk if risk > 0 else entry
    rr = round((takeprofit - entry) / risk, 2) if risk > 0 else 0
    return signal, score, reasons, entry, stoploss, takeprofit, rr


# ------------------------------------------------------------------ BACKTEST
@st.cache_data(show_spinner="Đang backtest...")
def run_backtest(df: pd.DataFrame, max_hold=20, stop_buffer=0.03, target_r=2.0) -> pd.DataFrame:
    trades = []
    for code, g in df.groupby("Mã"):
        g = g.reset_index(drop=True)
        for i in range(len(g) - 1):
            row = g.iloc[i]
            sig, score, _, entry, sl, tp, _ = analyze_signal(row, stop_buffer, target_r)
            if sig == "WAIT" or entry - sl <= 0:
                continue
            risk, r_result = entry - sl, None
            fwd = g.iloc[i + 1: i + 1 + max_hold]
            for _, f in fwd.iterrows():
                if f["Giá thấp nhất"] <= sl:       # ưu tiên SL nếu cùng phiên chạm cả hai
                    r_result = -1.0
                    break
                if f["Giá cao nhất"] >= tp:
                    r_result = target_r
                    break
            if r_result is None:
                r_result = (fwd["Giá đóng cửa"].iloc[-1] - entry) / risk
            trades.append({"Mã": code, "Ngày": row["Ngày"], "R": r_result})
    return pd.DataFrame(trades)


def backtest_stats(t: pd.DataFrame):
    if t.empty:
        return None
    wins, losses = t[t["R"] > 0]["R"], t[t["R"] <= 0]["R"]
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf")
    equity = t.sort_values("Ngày")["R"].cumsum()
    mdd = (equity - equity.cummax()).min()
    return {"n": len(t), "win": len(wins) / len(t) * 100, "pf": pf, "mdd": mdd, "exp": t["R"].mean()}


# ------------------------------------------------------------------ BIỂU ĐỒ
def make_chart(g: pd.DataFrame, code: str) -> go.Figure:
    g = g.tail(180)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=g["Ngày"], open=g["Giá mở cửa"], high=g["Giá cao nhất"],
                                 low=g["Giá thấp nhất"], close=g["Giá đóng cửa"], name=code,
                                 increasing_line_color="#0E8A6D", decreasing_line_color="#C93A52"))
    for n, col in ((9, "#F59E0B"), (20, "#3B82F6"), (50, "#8B5CF6"), (200, "#6B7280")):
        if g[f"MA{n}"].notna().any():
            fig.add_trace(go.Scatter(x=g["Ngày"], y=g[f"MA{n}"], name=f"MA{n}", line=dict(width=1.2, color=col)))
    if g["SpanA"].notna().any() and g["SpanB"].notna().any():
        fig.add_trace(go.Scatter(x=g["Ngày"], y=g["SpanA"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=g["Ngày"], y=g["SpanB"], line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(100,150,200,0.2)", name="Kumo", hoverinfo="skip"))
    fig.update_layout(height=520, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=1.05))
    return fig


# ------------------------------------------------------------------ NGUỒN DỮ LIỆU
with st.sidebar:
    st.header("📂 Dữ liệu")
    uploaded = st.file_uploader("Tải file Excel CafeF (.xlsx)", type=["xlsx"])
    repo_files = sorted(glob.glob("data/*.xlsx"))
    source = uploaded
    if source is None and repo_files:
        source = st.selectbox("Hoặc dùng file trong repo", repo_files, index=len(repo_files) - 1)

if source is None:
    st.title("📈 Trạm Tín Hiệu Chứng Khoán Việt Nam")
    st.info("👈 Hãy tải file Excel lên (hoặc đặt file `.xlsx` vào thư mục `data/` của repo).")
    st.stop()

try:
    df = load_and_process(source)
except Exception as e:
    st.error(f"Lỗi khi đọc hoặc xử lý dữ liệu: {e}")
    st.stop()

latest_date = df["Ngày"].max()
n_sessions = df.groupby("Mã").size().min()
latest_df = df[df["Ngày"] == latest_date]

results = []
for _, row in latest_df.iterrows():
    sig, sc, reas, entry, sl, tp, rr = analyze_signal(row)
    results.append({
        "Mã": row["Mã"], "Giá": row["Giá đóng cửa"],
        "Vol vs MA10": f"{row['Vol_vs_MA10']:.1f}x" if pd.notna(row["Vol_vs_MA10"]) else "-",
        "Position_%": f"{row['Position_%']:.0f}%" if pd.notna(row["Position_%"]) else "-",
        "Tín hiệu": sig, "Điểm số": sc, "Entry": round(entry, 2), "Stoploss": round(sl, 2),
        "TakeProfit": round(tp, 2), "R:R": rr, "reasons": reas,
    })
res_df = pd.DataFrame(results)


def header():
    st.caption(f"Dữ liệu đến ngày **{latest_date:%d/%m/%Y}** · {df['Mã'].nunique()} mã · "
               f"tối thiểu {n_sessions} phiên/mã")
    if n_sessions < 60:
        st.warning("Dữ liệu dưới 60 phiên/mã: Ichimoku, MA50/MA200 và backtest sẽ thiếu hoặc không đáng tin.")


# ------------------------------------------------------------------ TRANG 1: BỘ LỌC
def page_filter():
    st.title("🔍 Bộ Lọc Cổ Phiếu")
    header()

    c1, c2, c3 = st.columns(3)
    with c1:
        filter_sig = st.multiselect("Lọc tín hiệu", ["MUA MỚI (BREAKOUT)", "MUA GOM (SPRING)", "WAIT"],
                                    default=["MUA MỚI (BREAKOUT)", "MUA GOM (SPRING)", "WAIT"])
    with c2:
        min_score = st.slider("Điểm tối thiểu", 0.0, 6.0, 0.0, 0.5)
    with c3:
        search = st.text_input("Tìm mã", "").upper()

    f = res_df[res_df["Tín hiệu"].isin(filter_sig) & (res_df["Điểm số"] >= min_score)]
    if search:
        f = f[f["Mã"].str.contains(search)]
    f = f.sort_values("Điểm số", ascending=False).reset_index(drop=True)

    st.caption(f"{len(f)} mã phù hợp · bấm vào một dòng để chọn, rồi bấm nút bên dưới để xem biểu đồ.")
    event = st.dataframe(
        f.drop(columns=["reasons"]), use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row",
    )
    rows = event.selection.rows if event and event.selection else []
    if rows:
        code = f.iloc[rows[0]]["Mã"]
        if st.button(f"📊 Xem biểu đồ {code}", type="primary"):
            st.session_state["selected_code"] = code
            st.switch_page(chart_page)


# ------------------------------------------------------------------ TRANG 2: BIỂU ĐỒ
def page_chart():
    st.title("📊 Biểu Đồ & Thẻ Lý Do")
    header()

    codes = list(res_df["Mã"].unique())
    saved = st.session_state.get("selected_code")
    idx = codes.index(saved) if saved in codes else 0
    code = st.selectbox("Chọn mã:", codes, index=idx)
    st.session_state["selected_code"] = code

    info = res_df[res_df["Mã"] == code].iloc[0]

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Giá", info["Giá"])
    m2.metric("Vol vs MA10", info["Vol vs MA10"])
    m3.metric("Position %", info["Position_%"])
    m4.metric("Điểm số", f"{info['Điểm số']}/6.0")
    m5.metric("R:R", f"1 : {info['R:R']}")

    col_main, col_ticket = st.columns([2.2, 1])
    with col_main:
        st.plotly_chart(make_chart(df[df["Mã"] == code], code), use_container_width=True)

    with col_ticket:
        st.markdown("### 📋 Thẻ lý do")
        if info["Tín hiệu"] != "WAIT":
            st.markdown(f"""
            <div class="ticket-buy">
              <h3><b>{info['Tín hiệu']}</b></h3>
              <p><b>Điểm: {info['Điểm số']}/6.0</b></p><hr>
              <p>📍 <b>Entry:</b> {info['Entry']}</p>
              <p>🛑 <b>Stoploss:</b> {info['Stoploss']}</p>
              <p>🎯 <b>TakeProfit:</b> {info['TakeProfit']}</p>
            </div>""", unsafe_allow_html=True)
        else:
            st.warning("ĐỨNG NGOÀI (WAIT) – chưa đủ điểm đồng thuận")
        if info["reasons"]:
            for cat, pts, txt in info["reasons"]:
                st.write(f"• **{cat} (+{pts}đ):** {txt}")
        else:
            st.write("Chưa có chỉ báo nào đóng góp điểm.")

        st.markdown("---")
        st.markdown("#### Backtest (tính từ dữ liệu đã tải)")
        trades = run_backtest(df)
        t = trades[trades["Mã"] == code] if not trades.empty else trades
        stats = backtest_stats(t) if not t.empty else None
        if stats is None or stats["n"] < 5:
            st.caption("Chưa đủ lệnh mô phỏng cho mã này (cần dữ liệu dài hơn).")
        else:
            st.metric("Win rate", f"{stats['win']:.1f}%")
            st.metric("Profit factor", "∞" if stats["pf"] == float("inf") else f"{stats['pf']:.2f}")
            st.metric("Max drawdown", f"{stats['mdd']:.1f}R")
            st.caption(f"{stats['n']} lệnh · kỳ vọng {stats['exp']:.2f}R/lệnh · thoát tối đa 20 phiên")

    st.caption("Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")


# ------------------------------------------------------------------ ĐIỀU HƯỚNG
filter_page = st.Page(page_filter, title="Bộ lọc", icon="🔍", url_path="bo-loc", default=True)
chart_page = st.Page(page_chart, title="Biểu đồ", icon="📊", url_path="bieu-do")
st.navigation([filter_page, chart_page]).run()
