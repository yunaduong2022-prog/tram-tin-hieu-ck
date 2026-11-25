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
    daily, last_date = _daily_for(code, frames_d)
    close = daily['Giá đóng cửa'].iat[-1] if not daily.empty and 'Giá đóng cửa' in daily.columns else None
    fa, fa_tags, bank = vip.fa_score_for_symbol(code, fdict or {}, price_k=close, price_date=last_date, asof=asof)
    check_date = pd.to_datetime(asof, errors='coerce') if asof is not None else None
    stale = (last_date is not None and pd.notna(check_date) and
             last_date != check_date.normalize())
    if bank is not None and asof is not None:
        from market_eod_guard import stale as market_stale
        stale = stale or market_stale(asof)
    if daily.empty or last_date is None or stale:
        return {'code': code, 'frame': frame, 'fa': fa, 'ta': None, 'total': None,
                'system': None, 'grade': None, 'tags_fa': list(fa_tags), 'tags_ta': [],
                'asof': last_date, 'bank': bank,
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
    total = vip.total_score_for_symbol(fa, ta, sys_score, frame, bank)
    grade = vip.grade_of(total) if total is not None else None
    missing = [name for name, val in [('FA', fa), ('TA', ta), ('Score hệ thống', sys_score)] if val is None]
    status = ('Đủ FA, TA và Score hệ thống.' if not missing else
              'Thiếu ' + ', '.join(missing) + '; Tổng điểm nếu có đã được VIP phân bổ lại trọng số.')
    if bank is not None and (fa is None or bank['risk']):
        status = 'BANK FA: chưa đủ dữ liệu xác minh hoặc có cảnh báo rủi ro; không xếp hạng tổng điểm.'
    return {'code': code, 'frame': frame, 'fa': fa, 'ta': ta, 'total': total, 'bank': bank,
            'system': sys_score, 'grade': grade, 'tags_fa': list(fa_tags),
            'tags_ta': list(ta_tags), 'rsi': rsi, 'asof': last_date, 'status': status}


def bank_display_total(display, vip, frame):
    """Personal research only: use available score components without a risk veto."""
    fa = _finite(display.get('fa'))
    ta = _finite(display.get('ta'))
    system = _finite(display.get('system'))
    scale = display.get('fa_scale', 100)
    if fa is None or scale not in (85, 100) or not 0 <= fa <= scale:
        return None, 'Chưa có điểm FA để tính tổng.'
    if ta is None and system is None:
        return None, 'Chưa có TA hoặc điểm hệ thống để tính tổng.'
    total = vip.total_score(fa * 100 / scale, ta, system, frame)
    missing = []
    if scale == 85:
        missing.append('Thiếu P/B: FA tài chính quy về thang 100')
    if ta is None:
        missing.append('Thiếu TA')
    if system is None:
        missing.append('Thiếu điểm hệ thống')
    note = '; '.join(missing)
    if note:
        note += ' · Phân bổ theo thành phần có dữ liệu.'
    else:
        note = 'Đủ FA, TA và điểm hệ thống.'
    return total, note


def _display(v):
    n = _finite(v)
    return '—' if n is None else f'{n:.1f}'


def bank_metric_ranks(rows, current, prices, score_fn):
    """Compare raw metrics for the selected bank against comparable peers.

    Financial ratios: same quarter. P/B: same quarter and same valid EOD.
    Competition ranks (1, 2, 2, 4) use unrounded values; include cutoff ties.
    """
    if not rows or not current:
        return {}
    code=current.get('Mã')
    period=current.get('Kỳ')
    if not code or not period:
        return {}
    peers=[score_fn(row,*prices.get(symbol,(None,None,False)))
           for symbol,row in rows.items() if row.get('period_end')==period]
    out={}
    for k in ('ROE','NIM','CASA','NPL','LLR','PB'):
        field='P/B ứng viên' if k=='PB' else k
        point_field='Điểm P/B /15' if k=='PB' else k+' điểm'
        v=_finite(current.get(field))
        if v is None or _finite(current.get(point_field)) is None:
            continue
        if k=='PB' and not current.get('Phiên giá'):
            continue
        comparable=[]
        for p in peers:
            value=_finite(p.get(field))
            if value is None or _finite(p.get(point_field)) is None:
                continue
            if k=='PB' and p.get('Phiên giá')!=current.get('Phiên giá'):
                continue
            comparable.append((p['Mã'],value))
        if not any(s==code and value==v for s,value in comparable):
            continue
        low=k in ('NPL','PB')
        comparable.sort(key=lambda item: (item[1] if low else -item[1],item[0]))
        def rank(value):
            return 1+sum(1 for _,other in comparable if (other<value if low else other>value))
        out[k]={'rank':rank(v),'count':len(comparable),'low':low,
                'top':[(s,value,rank(value)) for s,value in comparable if rank(value)<=5]}
    return out


def bank_rank_table(ranks):
    """Small table for the leaders of each comparable metric."""
    result=[]
    for k,info in ranks.items():
        label={'PB':'P/B thấp (ước tính)','NPL':'NPL thấp'}.get(k,k+' cao')
        leaders=' · '.join(f"#{r} {s} ({v:.2f}{'x' if k=='PB' else '%'})" for s,v,r in info['top'])
        result.append({'Chỉ tiêu':label,'Top 5 theo chỉ tiêu':leaders,'Số mã so sánh':info['count']})
    return result


def bank_fa_notes(values, points, *, estimated=False, ranks=None):
    """Describe the existing rubric, not an independent valuation or score."""
    levels = {
        'ROE': {20:'Rất tốt',17:'Tốt',14:'Khá',10:'Trung bình',5:'Thấp',0:'Rất thấp'},
        'NIM': {15:'Rất tốt',12:'Tốt',9:'Khá',5:'Thấp',0:'Rất thấp'},
        'CASA': {10:'Rất tốt',8:'Tốt',6:'Khá',4:'Trung bình',2:'Thấp',0:'Rất thấp'},
        'NPL': {20:'Rất thấp',17:'Thấp',14:'Khá thấp',8:'Cần theo dõi',3:'Cao',0:'Rất cao'},
        'LLR': {20:'Rất tốt',17:'Tốt',14:'Khá',8:'Trung bình',4:'Thấp',0:'Rất thấp'},
        'PB': {15:'Rất tốt',13:'Tốt',11:'Khá',8:'Trung bình',5:'Thấp',2:'Rất thấp',0:'Rất thấp'},
    }
    notes=[]
    for k in ('ROE','NIM','CASA','NPL','LLR','PB'):
        v=_finite(values.get(k))
        p=points.get(k)
        label={'NPL':'NPL (nợ xấu)','LLR':'LLR (bao phủ nợ xấu)','PB':'P/B'}.get(k,k)
        if k=='PB' and estimated:
            label+=' ước tính'
        if v is None or p is None:
            notes.append(f'{label}: Chưa có dữ liệu')
            continue
        amount=f'{v:.2f}'.replace('.',',')+('x' if k=='PB' else '%')
        rating=levels[k].get(p,'Theo thang điểm FA')
        if k=='PB': rating='Điểm định giá '+rating.lower()
        info=(ranks or {}).get(k)
        suffix=''
        if info is not None:
            direction=' thấp nhất' if info['low'] else ''
            suffix=f" | TOP {info['rank']}{direction} Ngành Ngân hàng"
            if info['count'] != 28:
                suffix+=f" ({info['count']} mã có dữ liệu)"
        notes.append(f'{label} {amount} – {rating}'+suffix)
    return notes


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

    is_bds = str(result.get('code','')).upper() in __import__('bds_fa').SYMBOLS

    def score_text(value, *, total=False, scale=100, exact=False):
        n = _finite(value)
        if n is None:
            return '<span class="mvs-score">—</span>'
        score = f'{n:.2f}'.rstrip('0').rstrip('.') if exact else f'{n:.0f}'
        tip = html.escape(f'{n:.1f}/{scale}', quote=True)
        out = f'<span class="mvs-score" title="{tip}">{score}</span>'
        if not total:
            out += f'<span class="mvs-scale">/{scale}</span>'
        return out

    def bar(value):
        n = _finite(value)
        width = 0 if n is None else max(0.0, min(100.0, n))
        return f'<div class="mvs-bar"><div class="mvs-fill" style="width:{width:.1f}%"></div></div>'

    def tag_list(tags, limit=3):
        if not tags:
            return '<div class="mvs-missing">Chưa đủ lý do xác minh</div>'
        return '<ul class="mvs-tags">' + ''.join(
            f'<li>{html.escape(str(tag))}</li>' for tag in list(tags)[:limit]
        ) + '</ul>'

    fa = tag_list(result.get('tags_fa') or []) if _finite(result.get('fa')) is not None else \
        '<div class="mvs-missing">Chưa đủ chỉ tiêu FA</div>'
    if result.get('bank') is not None:
        fa = tag_list(result.get('tags_fa') or [], limit=6 if result.get('bank_fa_notes') else 3)
    elif is_bds and _finite(result.get('fa')) is not None:
        fa = tag_list(result.get('tags_fa') or [], limit=13)
    technical_tags = []
    rsi = _finite(result.get('rsi'))
    if rsi is not None:
        technical_tags.append(f'RSI {rsi:.1f}')
    technical_tags.extend(result.get('tags_ta') or [])
    ta = tag_list(technical_tags) if _finite(result.get('ta')) is not None else \
        '<div class="mvs-missing">Chưa đủ dữ liệu TA</div>'
    grade = result.get('grade')
    from vip_picks import component_grade_badge
    grade_html = component_grade_badge(result.get('total'), css_class='mvs-badge', grade=grade) if grade else ''
    cells = []
    for label, val, detail, is_total in (
        (result.get('fa_label','Điểm cơ bản (FA)'), result.get('fa'), fa, False),
        ('Điểm kỹ thuật (TA)', result.get('ta'), ta, False),
        (result.get('total_label','Tổng điểm'), result.get('total'), '', True),
    ):
        scale = result.get('fa_scale',100) if not cells else 100
        cell_badge = grade_html if is_total else component_grade_badge(val, scale=scale, css_class="mvs-badge")
        cells.append('<div class="mvs-item">'
                     f'<div class="mvs-label" style="color:{muted}">{html.escape(label)}</div>'
                     f'<div style="color:{text_color}">{score_text(val, total=is_total, scale=scale, exact=is_bds and not cells)}{cell_badge}</div>'
                     + bar(val*100/scale if _finite(val) is not None else None) + detail + '</div>')
    return (style + f'<section class="mvs-vip" style="background:{bg};border:1px solid {line};color:{text_color}">'
            '<div class="mvs-grid">' + ''.join(cells) + '</div></section>')


def bank_shared_display(result, research_rows, prices, vip, frame):
    """Common personal bank display for chart, livestream and VIP; no trade decisions."""
    import bank_web_review
    bank = result.get('bank')
    research = None
    ranks = {}
    pb_detail = None
    display = dict(result)
    if bank is not None and research_rows and result['code'] in research_rows:
        research = bank_web_review.score(research_rows[result['code']], *prices.get(result['code'], (None,None,False)))
        if result['fa'] is None and research is not None:
            fa_est=research['FA tham khảo /100']
            if fa_est is not None:
                display.update(fa=fa_est,fa_label='Điểm cơ bản (FA)',fa_scale=100)
            elif research['Tài chính /85'] is not None:
                display.update(fa=research['Tài chính /85'],fa_label='Điểm cơ bản (FA)',fa_scale=85)
            values={k:research.get(k) for k in ('ROE','NIM','CASA','NPL','LLR')}
            points={k:research.get(k+' điểm') for k in values}
            values['PB']=research.get('P/B ứng viên')
            points['PB']=research.get('Điểm P/B /15')
            ranks=bank_metric_ranks(research_rows,research,prices,bank_web_review.score)
            display['tags_fa']=bank_fa_notes(values,points,estimated=True,ranks=ranks)
            import bank_pb_compare
            pb_note, pb_detail = bank_pb_compare.chart_notes(
                research_rows, research, prices, bank_web_review.score)
            if pb_note:
                display['tags_fa'][-1]=display['tags_fa'][-1].split(' | TOP ',1)[0]+' | '+pb_note
            display['bank_fa_notes']=True
    if bank is not None and result['fa'] is not None:
        display['tags_fa']=bank_fa_notes(bank['values'],bank['points'])
        display['bank_fa_notes']=True
    personal_bank = bank is not None and display.get('fa') is not None
    if personal_bank:
        total, note = bank_display_total(display, vip, frame)
        display.update(total=total, grade=None, total_label='Tổng điểm tham khảo', status=note)
    return display, research, ranks, pb_detail, personal_bank


def render_vip_scores(code, frames_d, screener, fundamentals, asof, *, key, mode='stock'):
    """Reusable compact block. Scoring is EOD-backed even for DNSE/1H charts."""
    import streamlit as st
    import vip_picks as vip

    # Explicit horizon avoids silently displaying VIP long-horizon weights as medium.
    frame = st.selectbox('Khung chấm điểm (theo Khuyến nghị khách hàng)', FRAMES,
                         key=key + '_frame', help='Đối chiếu đúng khung Trung hạn hoặc Dài hạn trong Khuyến nghị khách hàng.')
    result = compute_vip_scores(code, frames_d, screener, fundamentals, frame=frame,
                                asof=asof, vip_module=vip)
    bank = result.get('bank')
    research_rows = None
    research = None
    ranks = {}
    pb_detail = None
    personal_bank = False
    display = dict(result)
    if bank is not None:
        import bank_web_review
        research_rows = bank_web_review.resolve_rows(st,key,compact=True)
        display, research, ranks, pb_detail, personal_bank = bank_shared_display(
            result, research_rows, bank_web_review.current_prices(frames_d,asof), vip, frame)
    st.markdown(_panel_html(display, mode=mode), unsafe_allow_html=True)
    if personal_bank and research is not None and result['fa'] is None:
        if research['Rủi ro']=='Cảnh báo':
            st.warning('Cảnh báo rủi ro tài chính theo ngưỡng BANK FA.')
        if display.get('fa_scale')==85:
            st.warning('Thiếu P/B: điểm tài chính trên thang 85.')
    if bank is not None:
        with st.expander('Chi tiết dữ liệu và cách chấm điểm ngân hàng', expanded=False):
            if pb_detail:
                st.caption(pb_detail)
            if personal_bank:
                st.caption('Điểm cá nhân theo dữ liệu hiện có · Cảnh báo rủi ro không chặn tính điểm · Không tự thay đổi khuyến nghị VIP.')
                if research is not None and result['fa'] is None:
                    st.caption(f"FA ước tính · BCTC {research['Kỳ']} · {research['Trạng thái']}")
            w = vip.weights_of(frame)
            eod = f" · EOD {result['asof']:%d/%m/%Y}" if result.get('asof') is not None else ''
            st.caption(f'Khung {frame} · FA {w[0]:.0%} / TA {w[1]:.0%} / Hệ thống {w[2]:.0%}{eod} · '
                       'Cùng công thức Khuyến nghị khách hàng; điểm TA lấy nến Ngày EOD.')
            if display.get('status'):
                st.caption(display['status'])
            bank = result.get('bank')
            if bank is not None and (research is None or result['fa'] is not None):
                import bank_fa
                st.caption(f"BANK FA · Độ phủ {bank['coverage']}% · {bank['status']} · Kỳ: {bank['period'] or 'Chưa xác minh'}")
                st.dataframe(pd.DataFrame([{'Chỉ tiêu': k, 'Giá trị': bank['values'][k],
                    'Điểm': bank['points'].get(k), 'Tối đa': w} for k,w in bank_fa.WEIGHTS.items()]),
                    hide_index=True, use_container_width=True)
                st.caption(f"P/B theo phiên: {bank['price_date'] or '—'} · BVPS: {bank['bvps'] if bank['bvps'] is not None else '—'} VND")
                st.write('Nguồn: ' + (bank['source'] or 'Chưa xác minh'))
                if bank['tags']:
                    st.caption('; '.join(bank['tags']))
            if bank is not None:
                import bank_web_review
                bank_web_review.render(frames_d, asof, symbol=result['code'], key=key, resolved=True, rows=research_rows)
    elif not str(result.get('code','')).upper() in __import__('bds_fa').SYMBOLS:
        w = vip.weights_of(frame)
        eod = f" · EOD {result['asof']:%d/%m/%Y}" if result.get('asof') is not None else ''
        st.caption(f'Khung {frame} · FA {w[0]:.0%} / TA {w[1]:.0%} / Hệ thống {w[2]:.0%}{eod} · '
                   'Cùng công thức Khuyến nghị khách hàng; điểm TA lấy nến Ngày EOD.')
        if display.get('status'):
            st.caption(display['status'])
    if ranks:
        with st.expander('Top 5 ngân hàng theo từng chỉ tiêu FA', expanded=False):
            st.caption('So sánh cùng kỳ BCTC trong 28 ngân hàng theo dõi; P/B cùng phiên EOD. NPL và P/B xếp từ thấp đến cao; các chỉ tiêu khác từ cao đến thấp. Đồng hạng nếu giá trị gốc bằng nhau. P/B thấp không đồng nghĩa cổ phiếu tốt.')
            st.dataframe(pd.DataFrame(bank_rank_table(ranks)),hide_index=True,use_container_width=True)
    with st.expander('Giải thích điểm FA / TA / hệ thống', expanded=False):
        if str(result.get('code','')).upper() in __import__('bds_fa').SYMBOLS:
            import bds_fa_eod
            st.write(bds_fa_eod.detail(result['code']))
        st.write('**FA:** ' + ('; '.join(display['tags_fa']) if display['tags_fa'] else 'Chưa đủ dữ liệu chỉ tiêu cơ bản.'))
        st.write('**TA:** ' + ('; '.join(result['tags_ta']) if result['tags_ta'] else 'Chưa đủ dữ liệu MA/RSI/khối lượng.'))
        st.write('**Điểm hệ thống:** ' + (_display(result['system']) + '/100' if result['system'] is not None else '—') +
                 ' (Score của app × 10).')
        if personal_bank:
            st.caption(display['status'])
        elif bank is not None and (result['fa'] is None or bank['risk']):
            st.caption('Chưa có tổng điểm theo dữ liệu hiện có trong chế độ này.')
        else:
            st.caption('Tổng điểm được chuẩn hóa theo các thành phần có dữ liệu như trang VIP; không tự coi dữ liệu thiếu là 0.')
