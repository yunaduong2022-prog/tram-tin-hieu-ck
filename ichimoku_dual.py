"""Dual Ichimoku: hai bộ Ichimoku cùng hiển thị trên biểu đồ giá (chuyển từ Pine v5 "Min Invest - Dual Ichimoku Setup").

Bộ 1 (9 - 26 - 52, dịch 26): chỉ vẽ MÂY KUMO, gồm Lead 1 (Senkou Span A), Leading Span B (Senkou Span B) và nền mây.
                              Tắt Tenkan, Kijun, Chikou.
Bộ 2 (65 - 129):              chỉ vẽ Tenkan-sen (xanh dương) và Kijun-sen (cam); không có mây, không có Chikou, không dịch.

Tenkan / Kijun / Span đều là trung điểm Donchian: (cao nhất N nến + thấp nhất N nến) / 2.
Mây vẽ lệch về tương lai `displacement - 1` nến, đúng như Pine (offset = displacement - 1), nên 25 nến cuối nằm
phía bên phải nến cuối cùng. Tham số chỉnh ở CFG.

Cần đủ lịch sử: Kijun 129 cần 129 nến, mây cần 52 nến. Khung Tháng thường không đủ 129 nến nên chỉ hiện phần có dữ liệu.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CFG = {
    "t1": 9, "k1": 26, "b1": 52, "disp1": 26,   # bộ 1: Tenkan, Kijun, Span B, độ dịch của mây
    "t2": 65, "k2": 129,                         # bộ 2: Tenkan, Kijun
}
COL = {
    "span_a": "#26A69A",      # teal (Lead 1)
    "span_b": "#800000",      # maroon (Leading Span B)
    "up": "rgba(76,175,80,0.25)",     # mây tăng: xanh lá, trong suốt 75%
    "down": "rgba(244,67,54,0.25)",   # mây giảm: đỏ, trong suốt 75%
    "tenkan2": "#2962FF",     # xanh dương
    "kijun2": "#FF9800",      # cam (Pine dùng color.orange)
}


def _donchian(h: pd.Series, l: pd.Series, n: int) -> pd.Series:
    return (h.rolling(n).max() + l.rolling(n).min()) / 2


def compute(g: pd.DataFrame, n_show: int, future_fn, cfg: dict | None = None) -> dict:
    """Tính dữ liệu vẽ cho `n_show` nến cuối của g (g đã sắp xếp theo ngày, đủ lịch sử để tính).

    future_fn(k) -> ngày của nến tương lai thứ k (k = 1..off). Trả về dict:
      x: ngày của vùng vẽ mây (n_show nến + `off` nến tương lai), a / b: Span A / Span B đã dịch tới đúng vị trí vẽ,
      xl: ngày n_show nến cuối, tenkan2 / kijun2: hai đường của bộ 2 trên cùng trục xl."""
    c = {**CFG, **(cfg or {})}
    h, l = g["Giá cao nhất"].astype(float), g["Giá thấp nhất"].astype(float)
    a = ((_donchian(h, l, c["t1"]) + _donchian(h, l, c["k1"])) / 2).to_numpy()
    b = _donchian(h, l, c["b1"]).to_numpy()
    off = int(c["disp1"]) - 1
    pad = np.full(off, np.nan)
    a_ext, b_ext = np.r_[pad, a], np.r_[pad, b]            # vị trí j chứa giá trị của nến j - off
    dates = list(pd.to_datetime(g["Ngày"])) + [future_fn(k) for k in range(1, off + 1)]
    m = min(n_show + off, len(dates))
    return {"x": dates[-m:], "a": a_ext[-m:], "b": b_ext[-m:], "off": off,
            "xl": list(pd.to_datetime(g["Ngày"]))[-n_show:],
            "tenkan2": _donchian(h, l, c["t2"]).to_numpy()[-n_show:],
            "kijun2": _donchian(h, l, c["k2"]).to_numpy()[-n_show:]}


def _with_crossings(x, a, b):
    """Chèn điểm giao nhau của hai đường để phần mây đổi màu cắt đúng chỗ thay vì bị khuyết một nến."""
    X, A, B = [], [], []
    for i in range(len(x)):
        if i > 0 and np.isfinite([a[i - 1], b[i - 1], a[i], b[i]]).all():
            d0, d1 = a[i - 1] - b[i - 1], a[i] - b[i]
            if d0 * d1 < 0:
                f = d0 / (d0 - d1)
                X.append(x[i - 1] + (x[i] - x[i - 1]) * f)
                A.append(a[i - 1] + (a[i] - a[i - 1]) * f)
                B.append(A[-1])
        X.append(x[i]); A.append(a[i]); B.append(b[i])
    return X, np.array(A, float), np.array(B, float)


def cloud_segments(x, a, b):
    """Tách mây thành đoạn tăng (Span A >= Span B) và đoạn giảm. Trả (X, hi_up, lo_up, hi_dn, lo_dn); ngoài đoạn là NaN."""
    X, A, B = _with_crossings(list(x), np.asarray(a, float), np.asarray(b, float))
    ok = np.isfinite(A) & np.isfinite(B)
    up = ok & (A >= B)
    dn = ok & (A <= B)             # điểm giao (A == B) thuộc cả hai màu nên hai đoạn khớp nhau
    hi, lo = np.maximum(A, B), np.minimum(A, B)
    nan = np.nan
    return (X, np.where(up, hi, nan), np.where(up, lo, nan), np.where(dn, hi, nan), np.where(dn, lo, nan))


def traces(g: pd.DataFrame, n_show: int, future_fn, cfg: dict | None = None) -> list:
    """Danh sách trace Plotly để add vào hàng giá (row=1). Mỗi trace đã gắn legendgroup nên bật/tắt theo nhóm."""
    import plotly.graph_objects as go
    d = compute(g, n_show, future_fn, cfg)
    X, hi_u, lo_u, hi_d, lo_d = cloud_segments(d["x"], d["a"], d["b"])
    out = []
    first = True
    for hi, lo, color in ((hi_u, lo_u, COL["up"]), (hi_d, lo_d, COL["down"])):
        if np.isfinite(hi).any():
            show, first = first, False          # chỉ một mục chú thích cho cả mây
            out.append(go.Scatter(x=X, y=lo, mode="lines", line=dict(width=0), showlegend=False, hoverinfo="skip", legendgroup="dich1"))
            out.append(go.Scatter(x=X, y=hi, mode="lines", line=dict(width=0), fill="tonexty", fillcolor=color,
                                  name="Ichimoku 1 · Mây Kumo (9-26-52)", showlegend=show, hoverinfo="skip", legendgroup="dich1"))
    x, a, b = d["x"], d["a"], d["b"]
    out.append(go.Scatter(x=x, y=a, name="Ichi 1 · Lead 1 (Span A)", line=dict(width=1, color=COL["span_a"]), legendgroup="dich1",
                          showlegend=False, hovertemplate="Lead 1: %{y:,.2f}<extra></extra>"))
    out.append(go.Scatter(x=x, y=b, name="Ichi 1 · Leading Span B", line=dict(width=1, color=COL["span_b"]), legendgroup="dich1",
                          showlegend=False, hovertemplate="Span B: %{y:,.2f}<extra></extra>"))
    cfgm = {**CFG, **(cfg or {})}
    out.append(go.Scatter(x=d["xl"], y=d["tenkan2"], name=f"Ichi 2 · Tenkan {cfgm['t2']}", line=dict(width=2, color=COL["tenkan2"])))
    out.append(go.Scatter(x=d["xl"], y=d["kijun2"], name=f"Ichi 2 · Kijun {cfgm['k2']}", line=dict(width=3, color=COL["kijun2"])))
    return out
