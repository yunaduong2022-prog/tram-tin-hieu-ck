"""Ngành > Dòng dẫn sóng: bảng xếp hạng các dòng theo biến động giai đoạn (trái) + cổ phiếu đại diện của dòng đang chọn (phải).
Chọn mốc giai đoạn 1 tuần ... 6 tháng; bấm vào một dòng để xem TẤT CẢ mã của dòng có trong dữ liệu (mạnh nhất lên đầu), nút "So sánh các mã" vẽ các mã mạnh nhất quy về 100.
Nhãn DẪN SÓNG: dòng nằm trong top theo giai đoạn, mạnh hơn VN-Index và có ít nhất nửa số mã tăng (xem hằng số trong nhom_nganh_data.py).
Danh sách dòng và mã: data/dong_dan_song.csv (cột Dòng, Mã, Mô tả, Leader); không có file thì dùng nhóm ngành mặc định.
Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import html as _html
import zlib

import numpy as np
import pandas as pd
import streamlit as st

import nhom_nganh_data as ND
from nhom_nganh_homnay import DECIMAL_COMMA, PALETTE, _cls, _pct, _vn

CSS = """
<style>
.dd-card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.dd-head{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line);font-weight:800;font-size:16px;color:var(--txt)}
.dd-desc{padding:12px 18px;color:var(--txt2);font-size:13px;border-bottom:1px solid var(--line)}
.dd-list{max-height:620px;overflow-y:auto}
.dd-row{display:grid;grid-template-columns:22px 42px 1fr auto auto;align-items:center;gap:12px;padding:10px 18px;border-bottom:1px solid var(--line2)}
.dd-rk{color:var(--muted);font-size:12px;font-weight:700;text-align:center}
.dd-row:hover{background:var(--card2)}
.dd-logo{width:42px;height:42px;border-radius:10px;background:var(--card2);border:1px solid var(--line);display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:12px;color:var(--txt2)}
.dd-code{font-weight:800;color:var(--txt);font-size:15px}
.dd-tag{margin-left:6px;font-size:10px;font-weight:800;padding:1px 7px;border-radius:5px;color:#E8C47C;border:1px solid #E8C47C;background:rgba(232,196,124,.12)}
.dd-name{color:var(--muted);font-size:12.5px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;max-width:260px}
.dd-px{text-align:right;font-weight:800;font-size:15px;font-variant-numeric:tabular-nums}
.dd-px small{display:block;font-size:11.5px;font-weight:700}
.dd-per{text-align:right;min-width:86px;font-size:11.5px;color:var(--muted)}
.dd-per b{display:block;font-size:14.5px}
.dd-up{color:var(--green)}.dd-dn{color:var(--red)}.dd-flat{color:#E8C47C}
.dd-bench{display:flex;gap:18px;flex-wrap:wrap;padding:10px 4px;color:var(--txt2);font-size:13px}
</style>
"""


def _px(v: float) -> str:
    return _vn(f"{v:,.2f}")


def _color(v):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return ""
    return "color:#089981;font-weight:700" if v > 0 else "color:#F23645;font-weight:700" if v < 0 else "color:#E8C47C"


def _styler(df: pd.DataFrame, cols: list[str]):
    sty = df.style.format({c: (lambda v: _pct(v, 1)) for c in cols}, na_rep="-")
    fn = getattr(sty, "map", None) or sty.applymap
    return fn(_color, subset=cols)


def _stock_rows(rep: pd.DataFrame, name_of) -> str:
    rows = []
    for i, (_, r) in enumerate(rep.iterrows(), 1):
        code = str(r["Mã"])
        tag = '<span class="dd-tag">LEADER</span>' if bool(r["Leader"]) else ""
        nm = _html.escape(str(name_of(code) or ""))
        rows.append(f'<div class="dd-row"><div class="dd-rk">{i}</div><div class="dd-logo">{_html.escape(code)}</div>'
                    f'<div><div><span class="dd-code">{_html.escape(code)}</span>{tag}</div><div class="dd-name" title="{nm}">{nm}</div></div>'
                    f'<div class="dd-px {_cls(r["Ngày"]).replace("nn-", "dd-")}">{_px(r["Giá"])}<small>{_pct(r["Ngày"])}</small></div>'
                    f'<div class="dd-per">Giai đoạn<b class="{_cls(r["Giai đoạn"]).replace("nn-", "dd-")}">{_pct(r["Giai đoạn"], 1)}</b></div></div>')
    return "".join(rows)


def render(raw: pd.DataFrame, mkt: pd.Series, default_groups: dict, data_key: str, name_of=None, on_open=None, openable: set | None = None) -> None:
    name_of = name_of or (lambda c: "")
    P = ND.pivots(raw, data_key)
    groups, meta = ND.load_groups(default_groups)
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("🌊 Dòng dẫn sóng thị trường")

    period = st.pills("Giai đoạn", list(ND.PERIODS), selection_mode="single", default="1 tháng", key="dds_period") or "1 tháng"
    n = ND.PERIODS[period]
    d, bench = ND.period_stats(P, groups, mkt, n)
    if d.empty:
        st.info("Chưa đủ dữ liệu cho giai đoạn này.")
        return

    left, right = st.columns([1.3, 1], gap="medium")
    with left:
        st.markdown(f'<div class="dd-bench"><b>VNINDEX (chỉ số cơ sở)</b><span>Giai đoạn <b class="{_cls(bench.get("per")).replace("nn-", "dd-")}">{_pct(bench.get("per"), 1)}</b></span>'
                    f'<span>Ngày <b class="{_cls(bench.get("day")).replace("nn-", "dd-")}">{_pct(bench.get("day"), 1)}</b></span></div>', unsafe_allow_html=True)
        view = pd.DataFrame({"#": d["#"], "Ngành / Dòng": np.where(d["Dẫn sóng"], d["Dòng"] + "  ·  DẪN SÓNG", d["Dòng"]), "Số mã": d["Số mã"],
                             "Biến động giai đoạn": d["Giai đoạn"], "Biến động ngày": d["Ngày"]})
        names = list(d["Dòng"])
        styler = _styler(view, ["Biến động giai đoạn", "Biến động ngày"])
        height = min(640, 40 + 36 * len(view))
        picked = None
        ev = None
        for mode in ("single-cell", "single-row"):          # bản Streamlit mới: bấm vào ô bất kỳ trong hàng; bản cũ hơn: tích ô vuông đầu hàng
            try:
                ev = st.dataframe(styler, hide_index=True, **ND.stretch(st.dataframe), height=height, on_select="rerun", selection_mode=mode,
                                  key=f"dds_table_{mode}_{n}")
                break
            except Exception:  # noqa: BLE001
                ev = None
        if ev is None:                                       # không có on_select: chọn bằng ô chọn
            st.dataframe(styler, hide_index=True, **ND.stretch(st.dataframe), height=height)
            picked = st.selectbox("Chọn dòng để xem cổ phiếu", names, key="dds_pick")
        else:
            try:
                cells = list(ev.selection.cells)
            except Exception:  # noqa: BLE001
                cells = []
            rows_sel = list(ev.selection.rows)
            i0 = (cells[0][0] if isinstance(cells[0], (list, tuple)) else cells[0]) if cells else (rows_sel[0] if rows_sel else None)
            if i0 is not None and 0 <= int(i0) < len(names):
                picked = names[int(i0)]
        if picked:
            st.session_state["dds_last"] = picked          # nhớ dòng đã chọn (kể cả khi đổi giai đoạn)
        st.caption("Bấm vào một dòng trong bảng để xem các mã của dòng đó 👉")

    last = st.session_state.get("dds_last")
    sel = int(d.index[d["Dòng"] == last][0]) if last in set(d["Dòng"]) else 0
    name = str(d.loc[sel, "Dòng"])
    info = meta.get(name, {})
    rep = ND.rep_stocks(P, groups.get(name, []), n, info.get("leaders"))
    with right:
        dot = PALETTE[zlib.crc32(name.encode("utf-8")) % len(PALETTE)]
        total = len(set(str(c).upper() for c in groups.get(name, [])))
        k = len(rep)
        body = _stock_rows(rep, name_of) if not rep.empty else '<div class="dd-desc">Chưa đủ dữ liệu của các mã trong dòng này.</div>'
        note = f"Dòng gồm {total} mã, dữ liệu của bạn có {k} mã; xếp từ mạnh nhất xuống yếu nhất theo biến động {period}."
        desc = (f'<div class="dd-desc">{_html.escape(info["desc"])}<br><span style="color:var(--muted);font-size:12px">{note}</span></div>' if info.get("desc")
                else f'<div class="dd-desc" style="color:var(--muted);font-size:12px">{note}</div>')
        st.markdown(f'<div class="dd-card"><div class="dd-head"><i style="width:13px;height:13px;border-radius:50%;background:{dot};display:inline-block"></i>'
                    f'CỔ PHIẾU ĐẠI DIỆN NHÓM {_html.escape(name.upper())}</div>{desc}<div class="dd-list">{body}</div></div>', unsafe_allow_html=True)
        if not rep.empty and on_open is not None:
            ok = [str(c) for c in rep["Mã"] if openable is None or str(c) in openable]
            if ok:
                c1, c2 = st.columns([3, 2])
                code = c1.selectbox("Xem biểu đồ của mã", ok, key=f"dds_code_{zlib.crc32(name.encode('utf-8'))}")
                c2.button("📈 Mở biểu đồ", key=f"dds_open_{zlib.crc32(name.encode('utf-8'))}", on_click=on_open, args=(code,), **ND.stretch(st.button))
        if not rep.empty and st.toggle("So sánh các mã", key="dds_cmp", help=f"Quy giá về 100 tại đầu giai đoạn; vẽ {ND.COMPARE_MAX} mã mạnh nhất."):
            import plotly.graph_objects as go
            cf = ND.compare_frame(P, rep["Mã"].head(ND.COMPARE_MAX).tolist(), n)
            fig = go.Figure()
            for code in cf.columns:
                fig.add_trace(go.Scatter(x=cf.index, y=cf[code], mode="lines", name=str(code), line=dict(width=1.8)))
            fig.add_hline(y=100, line_dash="dot", line_color="#6B7686")
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.1), template="plotly_dark",
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis_title="Quy về 100")
            st.plotly_chart(fig, **ND.stretch(st.plotly_chart))
    st.caption(f"Biến động dòng = trung vị % của các mã trong dòng (dòng dưới {ND.MIN_FOR_MEDIAN} mã dùng trung bình); giai đoạn tính trên {n} phiên. "
               f"Danh sách bên phải chỉ gồm các mã có trong dữ liệu của bạn. Chỉ để tham khảo, không phải khuyến nghị đầu tư.")
