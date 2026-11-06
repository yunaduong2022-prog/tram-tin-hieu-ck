"""Min Invest — read-only Top 10 MA strength from confirmed EOD bars.

No network, files, persistence, or DNSE intraday calls. Rankings use the same
EOD date as the MA dashboard and never forward-fill missing sessions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

_INDEX = ("VNINDEX", "VN-INDEX", "VN_INDEX", "^VNINDEX")
_MAS = (10, 20, 50, 100, 200)


def _valid(*values):
    return all(pd.notna(v) and np.isfinite(float(v)) and float(v) > 0 for v in values)


def _clean_history(daily):
    cols = {"Mã", "Ngày", "Giá đóng cửa"}
    if daily is None or daily.empty or not cols.issubset(daily.columns):
        return pd.DataFrame()
    d = daily.copy()
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    d["Ngày"] = pd.to_datetime(d["Ngày"], errors="coerce", dayfirst=True).dt.normalize()
    d["Giá đóng cửa"] = pd.to_numeric(d["Giá đóng cửa"], errors="coerce")
    for n in _MAS:
        key = f"MA{n}"
        d[key] = pd.to_numeric(d[key], errors="coerce") if key in d else np.nan
    d = d.dropna(subset=["Ngày", "Giá đóng cửa"])
    d = d[d["Giá đóng cửa"] > 0]
    return d.sort_values(["Mã", "Ngày"]).drop_duplicates(["Mã", "Ngày"], keep="last")


def rank_ma(daily, asof, groups=None, sector="Toàn thị trường", names=None, index_daily=None, limit=10):
    """Two ranked tables (total and short-term), strictly on asof EOD.

    100-point transparent rules:
    TOTAL: 40 price-vs-MAs, 40 ordering, 10 slope, 10 RS20.
    SHORT: 50 price-vs-MAs, 30 ordering, 10 slope, 10 RS20.
    The optional RS20 points are *not* awarded if VNINDEX EOD is absent.
    """
    empty = pd.DataFrame(columns=["Mã", "Tên công ty", "Giá", "Tổng hợp", "Ngắn hạn", "RS20", "Ngày"])
    h = _clean_history(daily)
    if h.empty:
        return empty.copy(), empty.copy(), False
    cutoff = pd.Timestamp(asof).normalize()
    h = h[h["Ngày"] <= cutoff]
    if h.empty:
        return empty.copy(), empty.copy(), False
    group_set = None
    if sector != "Toàn thị trường":
        group_set = {str(v).strip().upper() for v in (groups or {}).get(sector, [])}
    # MIN_RS20_INDEX_CSV_V1: index_daily is read from existing index_prices.csv.
    # Keep exactly matched trading dates; do not forward-fill missing index bars.
    index = pd.Series(dtype="float64")
    if isinstance(index_daily, pd.DataFrame) and {"Ngày", "Giá đóng cửa"}.issubset(index_daily.columns):
        idx = index_daily[["Ngày", "Giá đóng cửa"]].copy()
        idx["Ngày"] = pd.to_datetime(idx["Ngày"], errors="coerce", dayfirst=True).dt.normalize()
        idx["Giá đóng cửa"] = pd.to_numeric(idx["Giá đóng cửa"], errors="coerce")
        idx = idx.dropna(subset=["Ngày", "Giá đóng cửa"])
        idx = idx[(idx["Giá đóng cửa"] > 0) & (idx["Ngày"] <= cutoff)]
        if not idx.empty:
            index = (idx.sort_values("Ngày").drop_duplicates("Ngày", keep="last")
                     .set_index("Ngày")["Giá đóng cửa"])
    # Backward compatible: reuse index rows embedded in the stock input if needed.
    if cutoff not in index.index:
        for sym in _INDEX:
            tmp = h[h["Mã"] == sym].set_index("Ngày")["Giá đóng cửa"]
            if not tmp.empty and cutoff in tmp.index:
                index = tmp
                break
    rs_exists = bool(not index.empty and cutoff in index.index)
    labels = names or {}
    rows = []
    for sym, part in h.groupby("Mã", sort=False):
        if sym in _INDEX or (group_set is not None and sym not in group_set):
            continue
        part = part.sort_values("Ngày").reset_index(drop=True)
        last = part.iloc[-1]
        # Current snapshots only: no earlier EOD stock can rank today.
        if last["Ngày"] != cutoff:
            continue
        p = last["Giá đóng cửa"]
        ma = {n:last[f"MA{n}"] for n in _MAS}
        if not _valid(p, *ma.values()):
            # All five MAs are necessary for comparable 100-point total scores.
            continue
        total = sum(w for n, w in ((10,10),(20,10),(50,10),(100,5),(200,5)) if p > ma[n])
        total += 15 * (ma[10] > ma[20])
        total += 15 * (ma[20] > ma[50] > ma[100])
        total += 10 * (ma[50] > ma[100] > ma[200])
        short = 25 * (p > ma[10]) + 15 * (p > ma[20]) + 10 * (p > ma[50])
        short += 20 * (ma[10] > ma[20]) + 10 * (ma[20] > ma[50])
        # Slope compares MA values 5 observations apart (5 stock sessions).
        if len(part) >= 6:
            prev = part.iloc[-6]
            if _valid(prev["MA10"], prev["MA20"]):
                rising = ma[10] > prev["MA10"] and ma[20] > prev["MA20"]
                total += 10 * rising
                short += 10 * rising
        rs20 = np.nan
        if rs_exists and len(part) >= 21:
            old = part.iloc[-21]
            old_date = old["Ngày"]
            if old_date in index.index and _valid(old["Giá đóng cửa"], index.loc[old_date], index.loc[cutoff]):
                rs20 = (p / old["Giá đóng cửa"] / (index.loc[cutoff] / index.loc[old_date]) - 1) * 100
                if rs20 > 0:
                    total += 10
                    short += 10
        rows.append({"Mã":sym, "Tên công ty":labels.get(sym, ""), "Giá":float(p),
                     "Tổng hợp":int(total), "Ngắn hạn":int(short), "RS20":rs20, "Ngày":cutoff})
    if not rows:
        return empty.copy(), empty.copy(), rs_exists
    table = pd.DataFrame(rows)
    total = table.sort_values(["Tổng hợp","Ngắn hạn","Mã"], ascending=[False,False,True]).head(limit if limit is not None else len(table)).reset_index(drop=True)
    short = table.sort_values(["Ngắn hạn","Tổng hợp","Mã"], ascending=[False,False,True]).head(limit if limit is not None else len(table)).reset_index(drop=True)
    return total, short, rs_exists


def render_top10(snapshot, daily, asof, sector, groups, index_daily=None):
    """Render directly above stock cards, scoped only by selected sector."""
    names = dict(zip(snapshot["Mã"], snapshot["Tên công ty"])) if "Tên công ty" in snapshot else {}
    overall, short, has_index = rank_ma(daily, asof, groups, sector, names, index_daily=index_daily)
    st.subheader("🏆 Top 10 cổ phiếu mạnh nhất theo cấu trúc MA")
    st.caption(f"Phạm vi: {sector} · EOD {pd.Timestamp(asof):%d/%m/%Y} · chỉ xếp hạng mã đủ MA10/20/50/100/200 và có giá đúng ngày. Top 10 độc lập với bộ lọc tìm kiếm/trạng thái bên dưới.")
    tabs = st.tabs(["Top 10 tổng hợp", "Top 10 ngắn hạn (T+15–T+30)"])
    for tab, frame, key in zip(tabs, (overall, short), ("Tổng hợp", "Ngắn hạn")):
        with tab:
            if frame.empty:
                st.info("Chưa có mã đủ dữ liệu MA và EOD đúng phiên để xếp hạng.")
                continue
            view = frame[["Mã", "Tên công ty", "Giá", key, "RS20"]].copy()
            view.insert(0, "Hạng", range(1, len(view)+1))
            view["RS20"] = view["RS20"].map(lambda v: f"{float(v):+.2f}" if pd.notna(v) else "—")
            view = view.rename(columns={"Giá":"Giá EOD (nghìn đồng)",key:"Điểm / 100", "RS20":"RS20 so VN-Index (%)"})
            st.dataframe(view, hide_index=True, use_container_width=True,
                         column_config={"Điểm / 100":st.column_config.ProgressColumn("Điểm / 100", min_value=0, max_value=100, format="%d"),
                                        "Giá EOD (nghìn đồng)":st.column_config.NumberColumn("Giá EOD (nghìn đồng)",format="%.2f"),
                                        "RS20 so VN-Index (%)":st.column_config.TextColumn("RS20 so VN-Index (%)")})
    if not has_index:
        st.caption("RS20: không có chuỗi VN-Index chuẩn cùng phiên trong dữ liệu đầu vào, nên chưa cộng tối đa 10 điểm RS20 (điểm thực tế tối đa 90). Không thay bằng thị trường giả định.")
    st.caption("Tổng hợp = giá trên 5 MA (40đ) + trật tự MA (40đ) + MA10/MA20 cùng dốc lên (10đ) + RS20 dương (10đ). Ngắn hạn = vị trí giá so MA10/20/50 (50đ) + MA10>MA20 và MA20>MA50 (30đ) + độ dốc (10đ) + RS20 (10đ). Điểm là thước đo kỹ thuật, không phải khuyến nghị mua.")
