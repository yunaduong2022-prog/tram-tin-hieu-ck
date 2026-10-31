"""Giao diện "Bộ lọc & Backtest > Backtest chiến lược" và bộ đọc số liệu backtest cho thẻ Phân loại trạng thái.

Dữ liệu do hai script ghi ra (chạy ngoài app):
  backtest_setups.py -> data/setup_stats.csv, data/setup_stats_meta.json, data/setup_trades.csv
  forward_log.py     -> data/forward_signals.csv, data/forward_summary.csv
Nếu chưa có file thì app dùng số cũ (FALLBACK_BT) và trang này hướng dẫn chạy script.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

import theme as TH

STATS, META, FWD_LOG, FWD_SUM = ("data/setup_stats.csv", "data/setup_stats_meta.json", "data/forward_signals.csv", "data/forward_summary.csv")

# Số cũ (backtest 147 mã 2019-2026) chỉ dùng khi chưa có data/setup_stats.csv: (số lệnh, lãi TB %, thắng %, R/lệnh)
FALLBACK_BT = {"BOTTOM": (603, 4.1, 37, 0.53), "BASE_HL": (1309, 2.8, 34, 0.36), "BREAKOUT": (3074, 1.5, 30, 0.25), "TREND": (3629, 3.0, 34, 0.50)}
FALLBACK_BASE = (5880, 2.1, 34, 0.31)
SETUP_ORDER = ("BOTTOM", "BASE_HL", "BREAKOUT", "TREND", "RANGE", "WEAK")
GROUPS = {"ALL": "Toàn kỳ", "IS": "Trong mẫu (IS)", "OOS": "Ngoài mẫu (OOS)", "VNI Tăng": "VNINDEX trên MA200", "VNI Giảm": "VNINDEX dưới MA200"}


def _mtime(p: str) -> float:
    try:
        return Path(p).stat().st_mtime
    except OSError:
        return 0.0


@st.cache_data(show_spinner=False, max_entries=4)
def _read_csv(path: str, mtime: float) -> pd.DataFrame | None:
    try:
        return pd.read_csv(path, encoding="utf-8-sig", dtype={"Mã": str})
    except (OSError, ValueError, pd.errors.EmptyDataError):
        return None


@st.cache_data(show_spinner=False, max_entries=2)
def _read_meta(path: str, mtime: float) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_stats() -> tuple[pd.DataFrame | None, dict]:
    return _read_csv(STATS, _mtime(STATS)), _read_meta(META, _mtime(META))


def load_setup_bt() -> dict:
    """Số liệu cho thẻ setup trong app: {'bt': {setup: (n, lãi TB %, thắng %, R)}, 'base': (...), 'oos': {...}, 'neg_years': {...}, 'meta': {...}, 'src': 'file'|'fallback'}."""
    stats, meta = load_stats()
    if stats is None or stats.empty:
        return {"bt": FALLBACK_BT, "base": FALLBACK_BASE, "oos": {}, "neg_years": {}, "sig": {}, "meta": {}, "src": "fallback"}

    def pick(setup: str, grp: str):
        m = stats[(stats["Setup"] == setup) & (stats["Nhóm"] == grp)]
        if m.empty:
            return None
        r = m.iloc[0]
        return (int(r["Số lệnh"]), float(r["Lãi TB %"]), float(r["Thắng %"]), float(r["R TB"]))

    bt, oos, neg, sig = {}, {}, {}, {}
    for s in SETUP_ORDER:
        v = pick(s, "ALL")
        if v:
            bt[s] = v
        o = pick(s, "OOS")
        if o:
            oos[s] = o
        yrs = stats[(stats["Setup"] == s) & stats["Nhóm"].astype(str).str.startswith("Năm ") & (stats["Lãi TB %"] < 0)]
        neg[s] = sorted(int(str(x)[4:]) for x in yrs["Nhóm"])
        m = stats[(stats["Setup"] == s) & (stats["Nhóm"] == "ALL")]
        sig[s] = bool(m["Vượt nền (CI95)"].iat[0]) if not m.empty else False
    return {"bt": bt, "base": pick("BASE", "ALL") or FALLBACK_BASE, "base_oos": pick("BASE", "OOS"), "oos": oos, "neg_years": neg, "sig": sig, "meta": meta, "src": "file"}


def verdict(stats: pd.DataFrame, setup: str) -> str:
    """Kết luận một dòng cho setup: dựa trên cả toàn kỳ lẫn ngoài mẫu so với mức nền (vào ngẫu nhiên)."""
    def g(grp):
        m = stats[(stats["Setup"] == setup) & (stats["Nhóm"] == grp)]
        return m.iloc[0] if not m.empty else None
    a, o = g("ALL"), g("OOS")
    if a is None:
        return "—"
    if not bool(a["Vượt nền (CI95)"]):
        return "Không hơn mua ngẫu nhiên" if a["R hơn nền"] <= 0 else "Chưa đủ bằng chứng"
    if o is not None and bool(o["Vượt nền (CI95)"]):
        return "Có lợi thế, còn ngoài mẫu"
    if o is not None and o["R hơn nền"] > 0:
        return "Có lợi thế, ngoài mẫu yếu hơn (chưa chắc)"
    return "Có lợi thế nhưng mất đi ngoài mẫu"


def _plot_template() -> str:
    return "plotly_dark" if TH.is_dark() else "plotly_white"


def _fmt_cols(d: pd.DataFrame) -> dict:
    cfg = {}
    for c, fmt in (("Lãi TB %", "%.2f"), ("Lãi trung vị %", "%.2f"), ("Thắng %", "%.1f"), ("R TB", "%.3f"), ("R trung vị", "%.3f"),
                   ("R TB (CI95 thấp)", "%.3f"), ("R TB (CI95 cao)", "%.3f"), ("Profit factor", "%.2f"), ("MDD (R)", "%.2f"),
                   ("R hơn nền", "%+.3f"), ("Giữ TB (phiên)", "%.1f"), ("R TB bỏ 5% lệnh tốt nhất", "%.3f")):
        if c in d.columns:
            cfg[c] = st.column_config.NumberColumn(c, format=fmt)
    return cfg


def render(stretch: dict) -> None:
    st.title("🧪 Backtest chiến lược")
    st.caption("Đo xem các setup của **Phân loại trạng thái** (Bùng nổ đáy, Đáy nâng, Vượt đỉnh, Xu hướng tăng, ...) có thật sự hơn mua ngẫu nhiên hay không, "
               "trên toàn bộ dữ liệu, đã trừ phí, thuế, trượt giá và T+2. Số liệu do `backtest_setups.py` ghi ra, thẻ setup trong app đọc từ cùng file này. "
               "Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.")
    stats, meta = load_stats()
    t1, t2, t3 = st.tabs(["📊 Backtest", "🔭 Theo dõi tín hiệu thực", "ℹ️ Cách đọc & giới hạn"])
    with t1:
        _tab_backtest(stats, meta, stretch)
    with t2:
        _tab_forward(stretch)
    with t3:
        _tab_notes(meta)


# ------------------------------------------------------------------ tab 1
def _tab_backtest(stats: pd.DataFrame | None, meta: dict, stretch: dict) -> None:
    if stats is None or stats.empty:
        st.info("Chưa có số liệu backtest. Chạy `python backtest_setups.py` trong thư mục dự án (khoảng 1 phút) để tạo `data/setup_stats.csv`. "
                "Trong lúc đó thẻ setup vẫn dùng số cũ (147 mã, 2019-2026).")
        return
    m = st.columns(4)
    m[0].metric("Chạy lúc", meta.get("chạy lúc", "—"))
    m[1].metric("Dữ liệu", f"{meta.get('dữ liệu từ', '?')[:4]} - {meta.get('dữ liệu đến', '?')[:4]}", help=f"{meta.get('dữ liệu từ', '?')} → {meta.get('dữ liệu đến', '?')}")
    m[2].metric("Số mã", meta.get("số mã", "—"))
    m[3].metric("Ngày tách IS / OOS", meta.get("ngày tách IS/OOS", "—"), help="Tham số setup được chọn trên dữ liệu cũ; OOS là phần kiểm tra sau đó.")
    if meta.get("số mã đã ngừng giao dịch", 1) == 0:
        st.warning("Dữ liệu chỉ có mã đang niêm yết (không có mã đã hủy niêm yết hay ngừng giao dịch), nên kết quả có xu hướng lạc quan hơn thực tế (độ lệch sống sót).")

    st.subheader("Kết luận nhanh")
    rows = []
    for s in SETUP_ORDER:
        a = stats[(stats["Setup"] == s) & (stats["Nhóm"] == "ALL")]
        i = stats[(stats["Setup"] == s) & (stats["Nhóm"] == "IS")]
        o = stats[(stats["Setup"] == s) & (stats["Nhóm"] == "OOS")]
        if a.empty:
            continue
        rows.append({"Setup": s, "Nhãn": a["Nhãn"].iat[0], "Số lệnh": int(a["Số lệnh"].iat[0]), "R TB toàn kỳ": a["R TB"].iat[0],
                     "R TB trong mẫu": i["R TB"].iat[0] if len(i) else np.nan, "R TB ngoài mẫu": o["R TB"].iat[0] if len(o) else np.nan,
                     "R hơn nền (toàn kỳ)": a["R hơn nền"].iat[0], "Kết luận": verdict(stats, s)})
    base = {g: stats[(stats["Setup"] == "BASE") & (stats["Nhóm"] == g)]["R TB"] for g in ("ALL", "IS", "OOS")}
    rows.append({"Setup": "BASE", "Nhãn": "Vào ngẫu nhiên (mức nền)", "Số lệnh": int(stats[(stats["Setup"] == "BASE") & (stats["Nhóm"] == "ALL")]["Số lệnh"].sum()),
                 "R TB toàn kỳ": base["ALL"].iat[0] if len(base["ALL"]) else np.nan, "R TB trong mẫu": base["IS"].iat[0] if len(base["IS"]) else np.nan,
                 "R TB ngoài mẫu": base["OOS"].iat[0] if len(base["OOS"]) else np.nan, "R hơn nền (toàn kỳ)": np.nan, "Kết luận": "Mốc so sánh"})
    q = pd.DataFrame(rows)
    st.dataframe(q, hide_index=True, column_config={c: st.column_config.NumberColumn(c, format="%+.3f") for c in q.columns if c.startswith("R ")}, **stretch)
    st.caption("R = lãi ròng chia cho rủi ro ban đầu (giá vào − cắt lỗ). **Có lợi thế** chỉ khi khoảng tin cậy 95% của R trung bình nằm hoàn toàn trên R của mức nền; "
               "nếu R ngoài mẫu thấp hơn nhiều so với trong mẫu thì lợi thế có thể là do chọn tham số trên dữ liệu cũ.")

    st.subheader("Chi tiết theo nhóm")
    grp = st.radio("Giai đoạn / chế độ thị trường", list(GROUPS), format_func=lambda k: GROUPS[k], horizontal=True, key="bt_grp")
    d = stats[stats["Nhóm"] == grp].copy()
    order = {s: k for k, s in enumerate((*SETUP_ORDER, "BASE"))}
    d = d.sort_values("Setup", key=lambda c: c.map(order))
    cols = ["Setup", "Nhãn", "Số lệnh", "Lãi TB %", "Lãi trung vị %", "Thắng %", "R TB", "R TB (CI95 thấp)", "R TB (CI95 cao)", "R trung vị",
            "R TB bỏ 5% lệnh tốt nhất", "Profit factor", "MDD (R)", "Giữ TB (phiên)", "R hơn nền", "Vượt nền (CI95)"]
    st.dataframe(d[[c for c in cols if c in d.columns]], hide_index=True, column_config=_fmt_cols(d), **stretch)
    st.caption("**R TB bỏ 5% lệnh tốt nhất**: nếu cột này gần 0 hoặc âm thì lợi nhuận chỉ đến từ vài lệnh lớn. **MDD (R)**: mức sụt giảm tối đa của đường vốn cộng dồn theo đơn vị R.")

    st.subheader("R trung bình theo năm")
    yr = stats[stats["Nhóm"].astype(str).str.startswith("Năm ")].copy()
    if not yr.empty:
        yr["Năm"] = yr["Nhóm"].str[4:].astype(int)
        pv = yr.pivot_table(index="Setup", columns="Năm", values="R TB").reindex([s for s in (*SETUP_ORDER, "BASE") if s in set(yr["Setup"])])
        try:
            import plotly.graph_objects as go
            fig = go.Figure(go.Heatmap(z=pv.values, x=[str(c) for c in pv.columns], y=list(pv.index), zmid=0, colorscale="RdYlGn",
                                       text=np.round(pv.values, 2), texttemplate="%{text}", hovertemplate="%{y} · %{x}: %{z:.3f}R<extra></extra>"))
            fig.update_layout(template=_plot_template(), height=320, margin=dict(l=10, r=10, t=10, b=10), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.dataframe(pv.round(3), **stretch)
        st.caption("Xanh = có lãi, đỏ = lỗ. Setup tốt thật sự nên xanh hơn dòng BASE ở đa số năm, không chỉ ở một vài năm.")


# ------------------------------------------------------------------ tab 2
def _tab_forward(stretch: dict) -> None:
    log = _read_csv(FWD_LOG, _mtime(FWD_LOG))
    summ = _read_csv(FWD_SUM, _mtime(FWD_SUM))
    st.markdown("Tín hiệu được **ghi lại ngay khi xuất hiện** bằng đúng quy tắc đang chạy, rồi đo kết quả khi đủ phiên. "
                "Đây là bằng chứng đáng tin hơn backtest vì không thể điều chỉnh lại sau khi đã biết kết quả.")
    if log is None or log.empty:
        st.info("Chưa có tín hiệu nào được ghi. Chạy `python forward_log.py` sau mỗi lần cập nhật dữ liệu cuối phiên (hoặc đưa vào `update_eod.bat`). "
                "Lần đầu chỉ ghi ngày mới nhất; kết quả cần vài tuần đến vài tháng để có ý nghĩa.")
        return
    c = st.columns(4)
    c[0].metric("Tổng tín hiệu", len(log))
    c[1].metric("Đã đóng", int((log["Trạng thái"] == "Đã đóng").sum()))
    c[2].metric("Đang mở", int((log["Trạng thái"] == "Đang mở").sum()))
    c[3].metric("Từ ngày", str(log["Ngày tín hiệu"].min())[:10])
    if summ is not None and not summ.empty:
        st.subheader("Tổng hợp theo setup")
        keep = [c_ for c_ in ("Setup", "Nhãn", "Tín hiệu", "Đã vào", "Đã đóng", "Thắng %", "R TB", "R backtest (toàn kỳ)", "R backtest (OOS)",
                              "Lãi 20p % (TB)", "Vs VNI 20p % (TB)", "N 20p", "Lãi 60p % (TB)", "Vs VNI 60p % (TB)", "N 60p", "Đủ mẫu") if c_ in summ.columns]
        st.dataframe(summ[keep], hide_index=True, column_config={c_: st.column_config.NumberColumn(c_, format="%.2f") for c_ in keep if c_.startswith(("Lãi", "Vs", "R ", "Thắng"))}, **stretch)
        if not summ["Đủ mẫu"].any():
            st.warning("Chưa setup nào có đủ 30 lệnh đã đóng: các con số trên chưa kết luận được gì, chỉ để theo dõi.")
        st.caption("So cột **R TB** (thực tế) với **R backtest**: nếu thực tế thấp hơn rõ rệt và đã đủ mẫu thì setup có thể không còn hiệu quả. "
                   "**Vs VNI** là lợi suất vượt VNINDEX cùng kỳ (điểm phần trăm).")
    st.subheader("Tín hiệu gần đây")
    sel = st.multiselect("Setup", sorted(log["Setup"].dropna().unique()), key="fwd_setup", placeholder="Tất cả")
    d = log[log["Setup"].isin(sel)] if sel else log
    d = d.sort_values(["Ngày tín hiệu", "Mã"], ascending=[False, True]).head(300)
    show = [c_ for c_ in ("Ngày tín hiệu", "Mã", "Setup", "Giá đóng cửa", "Điểm vào tham chiếu", "Cắt lỗ", "Giá vào", "Trạng thái", "Lý do thoát", "R", "Lãi %",
                          "Lãi 20p %", "Vs VNI 20p %", "Lãi 60p %") if c_ in d.columns]
    st.dataframe(d[show], hide_index=True, **stretch)


# ------------------------------------------------------------------ tab 3
def _tab_notes(meta: dict) -> None:
    cost = meta.get("chi phí") or {}
    st.markdown(f"""
**Quy tắc mô phỏng** (cùng cách trong `backtest_setups.py`, chi phí lấy từ `engine.BT_COST`)
- Vào ở **giá mở cửa phiên kế tiếp** sau khi tín hiệu xuất hiện (cộng trượt giá, làm tròn lên bước giá). Phiên mở cửa khóa trần thì không mua được.
- **Cắt lỗ** theo `setups.choose_stop()` từ điểm vào tham chiếu. Thoát khi chạm cắt lỗ, khi đóng cửa dưới Supertrend (sau khi Supertrend đã tăng), hoặc sau {meta.get('max_hold', 60)} phiên.
- **T+2**: hai phiên đầu không bán được; cắt lỗ chạm trong thời gian đó thì bán ở mở cửa phiên đầu tiên bán được. Gap xuống dưới cắt lỗ thì khớp ở giá mở cửa.
- **Chi phí**: phí {cost.get('fee', 0.0015):.2%}/chiều, thuế bán {cost.get('sell_tax', 0.001):.2%}, trượt giá {cost.get('slip', 0.001):.2%}/chiều.
- **Mức nền (BASE)**: vào ngẫu nhiên cùng cách cắt lỗ và thoát. Setup chỉ đáng tin khi hơn mức này một cách có ý nghĩa.

**Giới hạn cần nhớ**
- **Độ lệch sống sót**: chỉ có mã còn trong dữ liệu; mã đã hủy niêm yết hoặc giảm sâu thường vắng mặt, làm kết quả lạc quan.
- **Chọn tham số trên chính dữ liệu kiểm tra**: ngưỡng của setup (biên độ nền, khối lượng, số phiên...) được chọn qua backtest cũ. Phần OOS là phép kiểm tra thật; phần IS thì không.
- **Lợi nhuận dồn vào vài lệnh lớn**: tỷ lệ thắng khoảng một phần ba, nên xem R trung vị, R bỏ 5% lệnh tốt nhất và MDD chứ không chỉ lãi trung bình.
- **Các lệnh chồng nhau**: nhiều mã báo cùng lúc trong một nhịp thị trường nên không độc lập; khoảng tin cậy thực tế rộng hơn con số hiển thị.
- **Chế độ thị trường**: chọn nhóm "VNINDEX trên / dưới MA200" ở tab này để xem setup phụ thuộc xu hướng chung đến đâu.
- Kết quả quá khứ không bảo đảm tương lai. Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
""")
