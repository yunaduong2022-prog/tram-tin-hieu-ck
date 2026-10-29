"""Bảng xếp hạng cơ bản theo ngành (Ngân hàng, Hàng công nghiệp, ...) cho trang Ngành > Xếp hạng cổ phiếu.

Nguồn số liệu: data/xep_hang_nganh.csv, nhập tay theo các bảng xếp hạng ngành. Mỗi dòng là một mã; cột "Ngành" phải trùng tên nhóm ngành trong
watchlist.GROUPS (vd. "Ngân hàng", "Hàng công nghiệp"); cột "STT" giữ đúng thứ tự dòng của bảng gốc; "Kỳ" và "Cập nhật nguồn" ghi kỳ và ngày của bảng gốc.
Chỉ lấy cổ phiếu đại diện ngành có vốn hóa từ MIN_VON_HOA (900 tỷ) trở lên. Ô trống = bảng gốc không có số ("-"). Đơn vị: Vốn hóa tỷ đồng, EPS và Giá trị sổ sách đồng/cổ phiếu, các tỷ lệ tính theo %.
Muốn thêm ngành mới: thêm dòng vào CSV, và (nếu muốn đúng thứ tự cột của bảng gốc) khai báo thêm một mục trong LAYOUT bên dưới.

Hai việc của module:
1. render_section(sector): vẽ bảng ở cuối trang Xếp hạng cổ phiếu khi đang chọn ngành có số liệu trong file.
2. apply_to_maps(fund_map, cap_map): điền P/E, P/B, ROE, EPS, Giá trị sổ sách, Xếp hạng và Vốn hóa vào dữ liệu cơ bản của app
   (thẻ Chờ mua, điểm FA ở Khuyến nghị khách hàng...). Chỉ điền ô còn THIẾU; số tự động đã có và số nhập tay trong nhap_tay.csv luôn được ưu tiên.
Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import html as _html
import io
import os
import re
import unicodedata

import numpy as np
import pandas as pd
import streamlit as st

PATH = "data/xep_hang_nganh.csv"
MIN_VON_HOA = 900        # tỷ đồng: chỉ lấy cổ phiếu đại diện ngành có vốn hóa từ mức này trở lên (dòng nhỏ hơn bị bỏ qua khi đọc file)
_NUM = ["STT", "Xếp hạng", "XH tài chính", "XH kinh doanh", "Số CP lưu hành", "Vốn hóa (tỷ)", "EPS", "P/E", "P/B", "Giá trị sổ sách",
        "ROE", "ROA", "NIM", "LLR", "CASA", "DTT", "LNST công ty mẹ", "Tăng trưởng DTT"]

# cột -> (tiêu đề, kiểu định dạng, căn lề)
COLS = {
    "Xếp hạng": ("Xếp hạng", "rank", "c"),
    "XH tài chính": ("Xếp hạng<small>tài chính</small>", "int", "c"),
    "XH kinh doanh": ("Xếp hạng<small>kinh doanh</small>", "int", "c"),
    "Số CP lưu hành": ("Số CP<small>lưu hành</small>", "n0", ""),
    "Vốn hóa (tỷ)": ("Vốn hóa<small>tỷ đồng</small>", "n0", ""),
    "EPS": ("EPS<small>đồng/CP</small>", "eps", ""),
    "P/E": ("P/E", "ratio", ""),
    "P/B": ("P/B", "pb", ""),
    "Giá trị sổ sách": ("Giá trị sổ sách<small>đồng/CP</small>", "n0", ""),
    "ROE": ("ROE", "pct", ""), "ROA": ("ROA", "pct", ""), "NIM": ("NIM", "pct", ""), "LLR": ("LLR", "pct", ""), "CASA": ("CASA", "pct", ""),
    "DTT": ("DTT", "eps", ""),
    "LNST công ty mẹ": ("LNST<small>công ty mẹ</small>", "eps", ""),
    "Tăng trưởng DTT": ("Tăng trưởng DTT<small>YoY</small>", "eps", ""),
}
# thứ tự cột theo bảng gốc của từng ngành
LAYOUT = {
    "Ngân hàng": ["Xếp hạng", "XH tài chính", "XH kinh doanh", "Số CP lưu hành", "Vốn hóa (tỷ)", "EPS", "P/E", "P/B", "ROE", "ROA", "NIM", "LLR", "CASA"],
}
_LAYOUT_ND = ["Xếp hạng", "XH tài chính", "XH kinh doanh", "Vốn hóa (tỷ)", "Số CP lưu hành", "EPS", "P/E", "P/B", "Giá trị sổ sách",
              "ROE", "ROA", "DTT", "LNST công ty mẹ"]            # bố cục của các bảng ngành phi ngân hàng
LAYOUT["Hàng công nghiệp"] = LAYOUT["Bán lẻ"] = _LAYOUT_ND
LAYOUT["Vận tải biển hàng hóa"] = ["Xếp hạng", "XH tài chính", "XH kinh doanh", "Vốn hóa (tỷ)", "Số CP lưu hành", "EPS", "P/E", "P/B", "Giá trị sổ sách",
                                   "ROE", "ROA", "LNST công ty mẹ", "Tăng trưởng DTT"]
DEFAULT_LAYOUT = ["Xếp hạng", "XH tài chính", "XH kinh doanh", "Vốn hóa (tỷ)", "Số CP lưu hành", "EPS", "P/E", "P/B", "Giá trị sổ sách", "ROE", "ROA"]


_CANON = ["Ngành", "STT", "Mã", "Xếp hạng", "XH tài chính", "XH kinh doanh", "Số CP lưu hành", "Vốn hóa (tỷ)", "EPS", "P/E", "P/B",
          "Giá trị sổ sách", "ROE", "ROA", "NIM", "LLR", "CASA", "DTT", "LNST công ty mẹ", "Tăng trưởng DTT", "Kỳ", "Cập nhật nguồn"]
_ERR = ""          # thông báo lỗi đọc file gần nhất ("" = đọc tốt); render_section hiển thị để dễ sửa file


def _norm(x) -> str:
    """Chuẩn hóa tên cột: gộp dấu tiếng Việt (NFC), bỏ BOM, bỏ khoảng trắng thừa, không phân biệt hoa thường."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(x)).replace("\ufeff", "")).strip().casefold()


_CANON_MAP = {_norm(c): c for c in _CANON}


def _read_text(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-16", "cp1258", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    return raw.decode("utf-8", errors="replace")


@st.cache_data(show_spinner=False)
def _load_cached(mtime: float) -> tuple[pd.DataFrame, str]:
    """Đọc data/xep_hang_nganh.csv: tự nhận dấu phân cách (, ; hoặc Tab), mã hóa (UTF-8, UTF-16, Windows) và dấu thập phân phẩy
    (file lưu từ Excel tiếng Việt thường dùng ;). Trả (bảng, thông báo lỗi); không bao giờ ném lỗi ra ngoài."""
    try:
        text = _read_text(PATH)
        first = next((ln for ln in text.splitlines() if ln.strip()), "")
        sep = max((",", ";", "\t"), key=first.count)
        d = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
        d.columns = [_CANON_MAP.get(_norm(c), str(c).strip()) for c in d.columns]
        miss = [c for c in ("Ngành", "Mã") if c not in d.columns]
        if miss:
            return pd.DataFrame(), f"thiếu cột {', '.join(miss)}; các cột tìm thấy: {', '.join(map(str, d.columns))}"
        d["Mã"] = d["Mã"].astype(str).str.upper().str.strip()
        d["Ngành"] = d["Ngành"].astype(str).str.strip()
        for c in _NUM:
            if c in d.columns:
                v = d[c].astype(str).str.replace("%", "", regex=False).str.replace("\u00a0", "", regex=False).str.replace(" ", "", regex=False)
                if sep == ";":
                    v = v.str.replace(",", ".", regex=False)
                d[c] = pd.to_numeric(v, errors="coerce")
            else:
                d[c] = np.nan
        d = d[d["Mã"].ne("") & d["Ngành"].ne("")]
        d = d[~(d["Vốn hóa (tỷ)"] < MIN_VON_HOA)]            # ô vốn hóa trống thì giữ lại
        return d.drop_duplicates(["Ngành", "Mã"], keep="last").reset_index(drop=True), ""
    except Exception as e:  # noqa: BLE001
        return pd.DataFrame(), f"{type(e).__name__}: {e}"


def load() -> pd.DataFrame:
    global _ERR
    try:
        d, _ERR = _load_cached(os.path.getmtime(PATH))
        return d
    except OSError:
        _ERR = ""                      # chưa có file thì coi như chưa dùng tính năng này
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
    """Điền vào fund_map / cap_map các ô còn thiếu (xem docstring đầu file). P/E phải trong (0, 1000), P/B trong (0, 200)."""
    try:
        d = load() if df is None else df
        if d is None or d.empty:
            return
        _apply(fund_map, cap_map, d)
    except Exception:  # noqa: BLE001  (dữ liệu bổ sung lỗi thì bỏ qua, không làm hỏng các trang khác)
        return


def _apply(fund_map: dict, cap_map: dict, d: pd.DataFrame) -> None:
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
        put("Giá trị sổ sách", r["Giá trị sổ sách"])
        put("Xếp hạng", r["Xếp hạng"])
        put("Xếp hạng tài chính", r["XH tài chính"])
        put("Xếp hạng kinh doanh", r["XH kinh doanh"])
        if _missing(fm.get("Bảng xếp hạng")) or not str(fm.get("Bảng xếp hạng")).strip():
            kỳ = str(r["Kỳ"]) if "Kỳ" in d.columns and pd.notna(r["Kỳ"]) else ""
            fm["Bảng xếp hạng"] = f"Ngành {r['Ngành']} {kỳ}".strip()
        cap = _f(r["Vốn hóa (tỷ)"])
        if cap and cap > 0 and _missing(cap_map.get(code)):
            cap_map[code] = cap


# ------------------------------------------------------------------ BẢNG
CSS = """
<style>
.bk-wrap{overflow:auto;max-height:640px;border:1px solid var(--line);border-radius:12px;background:var(--card)}
.bk-tb{border-collapse:collapse;width:100%;min-width:1100px;font-size:13px;color:var(--txt)}
.bk-tb th{position:sticky;top:0;z-index:1;background:var(--card2);color:var(--txt2);font-weight:700;font-size:12px;padding:11px 10px;
  text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
.bk-tb th small{display:block;font-weight:600;color:var(--muted);font-size:10.5px}
.bk-tb td{padding:9px 10px;border-bottom:1px solid var(--line2);text-align:right;font-variant-numeric:tabular-nums}
.bk-tb th.c,.bk-tb td.c{text-align:center}
.bk-tb th.l,.bk-tb td.l{text-align:left}
.bk-tb tr:hover td{background:var(--card2)}
.bk-code{font-weight:800;color:var(--txt2)}
.bk-rk{font-weight:800;color:var(--accent)}
.bk-neg{color:var(--red)}.bk-mu{color:var(--muted)}
</style>
"""


def _pct(v: float) -> str:              # 22.2% | 9.55% | 107%
    return f"{v:,.0f}%" if abs(v) >= 100 else f"{v:.1f}%" if abs(v) >= 10 else f"{v:.2f}%"


def _ratio(v: float) -> str:            # 159 | 11.3 | 5.92
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:.1f}" if abs(v) >= 10 else f"{v:.2f}"


def _eps(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.1f}"


_FMT = {"int": lambda v: f"{int(v)}", "rank": lambda v: f"{int(v)}", "n0": lambda v: f"{v:,.0f}", "eps": _eps, "ratio": _ratio,
        "pb": lambda v: f"{v:.2f}", "pct": _pct}


def _cell(v, kind: str, cls: str) -> str:
    v = _f(v)
    if v is None:
        return f'<td class="{cls}"><span class="bk-mu">-</span></td>'
    text = _FMT[kind](v)
    if kind == "rank":
        text = f'<span class="bk-rk">{text}</span>'
    return f'<td class="{cls}{" bk-neg" if v < 0 else ""}">{text}</td>'


def table_html(d: pd.DataFrame, layout: list[str]) -> str:
    layout = [c for c in layout if c in COLS and c in d.columns]
    th = '<th class="c">STT</th><th class="l">Mã CP</th>' + "".join(f'<th class="{COLS[c][2]}">{COLS[c][0]}</th>' for c in layout)
    rows = []
    for i, (_, r) in enumerate(d.iterrows(), 1):
        rows.append(f'<tr><td class="c">{i}</td><td class="l"><span class="bk-code">{_html.escape(str(r["Mã"]))}</span></td>'
                    + "".join(_cell(r[c], COLS[c][1], COLS[c][2]) for c in layout) + "</tr>")
    return f'<div class="bk-wrap"><table class="bk-tb"><thead><tr>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def render_section(sector: str | None) -> None:
    """Gọi ở cuối trang Xếp hạng cổ phiếu; chỉ vẽ khi ngành đang chọn có số liệu trong data/xep_hang_nganh.csv."""
    if not sector:
        return
    d = load()
    if _ERR:
        st.warning(f"Không đọc được {PATH}: {_ERR}. Kiểm tra dòng tiêu đề có các cột Ngành, Mã, ... (mẫu trong file gốc).")
        return
    if d.empty:
        return
    d = d[d["Ngành"] == sector].sort_values("STT", na_position="last")
    if d.empty:
        return
    kỳ = str(d["Kỳ"].dropna().iat[0]) if "Kỳ" in d.columns and d["Kỳ"].notna().any() else ""
    ngày = str(d["Cập nhật nguồn"].dropna().iat[0]) if "Cập nhật nguồn" in d.columns and d["Cập nhật nguồn"].notna().any() else ""
    st.subheader(f"📋 Bảng xếp hạng cơ bản ngành {sector}" + (f" · {kỳ}" if kỳ else ""))
    st.caption((f"Cập nhật theo bảng gốc ngày {ngày}. " if ngày else "") + f"Cổ phiếu đại diện ngành có vốn hóa từ {MIN_VON_HOA:,} tỷ trở lên ({len(d)} mã). "
               "Dấu \"-\" là bảng gốc không có số. Số liệu nhập tay ở data/xep_hang_nganh.csv; chỉ để tham khảo, không phải khuyến nghị đầu tư.")
    st.markdown(CSS + table_html(d, LAYOUT.get(sector, DEFAULT_LAYOUT)), unsafe_allow_html=True)
    with st.expander("ℹ️ Cách đọc"):
        st.markdown("- **Xếp hạng** là thứ hạng tổng hợp trong ngành; **tài chính** và **kinh doanh** là hạng theo từng nhóm chỉ tiêu (số nhỏ là tốt hơn). "
                    "Thứ tự dòng (STT) giữ đúng như bảng gốc.\n"
                    "- **ROE, ROA** tính theo %. Với ngân hàng: **NIM** là biên lãi ròng, **LLR** là tỷ lệ bao phủ nợ xấu, **CASA** là tỷ lệ tiền gửi không kỳ hạn.\n"
                    "- P/E, P/B, ROE, EPS, Giá trị sổ sách và Vốn hóa cũng được đưa vào dữ liệu cơ bản của app (thẻ Chờ mua, điểm FA ở Khuyến nghị khách hàng) "
                    "cho những ô app chưa có số; số nhập tay ở data/nhap_tay.csv luôn được ưu tiên.")
