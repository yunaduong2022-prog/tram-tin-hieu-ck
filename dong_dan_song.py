"""Ngành > Dòng dẫn sóng: bảng xếp hạng các dòng theo biến động giai đoạn (trái) + cổ phiếu đại diện của dòng đang chọn (phải).
Chọn mốc giai đoạn 1 tuần ... 6 tháng; bấm vào một dòng để xem TẤT CẢ mã của dòng có trong dữ liệu (mạnh nhất lên đầu), nút "So sánh các mã" vẽ các mã mạnh nhất quy về 100.
Nhãn DẪN SÓNG: dòng nằm trong top theo giai đoạn, mạnh hơn VN-Index và có ít nhất nửa số mã tăng (xem hằng số trong nhom_nganh_data.py).
Danh sách dòng và mã: data/dong_dan_song.csv (cột Dòng, Mã, Mô tả, Leader); không có file thì dùng nhóm ngành mặc định.
Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import html as _html
import inspect
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
.dd-row,.dd-colhead{display:grid;grid-template-columns:22px 42px 1fr auto 74px;align-items:center;gap:12px;padding:10px 18px}
.dd-row{border-bottom:1px solid var(--line2)}
.dd-colhead{padding:8px 18px;border-bottom:1px solid var(--line);color:var(--muted);font-size:11.5px;font-weight:700;letter-spacing:.3px}
.dd-colhead .r{text-align:right}
.dd-foot{padding:10px 18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}
.dd-topbar{min-height:46px;display:flex;align-items:center;color:var(--muted);font-size:13px}
.dd-rk{color:var(--muted);font-size:12px;font-weight:700;text-align:center}
.dd-row:hover{background:var(--card2)}
.dd-logo{width:42px;height:42px;border-radius:10px;background:var(--card2);border:1px solid var(--line);display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:12px;color:var(--txt2)}
.dd-code{font-weight:800;color:var(--txt);font-size:15px}
.dd-tag{margin-left:6px;font-size:10px;font-weight:800;padding:1px 7px;border-radius:5px;color:#E8C47C;border:1px solid #E8C47C;background:rgba(232,196,124,.12)}
.dd-name{color:var(--muted);font-size:12.5px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;max-width:260px}
.dd-px{text-align:right;font-weight:800;font-size:15px;font-variant-numeric:tabular-nums}
.dd-px small{display:block;font-size:11.5px;font-weight:700}
.dd-per{text-align:right;font-weight:800;font-size:14.5px;font-variant-numeric:tabular-nums}
.dd-up{color:var(--green)}.dd-dn{color:var(--red)}.dd-flat{color:#E8C47C}
.dd-chips{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:4px 0 14px}
.dd-chip{padding:6px 12px;border:1px solid var(--line);border-radius:999px;background:var(--card);color:var(--txt2);font-size:13px}
.dd-chip b{font-weight:800}
.dd-chip.lead{border-color:#E8C47C;color:#E8C47C;background:rgba(232,196,124,.10);font-weight:700}
.dd-chip.mu{color:var(--muted)}
</style>
"""


_VALIGN = "vertical_alignment" in inspect.signature(st.columns).parameters


def _px(v: float) -> str:
    return _vn(f"{v:,.2f}")


def _color(v):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return ""
    return "color:#089981;font-weight:700" if v > 0 else "color:#F23645;font-weight:700" if v < 0 else "color:#E8C47C"


def _tag_style(v):
    return "color:#E8C47C;font-weight:800;background-color:rgba(232,196,124,.07)" if v else ""


def _styler(df: pd.DataFrame, pct_cols: list[str], selected: str | None):
    sty = df.style.format({c: (lambda v: _pct(v, 1)) for c in pct_cols}, na_rep="-")
    fn = getattr(sty, "map", None) or sty.applymap
    sty = fn(_color, subset=pct_cols)
    sty = fn(_tag_style, subset=["Tín hiệu"])
    if selected:                                            # tô sáng cả hàng đang được chọn
        sty = sty.apply(lambda r: ["background-color: rgba(45,212,167,.18)" if r["Ngành / Dòng"] == selected else ""] * len(r), axis=1)
    return sty


def _g(obj, key):
    try:
        return obj[key]
    except Exception:  # noqa: BLE001
        return getattr(obj, key, None)


def _pick_from(sel, names: list[str]):
    """Tên dòng được chọn từ kết quả chọn của st.dataframe (ô hoặc hàng); None nếu chưa chọn."""
    if sel is None:
        return None
    cells, rows = list(_g(sel, "cells") or []), list(_g(sel, "rows") or [])
    i0 = (cells[0][0] if isinstance(cells[0], (list, tuple)) else cells[0]) if cells else (rows[0] if rows else None)
    return names[int(i0)] if i0 is not None and 0 <= int(i0) < len(names) else None


def _table_cfg() -> dict:
    """Cấu hình cột: Hạng / Ngành / Tín hiệu / Số mã có độ rộng cố định vừa đủ để hai cột biến động luôn nằm trong khung; bản Streamlit cũ không nhận px thì dùng cỡ chữ."""
    for w in ((64, 185, 100, 64), ("small", "medium", "small", "small")):
        try:
            return {"Hạng": st.column_config.NumberColumn("Hạng", width=w[0], format="%d"),
                    "Ngành / Dòng": st.column_config.TextColumn("Ngành / Dòng", width=w[1]),
                    "Tín hiệu": st.column_config.TextColumn("Tín hiệu", width=w[2]),
                    "Số mã": st.column_config.NumberColumn("Số mã", width=w[3], format="%d")}
        except Exception:  # noqa: BLE001
            continue
    return {}


def _state_selection(key: str):
    s = st.session_state.get(key)
    if s is None:
        return None
    try:
        return s["selection"]
    except Exception:  # noqa: BLE001
        return getattr(s, "selection", None)


def _stock_rows(rep: pd.DataFrame, name_of) -> str:
    rows = []
    for i, (_, r) in enumerate(rep.iterrows(), 1):
        code = str(r["Mã"])
        tag = '<span class="dd-tag">LEADER</span>' if bool(r["Leader"]) else ""
        nm = _html.escape(str(name_of(code) or ""))
        rows.append(f'<div class="dd-row"><div class="dd-rk">{i}</div><div class="dd-logo">{_html.escape(code)}</div>'
                    f'<div><div><span class="dd-code">{_html.escape(code)}</span>{tag}</div><div class="dd-name" title="{nm}">{nm}</div></div>'
                    f'<div class="dd-px {_cls(r["Ngày"]).replace("nn-", "dd-")}">{_px(r["Giá"])}<small>{_pct(r["Ngày"])}</small></div>'
                    f'<div class="dd-per {_cls(r["Giai đoạn"]).replace("nn-", "dd-")}">{_pct(r["Giai đoạn"], 1)}</div></div>')
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
    d = d.sort_values("#").reset_index(drop=True)
    names = list(d["Dòng"])

    # --- dòng chip: VNINDEX chuẩn + số dòng dẫn sóng (cùng một hàng, nằm trên cả hai cột) ---
    n_lead = int(d["Dẫn sóng"].sum())
    cc = lambda v: _cls(v).replace("nn-", "dd-")        # noqa: E731
    lead_chip = (f'<span class="dd-chip lead">{n_lead} dòng dẫn sóng</span>' if n_lead
                 else '<span class="dd-chip mu">Chưa có dòng nào đủ điều kiện dẫn sóng ở giai đoạn này</span>')
    st.markdown(f'<div class="dd-chips"><span class="dd-chip"><b>VNINDEX</b> · chỉ số cơ sở</span>'
                f'<span class="dd-chip">Giai đoạn <b class="{cc(bench.get("per"))}">{_pct(bench.get("per"), 1)}</b></span>'
                f'<span class="dd-chip">Ngày <b class="{cc(bench.get("day"))}">{_pct(bench.get("day"), 1)}</b></span>{lead_chip}</div>', unsafe_allow_html=True)

    # --- dòng đang chọn: lấy từ lần bấm mới nhất (đọc từ state trước khi vẽ bảng để hàng được tô sáng ngay) ---
    for mode in ("single-cell", "single-row"):
        pre = _pick_from(_state_selection(f"dds_table_{mode}_{n}"), names)
        if pre:
            st.session_state["dds_last"] = pre
            break
    last = st.session_state.get("dds_last")
    sel_name = last if last in set(names) else names[0]

    view = pd.DataFrame({"Hạng": d["#"], "Ngành / Dòng": d["Dòng"], "Tín hiệu": np.where(d["Dẫn sóng"], "DẪN SÓNG", ""), "Số mã": d["Số mã"],
                         "Biến động giai đoạn": d["Giai đoạn"], "Biến động ngày": d["Ngày"]})
    height = min(620, 40 + 36 * len(view))
    cfg = _table_cfg()

    left, right = st.columns([1.3, 1], gap="medium")
    with left:
        st.markdown('<div class="dd-topbar"><b style="color:#E6EDF3;letter-spacing:.4px">TRẠM TÍN HIỆU</b>&nbsp;<span style="color:#6B7686">|</span>&nbsp;<b style="color:#E8C47C;letter-spacing:.4px">MIN TRADING</b></div>', unsafe_allow_html=True)
        styler = _styler(view, ["Biến động giai đoạn", "Biến động ngày"], sel_name)
        picked = None
        ev = None
        for mode in ("single-cell", "single-row"):          # bản Streamlit mới: bấm vào ô bất kỳ trong hàng; bản cũ hơn: tích ô vuông đầu hàng
            try:
                ev = st.dataframe(styler, hide_index=True, **ND.stretch(st.dataframe), height=height, on_select="rerun", selection_mode=mode,
                                  column_config=cfg, key=f"dds_table_{mode}_{n}")
                break
            except Exception:  # noqa: BLE001
                ev = None
        if ev is None:                                       # không có on_select: chọn bằng ô chọn
            try:
                st.dataframe(styler, hide_index=True, **ND.stretch(st.dataframe), height=height, column_config=cfg)
            except Exception:  # noqa: BLE001
                st.dataframe(styler, hide_index=True, **ND.stretch(st.dataframe), height=height)
            picked = st.selectbox("Chọn dòng để xem cổ phiếu", names, index=names.index(sel_name), key="dds_pick")
        else:
            picked = _pick_from(ev.selection, names)
        if picked:
            st.session_state["dds_last"] = picked          # nhớ dòng đã chọn (kể cả khi đổi giai đoạn)
            sel_name = picked

    name = sel_name
    info = meta.get(name, {})
    rep = ND.rep_stocks(P, groups.get(name, []), n, info.get("leaders"))
    with right:
        crc = zlib.crc32(name.encode("utf-8"))
        ok = [str(c) for c in rep["Mã"] if openable is None or str(c) in openable] if (not rep.empty and on_open is not None) else []
        compare = False
        c1, c2, c3 = st.columns([3, 2.4, 2.6], vertical_alignment="center") if _VALIGN else st.columns([3, 2.4, 2.6])
        if ok:
            code = c1.selectbox("Mã", ok, key=f"dds_code_{crc}", label_visibility="collapsed")
            c2.button("📈 Mở biểu đồ", key=f"dds_open_{crc}", on_click=on_open, args=(code,), **ND.stretch(st.button))
        if not rep.empty:
            compare = c3.toggle("So sánh các mã", key="dds_cmp", help=f"Quy giá về 100 tại đầu giai đoạn; vẽ {ND.COMPARE_MAX} mã mạnh nhất.")

        dot = PALETTE[crc % len(PALETTE)]
        total = len(set(str(c).upper() for c in groups.get(name, [])))
        k = len(rep)
        list_h = max(240, height - 130)
        body = _stock_rows(rep, name_of) if not rep.empty else '<div class="dd-desc">Chưa đủ dữ liệu của các mã trong dòng này.</div>'
        desc = f'<div class="dd-desc">{_html.escape(info["desc"])}</div>' if info.get("desc") else ""
        colhead = f'<div class="dd-colhead"><div>#</div><div></div><div>Cổ phiếu</div><div class="r">Giá · % ngày</div><div class="r">{_html.escape(period)}</div></div>'
        foot = f'<div class="dd-foot">Dòng gồm {total} mã, dữ liệu của bạn có {k} mã; xếp từ mạnh nhất xuống yếu nhất theo biến động {_html.escape(period)}.</div>'
        st.markdown(f'<div class="dd-card"><div class="dd-head"><i style="width:13px;height:13px;border-radius:50%;background:{dot};display:inline-block"></i>'
                    f'CỔ PHIẾU ĐẠI DIỆN NHÓM {_html.escape(name.upper())}</div>{desc}{colhead}<div class="dd-list" style="max-height:{list_h}px">{body}</div>{foot}</div>',
                    unsafe_allow_html=True)
    if compare and not rep.empty:
        import plotly.graph_objects as go
        cf = ND.compare_frame(P, rep["Mã"].head(ND.COMPARE_MAX).tolist(), n)
        fig = go.Figure()
        for code_ in cf.columns:
            fig.add_trace(go.Scatter(x=cf.index, y=cf[code_], mode="lines", name=str(code_), line=dict(width=1.8)))
        fig.add_hline(y=100, line_dash="dot", line_color="#6B7686")
        fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=1.1), template="plotly_dark",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", yaxis_title="Quy về 100")
        st.plotly_chart(fig, **ND.stretch(st.plotly_chart))
    st.caption(f"Biến động dòng = trung vị % của các mã trong dòng (dòng dưới {ND.MIN_FOR_MEDIAN} mã dùng trung bình); giai đoạn tính trên {n} phiên. "
               f"Danh sách bên phải chỉ gồm các mã có trong dữ liệu của bạn. Chỉ để tham khảo, không phải khuyến nghị đầu tư.")
