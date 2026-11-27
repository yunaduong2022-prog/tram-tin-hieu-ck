"""Read-only per-stock foreign flow card, with strict contiguous EOD sessions."""
from __future__ import annotations
import html
import math
from pathlib import Path
import pandas as pd

FIELDS = ('buy_vol','buy_val','sell_vol','sell_val','net_vol','net_val')
SOURCES = ('SSI_IBOARD_PUBLIC_FOREIGN','VNSTOCK5_VCI_FOREIGN')
GROSS_FILE = Path('data/foreign_stock_flow.csv')
CALENDAR_FILE = Path('data/index_prices.csv')


def _dates(values):
    s = pd.Series(values, dtype='object')
    raw = s.astype(str).str.strip()
    iso = raw.str.match(r'^\d{4}-\d{2}-\d{2}')
    out = pd.to_datetime(raw.where(~iso), format='mixed', dayfirst=True, errors='coerce')
    out.loc[iso] = pd.to_datetime(raw.loc[iso].str[:10], format='%Y-%m-%d', errors='coerce')
    return out.dt.normalize()


def calendar_sessions(daily, asof, path=CALENDAR_FILE, *, period=10):
    """Use the VNINDEX calendar, not a ticker's last ten observations."""
    if period not in (10,20): raise ValueError("Invalid period")
    end = _dates([asof]).iloc[0]
    if pd.isna(end): return []
    candidates = []
    try:
        if daily is not None and {'Mã','Ngày'}.issubset(daily):
            candidates.append(daily.loc[daily['Mã'].astype(str).str.strip().str.upper().eq('VNINDEX'),'Ngày'].tolist())
    except (TypeError, ValueError, KeyError): pass
    try:
        idx = pd.read_csv(path, usecols=['Mã','Ngày'], encoding='utf-8-sig')
        candidates.append(idx.loc[idx['Mã'].astype(str).str.strip().str.upper().eq('VNINDEX'),'Ngày'].tolist())
    except (OSError, ValueError, KeyError): pass
    # Merge valid calendar observations; never use dates after the displayed session.
    dates = _dates([v for values in candidates for v in values]).dropna()
    sessions = sorted(set(dates[dates.le(end)]))
    return sessions[-period:] if sessions and sessions[-1] == end else []


def _number(x):
    try:
        v = float(x)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError, OverflowError): return None


def _clean(rec):
    vals = {k:_number(rec.get(k)) for k in FIELDS}
    if any(vals[k] is not None and vals[k] < 0 for k in ('buy_vol','buy_val','sell_vol','sell_val')): return None
    if any(v is not None and abs(v)>1e16 for v in vals.values()): return None
    for suf, tol_min in [('val', 1_000_000), ('vol', 1)]:
        b,s,n = (vals[f'{k}_{suf}'] for k in ('buy','sell','net'))
        if b is not None and s is not None:
            if n is None: vals[f'net_{suf}'] = b-s
            elif abs(b-s-n) > max(tol_min,.005*max(abs(b),abs(s),abs(n))): return None
    # Net value is required by the existing verified file contract.
    return vals if vals['net_val'] is not None else None


def build_summary(flows, code, asof, sessions, *, period=10):
    """Exact day and selected consecutive sessions; never fill missing data."""
    if period not in (10,20): raise ValueError("Invalid period")
    end = _dates([asof]).iloc[0]
    code = str(code).strip().upper()
    dates = sorted(set(_dates(sessions).dropna())) if sessions is not None else []
    dates = [d for d in dates if pd.notna(end) and d<=end][-period:]
    if not dates or dates[-1] != end: dates=[]
    by_day = {}
    if isinstance(flows,pd.DataFrame) and {'symbol','trading_date','data_source'}.issubset(flows):
        own = flows.loc[flows.symbol.astype(str).str.strip().str.upper().eq(code)].copy()
        own['_day'] = _dates(own.trading_date.tolist()).values
        own = own.loc[own['_day'].notna() & own['_day'].le(end)]
        for day, group in own.groupby('_day'):
            if len(group)!=1: continue
            rec=group.iloc[0]
            if not str(rec['data_source']).startswith(SOURCES): continue
            clean=_clean(rec)
            if clean is not None: by_day[day]=clean
    today = by_day.get(end)
    rows=[by_day.get(d) for d in dates]
    present=sum(x is not None for x in rows)
    totals={k:None for k in FIELDS}
    if len(dates)==period and present==period:
        for k in FIELDS:
            vals=[r[k] for r in rows]
            if all(v is not None for v in vals): totals[k]=sum(vals)
    return dict(period=period,code=code,day=end,today=today,dates=dates,rows=rows,coverage=present,totals=totals,
                latest=max(by_day) if by_day else None)



def flow_conclusion(model):
    """Describe observed net flow only; do not imply a trade signal."""
    period = model.get('period',10)
    if len(model['dates']) != period or model['coverage'] != period:
        return None
    vals = [r['net_val'] for r in model['rows']]
    buy = sum(v > 0 for v in vals)
    sell = sum(v < 0 for v in vals)
    flat = period - buy - sell
    last_sign = (vals[-1] > 0) - (vals[-1] < 0)
    streak = 0
    if last_sign:
        for v in reversed(vals):
            if (v > 0) - (v < 0) != last_sign:
                break
            streak += 1
    net = model['totals']['net_val']
    direction = 'Mua ròng' if net > 0 else 'Bán ròng' if net < 0 else 'Cân bằng'
    chain = (('Mua ròng' if last_sign > 0 else 'Bán ròng') + f' {streak} phiên liên tiếp (trong {period} phiên)' if last_sign else 'Phiên cuối cân bằng')
    return dict(buy=buy,sell=sell,flat=flat,streak=streak,net=net,direction=direction,chain=chain)


def _fmt(v, value=False):
    if v is None: return '—'
    if value: return f'{v/1e9:,.2f} tỷ'
    return f'{v:,.0f}'


def _tone(v):
    return '#21bd87' if v is not None and v>0 else '#f05e70' if v is not None and v<0 else '#a4adb9'


def multi_horizon(m10, m20):
    """Read the same EOD session across both complete, nested windows."""
    if (m10.get('period') != 10 or m20.get('period') != 20 or
            m10['code'] != m20['code'] or m10['day'] != m20['day'] or
            m10['dates'] != m20['dates'][-10:]):
        return dict(values=(None,None,None), title='CHƯA ĐỦ DỮ LIỆU ĐỒNG NHẤT',
                    body='Chưa thể đối chiếu ba khung thời gian.', tone='neutral')
    today = (m10['today'] or {}).get('net_val')
    q10, q20 = flow_conclusion(m10), flow_conclusion(m20)
    n10 = q10['net'] if q10 else None
    n20 = q20['net'] if q20 else None
    values = (today,n10,n20)
    def result(title,body,tone='neutral'):
        return dict(values=values,title=title,body=body,tone=tone)
    if any(v is None for v in values):
        missing = ', '.join(k for k,v in zip(('phiên hiện tại','10 phiên','20 phiên'),values) if v is None)
        return result('CHƯA ĐỦ DỮ LIỆU', f'Thiếu {missing}; chưa kết luận xu hướng đa khung.')
    prev = m10['rows'][-2]['net_val']
    if today>0 and n10<0 and n20<0:
        title=('QUAY LẠI MUA RÒNG' if prev<0 else 'MUA RÒNG PHIÊN MỚI')+' – CHƯA XÁC NHẬN ĐẢO CHIỀU'
        body='Phiên mới nhất mua ròng, nhưng lũy kế 10 và 20 phiên vẫn âm. Cần theo dõi khả năng duy trì lực mua.'
        tone='mixed'
    elif today<0 and n10>0 and n20>0:
        title='BÁN RÒNG PHIÊN MỚI – LŨY KẾ VẪN DƯƠNG'
        body='Phiên mới nhất bán ròng, nhưng lũy kế 10 và 20 phiên vẫn dương. Chưa xác nhận đảo chiều dòng tiền.'
        tone='mixed'
    elif all(v>0 for v in values):
        title='MUA RÒNG ĐỒNG THUẬN';body='Cả ba khung đều mua ròng.';tone='buy'
    elif all(v<0 for v in values):
        title='BÁN RÒNG ĐỒNG THUẬN';body='Cả ba khung đều bán ròng.';tone='sell'
    elif n10>0 and n20<0:
        title='DÒNG TIỀN 10 PHIÊN CẢI THIỆN'
        body='Lũy kế 10 phiên dương nhưng 20 phiên vẫn âm. Chưa xác nhận đảo chiều dài hơn.';tone='mixed'
    elif n10<0 and n20>0:
        title='DÒNG TIỀN 10 PHIÊN SUY YẾU'
        body='Lũy kế 10 phiên âm nhưng 20 phiên vẫn dương. Cần theo dõi áp lực bán.';tone='mixed'
    elif all(v==0 for v in values):
        title='CÂN BẰNG CẢ BA KHUNG';body='Giá trị ròng bằng 0 ở cả ba khung.';tone='neutral'
    else:
        title='DÒNG TIỀN CHƯA ĐỒNG THUẬN';body='Ba khung có dấu ròng khác nhau hoặc có khung cân bằng.';tone='mixed'
    # Compare disjoint 10-session windows, not overlapping totals.
    prior10=n20-n10
    if n10<0 and prior10<0:
        if n10>prior10: body='Giá trị bán ròng 10 phiên gần đây thu hẹp so với 10 phiên trước. '+body
        elif n10<prior10: body='Giá trị bán ròng 10 phiên gần đây tăng so với 10 phiên trước. '+body
    elif n10>0 and prior10>0:
        if n10>prior10: body='Giá trị mua ròng 10 phiên gần đây tăng so với 10 phiên trước. '+body
        elif n10<prior10: body='Giá trị mua ròng 10 phiên gần đây giảm so với 10 phiên trước. '+body
    return result(title,body,tone)


def assessment_html(assessment, dark=True):
    fg,muted,border=('#E6EDF5','#94A3B8','#303B4D') if dark else ('#20324b','#586981','#d6e0eb')
    green,red,amber=('#21bd87','#f05e70','#e4bf75') if dark else ('#087c56','#b4233c','#8b5e08')
    colors={'buy':green,'sell':red,'mixed':amber,'neutral':muted}
    spans=[]
    for label,v in zip(('Phiên','10 phiên','20 phiên'),assessment['values']):
        c=green if v is not None and v>0 else red if v is not None and v<0 else muted
        txt='—' if v is None else f'{v/1e9:+,.2f} tỷ' if v else '0.00 tỷ'
        spans.append(f'<span style="white-space:nowrap">{label}: <b style="color:{c}">{txt}</b></span>')
    return (f'<div style="font-size:12px;line-height:1.5;border-top:1px solid {border};margin-top:6px;padding-top:5px;color:{fg}">'
            '<div style="font-weight:800;font-size:12px">ĐÁNH GIÁ DÒNG TIỀN KHỐI NGOẠI</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:2px 12px;color:{muted}">'+''.join(spans)+'</div>'
            f'<b style="color:{colors[assessment["tone"]]}">{html.escape(assessment["title"])}</b>'
            f'<div>{html.escape(assessment["body"])}</div></div>')


def card_html(model, dark=True, *, assessment=None):
    """Compact two-row table, using the same values and coverage rules."""
    bg,tile,fg,muted,border = ('#1D2432','#252E3E','#E6EDF5','#94A3B8','#303B4D') if dark else ('#ffffff','#eef3f9','#20324b','#586981','#d6e0eb')
    period=model.get('period',10)
    def date(d): return d.strftime('%d/%m/%Y') if d is not None and pd.notna(d) else '—'
    def tone(v):
        c=_tone(v)
        return c if dark else ('#087c56' if c=='#21bd87' else '#b4233c' if c=='#f05e70' else muted)
    def row(label,vals,detail):
        vals=vals or {}; cells=[]
        for k in ('buy','sell','net'):
            v=vals.get(k+'_val'); vol=vals.get(k+'_vol')
            c=tone((1 if k=='buy' else -1) if k!='net' and (v is not None or vol is not None) else (v if v is not None else vol))
            cells.append(f'<td style="padding:5px 4px;text-align:center;background:{tile};border:1px solid {border};white-space:nowrap"><b style="font-size:15px;color:{c}">{_fmt(v,True)}</b><div style="font-size:12px;color:{c}">{_fmt(vol)} cp</div></td>')
        return f'<tr><th scope="row" style="text-align:left;padding:5px 6px;font-size:12px;color:{fg};border:1px solid {border}">{label}<div style="font-size:10px;font-weight:400;color:{muted}">{detail}</div></th>'+''.join(cells)+'</tr>'
    count=model['coverage']; days=model['dates']
    detail=f'{date(days[0])[:5]} – {date(days[-1])} · {count}/{period} phiên' if days else 'Chưa có lịch phiên khớp EOD'
    warnings=[]
    if model['today'] is None: warnings.append(f'Chưa có số liệu đúng phiên; gần nhất: {date(model["latest"])}.')
    if count!=period or len(days)!=period: warnings.append(f'Chưa đủ {period} phiên liền kề; không tính lũy kế.')
    elif any(v is None for v in model['totals'].values()): warnings.append('Chỉ tiêu thiếu dữ liệu được để trống.')
    conclusion=flow_conclusion(model); note=''
    if conclusion:
        note=(f'<div style="font-size:12px;line-height:1.45;margin-top:6px"><b style="color:{tone(conclusion["net"])}">Lũy kế: {conclusion["direction"]} · {_fmt(abs(conclusion["net"]),True)}</b>'
              f' · {conclusion["buy"]} phiên mua ròng · {conclusion["sell"]} phiên bán ròng'
              + (f' · {conclusion["flat"]} phiên cân bằng' if conclusion['flat'] else '')
              + f'<div>{conclusion["chain"]}</div></div>')
    header='<tr>'+''.join(f'<th style="text-align:{"left" if i==0 else "center"};padding:4px;color:{muted};font-size:12px">{v}</th>' for i,v in enumerate(('Khung','NN mua','NN bán','Mua/bán ròng')))+'</tr>'
    return (f'<div style="color:{fg};background:{bg};border-radius:8px;padding:6px 8px">'
            f'<div style="font-size:14px;font-weight:800;margin-bottom:3px">🌐 GIAO DỊCH KHỐI NGOẠI · {html.escape(model["code"])}</div>'
            f'<div style="overflow-x:auto"><table aria-label="Giao dịch khối ngoại" style="width:100%;min-width:420px;border-collapse:collapse">'+header
            +row('Phiên hiện tại',model['today'],date(model['day']))
            +row(f'LŨY KẾ {period} PHIÊN LIỀN KỀ',model['totals'],detail)+'</table></div>'
            + (f'<div style="font-size:11px;color:{muted};margin-top:4px">'+html.escape(' '.join(warnings))+'</div>' if warnings else '')
            +note+(assessment_html(assessment,dark) if assessment is not None else '')+'</div>')


def render(code,daily,asof,*,key,dark=True):
    """Uses existing R2 mirror, no network/provider requests and no writes."""
    import streamlit as st
    import plotly.graph_objects as go
    from foreign_stock_tab import read_verified
    try:
        # Cache by local file version; don't pin stale R2 data across syncs.
        @st.cache_data(show_spinner=False,max_entries=3)
        def _read(path, mtime_ns, size):
            return read_verified(Path(path))
        if GROSS_FILE.is_file():
            stat=GROSS_FILE.stat(); flows=_read(str(GROSS_FILE),stat.st_mtime_ns,stat.st_size)
        else: flows=pd.DataFrame()
        with st.container(border=True):
            period=st.radio('Lũy kế khối ngoại', (10,20), index=0, horizontal=True,
                            format_func=lambda n:f'{n} phiên', key=f'foreign_period_v3_{key}',
                            label_visibility='collapsed')
            sessions=calendar_sessions(daily,asof,period=20)
            m10=build_summary(flows,code,asof,sessions,period=10)
            m20=build_summary(flows,code,asof,sessions,period=20)
            m=m10 if period==10 else m20
            assessment=multi_horizon(m10,m20)
            st.markdown(card_html(m,dark=dark,assessment=assessment),unsafe_allow_html=True)
            if m['coverage']:
                dates=[d.strftime('%d/%m') for d in m['dates']]
                net=[r['net_val']/1e9 if r is not None else None for r in m['rows']]
                fig=go.Figure(go.Bar(x=dates,y=net,marker_color=[_tone(v) for v in net],hovertemplate='%{x}<br>Ròng: %{y:,.2f} tỷ<extra></extra>'))
                fig.add_hline(y=0,line_color='#8794a4',line_width=1)
                fig.update_layout(title=dict(text=f'Giá trị ròng {period} phiên · tỷ đồng',font=dict(size=12)),height=155,showlegend=False,template='plotly_dark' if dark else 'plotly_white',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',margin=dict(l=5,r=5,t=30,b=20),xaxis=dict(type='category',categoryorder='array',categoryarray=dates,tickfont=dict(size=10),tickmode='array',tickvals=dates if period==10 else dates[::2]+[dates[-1]]),yaxis=dict(tickfont=dict(size=10)))
                st.plotly_chart(fig,use_container_width=True,config={'displayModeBar':False},key=f'foreign_session_{key}_{code}')
    except Exception:
        # Optional display must not interrupt charts or signals.
        st.caption('Chưa đọc được dữ liệu khối ngoại đã xác minh; không hiển thị số liệu suy đoán.')
