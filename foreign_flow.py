"""Dashboard theo dõi giao dịch mua/bán ròng khối ngoại.

Nguồn dữ liệu được nạp từ data/foreign_flow.csv hoặc CSV tải lên trong giao diện.
Không suy diễn giao dịch khối ngoại từ dữ liệu giá OHLCV.
"""
from __future__ import annotations
import os
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

DATA_PATH = "data/foreign_flow.csv"
REQUIRED = ["Ngày", "Mã", "Giá trị mua", "Giá trị bán"]
OPTIONAL_DEFAULTS = {
    "Sàn": "", "Khối lượng mua": 0, "Khối lượng bán": 0,
    "Giá đóng cửa": None, "Tổng GTGD": None, "Nhóm ngành": "Khác"
}
TEMPLATE_COLS = REQUIRED + list(OPTIONAL_DEFAULTS.keys())


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=TEMPLATE_COLS + ["Mua/bán ròng", "Lũy kế 5 phiên", "Lũy kế 20 phiên", "Tỷ lệ ròng/GTGD"])
    df = df.copy()
    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
    aliases = {
        "trading_date": "Ngày", "date": "Ngày", "symbol": "Mã", "ticker": "Mã",
        "exchange": "Sàn", "buy_value": "Giá trị mua", "foreign_buy_value": "Giá trị mua",
        "sell_value": "Giá trị bán", "foreign_sell_value": "Giá trị bán",
        "buy_volume": "Khối lượng mua", "sell_volume": "Khối lượng bán",
        "close": "Giá đóng cửa", "turnover": "Tổng GTGD", "sector": "Nhóm ngành"
    }
    df = df.rename(columns={c: aliases.get(c.lower(), c) for c in df.columns})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("Thiếu cột bắt buộc: " + ", ".join(missing))
    for c, default in OPTIONAL_DEFAULTS.items():
        if c not in df.columns:
            df[c] = default
    df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce", dayfirst=True)
    df["Mã"] = df["Mã"].astype(str).str.upper().str.strip()
    for c in ["Giá trị mua", "Giá trị bán", "Khối lượng mua", "Khối lượng bán", "Giá đóng cửa", "Tổng GTGD"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Ngày", "Mã", "Giá trị mua", "Giá trị bán"])
    df = df[df["Mã"].ne("")]
    df["Mua/bán ròng"] = df["Giá trị mua"].fillna(0) - df["Giá trị bán"].fillna(0)
    df = df.sort_values(["Mã", "Ngày"])
    df["Lũy kế 5 phiên"] = df.groupby("Mã")["Mua/bán ròng"].transform(lambda s: s.rolling(5, min_periods=1).sum())
    df["Lũy kế 20 phiên"] = df.groupby("Mã")["Mua/bán ròng"].transform(lambda s: s.rolling(20, min_periods=1).sum())
    df["Tỷ lệ ròng/GTGD"] = df["Mua/bán ròng"] / df["Tổng GTGD"].replace(0, pd.NA) * 100
    return df.sort_values(["Ngày", "Mã"]).reset_index(drop=True)


def _load_saved() -> pd.DataFrame:
    if not os.path.exists(DATA_PATH):
        return pd.DataFrame()
    try:
        return pd.read_csv(DATA_PATH)
    except Exception:
        return pd.DataFrame()


def render():
    st.title("🌐 Dòng tiền khối ngoại")
    st.caption("Theo dõi mua/bán ròng, dòng tiền theo cổ phiếu và nhóm ngành. Đơn vị giá trị mặc định: tỷ đồng; cần thống nhất đơn vị ở nguồn dữ liệu.")

    with st.expander("📥 Nạp dữ liệu khối ngoại", expanded=not os.path.exists(DATA_PATH)):
        st.markdown("Tải CSV có các cột bắt buộc **Ngày, Mã, Giá trị mua, Giá trị bán**. Cột bổ sung: Sàn, Khối lượng mua, Khối lượng bán, Giá đóng cửa, Tổng GTGD, Nhóm ngành.")
        st.caption("App không suy ra mua/bán ròng từ giá OHLCV. Để tự cập nhật tự động, cần kết nối API dữ liệu có trường giao dịch khối ngoại và quyền sử dụng phù hợp.")
        template = pd.DataFrame([
            {"Ngày":"2026-10-20", "Mã":"AAA", "Giá trị mua":100, "Giá trị bán":60, "Sàn":"HOSE", "Khối lượng mua":100000, "Khối lượng bán":60000, "Giá đóng cửa":25.4, "Tổng GTGD":500, "Nhóm ngành":"Ví dụ"}
        ], columns=TEMPLATE_COLS)
        st.download_button("Tải file CSV mẫu", template.to_csv(index=False).encode("utf-8-sig"), "foreign_flow_template.csv", "text/csv")
        uploaded = st.file_uploader("Chọn file CSV dữ liệu khối ngoại", type=["csv"], key="foreign_flow_upload")
        if uploaded is not None:
            try:
                incoming = pd.read_csv(uploaded)
                normalized = _normalize(incoming)
                os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
                normalized[TEMPLATE_COLS].to_csv(DATA_PATH, index=False, encoding="utf-8-sig")
                st.cache_data.clear()
                st.success(f"Đã lưu {len(normalized):,} dòng vào {DATA_PATH}. Dữ liệu sẽ được giữ trong thư mục app khi file được commit vào GitHub.")
                st.rerun()
            except Exception as e:
                st.error(f"Không đọc được file: {e}")

    try:
        raw = _load_saved()
        data = _normalize(raw)
    except Exception as e:
        st.error(f"Không thể đọc dữ liệu: {e}")
        return
    if data.empty:
        st.info("Chưa có dữ liệu khối ngoại. Tải file CSV mẫu, điền dữ liệu từ nguồn được cấp phép rồi nạp tại phần trên. Các bảng và biểu đồ sẽ tự hiện khi có dữ liệu hợp lệ.")
        st.markdown("**Bốn phần sẽ có sau khi nạp dữ liệu:** tổng quan mua/bán ròng, Top cổ phiếu, lịch sử 5–20 phiên và phân tích theo nhóm ngành.")
        return

    data["Ngày"] = pd.to_datetime(data["Ngày"], errors="coerce")
    dates = sorted(data["Ngày"].dropna().dt.date.unique())
    if not dates:
        st.warning("Không có ngày giao dịch hợp lệ trong dữ liệu.")
        return
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        chosen_date = st.selectbox("Ngày giao dịch", dates, index=len(dates)-1, format_func=lambda d: d.strftime("%d/%m/%Y"))
    with c2:
        exchanges = ["Tất cả"] + sorted([str(x) for x in data["Sàn"].dropna().unique() if str(x).strip()])
        exchange = st.selectbox("Sàn", exchanges)
    with c3:
        sectors = ["Tất cả"] + sorted([str(x) for x in data["Nhóm ngành"].dropna().unique() if str(x).strip()])
        sector = st.selectbox("Nhóm ngành", sectors)

    day = data[data["Ngày"].dt.date.eq(chosen_date)].copy()
    if exchange != "Tất cả": day = day[day["Sàn"].astype(str) == exchange]
    if sector != "Tất cả": day = day[day["Nhóm ngành"].astype(str) == sector]
    if day.empty:
        st.warning("Không có dữ liệu phù hợp với bộ lọc.")
        return
    net = float(day["Mua/bán ròng"].sum())
    total_buy, total_sell = float(day["Giá trị mua"].sum()), float(day["Giá trị bán"].sum())
    pos_count, neg_count = int((day["Mua/bán ròng"] > 0).sum()), int((day["Mua/bán ròng"] < 0).sum())
    k1,k2,k3,k4 = st.columns(4)
    k1.metric("Mua/bán ròng", f"{net:+,.1f} tỷ", delta="Mua ròng" if net > 0 else ("Bán ròng" if net < 0 else "Cân bằng"))
    k2.metric("Số mã có dữ liệu", f"{day['Mã'].nunique():,}")
    k3.metric("Tổng giá trị mua", f"{total_buy:,.1f} tỷ")
    k4.metric("Mã mua ròng / bán ròng", f"{pos_count} / {neg_count}")

    st.subheader("Top cổ phiếu mua/bán ròng")
    left, right = st.columns(2)
    top_buy = day.nlargest(10, "Mua/bán ròng").sort_values("Mua/bán ròng")
    top_sell = day.nsmallest(10, "Mua/bán ròng").sort_values("Mua/bán ròng")
    with left:
        st.markdown("**Mua ròng nhiều nhất**")
        fig = px.bar(top_buy, x="Mua/bán ròng", y="Mã", orientation="h", color_discrete_sequence=["#25a879"])
        fig.update_layout(height=360, margin=dict(l=10,r=10,t=10,b=10), xaxis_title="Mua/bán ròng (tỷ đồng)", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.markdown("**Bán ròng nhiều nhất**")
        fig = px.bar(top_sell, x="Mua/bán ròng", y="Mã", orientation="h", color_discrete_sequence=["#e05260"])
        fig.update_layout(height=360, margin=dict(l=10,r=10,t=10,b=10), xaxis_title="Mua/bán ròng (tỷ đồng)", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Lịch sử dòng tiền 5–20 phiên")
    selected = st.multiselect("Chọn mã để xem lịch sử", sorted(data["Mã"].unique()), default=list(top_buy.sort_values("Mua/bán ròng", ascending=False)["Mã"].head(3)), key="foreign_flow_symbols")
    history = data[data["Mã"].isin(selected)].copy()
    if not history.empty:
        history = history.sort_values(["Mã", "Ngày"])
        hist_metric = st.radio("Chỉ số lịch sử", ["Mua/bán ròng từng phiên", "Lũy kế 5 phiên", "Lũy kế 20 phiên"], horizontal=True)
        ycol = {"Mua/bán ròng từng phiên":"Mua/bán ròng", "Lũy kế 5 phiên":"Lũy kế 5 phiên", "Lũy kế 20 phiên":"Lũy kế 20 phiên"}[hist_metric]
        fig = px.line(history, x="Ngày", y=ycol, color="Mã", markers=True)
        fig.update_layout(height=400, margin=dict(l=10,r=10,t=10,b=10), yaxis_title="Tỷ đồng")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Dòng tiền theo nhóm ngành")
    sector_flow = day.groupby("Nhóm ngành", dropna=False).agg(**{"Mua/bán ròng":("Mua/bán ròng","sum"), "Số mã":("Mã","nunique"), "Mã mua ròng":("Mua/bán ròng",lambda s:int((s>0).sum())), "Mã bán ròng":("Mua/bán ròng",lambda s:int((s<0).sum()))}).reset_index().sort_values("Mua/bán ròng")
    fig = px.bar(sector_flow, x="Mua/bán ròng", y="Nhóm ngành", orientation="h", color="Mua/bán ròng", color_continuous_scale=["#e05260","#e5b34c","#25a879"])
    fig.update_layout(height=max(280, 34*len(sector_flow)), margin=dict(l=10,r=10,t=10,b=10), coloraxis_showscale=False, xaxis_title="Mua/bán ròng (tỷ đồng)", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Bảng dữ liệu chi tiết")
    show_cols = [c for c in ["Ngày","Mã","Sàn","Nhóm ngành","Giá trị mua","Giá trị bán","Mua/bán ròng","Khối lượng mua","Khối lượng bán","Giá đóng cửa","Tổng GTGD","Tỷ lệ ròng/GTGD","Lũy kế 5 phiên","Lũy kế 20 phiên"] if c in day.columns]
    st.dataframe(day[show_cols].sort_values("Mua/bán ròng", ascending=False), use_container_width=True, hide_index=True)
    st.download_button("Xuất bảng đang lọc (CSV)", day[show_cols].to_csv(index=False).encode("utf-8-sig"), "foreign_flow_filtered.csv", "text/csv")
    st.caption("Lũy kế được tính trên các dòng dữ liệu theo từng mã trong file đã nạp. Hãy bảo đảm file có đủ các phiên giao dịch liên tiếp và đơn vị giá trị thống nhất. Đây là công cụ phân tích dữ liệu, không phải khuyến nghị mua/bán.")
