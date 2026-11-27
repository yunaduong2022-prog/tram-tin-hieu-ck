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


def calendar_sessions(daily, asof, path=CALENDAR_FILE):
    """Use the VNINDEX calendar, not a ticker's last ten observations."""
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
    return sessions[-10:] if sessions and sessions[-1] == end else []


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


def build_summary(flows, code, asof, sessions):
    """Exact day, exact ten sessions. Unknown values stay unknown, never zero."""
    end = _dates([asof]).iloc[0]
    code = str(code).strip().upper()
    dates = sorted(set(_dates(sessions).dropna())) if sessions is not None else []
    dates = [d for d in dates if pd.notna(end) and d<=end][-10:]
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
    if len(dates)==10 and present==10:
        for k in FIELDS:
            vals=[r[k] for r in rows]
            if all(v is not None for v in vals): totals[k]=sum(vals)
    return dict(code=code,day=end,today=today,dates=dates,rows=rows,coverage=present,totals=totals,
                latest=max(by_day) if by_day else None)



def flow_conclusion(model):
    """Describe observed net flow only; do not imply a trade signal."""
    if len(model['dates']) != 10 or model['coverage'] != 10:
        return None
    vals = [r['net_val'] for r in model['rows']]
    buy = sum(v > 0 for v in vals)
    sell = sum(v < 0 for v in vals)
    flat = 10 - buy - sell
    last_sign = (vals[-1] > 0) - (vals[-1] < 0)
    streak = 0
    if last_sign:
        for v in reversed(vals):
            if (v > 0) - (v < 0) != last_sign:
                break
            streak += 1
    net = model['totals']['net_val']
    direction = 'Mua ròng' if net > 0 else 'Bán ròng' if net < 0 else 'Cân bằng'
    chain = (('Mua ròng' if last_sign > 0 else 'Bán ròng') + f' {streak} phiên liên tiếp (trong 10 phiên)' if last_sign else 'Phiên cuối cân bằng')
    return dict(buy=buy,sell=sell,flat=flat,streak=streak,net=net,direction=direction,chain=chain)


def _fmt(v, value=False):
    if v is None: return '—'
    if value: return f'{v/1e9:,.2f} tỷ'
    return f'{v:,.0f}'


def _tone(v):
    return '#21bd87' if v is not None and v>0 else '#f05e70' if v is not None and v<0 else '#a4adb9'


def card_html(model, dark=True):
    bg, tile, fg, muted, border = ('#111b2b','#1c293a','#edf3fa','#a0b1c7','#29384d') if dark else ('#ffffff','#eef3f9','#20324b','#586981','#d6e0eb')
    e=html.escape
    def date(d): return d.strftime('%d/%m/%Y') if d is not None and pd.notna(d) else '—'
    def tiles(vals):
        vals=vals or {}
        items=[]
        for k,label in [('buy','NN mua'),('sell','NN bán'),('net','Mua/bán ròng')]:
            v=vals.get(k+'_val'); vol=vals.get(k+'_vol')
            c=('#21bd87' if k=='buy' else '#f05e70') if k!='net' and (v is not None or vol is not None) else _tone(v if v is not None else vol)
            if not dark: c='#087c56' if c=='#21bd87' else '#b4233c' if c=='#f05e70' else muted
            if k=='net' and v is not None: label='Mua ròng' if v>0 else 'Bán ròng' if v<0 else 'Ròng cân bằng'
            items.append(f'<div style="min-width:0;background:{tile};border-radius:8px;padding:9px 4px;text-align:center;overflow-wrap:anywhere"><div style="font-size:12px;color:{muted}">{label}</div><div style="font-size:16px;font-weight:800;color:{c};margin:5px 0">{_fmt(vol)}</div><div style="font-size:12px;color:{fg}">{_fmt(v,True)}</div></div>')
        return '<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px">'+''.join(items)+'</div>'
    top=f'<div style="font-size:11px;color:{muted};margin:0 0 8px">Phiên {date(model["day"])}</div>'
    if model['today'] is None:
        top+=f'<div style="color:{muted};font-size:12px;margin-bottom:8px">Chưa có số liệu đúng phiên. Gần nhất có dữ liệu: {date(model["latest"])}</div>'
    count=model['coverage']; days=model['dates']
    detail=(f'{date(days[0])} – {date(days[-1])} · {count}/10 phiên có dữ liệu' if days else 'Chưa có lịch phiên VN-Index khớp EOD')
    warning= '' if count==10 and len(days)==10 else f'<div style="font-size:11px;color:{muted};margin-top:7px">Chưa đủ 10 phiên liền kề; không tính lũy kế.</div>'
    if count==10 and any(v is None for v in model['totals'].values()):
        warning=f'<div style="font-size:11px;color:{muted};margin-top:7px">Chỉ tiêu thiếu dữ liệu được để trống.</div>'
    conclusion=flow_conclusion(model)
    note=''
    if conclusion:
        c=_tone(conclusion['net']) if dark else ('#087c56' if conclusion['net']>0 else '#b4233c' if conclusion['net']<0 else muted)
        note=(f'<div style="font-size:12px;line-height:1.6;border-top:1px solid {border};margin-top:10px;padding-top:8px">'
              f'<b style="color:{c}">Lũy kế: {conclusion["direction"]} · {_fmt(abs(conclusion["net"]),True)}</b>'
              f'<div>{conclusion["buy"]} phiên mua ròng · {conclusion["sell"]} phiên bán ròng'
              + (f' · {conclusion["flat"]} phiên cân bằng' if conclusion['flat'] else '')
              + f'</div><div>{conclusion["chain"]}</div></div>')
    return (f'<div style="background:{bg};border:1px solid {border};border-radius:13px;padding:13px;margin:0 0 10px;color:{fg}">'
            f'<div style="font-weight:800;font-size:14px;margin-bottom:5px">🌐 GIAO DỊCH KHỐI NGOẠI · {e(model["code"])}</div>'+top+tiles(model['today'])+
            f'<div style="border-top:1px solid {border};margin:12px 0 8px;padding-top:10px;font-weight:800;font-size:13px">LŨY KẾ 10 PHIÊN LIỀN KỀ</div>'
            f'<div style="font-size:11px;color:{muted};margin-bottom:7px">{detail}</div>'+tiles(model['totals'])+warning+note+'</div>')


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
        sessions=calendar_sessions(daily,asof)
        m=build_summary(flows,code,asof,sessions)
        st.markdown(card_html(m,dark=dark),unsafe_allow_html=True)
        if m['coverage']:
            dates=[d.strftime('%d/%m') for d in m['dates']]
            net=[r['net_val']/1e9 if r is not None else None for r in m['rows']]
            fig=go.Figure(go.Bar(x=dates,y=net,marker_color=[_tone(v) for v in net],hovertemplate='%{x}<br>Ròng: %{y:,.2f} tỷ<extra></extra>'))
            fig.add_hline(y=0,line_color='#8794a4',line_width=1)
            fig.update_layout(title=dict(text='Giá trị ròng từng phiên · tỷ đồng',font=dict(size=12)),height=175,showlegend=False,template='plotly_dark' if dark else 'plotly_white',paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)',margin=dict(l=5,r=5,t=30,b=20),xaxis=dict(type='category',categoryorder='array',categoryarray=dates,tickfont=dict(size=10)),yaxis=dict(tickfont=dict(size=10)))
            st.plotly_chart(fig,use_container_width=True,config={'displayModeBar':False},key=f'foreign_session_{key}_{code}')
    except Exception:
        # Optional display must not interrupt charts or signals.
        st.caption('Chưa đọc được dữ liệu khối ngoại đã xác minh; không hiển thị số liệu suy đoán.')
