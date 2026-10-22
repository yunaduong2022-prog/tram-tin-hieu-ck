"""Số liệu thị trường tự tính từ data/eod_prices.csv cho trang Góc nhìn thị trường (không phụ thuộc Streamlit).

- VN-Index lấy từ mã VNINDEX trong file giá (đơn vị điểm).
- Thanh khoản và độ rộng chỉ tính trên RỔ MÃ của app (~200 mã), không phải toàn thị trường,
  nên là số tương đối (so với phiên trước, trung bình 20 phiên), không dùng để so với con số của sàn.
"""
from __future__ import annotations

import pandas as pd

INDEX_CODES = {"VNINDEX", "VN-INDEX", "VNI", "VN INDEX", "^VNINDEX"}
CLOSE, VOL = "Giá đóng cửa", "Khối lượng khớp lệnh"


def daily_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Bảng mỗi phiên một dòng: value (tỷ đồng, rổ), up/down/flat/n (số mã), index (điểm VN-Index)."""
    d = raw[["Mã", "Ngày", CLOSE, VOL]].copy()
    d["Mã"] = d["Mã"].astype(str).str.upper()
    is_idx = d["Mã"].isin(INDEX_CODES)
    idx = d[is_idx].groupby("Ngày")[CLOSE].last().sort_index()
    if len(idx) and idx.median() < 10:            # phòng khi điểm bị chia 1.000 ở bước lấy dữ liệu
        idx = idx * 1000
    s = d[~is_idx].sort_values(["Mã", "Ngày"]).copy()
    s["value"] = s[CLOSE] * s[VOL].fillna(0) / 1e6          # giá nghìn đồng x cổ phiếu -> tỷ đồng
    cnt = s.groupby("Ngày")["Mã"].nunique()
    cal = cnt[cnt >= max(1, 0.3 * s["Mã"].nunique())].index.sort_values()   # lịch phiên của thị trường
    prev_cal = pd.Series(cal[:-1], index=cal[1:])
    g = s.groupby("Mã")
    s["prev_close"], s["prev_date"] = g[CLOSE].shift(1), g["Ngày"].shift(1)
    ok = s["prev_date"] == s["Ngày"].map(prev_cal)                          # chỉ so với đúng phiên kề trước
    diff = (s[CLOSE] - s["prev_close"]).where(ok)
    s["up"], s["down"] = diff > 0.001, diff < -0.001
    s["flat"] = ok & ~s["up"] & ~s["down"]
    gd = s[s["Ngày"].isin(cal)].groupby("Ngày")
    t = pd.DataFrame({"value": gd["value"].sum(), "up": gd["up"].sum(), "down": gd["down"].sum(),
                      "flat": gd["flat"].sum(), "n": gd["Mã"].nunique()})
    t["index"] = idx.reindex(t.index)
    return t


def _pct(a, b):
    return (a / b - 1) * 100 if b and b > 0 else None


def stats_for(t: pd.DataFrame, day) -> dict | None:
    """Số liệu của một ngày; None nếu ngày đó không có trong dữ liệu."""
    day = pd.Timestamp(day).normalize()
    if t is None or t.empty or day not in t.index:
        return None
    i = t.index.get_loc(day)
    out: dict = {"date": day}
    v = t["value"]
    out["value"] = float(v.iloc[i])
    out["value_prev_pct"] = _pct(v.iloc[i], v.iloc[i - 1]) if i > 0 else None
    w = v.iloc[max(0, i - 20):i]
    out["value_avg20_pct"] = _pct(v.iloc[i], w.mean()) if len(w) >= 10 else None
    n = 0                                            # số phiên liền trước đều có thanh khoản thấp hơn hôm nay
    for j in range(i - 1, max(-1, i - 121), -1):
        if v.iloc[j] > v.iloc[i]:
            break
        n += 1
    out["value_highest_n"] = n if n >= 20 else None
    for c in ("up", "down", "flat", "n"):
        out[c] = int(t[c].iloc[i])
    ix = t["index"].iloc[: i + 1].dropna()
    if len(ix) and ix.index[-1] == day:
        close = float(ix.iloc[-1])
        out["index"] = close
        if len(ix) > 1:
            out["index_pts"] = close - float(ix.iloc[-2])
            out["index_pct"] = _pct(close, float(ix.iloc[-2]))
        if len(ix) >= 20:
            out["ma20"] = float(ix.tail(20).mean())
            if len(ix) >= 25:
                out["ma20_5ago"] = float(ix.iloc[:-5].tail(20).mean())
            out["hi20"], out["lo20"] = float(ix.tail(20).max()), float(ix.tail(20).min())
            out["from_lo20_pct"] = _pct(close, out["lo20"])
    return out


def foreign_from_csv(path: str) -> pd.Series:
    """Mua/bán ròng khối ngoại theo ngày (tỷ đồng) cộng từ data/foreign_flow.csv; rỗng nếu chưa có file."""
    import os
    if not os.path.exists(path):
        return pd.Series(dtype=float)
    df = pd.read_csv(path)
    df.columns = [str(c).strip().replace("\ufeff", "") for c in df.columns]
    if not {"Ngày", "Giá trị mua", "Giá trị bán"} <= set(df.columns):
        return pd.Series(dtype=float)
    df["Ngày"] = pd.to_datetime(df["Ngày"], errors="coerce", dayfirst=True)
    net = pd.to_numeric(df["Giá trị mua"], errors="coerce").fillna(0) - pd.to_numeric(df["Giá trị bán"], errors="coerce").fillna(0)
    return net.groupby(df["Ngày"]).sum().dropna().sort_index()


def foreign_stats(series: pd.Series, day) -> dict | None:
    """Mua/bán ròng của một ngày và lũy kế 5 phiên gần nhất (chỉ khi đủ 5 ngày có số liệu trong 9 ngày lịch)."""
    day = pd.Timestamp(day).normalize()
    if series is None or day not in series.index:
        return None
    out = {"value": float(series.loc[day])}
    last5 = series[series.index <= day].tail(5)
    if len(last5) == 5 and (day - last5.index[0]).days <= 9:
        out["cum5"] = float(last5.sum())
    return out
