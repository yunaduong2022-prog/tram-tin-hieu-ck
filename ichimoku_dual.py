"""Dual Ichimoku: hai bộ Ichimoku cùng hiển thị trên biểu đồ giá (chuyển từ Pine v5 "Min Invest - Dual Ichimoku Setup").

Bộ 1 (9 - 17 - 26, dịch 26; đúng thông số Ichimoku 1 trên TradingView): chỉ vẽ MÂY KUMO, gồm Lead 1 (Senkou Span A), Leading Span B (Senkou Span B) và nền mây.
                              Tắt Tenkan, Kijun, Chikou.
Bộ 2 (65 - 129, Span B 52):             chỉ vẽ Tenkan-sen (xanh dương) và Kijun-sen (cam); không có mây, không có Chikou, không dịch.

Tenkan / Kijun / Span đều là trung điểm Donchian: (cao nhất N nến + thấp nhất N nến) / 2.
Mây vẽ lệch về tương lai `displacement - 1` nến, đúng như Pine (offset = displacement - 1), nên 25 nến cuối nằm
phía bên phải nến cuối cùng. Tham số chỉnh ở CFG.

Cần đủ lịch sử: Kijun 129 cần 129 nến, mây cần 26 nến. Khung Tháng thường không đủ 129 nến nên chỉ hiện phần có dữ liệu.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CFG = {
    "t1": 9, "k1": 17, "b1": 26, "disp1": 26,   # bộ 1: Tenkan, Kijun, Span B, độ dịch của mây
    "t2": 65, "k2": 129,                         # bộ 2: Tenkan, Kijun
}
COL = {
    "span_a": "#A8D5B6",      # Lead 1 (Span A): xanh lá nhạt, như TradingView
    "span_b": "#FABAA1",      # Leading Span B: cam đào nhạt
    "up": "rgba(76,175,80,0.38)",     # mây tăng: xanh lá
    "down": "rgba(242,54,69,0.35)",   # mây giảm: đỏ
    "tenkan2": "#2822F4",     # xanh dương đậm (đúng màu Ichimoku 2)
    "kijun2": "#FFB74D",      # cam vàng (đúng màu Ichimoku 2)
}
W_EDGE = 1       # viền mây (Span A / Span B)
W_LINE = 2       # Tenkan / Kijun bộ 2


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


def _polygons(X, hi, lo):
    """Tách mây thành các đoạn liên tục (không NaN) rồi nối thành đa giác khép kín (biên trên đi, biên dưới về), ngăn cách bằng None.
    Dùng fill="toself" nên mỗi đoạn được tô riêng; không bị nối qua khoảng trống như fill="tonexty"."""
    px, py = [], []
    ok = np.isfinite(hi) & np.isfinite(lo)
    i, n = 0, len(X)
    while i < n:
        if not ok[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and ok[j + 1]:
            j += 1
        if j > i:                                   # cần ít nhất 2 điểm mới thành một mảng mây
            xs, h_, l_ = X[i:j + 1], hi[i:j + 1], lo[i:j + 1]
            px += list(xs) + list(xs[::-1]) + [None]
            py += list(h_) + list(l_[::-1]) + [None]
        i = j + 1
    return px, py


def cloud_end(g: pd.DataFrame, future_fn, cfg: dict | None = None):
    """Ngày của điểm mây xa nhất về tương lai: biểu đồ cần kéo trục ngày tới đây để không cắt mất phần mây phía phải nến cuối."""
    off = int({**CFG, **(cfg or {})}["disp1"]) - 1
    return future_fn(off) if off > 0 else pd.Timestamp(g["Ngày"].iloc[-1])


def traces(g: pd.DataFrame, n_show: int, future_fn, cfg: dict | None = None) -> list:
    """Danh sách trace Plotly để add vào hàng giá (row=1). Mỗi trace đã gắn legendgroup nên bật/tắt theo nhóm."""
    import plotly.graph_objects as go
    d = compute(g, n_show, future_fn, cfg)
    X, hi_u, lo_u, hi_d, lo_d = cloud_segments(d["x"], d["a"], d["b"])
    out = []
    first = True
    for hi, lo, color in ((hi_u, lo_u, COL["up"]), (hi_d, lo_d, COL["down"])):
        px, py = _polygons(X, hi, lo)
        if px:
            show, first = first, False          # chỉ một mục chú thích cho cả mây
            out.append(go.Scatter(x=px, y=py, mode="lines", fill="toself", fillcolor=color, line=dict(width=0),
                                  name="Ichimoku 1 · Mây Kumo (9-17-26)", showlegend=show, hoverinfo="skip", legendgroup="dich1"))
    x, a, b = d["x"], d["a"], d["b"]
    out.append(go.Scatter(x=x, y=a, name="Ichi 1 · Lead 1 (Span A)", line=dict(width=W_EDGE, color=COL["span_a"]), legendgroup="dich1",
                          showlegend=False, hovertemplate="Lead 1: %{y:,.2f}<extra></extra>"))
    out.append(go.Scatter(x=x, y=b, name="Ichi 1 · Leading Span B", line=dict(width=W_EDGE, color=COL["span_b"]), legendgroup="dich1",
                          showlegend=False, hovertemplate="Span B: %{y:,.2f}<extra></extra>"))
    cfgm = {**CFG, **(cfg or {})}
    out.append(go.Scatter(x=d["xl"], y=d["tenkan2"], name=f"Ichi 2 · Tenkan {cfgm['t2']}", line=dict(width=W_LINE, color=COL["tenkan2"]),
                          hovertemplate="Tenkan: %{y:,.2f}<extra></extra>"))
    out.append(go.Scatter(x=d["xl"], y=d["kijun2"], name=f"Ichi 2 · Kijun {cfgm['k2']}", line=dict(width=W_LINE, color=COL["kijun2"]),
                          hovertemplate="Kijun: %{y:,.2f}<extra></extra>"))
    return out


def price_tags(g: pd.DataFrame, n_show: int, future_fn, cfg: dict | None = None) -> list:
    """Nhãn giá cuối của từng đường để gắn bên phải biểu đồ (như TradingView): [(giá, màu nền, màu chữ)], sắp từ cao xuống thấp.
    Tenkan / Kijun lấy ở nến cuối; Lead 1 / Span B lấy ở điểm mây xa nhất về tương lai."""
    d = compute(g, n_show, future_fn, cfg)
    out = []
    for v, bg, fg in ((d["tenkan2"][-1], COL["tenkan2"], "#FFFFFF"), (d["kijun2"][-1], COL["kijun2"], "#131722"),
                      (d["b"][-1], COL["span_b"], "#131722"), (d["a"][-1], COL["span_a"], "#131722")):
        if np.isfinite(v):
            out.append((float(v), bg, fg))
    return sorted(out, key=lambda t: -t[0])
