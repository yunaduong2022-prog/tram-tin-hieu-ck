# -*- coding: utf-8 -*-
"""MIN_WATCHLIST_T2_TABLE_V1 — Watchlist-only, read-only grouped table.

No orders, no data writes, no modifications to the T+2 engine. TP1/TP2,
stop and R:R are obtained from the *same* functions used by the Trading T+2
page. Only the Watchlist CSV controls membership.
"""
from __future__ import annotations

import html
import string
import math

import numpy as np
import pandas as pd
import streamlit as st

import min_t2_swing as T2
import watchlist as WL
import theme as TH

# Visual-only grouping for the themes in the user's table example. These are
# NOT watchlist members: a symbol is included only if present in MW.load().
_THEMES = {
    "KCN": {"IDC", "SZC", "VGC", "KBC", "BCM", "LHG", "TIP", "SIP", "GVR", "PHR", "NTC"},
    "ĐẦU TƯ CÔNG": {"CTD", "HHV", "LCG", "C4G", "FCN", "VCG", "PLC", "PC1"},
    "BẤT ĐỘNG SẢN": {"TCH", "DXG", "CEO", "DIG", "PDR", "CII", "NLG", "VHM", "VIC", "VRE", "NVL", "KDH", "HDG", "HDC", "IJC", "AGG"},
}

_HEADERS = ["Hạng", "Mã CP", "Loại tín hiệu", "Xu hướng giá", "Ngành", "Giá đáy",
            "% từ đáy", "Giá tín hiệu", "Ngày tín hiệu", "Giá hiện tại",
            "Tăng/Giảm (%)", "TP1", "TP2", "Cắt lỗ", "R:R TP1", "R:R TP2"]


def _num(value):
    try:
        n = float(value)
        return n if np.isfinite(n) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _fmt(value, digits=2):
    n = _num(value)
    return f"{n:,.{digits}f}" if np.isfinite(n) else "—"


def _pct(value):
    n = _num(value)
    return f"{n:+.2f}%" if np.isfinite(n) else "—"


def _safe(value):
    s = str(value or "").strip()
    return "—" if s.lower() in ("", "nan", "none", "nat", "<na>") else s


def _symbol_group(code: str) -> str:
    # Screenshot-specific display buckets have priority over broad categories.
    for name, symbols in _THEMES.items():
        if code in symbols:
            return name
    for name, symbols in WL.GROUPS.items():
        if code in symbols:
            return name.upper()
    return "KHÁC"


def _last_confirmed_low(g: pd.DataFrame) -> float:
    """Most recent confirmed swing low (two candles to its right); no future lookahead."""
    if len(g) < 5:
        return np.nan
    lows = pd.to_numeric(g["Giá thấp nhất"], errors="coerce").to_numpy(dtype=float)
    for i in range(len(lows) - 3, 1, -1):
        pivot = lows[i]
        if (np.isfinite(pivot) and pivot > 0
                and np.isfinite(lows[i-2:i+3]).all()
                and pivot < lows[i-2] and pivot <= lows[i-1]
                and pivot < lows[i+1] and pivot <= lows[i+2]):
            return float(pivot)
    return np.nan


@st.cache_data(show_spinner="Đang đồng bộ tín hiệu Watchlist với Trading T+2...", max_entries=2)
def _t2_history_cached(_daily: pd.DataFrame, asof_iso: str, data_key: str) -> pd.DataFrame:
    """Data key comes from app's EOD last-bar digest; _daily is deliberately not hashed."""
    _, history = T2.scan(_daily, asof=pd.Timestamp(asof_iso))
    return history


def build_board(w: pd.DataFrame, wb: pd.DataFrame, res: pd.DataFrame,
                daily: pd.DataFrame, history: pd.DataFrame, asof) -> pd.DataFrame:
    """Pure dataframe transformation; tested separately from Streamlit rendering.

    Every result symbol must exist in w. No buy-now inference or synthetic TP.
    Only latest T+0–T+15 T+2 event is eligible for target display.
    """
    columns = ["Mã", "Nhóm bảng", "Ngành", "Hạng", "Loại tín hiệu", "Xu hướng giá",
               "Giá đáy", "% từ đáy", "Giá tín hiệu", "Ngày tín hiệu", "Giá hiện tại",
               "Tăng/Giảm (%)", "TP1", "TP2", "Dư địa TP1", "Dư địa TP2", "Cắt lỗ", "R:R", "Nguồn TP1", "Nguồn TP2", "R:R TP2"]
    if w is None or w.empty:
        return pd.DataFrame(columns=columns)
    symbols = list(dict.fromkeys(str(v).strip().upper() for v in w["Mã"] if str(v).strip()))
    symbols = [s for s in symbols if s and s != "NAN"]
    if not symbols:
        return pd.DataFrame(columns=columns)

    asof_ts = pd.Timestamp(asof).normalize()
    d = T2.prepare(daily, asof=asof_ts)
    # A stale/incomplete symbol is retained in the Watchlist, without a false
    # 'current' price or inferred T+2 targets.
    grouped = {str(code): g.reset_index(drop=True)
               for code, g in d[d["Mã"].isin(symbols)].groupby("Mã", sort=False)}
    wb_lookup = (wb.drop_duplicates("Mã").set_index("Mã") if wb is not None and not wb.empty and "Mã" in wb else pd.DataFrame())
    res_lookup = (res.drop_duplicates("Mã").set_index("Mã") if res is not None and not res.empty and "Mã" in res else pd.DataFrame())

    h = history.copy() if history is not None else pd.DataFrame()
    if not h.empty and {"Mã", "Phiên từ tín hiệu", "Ngày tín hiệu"}.issubset(h.columns):
        h = h[h["Mã"].astype(str).str.upper().isin(symbols)].copy()
        h["Phiên từ tín hiệu"] = pd.to_numeric(h["Phiên từ tín hiệu"], errors="coerce")
        h = h[h["Phiên từ tín hiệu"].between(0, 15)]
        h = h.sort_values(["Ngày tín hiệu", "Mã"], ascending=[False, True]).drop_duplicates("Mã")
        # Exact T+2 dynamic TP update and EOD R:R used by Trading T+2 page.
        if not h.empty:
            h = T2._add_dynamic_targets(h, d, 3.0)
        h_lookup = h.set_index("Mã") if not h.empty else pd.DataFrame()
    else:
        h_lookup = pd.DataFrame()

    out = []
    for code in symbols:
        g = grouped.get(code)
        fresh = bool(g is not None and not g.empty and g["Ngày"].iloc[-1] == asof_ts)
        now = _num(g["Giá đóng cửa"].iloc[-1]) if fresh else np.nan
        low = _last_confirmed_low(g) if fresh else np.nan
        wb_row = wb_lookup.loc[code] if code in wb_lookup.index else pd.Series(dtype=object)
        res_row = res_lookup.loc[code] if code in res_lookup.index else pd.Series(dtype=object)
        # MIN_WATCHLIST_T2_MA_MIDTERM_V2: reuse engine.build_screener's
        # Trend_TrungHan, which compares daily MA20 > MA50 > MA100 (TĂNG),
        # MA20 < MA50 < MA100 (GIẢM), otherwise LẪN LỘN.
        # Do not use full 'MA align' (MA10/20/50/100/200); it is a different signal.
        trend = _safe(res_row.get("Trend_TrungHan", "")) if fresh else "—"
        if trend not in ("TĂNG", "GIẢM", "LẪN LỘN"):
            trend = "—"
        row = dict.fromkeys(columns, np.nan)
        row.update({"Mã": code, "Nhóm bảng": _symbol_group(code),
                    "Ngành": _symbol_group(code), "Hạng": np.nan,
                    "Loại tín hiệu": "—", "Xu hướng giá": trend,
                    "Giá đáy": low,
                    "% từ đáy": ((now / low - 1) * 100 if np.isfinite(now) and np.isfinite(low) and low > 0 else np.nan),
                    "Giá hiện tại": now})
        if fresh and code in h_lookup.index:
            s = h_lookup.loc[code]
            signal_price = _num(s.get("Giá tín hiệu"))
            t2_price = _num(s.get("Giá EOD"))
            # Never mix a signal from one EOD snapshot with a different quote.
            if np.isfinite(signal_price) and np.isfinite(t2_price) and abs(t2_price - now) <= .011:
                tp1, tp2 = _num(s.get("Mục tiêu 1")), _num(s.get("Mục tiêu 2"))
                sl = _num(s.get("Cắt lỗ tham khảo"))
                stamp = pd.to_datetime(s.get("Ngày tín hiệu"), errors="coerce")
                row.update({
                    "Loại tín hiệu": _safe(s.get("Tín hiệu", "")),
                    "Giá tín hiệu": signal_price,
                    "Ngày tín hiệu": stamp,
                    "Tăng/Giảm (%)": ((now / signal_price - 1) * 100 if signal_price > 0 else np.nan),
                    "TP1": tp1, "TP2": tp2,
                    # MIN_WATCHLIST_T2_LEVEL_STACK_V3
                    "Nguồn TP1": _safe(s.get("Nguồn TP1", "")) if np.isfinite(tp1) else "—",
                    "Nguồn TP2": _safe(s.get("Nguồn TP2", "")) if np.isfinite(tp2) else "—",
                    # Same percent convention as T+2 level() in min_t2_swing.py.
                    "Dư địa TP1": ((tp1 / now - 1) * 100 if np.isfinite(tp1) and now > 0 else np.nan),
                    "Dư địa TP2": ((tp2 / now - 1) * 100 if np.isfinite(tp2) and now > 0 else np.nan),
                    "Cắt lỗ": sl,
                    "R:R": _num(T2._rr_for_display(s, "Mục tiêu 1", "R:R TP1")),
                    "R:R TP2": _num(T2._rr_for_display(s, "Mục tiêu 2", "R:R TP2")),
                })
        out.append(row)
    board = pd.DataFrame(out, columns=columns)
    # Stable order: first appearance in Watchlist, then within a group.
    group_order = [*_THEMES, *[k.upper() for k in WL.GROUPS], "KHÁC"]
    groups = {s: i for i, s in enumerate(dict.fromkeys(group_order))}
    board["_group_sort"] = board["Nhóm bảng"].map(lambda g: groups.get(g, 999))
    board["_watch_order"] = range(len(board))
    board = board.sort_values(["_group_sort", "_watch_order"], kind="stable")
    board["Hạng"] = board.groupby("Nhóm bảng").cumcount() + 1
    return board.drop(columns=["_group_sort", "_watch_order"]).reset_index(drop=True)


def table_html(board: pd.DataFrame, dark: bool) -> str:
    """Read-only HTML table, escaped cells, light/dark responsive horizontal scroll."""
    bg = "#11271f" if dark else "#ffffff"
    alt = "#1a332a" if dark else "#e8f2fa"
    fg = "#e9f4ed" if dark else "#19362c"
    border = "#335447" if dark else "#b6c9c3"
    groupbg = "#223c32" if dark else "#ecf0fc"
    groupfg = "#b9e5da" if dark else "#123b88"
    esc = lambda v: html.escape(str(v), quote=True)
    def td(v, cls="", extra=""):
        return f'<td class="{cls}" {extra}>{esc(v)}</td>'
    def positive(v):
        val = _num(v)
        color = "pos" if np.isfinite(val) and val > 0 else "neg" if np.isfinite(val) and val < 0 else ""
        return td(_pct(v), color)
    def level_cell(price, pct, source="", stop=False, now=np.nan):
        val, percent = _num(price), _num(pct)
        if not np.isfinite(val) or val <= 0:
            return '<td class="wl-t2-level">—</td>'
        tone = "neg" if stop or (
            np.isfinite(percent) and percent < 0
        ) else "pos"
        detail = (
            f'<small class="wl-t2-level-pct {tone}">{esc(_pct(percent))}</small>'
            if np.isfinite(percent) else ""
        )
        source = _safe(source)
        hint = (
            f'<small class="wl-t2-level-source">{esc(source)}</small>'
            if not stop and source != "—" else ""
        )
        crossed = (
            stop and np.isfinite(_num(now)) and _num(now) <= val
        )
        warn = (
            '<small class="wl-t2-level-warn">EOD ≤ SL</small>'
            if crossed else ""
        )
        return (
            f'<td class="wl-t2-level"><div class="wl-t2-level-stack">'
            f'<b>{esc(_fmt(val))}</b>{detail}{hint}{warn}</div></td>'
        )

    lines = []
    for i, (grp, sub) in enumerate(board.groupby("Nhóm bảng", sort=False)):
        label = f"PHẦN {string.ascii_uppercase[i] if i < 26 else i+1}: DANH MỤC THEO DÕI {grp}"
        lines.append(f'<tr class="wl-t2-group"><td colspan="{len(_HEADERS)}">{esc(label)}</td></tr>')
        for _, r in sub.iterrows():
            sig = _safe(r.get("Loại tín hiệu", ""))
            css = "sig-empty" if sig == "—" else "sig-active"
            trend = _safe(r.get("Xu hướng giá", ""))
            trend_css = {"TĂNG": "trend-up", "GIẢM": "trend-down", "LẪN LỘN": "trend-mixed"}.get(trend, "trend-empty")
            day = pd.to_datetime(r.get("Ngày tín hiệu"), errors="coerce")
            day_s = day.strftime("%d/%m/%Y") if pd.notna(day) else "—"
            cells = [td(int(r["Hạng"]), "rank"), td(r["Mã"], "ticker"),
                     f'<td><span class="wl-t2-sig {css}">{esc(sig)}</span></td>',
                     f'<td class="trend"><span class="wl-t2-trend {trend_css}" title="MA trung hạn: MA20 / MA50 / MA100">{esc(trend)}</span></td>',
                     td(r["Ngành"]), td(_fmt(r["Giá đáy"])),
                     positive(r["% từ đáy"]), td(_fmt(r["Giá tín hiệu"])), td(day_s),
                     td(_fmt(r["Giá hiện tại"]), "price"), positive(r["Tăng/Giảm (%)"]),
                     level_cell(r["TP1"], r["Dư địa TP1"], r["Nguồn TP1"]),
                     level_cell(r["TP2"], r["Dư địa TP2"], r["Nguồn TP2"]),
                     level_cell(r["Cắt lỗ"],
                         ((_num(r["Cắt lỗ"]) / _num(r["Giá hiện tại"]) - 1) * 100
                          if np.isfinite(_num(r["Cắt lỗ"]))
                          and np.isfinite(_num(r["Giá hiện tại"]))
                          and _num(r["Giá hiện tại"]) > 0 else np.nan),
                         stop=True, now=r["Giá hiện tại"]),
                     td(_fmt(r["R:R"])), td(_fmt(r["R:R TP2"]))]
            lines.append('<tr>' + ''.join(cells) + '</tr>')
    css = f"""<style>
      .wl-t2-scroll{{max-width:100%;overflow-x:auto;border:1px solid {border};border-radius:9px;}}
      .wl-t2-table{{width:100%;min-width:1580px;border-collapse:collapse;background:{bg};color:{fg};
        font-size:12px;font-variant-numeric:tabular-nums;}}
      .wl-t2-table th{{background:#37206c;color:#fff;font-weight:750;position:sticky;top:0;z-index:2;
        padding:10px 7px;line-height:1.25;text-align:center;white-space:normal;border:1px solid #695a91;}}
      .wl-t2-table td{{padding:8px 8px;text-align:center;white-space:nowrap;border:1px solid {border};}}
      .wl-t2-table tbody tr:not(.wl-t2-group):nth-child(2n) td{{background:{alt};}}
      .wl-t2-table tbody tr:not(.wl-t2-group):hover td{{background:rgba(28,157,125,.18);}}
      .wl-t2-table .wl-t2-group td{{background:{groupbg} !important;color:{groupfg};
        text-align:center;font-weight:850;letter-spacing:.06em;padding:11px;}}
      .wl-t2-table .ticker{{color:#4aa5ed;font-weight:850;position:sticky;left:0;z-index:1;background:{bg};}}
      .wl-t2-table .rank{{font-weight:750;}}
      .wl-t2-table .price{{font-weight:800;background:rgba(41,133,124,.12);}}
      .wl-t2-table .pos{{color:{'#5cddb3' if dark else '#08784e'};font-weight:800;}}
      .wl-t2-level{{min-width:105px;vertical-align:middle;}}
      .wl-t2-level-stack{{display:flex;flex-direction:column;align-items:center;gap:3px;
        max-width:155px;white-space:normal;line-height:1.2;}}
      .wl-t2-level-stack b{{font-size:13px;white-space:nowrap;}}
      .wl-t2-level-pct{{font-size:11px;font-weight:750;white-space:nowrap;}}
      .wl-t2-level-pct.pos{{color:{'#5cddb3' if dark else '#08784e'};}}
      .wl-t2-level-pct.neg{{color:{'#ff8fa0' if dark else '#c52b45'};}}
      .wl-t2-level-source{{font-size:10px;color:{'#acc5b6' if dark else '#54685f'};
        text-align:center;overflow-wrap:anywhere;}}
      .wl-t2-level-warn{{font-size:10px;font-weight:800;color:{'#ffacba' if dark else '#b72b47'};}}
      .wl-t2-table .neg{{color:{'#ff8fa0' if dark else '#c52b45'};font-weight:800;}}
      .wl-t2-sig{{display:inline-block;padding:3px 8px;border-radius:99px;font-weight:750;max-width:230px;white-space:normal;}}
      .wl-t2-sig.sig-active{{background:{'#174d3e' if dark else '#d5f0e1'};color:{'#70e8be' if dark else '#086642'};}}
      .wl-t2-sig.sig-empty{{background:{'#2b3c34' if dark else '#e4e9e7'};color:{'#9bb5a6' if dark else '#5b6963'};}}
      .wl-t2-table .trend{{white-space:normal;max-width:170px;font-weight:650;}}
      .wl-t2-trend{{display:inline-block;padding:4px 10px;border-radius:99px;white-space:nowrap;font-weight:800;}}
      .wl-t2-trend.trend-up{{background:{'#164b3a' if dark else '#daf4e8'};color:{'#6ce7b7' if dark else '#08774e'};}}
      .wl-t2-trend.trend-down{{background:{'#562936' if dark else '#fce1e7'};color:{'#ffa0ae' if dark else '#b72b47'};}}
      .wl-t2-trend.trend-mixed{{background:{'#4e4224' if dark else '#fff0c7'};color:{'#ffd98a' if dark else '#906113'};}}
      .wl-t2-trend.trend-empty{{background:{'#2b3c34' if dark else '#e9edef'};color:{'#9bb5a6' if dark else '#68777a'};}}
      @media(max-width:800px){{.wl-t2-table{{font-size:11px;}}.wl-t2-table td{{padding:7px 6px;}}}}
    </style>"""
    headers = ''.join('<th>'+esc(h)+'</th>' for h in _HEADERS)
    return css+'<div class="wl-t2-scroll"><table class="wl-t2-table"><thead><tr>'+headers+'</tr></thead><tbody>'+''.join(lines)+'</tbody></table></div>'


def render_board(w: pd.DataFrame, wb: pd.DataFrame, res: pd.DataFrame,
                 daily: pd.DataFrame, asof, data_key: str):
    """Called only for an existing nonempty Watchlist in 'Bảng' view."""
    if daily is None or asof is None:
        st.warning("Chưa có dữ liệu EOD để đồng bộ bảng Watchlist với Trading T+2.")
        return
    try:
        hist = _t2_history_cached(daily, pd.Timestamp(asof).strftime("%Y-%m-%d"), str(data_key))
    except Exception as exc:
        st.warning("Chưa tải được tín hiệu T+2 (" + type(exc).__name__
                   + "). Danh sách Watchlist vẫn hiển thị; các ô T+2 sẽ để trống.")
        hist = pd.DataFrame()
    board = build_board(w, wb, res, daily, hist, asof)
    st.markdown(table_html(board, TH.is_dark()), unsafe_allow_html=True)
    st.caption("Chỉ gồm mã đã thêm vào Watchlist. Loại tín hiệu, TP1/TP2 động, cắt lỗ và R:R lấy theo "
               "Trading T+2; dư địa = (TP/Giá EOD − 1) × 100. Chỉ hiển thị tín hiệu T+0–T+15; "
               "mã không có tín hiệu hoặc dữ liệu đồng bộ hiển thị —. Giá đáy là swing low xác nhận; "
               "xu hướng MA trung hạn lấy từ Trend_TrungHan của bộ lọc (MA20/MA50/MA100: TĂNG, GIẢM, LẪN LỘN). "
               "Tín hiệu T+2 không đồng nghĩa MUA NGAY; "
               "TP có thể đã chạm và cần đối chiếu vòng đời trước khi giao dịch.")
