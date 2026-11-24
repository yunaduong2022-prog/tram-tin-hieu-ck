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
    rsi = _finite(daily['RSI'].iloc[-1]) if ta is not None and 'RSI' in daily.columns else None
    if fa is not None and fa < getattr(vip, 'FA_WEAK', 30):
        fa_tags = [f'Cơ bản yếu (FA dưới {getattr(vip, "FA_WEAK", 30)})'] + list(fa_tags)
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
            'tags_ta': list(ta_tags), 'rsi': rsi, 'asof': last_date, 'status': status}


def _display(v):
    n = _finite(v)
    return '—' if n is None else f'{n:.1f}'


def _panel_html(result, *, mode):
    """Three compact VIP-style columns with a gradient bar and sourced FA/TA tags.

    Only presentation changes: all score values and rank come from VIP routines.
    Text is escaped because fundamental/technical tags may come from data files.
    """
    dark = mode == 'live'
    bg = '#102620' if dark else 'var(--card, #102620)'
    line = '#255249' if dark else 'var(--line, #255249)'
    text_color = '#edf8f2' if dark else 'var(--txt, #edf8f2)'
    muted = '#92b4a8' if dark else 'var(--muted, #92b4a8)'
    green = '#3fd68f'
    style = """<style>
    .mvs-vip{border-radius:12px;padding:10px 12px;box-sizing:border-box;margin:10px 0 12px}
    .mvs-vip .mvs-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:0}
    .mvs-vip .mvs-item{min-width:0;padding:10px 13px 8px;text-align:center;border-right:1px solid #27554b}
    .mvs-vip .mvs-item:last-child{border-right:0}
    .mvs-vip .mvs-label{font-size:11px;min-height:29px;font-weight:800;letter-spacing:.15px;text-transform:uppercase;line-height:1.4}
    .mvs-vip .mvs-score{font-size:27px;font-weight:800;line-height:1.12;font-variant-numeric:tabular-nums}
    .mvs-vip .mvs-scale{font-size:12px;font-weight:500;opacity:.83}
    .mvs-vip .mvs-badge{background:#14463a;color:#3fd68f;border-radius:6px;padding:2px 8px;font-size:12px;font-weight:800;margin-left:7px}
    .mvs-vip .mvs-bar{height:7px;border-radius:20px;background:#25584f;overflow:hidden;margin:8px auto 9px;max-width:190px}
    .mvs-vip .mvs-fill{height:100%;border-radius:20px;background:linear-gradient(90deg,#ee6979 0%,#e3bf78 45%,#43d69d 100%)}
    .mvs-vip .mvs-tags{list-style:none;padding:0;margin:0;text-align:left;font-size:11px;line-height:1.5}
    .mvs-vip .mvs-tags li{margin:3px 0;padding-left:11px;position:relative;overflow-wrap:anywhere}
    .mvs-vip .mvs-tags li:before{content:'•';position:absolute;left:0;color:#3fd68f}
    .mvs-vip .mvs-missing{font-size:11px;opacity:.8;min-height:18px}
    @media(max-width:760px){.mvs-vip .mvs-grid{grid-template-columns:1fr}
      .mvs-vip .mvs-item{border-right:0;border-bottom:1px solid #27554b;padding:10px 12px}
      .mvs-vip .mvs-item:last-child{border-bottom:0}
      .mvs-vip .mvs-label{min-height:0;margin-bottom:7px}}
    </style>"""

    def score_text(value, *, total=False):
        n = _finite(value)
        if n is None:
            return '<span class="mvs-score">—</span>'
        score = f'{n:.0f}'
        tip = html.escape(f'{n:.1f}/100', quote=True)
        out = f'<span class="mvs-score" title="{tip}">{score}</span>'
        if not total:
            out += '<span class="mvs-scale">/100</span>'
        return out

    def bar(value):
        n = _finite(value)
        width = 0 if n is None else max(0.0, min(100.0, n))
        return f'<div class="mvs-bar"><div class="mvs-fill" style="width:{width:.1f}%"></div></div>'

    def tag_list(tags):
        if not tags:
            return '<div class="mvs-missing">Chưa đủ lý do xác minh</div>'
        return '<ul class="mvs-tags">' + ''.join(
            f'<li>{html.escape(str(tag))}</li>' for tag in list(tags)[:3]
        ) + '</ul>'

    fa = tag_list(result.get('tags_fa') or []) if _finite(result.get('fa')) is not None else \
        '<div class="mvs-missing">Chưa đủ chỉ tiêu FA</div>'
    technical_tags = []
    rsi = _finite(result.get('rsi'))
    if rsi is not None:
        technical_tags.append(f'RSI {rsi:.1f}')
    technical_tags.extend(result.get('tags_ta') or [])
    ta = tag_list(technical_tags) if _finite(result.get('ta')) is not None else \
        '<div class="mvs-missing">Chưa đủ dữ liệu TA</div>'
    grade = result.get('grade')
    grade_html = (f'<span class="mvs-badge" title="Hạng {html.escape(str(grade), quote=True)}">'
                  f'{html.escape(str(grade))}</span>') if grade and _finite(result.get('total')) is not None else ''
    cells = []
    for label, val, detail, is_total in (
        ('Điểm cơ bản (FA)', result.get('fa'), fa, False),
        ('Điểm kỹ thuật (TA)', result.get('ta'), ta, False),
        ('Tổng điểm', result.get('total'), '', True),
    ):
        cells.append('<div class="mvs-item">'
                     f'<div class="mvs-label" style="color:{muted}">{html.escape(label)}</div>'
                     f'<div style="color:{text_color}">{score_text(val, total=is_total)}{grade_html if is_total else ""}</div>'
                     + bar(val) + detail + '</div>')
    return (style + f'<section class="mvs-vip" style="background:{bg};border:1px solid {line};color:{text_color}">'
            '<div class="mvs-grid">' + ''.join(cells) + '</div></section>')


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
    eod = f" · EOD {result['asof']:%d/%m/%Y}" if result.get('asof') is not None else ''
    st.caption(f'Khung {frame} · FA {w[0]:.0%} / TA {w[1]:.0%} / Hệ thống {w[2]:.0%}{eod} · '
               'Cùng công thức Khuyến nghị khách hàng; điểm TA lấy nến Ngày EOD.')
    if result.get('status') and result['status'] != 'Đủ FA, TA và Score hệ thống.':
        st.caption(result['status'])
    with st.expander('Giải thích điểm FA / TA / hệ thống', expanded=False):
        st.write('**FA:** ' + ('; '.join(result['tags_fa']) if result['tags_fa'] else 'Chưa đủ dữ liệu chỉ tiêu cơ bản.'))
        st.write('**TA:** ' + ('; '.join(result['tags_ta']) if result['tags_ta'] else 'Chưa đủ dữ liệu MA/RSI/khối lượng.'))
        st.write('**Điểm hệ thống:** ' + (_display(result['system']) + '/100' if result['system'] is not None else '—') +
                 ' (Score của app × 10).')
        st.caption('Tổng điểm được chuẩn hóa theo các thành phần có dữ liệu như trang VIP; '
                   'không tự coi dữ liệu thiếu là 0 và không phải khuyến nghị mua/bán.')
