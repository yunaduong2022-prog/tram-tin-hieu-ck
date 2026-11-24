"""Read-only VIP score presentation for Stock Chart and Livestream.

All actual scoring stays in vip_picks: fa_score_fd, ta_score, total_score,
grade_of and weights_of. No copies of scoring rules or VIP plan mutations.
"""
from __future__ import annotations

from datetime import date
import html
import math

import pandas as pd


SOURCE_NAME = 'Khuyến nghị khách hàng'
FRAMES = ('Trung hạn', 'Dài hạn')


def _finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if math.isfinite(v) else None


def _daily_for(code, frames_d):
    """Identical 30-session slice to vip_picks.build_view, without mutating data."""
    if not isinstance(frames_d, pd.DataFrame) or frames_d.empty or not {'Mã', 'Ngày'}.issubset(frames_d.columns):
        return pd.DataFrame(), None
    view = frames_d.loc[frames_d['Mã'].astype(str).str.upper().eq(code)]
    if view.empty:
        return view, None
    view = view.sort_values('Ngày').tail(30)
    stamp = pd.to_datetime(view['Ngày'].iloc[-1], errors='coerce')
    return view, stamp.normalize() if pd.notna(stamp) else None


def compute_vip_scores(code, frames_d, screener, fundamentals, frame='Trung hạn', *, asof=None, vip_module=None):
    """Use exactly the same score functions and raw inputs as VIP.build_view.

    A stale symbol must not be presented as a current technical/system rating.
    Missing components stay missing: VIP.total_score redistributes available
    weights as in the customer recommendations page.
    """
    if frame not in FRAMES:
        raise ValueError('UNSUPPORTED_VIP_SCORE_FRAME')
    vip = vip_module if vip_module is not None else __import__('vip_picks')

    code = str(code or '').strip().upper()
    if not code or code in ('VNINDEX', 'VN30', 'VN100', 'VNMIDCAP', 'VNSMALLCAP'):
        return {'code': code, 'frame': frame, 'fa': None, 'ta': None, 'total': None,
                'system': None, 'grade': None, 'tags_fa': [], 'tags_ta': [],
                'asof': None, 'status': 'Chỉ chấm điểm cổ phiếu, không chấm chỉ số.'}

    fdict = (fundamentals or {}).get(code, {}) if isinstance(fundamentals, dict) else {}
    fa, fa_tags = vip.fa_score_fd(fdict or {})
    daily, last_date = _daily_for(code, frames_d)
    check_date = pd.to_datetime(asof, errors='coerce') if asof is not None else None
    stale = (last_date is not None and pd.notna(check_date) and
             last_date != check_date.normalize())
    if daily.empty or last_date is None or stale:
        return {'code': code, 'frame': frame, 'fa': fa, 'ta': None, 'total': None,
                'system': None, 'grade': None, 'tags_fa': list(fa_tags), 'tags_ta': [],
                'asof': last_date,
                'status': ('Chưa có nến EOD hợp lệ để chấm TA / Tổng điểm.' if daily.empty or last_date is None
                           else f'Dữ liệu EOD của mã mới đến {last_date:%d/%m/%Y}; chưa tính TA / Tổng điểm như phiên hiện tại.')}

    ta, ta_tags = vip.ta_score(daily)
    sys_score = None
    if isinstance(screener, pd.DataFrame) and {'Mã', 'Score'}.issubset(screener.columns):
        match = screener.loc[screener['Mã'].astype(str).str.upper().eq(code), 'Score']
        if not match.empty:
            v = _finite(match.iloc[-1])  # VIP dict(zip(...)) keeps the last matching row
            if v is not None:
                sys_score = min(100.0, max(0.0, v * 10))
    total = vip.total_score(fa, ta, sys_score, frame)
    grade = vip.grade_of(total) if total is not None else None
    missing = [name for name, val in [('FA', fa), ('TA', ta), ('Score hệ thống', sys_score)] if val is None]
    status = ('Đủ FA, TA và Score hệ thống.' if not missing else
              'Thiếu ' + ', '.join(missing) + '; Tổng điểm nếu có đã được VIP phân bổ lại trọng số.')
    return {'code': code, 'frame': frame, 'fa': fa, 'ta': ta, 'total': total,
            'system': sys_score, 'grade': grade, 'tags_fa': list(fa_tags),
            'tags_ta': list(ta_tags), 'asof': last_date, 'status': status}


def _display(v):
    n = _finite(v)
    return '—' if n is None else f'{n:.1f}'


def _panel_html(result, *, mode):
    dark = mode == 'live'
    bg = '#111b2b' if dark else 'var(--card, #162338)'
    panel = '#0b1422' if dark else 'var(--card2, #1f304a)'
    fg = '#f1f5f9' if dark else 'var(--txt, #e2e8f0)'
    muted = '#9bb0c6' if dark else 'var(--muted, #94a3b8)'
    border = '#29384d' if dark else 'var(--line, #334155)'
    grade = f" · Hạng {html.escape(str(result['grade']))}" if result.get('grade') else ''
    cards = [('Điểm cơ bản (FA)', result['fa']), ('Điểm kỹ thuật (TA)', result['ta']),
             ('Tổng điểm', result['total'])]
    chunks = []
    for label, value in cards:
        suffix = grade if label == 'Tổng điểm' else ''
        chunks.append(
            '<div style="min-width:0;padding:10px;border-radius:9px;'
            f'background:{panel};border:1px solid {border}">'
            f'<div style="font-size:11px;line-height:1.3;color:{muted}">{html.escape(label)}</div>'
            f'<div style="color:{fg};font-size:21px;font-weight:800;margin-top:4px">'
            f'{_display(value)}<span style="font-size:11px;color:{muted}">/100</span></div>'
            f'<div style="font-size:11px;color:{muted}">{suffix.lstrip(" ·") if suffix else " "}</div></div>'
        )
    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:12px;'
        f'padding:12px;margin:8px 0;color:{fg}">'
        f'<div style="font-size:13px;font-weight:800;margin-bottom:9px">'
        f'📊 CHẤM ĐIỂM FA · TA · TỔNG ĐIỂM</div>'
        '<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px">'
        + ''.join(chunks) + '</div></div>'
    )


def render_vip_scores(code, frames_d, screener, fundamentals, asof, *, key, mode='stock'):
    """Reusable compact block. Scoring is EOD-backed even for DNSE/1H charts."""
    import streamlit as st
    import vip_picks as vip

    # Explicit horizon avoids silently displaying VIP long-horizon weights as medium.
    frame = st.selectbox('Khung chấm điểm (theo Khuyến nghị khách hàng)', FRAMES,
                         key=key + '_frame', help='Đối chiếu đúng khung Trung hạn hoặc Dài hạn trong Khuyến nghị khách hàng.')
    result = compute_vip_scores(code, frames_d, screener, fundamentals, frame=frame,
                                asof=asof, vip_module=vip)
    st.markdown(_panel_html(result, mode=mode), unsafe_allow_html=True)
    w = vip.weights_of(frame)
    st.caption(f'Khung {frame}: FA {w[0]:.0%} · TA {w[1]:.0%} · Score hệ thống {w[2]:.0%}. '
               'Cùng công thức và nguồn chấm điểm với Khuyến nghị khách hàng; TA là khung Ngày EOD, '
               'khác điểm xu hướng đa khung D/W/M.')
    if result.get('status'):
        st.caption(result['status'])
    if result.get('asof') is not None:
        st.caption(f"Phiên EOD của mã: {result['asof']:%d/%m/%Y} · Giá biểu đồ 1H/DNSE có thể thuộc kỳ khác.")
    with st.expander('Giải thích điểm FA / TA / hệ thống', expanded=False):
        st.write('**FA:** ' + ('; '.join(result['tags_fa']) if result['tags_fa'] else 'Chưa đủ dữ liệu chỉ tiêu cơ bản.'))
        st.write('**TA:** ' + ('; '.join(result['tags_ta']) if result['tags_ta'] else 'Chưa đủ dữ liệu MA/RSI/khối lượng.'))
        st.write('**Điểm hệ thống:** ' + (_display(result['system']) + '/100' if result['system'] is not None else '—') +
                 ' (Score của app × 10).')
        st.caption('Tổng điểm được chuẩn hóa theo các thành phần có dữ liệu như trang VIP; '
                   'không tự coi dữ liệu thiếu là 0 và không phải khuyến nghị mua/bán.')
