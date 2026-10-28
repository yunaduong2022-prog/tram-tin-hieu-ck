"""Bảng xếp hạng cơ bản ngành Ngân hàng (Xếp hạng, XH tài chính, XH kinh doanh, Số CP, Vốn hóa, EPS, P/E, P/B, ROE, ROA, NIM, LLR, CASA).

Nguồn số liệu: data/xep_hang_ngan_hang.csv, nhập tay theo bảng xếp hạng ngành ngân hàng (cột "Kỳ", "Cập nhật nguồn" ghi kỳ và ngày của bảng gốc).
Ô trống = bảng gốc không có số ("-"). Để cập nhật, sửa thẳng file CSV (đơn vị: Vốn hóa tỷ đồng, EPS đồng/cổ phiếu, các tỷ lệ tính theo %).

Hai việc của module:
1. render_section(sector): vẽ bảng ở Ngành > Xếp hạng cổ phiếu khi đang chọn ngành Ngân hàng.
2. apply_to_maps(fund_map, cap_map): điền P/E, P/B, ROE, EPS, Xếp hạng và Vốn hóa của các ngân hàng vào dữ liệu cơ bản của app
   (thẻ Chờ mua, điểm FA ở Khuyến nghị khách hàng...). Chỉ điền ô còn THIẾU; số tự động đã có và số nhập tay trong nhap_tay.csv luôn được ưu tiên.
Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import html as _html
import os

import numpy as np
import pandas as pd
import streamlit as st

PATH = "data/xep_hang_ngan_hang.csv"
SECTOR = "Ngân hàng"            # tên nhóm ngành trong watchlist.GROUPS
_NUM = ["Xếp hạng", "XH tài chính", "XH kinh doanh", "Số CP lưu hành", "Vốn hóa (tỷ)", "EPS", "P/E", "P/B", "ROE", "ROA", "NIM", "LLR", "CASA"]


@st.cache_data(show_spinner=False)
def _load_cached(mtime: float) -> pd.DataFrame:
    try:
        d = pd.read_csv(PATH, dtype={"Mã": str}, encoding="utf-8-sig")
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    d.columns = [str(c).strip() for c in d.columns]
    d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
    for c in _NUM:
        d[c] = pd.to_numeric(d[c], errors="coerce") if c in d.columns else np.nan
    return d.drop_duplicates("Mã", keep="last").sort_values("Xếp hạng", na_position="last").reset_index(drop=True)


def load() -> pd.DataFrame:
    try:
        return _load_cached(os.path.getmtime(PATH))
    except OSError:
        return pd.DataFrame()


def _f(v) -> float | None:
    try:
        x = float(v)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _missing(v) -> bool:
    return v is None or (isinstance(v, float) and np.isnan(v))


def apply_to_maps(fund_map: dict, cap_map: dict, df: pd.DataFrame | None = None) -> None:
    """Điền vào fund_map / cap_map các ô còn thiếu của ngân hàng (xem docstring đầu file). P/E phải trong (0, 1000), P/B trong (0, 200)."""
    d = load() if df is None else df
    if d is None or d.empty:
        return
    kỳ = str(d["Kỳ"].dropna().iat[0]) if "Kỳ" in d.columns and d["Kỳ"].notna().any() else ""
    for _, r in d.iterrows():
        code = str(r["Mã"]).upper()
        fm = fund_map.setdefault(code, {})

        def put(key: str, val, ok=lambda v: True):
            v = _f(val)
            if v is not None and ok(v) and _missing(fm.get(key)):
                fm[key] = v

        put("P/E", r["P/E"], lambda v: 0 < v < 1000)
        put("P/B", r["P/B"], lambda v: 0 < v < 200)
        put("ROE", r["ROE"])
        put("EPS", r["EPS"])
        put("Xếp hạng", r["Xếp hạng"])
        put("Xếp hạng tài chính", r["XH tài chính"])
        put("Xếp hạng kinh doanh", r["XH kinh doanh"])
        if _missing(fm.get("Bảng xếp hạng")) or not str(fm.get("Bảng xếp hạng")).strip():
            fm["Bảng xếp hạng"] = f"Ngành Ngân hàng {kỳ}".strip()
        cap = _f(r["Vốn hóa (tỷ)"])
        if cap and cap > 0 and _missing(cap_map.get(code)):
            cap_map[code] = cap


# ------------------------------------------------------------------ BẢNG
CSS = """
<style>
.bk-wrap{overflow:auto;max-height:640px;border:1px solid var(--line);border-radius:12px;background:var(--card)}
.bk-tb{border-collapse:collapse;width:100%;min-width:1180px;font-size:13px;color:var(--txt)}
.bk-tb th{position:sticky;top:0;z-index:1;background:var(--card2);color:var(--txt2);font-weight:700;font-size:12px;padding:11px 10px;
  text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
.bk-tb th small{display:block;font-weight:600;color:var(--muted);font-size:10.5px}
.bk-tb td{padding:9px 10px;border-bottom:1px solid var(--line2);text-align:right;font-variant-numeric:tabular-nums}
.bk-tb th.c,.bk-tb td.c{text-align:center}
.bk-tb th.l,.bk-tb td.l{text-align:left}
.bk-tb tr:hover td{background:var(--card2)}
.bk-code{font-weight:800;color:var(--txt2)}
.bk-rk{font-weight:800;color:var(--accent)}
.bk-neg{color:var(--red)}.bk-pos{color:var(--green)}.bk-mu{color:var(--muted)}
</style>
"""


def _dash() -> str:
    return '<span class="bk-mu">-</span>'


def _cell(v, fmt, cls: str = "") -> str:
    v = _f(v)
    if v is None:
        return f'<td class="{cls}">{_dash()}</td>'
    neg = " bk-neg" if v < 0 else ""
    return f'<td class="{cls}{neg}">{fmt(v)}</td>'


def _pct(v: float) -> str:              # 22.2% | 9.55% | 107%
    return f"{v:,.0f}%" if abs(v) >= 100 else f"{v:.1f}%" if abs(v) >= 10 else f"{v:.2f}%"


def _ratio(v: float) -> str:            # 159 | 11.3 | 5.92
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:.1f}" if abs(v) >= 10 else f"{v:.2f}"


def _eps(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


def table_html(d: pd.DataFrame) -> str:
    heads = [("STT", "c"), ("Mã CP", "l"), ("Xếp hạng", "c"), ("Xếp hạng<small>tài chính</small>", "c"), ("Xếp hạng<small>kinh doanh</small>", "c"),
             ("Số CP<small>lưu hành</small>", ""), ("Vốn hóa<small>tỷ đồng</small>", ""), ("EPS<small>đồng/CP</small>", ""), ("P/E", ""), ("P/B", ""),
             ("ROE", ""), ("ROA", ""), ("NIM", ""), ("LLR", ""), ("CASA", "")]
    th = "".join(f'<th class="{c}">{h}</th>' for h, c in heads)
    rows = []
    for i, (_, r) in enumerate(d.iterrows(), 1):
        rk = lambda v: f'<td class="c"><span class="bk-rk">{int(v)}</span></td>' if _f(v) is not None else f'<td class="c">{_dash()}</td>'   # noqa: E731
        ic = lambda v: _cell(v, lambda x: f"{int(x)}", "c")                                                                                      # noqa: E731
        rows.append(
            f'<tr><td class="c">{i}</td><td class="l"><span class="bk-code">{_html.escape(str(r["Mã"]))}</span></td>'
            + rk(r["Xếp hạng"]) + ic(r["XH tài chính"]) + ic(r["XH kinh doanh"])
            + _cell(r["Số CP lưu hành"], lambda x: f"{x:,.0f}") + _cell(r["Vốn hóa (tỷ)"], lambda x: f"{x:,.0f}")
            + _cell(r["EPS"], _eps) + _cell(r["P/E"], _ratio) + _cell(r["P/B"], lambda x: f"{x:.2f}")
            + _cell(r["ROE"], _pct) + _cell(r["ROA"], lambda x: f"{x:.2f}%") + _cell(r["NIM"], _pct)
            + _cell(r["LLR"], _pct) + _cell(r["CASA"], _pct) + "</tr>")
    return f'<div class="bk-wrap"><table class="bk-tb"><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def render_section(sector: str | None) -> None:
    """Gọi ở cuối trang Xếp hạng cổ phiếu; chỉ vẽ khi đang chọn ngành Ngân hàng và có số liệu."""
    if sector != SECTOR:
        return
    d = load()
    if d.empty:
        return
    kỳ = str(d["Kỳ"].dropna().iat[0]) if "Kỳ" in d.columns and d["Kỳ"].notna().any() else ""
    ngày = str(d["Cập nhật nguồn"].dropna().iat[0]) if "Cập nhật nguồn" in d.columns and d["Cập nhật nguồn"].notna().any() else ""
    st.subheader(f"🏦 Bảng xếp hạng cơ bản ngành Ngân hàng" + (f" · {kỳ}" if kỳ else ""))
    st.caption((f"Cập nhật theo bảng gốc ngày {ngày}. " if ngày else "")
               + "Dấu \"-\" là bảng gốc không có số. Số liệu nhập tay ở data/xep_hang_ngan_hang.csv; chỉ để tham khảo, không phải khuyến nghị đầu tư.")
    st.markdown(CSS + table_html(d), unsafe_allow_html=True)
    with st.expander("ℹ️ Cách đọc"):
        st.markdown("- **Xếp hạng** là thứ hạng tổng hợp trong ngành; **tài chính** và **kinh doanh** là hạng theo từng nhóm chỉ tiêu (số nhỏ là tốt hơn).\n"
                    "- **ROE, ROA** tính theo %; **NIM** là biên lãi ròng, **LLR** là tỷ lệ bao phủ nợ xấu, **CASA** là tỷ lệ tiền gửi không kỳ hạn.\n"
                    "- Các chỉ số này (trừ Số CP) cũng được đưa vào dữ liệu cơ bản của app (thẻ Chờ mua, điểm FA ở Khuyến nghị khách hàng) "
                    "cho những ô app chưa có số; số nhập tay ở data/nhap_tay.csv luôn được ưu tiên.")
