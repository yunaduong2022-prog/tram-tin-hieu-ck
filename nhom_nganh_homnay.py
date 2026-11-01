"""Thị trường > Nhóm ngành: "Xếp hạng sức mạnh nhóm ngành hôm nay".
Hai cột xếp hạng: nhóm ngành, hiệu suất theo 1 phiên/1 tuần/1 tháng/3 tháng, GTGD TB/phiên, RS theo kỳ, mã dẫn đầu theo kỳ.
Sắp xếp theo % tăng mạnh (mặc định), dòng tiền (GTGD) hoặc RS. Số liệu lấy từ nhom_nganh_data.py (cùng cách tính với Cảnh báo luân chuyển dòng tiền).
Chỉ phục vụ nghiên cứu, không phải khuyến nghị đầu tư.
"""
from __future__ import annotations

import html as _html
import hashlib
import zlib

import numpy as np
import pandas as pd
import streamlit as st

import nhom_nganh_data as ND

DECIMAL_COMMA = True            # True: +0,93% và 1.234 Tỷ (như bảng mẫu); False: +0.93% và 1,234 Tỷ
SORTS = ["% Tăng mạnh", "Dòng tiền (GTGD)", "RS"]
PALETTE = ["#38BDF8", "#A3E635", "#22D3EE", "#C084FC", "#F43F5E", "#9333EA", "#F472B6", "#E11D48", "#0EA5E9", "#38BDF8",
           "#94A3B8", "#34D399", "#3B82F6", "#FACC15", "#FB923C", "#EAB308", "#A855F7", "#EC4899", "#818CF8", "#2DD4BF", "#14B8A6", "#FBBF24"]

CSS = """
<style>
.nn-wrap{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.nn-head{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--line);flex-wrap:wrap}
.nn-title{font-weight:800;font-size:17px;color:var(--txt);letter-spacing:.2px}
.nn-badge{font-size:11.5px;font-weight:800;padding:3px 10px;border-radius:7px;border:1px solid var(--line);color:var(--muted)}
.nn-badge.live{color:var(--green);border-color:var(--green);background:rgba(8,153,129,.12)}
.nn-grid{display:grid;grid-template-columns:1fr 1fr;gap:0 26px;padding:0 18px 8px}
@media(max-width:1000px){.nn-grid{grid-template-columns:1fr}}
.nn-hd,.nn-row{display:grid;grid-template-columns:34px minmax(110px,1fr) 78px 82px 92px 104px;align-items:center;gap:6px}
.nn-hd{padding:12px 4px;font-size:11.5px;font-weight:800;color:var(--muted);letter-spacing:.4px;border-bottom:1px solid var(--line)}
.nn-row{padding:9px 4px;border-bottom:1px solid var(--line2);font-size:14px;color:var(--txt)}
.nn-row:hover{background:var(--card2)}
.nn-hd .r,.nn-row .r{text-align:right;font-variant-numeric:tabular-nums}
.nn-rk{color:var(--muted);font-weight:700;text-align:center;font-size:13px}
.nn-medal{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;font-size:12px;font-weight:800;border:2px solid}
.nn-medal.m1{border-color:#E8C47C;color:#E8C47C}.nn-medal.m2{border-color:#C9D1D9;color:#C9D1D9}.nn-medal.m3{border-color:#D28A4A;color:#D28A4A}
.nn-name{display:flex;align-items:center;gap:9px;font-weight:700;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.nn-dot{flex:none;width:11px;height:11px;border-radius:50%}
.nn-perf{font-weight:800;font-size:15px}
.nn-up{color:var(--green)}.nn-dn{color:var(--red)}.nn-flat{color:#E8C47C}
.nn-val{color:var(--txt2)}
.nn-rs{font-size:12.5px;font-weight:700}
.nn-lead b{color:var(--txt2);margin-right:5px}
.nn-lead span{font-size:12.5px;font-weight:700}
.nn-note{padding:8px 18px 14px;color:var(--muted);font-size:12px}
</style>
"""


def _vn(s: str) -> str:
    return s.translate(str.maketrans(",.", ".,")) if DECIMAL_COMMA else s


def _cls(v) -> str:
    return "nn-flat" if v is None or not np.isfinite(v) or abs(v) < 0.005 else ("nn-up" if v > 0 else "nn-dn")


def _pct(v, nd: int = 2) -> str:
    return "-" if v is None or not np.isfinite(v) else _vn(f"{v:+.{nd}f}%")


def _val(v) -> str:
    return "-" if v is None or not np.isfinite(v) else _vn(f"{v:,.0f}") + " Tỷ"


def _dot(name: str) -> str:
    return PALETTE[zlib.crc32(name.encode("utf-8")) % len(PALETTE)]


def _row(i: int, r: pd.Series) -> str:
    rk = f'<span class="nn-medal m{i}">{i}</span>' if i <= 3 else f'<span class="nn-rk">{i}</span>'
    rs = r["RS kỳ"]
    rs_html = '<span class="nn-rs nn-flat">-</span>' if rs is None or not np.isfinite(rs) else \
        f'<span class="nn-rs {_cls(rs)}">{"▲" if rs > 0 else "▼" if rs < 0 else "■"} {_vn(f"{abs(rs):.1f}")}đ%</span>'
    nm = _html.escape(str(r["Nhóm"]))
    return (f'<div class="nn-row"><div style="text-align:center">{rk}</div>'
            f'<div class="nn-name" title="{nm}"><i class="nn-dot" style="background:{_dot(str(r["Nhóm"]))}"></i>{nm}</div>'
            f'<div class="r nn-perf {_cls(r["Hiệu suất"])}">{_pct(r["Hiệu suất"])}</div>'
            f'<div class="r nn-val">{_val(r["GTGD"])}</div>'
            f'<div class="r">{rs_html}</div>'
            f'<div class="r nn-lead"><b>{_html.escape(str(r["Mã dẫn đầu"]))}</b><span class="{_cls(r["% dẫn đầu"])}">{_pct(r["% dẫn đầu"])}</span></div></div>')


_HEAD = ('<div class="nn-hd"><div style="text-align:center">#</div><div>NHÓM NGÀNH</div><div class="r">HIỆU SUẤT</div><div class="r" title="Giá trị giao dịch bình quân mỗi phiên trong kỳ được chọn">GTGD TB</div>'
         '<div class="r" title="Hiệu suất ngành trừ hiệu suất thị trường trong kỳ (điểm phần trăm)">RS KỲ</div><div class="r">MÃ DẪN ĐẦU</div></div>')


@st.cache_data(show_spinner="Đang tính sức mạnh nhóm ngành...", max_entries=12)
def _period_cached(_P: dict, _mkt: pd.Series, _groups: dict, sig: str, data_key: str, lead_min: float, period: str) -> pd.DataFrame:
    n = ND.RANK_WINDOWS[period]
    return ND.window_stats(_P, _groups, _mkt, n, lead_min)


def render(raw: pd.DataFrame, mkt: pd.Series, default_groups: dict, data_key: str, live: bool = False, asof: str = "") -> None:
    P = ND.pivots(raw, data_key)
    groups, _meta = ND.load_groups(default_groups)
    st.markdown(CSS, unsafe_allow_html=True)

    c1, c2, c3 = st.columns([5, 3, 3])
    with c1:
        # MIN_MARKET_SECTOR_PERIOD_CONTROL_V1
        period = st.pills("Khung thời gian", list(ND.RANK_WINDOWS), selection_mode="single", default="1 phiên", key="nn_period") or "1 phiên"
    with c2:
        sort = st.pills("Sắp xếp", SORTS, selection_mode="single", default=SORTS[0], key="nn_sort", label_visibility="collapsed") or SORTS[0]
    with c3:
        only_liq = st.toggle("Mã dẫn đầu: GTGD ≥ 1 tỷ", value=False, key="nn_leader_liq", help="Bỏ qua mã thanh khoản mỏng khi chọn mã dẫn đầu của nhóm.")
    sig = hashlib.sha256(repr(sorted((str(k), tuple(map(str, v))) for k, v in groups.items())).encode("utf-8")).hexdigest()[:16]
    d = _period_cached(P, mkt, groups, sig, data_key, 1.0 if only_liq else 0.0, period)
    if d.empty:
        st.info(f"Không đủ dữ liệu lịch sử để xếp hạng {period} hoặc nhóm chưa đủ 2 mã hợp lệ.")
        return
    key = {"% Tăng mạnh": ("Hiệu suất", False), "Dòng tiền (GTGD)": ("GTGD", False), "RS": ("RS kỳ", False)}[sort]
    d = d.sort_values(key[0], ascending=key[1], na_position="last").reset_index(drop=True)

    # This panel ranks CONFIRMED EOD sessions even if another site mode is intraday.
    badge = f'<span class="nn-badge">🕒 EOD {(_html.escape(str(asof)) if asof else "")} · {period}</span>'
    half = int(np.ceil(len(d) / 2))
    left = "".join(_row(i + 1, r) for i, (_, r) in enumerate(d.iloc[:half].iterrows()))
    right = "".join(_row(half + i + 1, r) for i, (_, r) in enumerate(d.iloc[half:].iterrows()))
    st.markdown(CSS + f'<div class="nn-wrap"><div class="nn-head"><span style="font-size:20px">🔥</span><span class="nn-title">XẾP HẠNG SỨC MẠNH NHÓM NGÀNH</span>{badge}</div>'
                f'<div class="nn-grid"><div>{_HEAD}{left}</div><div>{_HEAD if right else ""}{right}</div></div>'
                f'<div class="nn-note">Khung {period}: hiệu suất tính từ nến EOD đã đóng của {ND.RANK_WINDOWS[period]} phiên giao dịch (1/5/21/63); nhóm dùng trung vị hoặc trung bình nếu dưới {ND.MIN_FOR_MEDIAN} mã. '
                'GTGD TB = tổng GTGD khớp lệnh bình quân mỗi phiên trong khung; RS KỲ = hiệu suất nhóm trừ hiệu suất chuỗi thị trường (VN-Index nếu có, nếu không là proxy), đơn vị điểm phần trăm. '
                'Mã dẫn đầu xét cùng khung; những mã thiếu giá đầu/cuối kỳ không được suy đoán. Không phải realtime hoặc tín hiệu mua/bán.</div></div>',
                unsafe_allow_html=True)
