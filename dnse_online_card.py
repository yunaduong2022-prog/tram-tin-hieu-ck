"""Local research view of SSI BU/SD fields. Not a verified aggressor-side feed."""
import csv, html, os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from foreign_session_card import calendar_sessions

STATUS = 'FIELD_MEANING_UNVERIFIED'
ROOT = Path(__file__).resolve().parent

def read_record(folder, date, code):
    try:
        with (Path(folder)/f'ssi_fields_{date}.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=[r for r in csv.DictReader(f) if r.get('symbol')==code]
        if len(rows)!=1:return None
        r=rows[0]
        if r.get('date')!=date or r.get('status')!=STATUS or r.get('exchange') not in ('HOSE','HNX','UPCOM'):return None
        b,s,t,v=(int(r[k]) for k in ('ssi_bu','ssi_sd','ssi_total','eod_volume'))
        if min(b,s)<0 or not 0<t==v==b+s:return None
        def optional_int(k):
            try:
                v=int(r.get(k,''));return v if v>=0 else None
            except (ValueError,TypeError):return None
        value=optional_int('ssi_matched_value')
        if not value:value=None
        # Estimate side values by each day's volume share, preserving total turnover.
        est=(Decimal(value)*b/t,Decimal(value)*s/t) if value is not None else None
        try:
            close=Decimal(r.get('close_vnd',''))
            if not close.is_finite() or close<=0:close=None
        except (InvalidOperation,TypeError):close=None
        floor_known={'1':True,'0':False}.get(r.get('close_at_floor'))
        return dict(pair=(b,s),est=est,floor=r.get('close_at_floor')=='1',floor_offer=optional_int('floor_offer_qty'),close_vnd=close,floor_known=floor_known)
    except (OSError,ValueError,KeyError,TypeError):return None

def read_day(folder,date,code):
    r=read_record(folder,date,code)
    return r['pair'] if r else None

def build(folder, code, dates, period):
    if period not in (5,10,20):raise ValueError('BAD_PERIOD')
    dates=list(dates)[-period:]
    if dates!=sorted(set(dates)):raise ValueError('BAD_CALENDAR')
    rows=[read_day(folder,d,code) for d in dates]
    count=sum(r is not None for r in rows)
    total=tuple(sum(r[i] for r in rows) for i in (0,1)) if count==period and len(dates)==period else None
    return dict(dates=dates,rows=rows,today=rows[-1] if rows else None,total=total,count=count,period=period)

def local_path(address, value):
    if address not in ('127.0.0.1','::1','localhost') or not value:return None
    p=Path(value).expanduser().resolve()
    if p==ROOT or ROOT in p.parents or not p.is_dir():return None
    return p

def private_enabled():
    import streamlit as st
    return local_path(st.get_option('server.address'),os.getenv('SSI_ACTIVE_FLOW_PRIVATE_DIR')) is not None

def build_all(folder, code, dates):
    dates=list(dates)[-20:]
    if dates!=sorted(set(dates)):raise ValueError('BAD_CALENDAR')
    rows=[read_record(folder,d,code) for d in dates]
    models={}
    for n in (1,5,10,20):
        window=rows[-n:]; count=sum(r is not None for r in window)
        complete=count==n and len(window)==n
        total=tuple(sum(r['pair'][i] for r in window) for i in (0,1)) if complete else None
        est=tuple(sum(r['est'][i] for r in window) for i in (0,1)) if complete and all(r['est'] is not None for r in window) else None
        models[n]={'total':total,'count':count,'est':est,'floor':bool(n==1 and complete and window[-1]['floor']),'floor_offer':window[-1]['floor_offer'] if n==1 and complete else None}
    return models

def pct(pair):
    return 100*pair[0]/sum(pair) if pair is not None and sum(pair)>0 else None

def floor_assessment(volume, offer):
    # Relative queue / traded volume is a snapshot diagnostic, not a forecast.
    # Never infer a missing side, a missing offer, or absence of every buyer.
    if offer is None or volume is None or volume <= 0:
        return ('CẢNH BÁO GIÁ SÀN', 'Giá đóng cửa tại giá sàn; chưa đủ dữ liệu để đánh giá khả năng hấp thụ cung.')
    if offer >= volume and (volume < 10_000 or offer >= 10 * volume):
        detail = 'Không có lực cầu đủ mạnh tham gia đỡ giá.'
        if volume < 10_000:
            detail += ' Thanh khoản rất thấp, rủi ro giảm giá tiếp diễn.'
        else:
            detail += ' Dư bán lớn so với khối lượng đã khớp, rủi ro giảm giá tiếp diễn.'
        return ('CẢNH BÁO GIÁ SÀN – ÁP LỰC BÁN ÁP ĐẢO', detail)
    if offer >= volume:
        return ('CẢNH BÁO GIÁ SÀN – ÁP LỰC BÁN MẠNH', 'Có giao dịch khớp lệnh nhưng lượng dư bán vẫn lớn; giá chưa thoát sàn.')
    if offer > 0:
        return ('CẢNH BÁO GIÁ SÀN', 'Vẫn còn dư bán tại giá sàn; chưa xác nhận lực cầu đủ sức đỡ giá.')
    return ('CẢNH BÁO GIÁ SÀN', 'Giá đóng cửa tại giá sàn; ảnh chụp SSI ghi nhận dư bán bằng 0, chưa xác nhận giá đã thoát sàn.')

def ceiling_assessment(volume,bid):
    if bid is None or volume is None or volume<=0:
        return 'GIÁ ĐÓNG CỬA TẠI TRẦN','Chưa đủ dữ liệu dư mua để đánh giá cân bằng cung cầu.'
    if bid>=volume and (volume<10_000 or bid>=10*volume):
        return 'GIÁ TRẦN – LỰC CẦU CHỜ ÁP ĐẢO','Dư mua trần lớn so với khối lượng đã khớp; nguồn cung khớp lệnh hạn chế. Chưa xác nhận giá sẽ tiếp tục tăng.'
    if bid>=volume:
        return 'GIÁ TRẦN – DƯ MUA LỚN','Lực cầu chờ mua lớn; vẫn cần theo dõi thanh khoản và nguồn cung.'
    if bid>0:
        return 'GIÁ TRẦN – CÒN DƯ MUA','Còn lệnh chờ mua tại giá trần; chưa đủ cơ sở xác nhận lực cầu bền vững.'
    return 'GIÁ ĐÓNG CỬA TẠI TRẦN','Ảnh chụp SSI ghi nhận dư mua bằng 0; không đồng nghĩa lực cầu sẽ tiếp tục mạnh.'

def conclusion(models, price_warning=None, quote=None):
    now=pct(models[1]['total']); five=pct(models[5]['total']); ten=pct(models[10]['total']); twenty=pct(models[20]['total'])
    if quote and quote.get('floor'):
        title,detail=floor_assessment(quote.get('volume'),quote.get('offer'))
        if quote.get('offer') is not None:detail+=' Dư bán sàn: '+fmt_vol_exact(quote['offer'])+'.'
        return (title,detail,'sell')
    if quote and quote.get('ceiling') and not models[1].get('floor'):
        title,detail=ceiling_assessment(quote.get('volume'),quote.get('bid'))
        return title,detail,'ceiling'
    if now is None:
        if price_warning:return ('GIÁ CHƯA XÁC NHẬN LỰC MUA',price_warning+' Thiếu Mua/Bán CĐ.', 'sell')
        if quote and quote['volume']<10000:return ('THANH KHOẢN RẤT THẤP','Thiếu Mua/Bán CĐ; không suy đoán tỷ trọng.','neutral')
        return ('Chưa có dữ liệu đúng phiên','Không thay bằng phiên cũ.','neutral')
    today=models[1]
    if today.get('floor'):
        q=today.get('floor_offer');title,detail=floor_assessment(sum(today['total']) if today['total'] is not None else None,q)
        if q is not None:detail+=f' Dư bán mức sàn (ảnh SSI): {q:,} CP.'.replace(',','.')
        return (title,detail,'sell')
    if sum(today['total'])<10_000:
        return ('THANH KHOẢN RẤT THẤP','Khớp dưới 10.000 CP; tỷ trọng Mua/Bán CĐ không đủ để kết luận lực cầu.','neutral')
    if price_warning:return ('GIÁ CHƯA XÁC NHẬN LỰC MUA',price_warning,'sell')
    if five is None or ten is None:return ('Mua CĐ chiếm ưu thế' if now>50 else 'Bán CĐ chiếm ưu thế' if now<50 else 'Mua/Bán CĐ cân bằng','Chưa đủ lịch sử 5 và 10 phiên để đánh giá thay đổi lực mua/bán.','buy' if now>50 else 'sell' if now<50 else 'neutral')
    if now>five>ten and five>50:
        title='TỶ TRỌNG MUA CĐ NGẮN HẠN GIA TĂNG'; tone='buy'
    elif now<five<ten and five<50:
        title='TỶ TRỌNG BÁN CĐ NGẮN HẠN GIA TĂNG'; tone='sell'
    elif min(now,five,ten)>50:
        title='MUA CĐ CHIẾM ƯU THẾ ĐA KHUNG'; tone='buy'
    elif max(now,five,ten)<50:
        title='BÁN CĐ CHIẾM ƯU THẾ ĐA KHUNG'; tone='sell'
    else:
        title='MUA/BÁN CĐ CHƯA ĐỒNG THUẬN'; tone='neutral'
    desc=f'Mua CĐ phiên hiện tại {now:.2f}%, 5 phiên {five:.2f}%, 10 phiên {ten:.2f}%.'
    if twenty is not None:desc+=f' Lũy kế 20 phiên {twenty:.2f}%.'
    return title,desc.replace('.',',').replace('%,','%.'),tone

def fmt_vol(v):
    if v>=1_000_000:return f'{v/1e6:.2f}'.replace('.',',')+'M CP'
    if v>=100_000:return f'{v/1000:.1f}'.replace('.',',')+'K CP'
    return f'{v:,}'.replace(',','.')+' CP'

def fmt_vol_exact(v):
    return "—" if v is None else f"{v:,}".replace(",",".")+" CP"

def fmt_val(v):
    return '—' if v is None else '≈'+f'{v/Decimal(1_000_000_000):.2f}'.replace('.',',')+' tỷ'

def nonnegative_number(v):
    try:
        x=Decimal(str(v))
        return x if x.is_finite() and x>=0 else None
    except (InvalidOperation,TypeError,ValueError):return None


def prior_volume_ma20(daily,code,dates):
    """Require all 20 preceding sessions in the existing VNINDEX EOD calendar."""
    import pandas as pd
    try:
        if len(dates)<2:return None
        prev=[d.strftime('%Y-%m-%d') for d in calendar_sessions(daily,dates[-2],period=20)]
        if len(prev)!=20 or prev!=sorted(set(prev)) or prev[-1]!=dates[-2] or prev[-1]>=dates[-1]:return None
        own=daily.loc[daily['Mã'].astype(str).str.strip().str.upper().eq(str(code).strip().upper()),['Ngày','Khối lượng khớp lệnh']].copy()
        from foreign_session_card import _dates
        own['_day']=_dates(own['Ngày'].tolist()).dt.strftime('%Y-%m-%d').values
        own=own.loc[own['_day'].isin(prev)].sort_values('_day')
        if own['_day'].tolist()!=prev:return None
        vols=[nonnegative_number(v) for v in own['Khối lượng khớp lệnh']]
        if any(v is None or v!=v.to_integral_value() for v in vols):return None
        avg=sum(vols)/20
        return avg if avg>0 else None
    except (KeyError,TypeError,ValueError,AttributeError,ArithmeticError):return None


def queue_ratio(qty,denominator):
    q,d=nonnegative_number(qty),nonnegative_number(denominator)
    return q/d*100 if q is not None and d is not None and d>0 else None


def queue_level(pct):
    if pct is None:return None
    if pct==0:return 'Không còn dư'
    if pct<10:return 'Thấp'
    if pct<30:return 'Trung bình'
    if pct<50:return 'Khá lớn'
    if pct<100:return 'Lớn'
    if pct<=200:return 'Rất lớn'
    return 'Áp đảo'


def ratio_text(p):
    if p is None:return '—'
    if 0<p<Decimal('0.005'):return '<0,01%'
    def vn(x):return f'{x:,.2f}'.translate(str.maketrans({',':'.','.':','}))
    return vn(p)+'%'+(' ('+vn(p/100)+' lần)' if p>=100 else '')


def queue_comparison_html(qty,avg,volume,fg,muted,color):
    p=queue_ratio(qty,avg);day=queue_ratio(qty,volume)
    level=queue_level(p)
    avg_label='So với KL TB 20 phiên trước'
    avg_text=ratio_text(p)+((' · '+level) if level else ' · Chưa đủ dữ liệu')
    day_text=ratio_text(day)+(' · Chưa đủ dữ liệu' if day is None else '')
    return (f'<div class="active-queue-ratios" style="display:flex;gap:6px 18px;flex-wrap:wrap;margin:4px 0;font-size:11px;color:{muted}">'
            f'<span>{avg_label}: <b style="color:{color if p is not None else muted}">{html.escape(avg_text)}</b></span>'
            f'<span>So với KL khớp phiên: <b style="color:{color if day is not None else muted}">{html.escape(day_text)}</b></span></div>')


def dnse_flow_assessment(models, price_warning=None, quote=None):
    """Display-only assessment; shares of all G1 volume, including unknown."""
    def ratio(n):
        m=models.get(n,{})
        pair=m.get('total'); u=m.get('unknown')
        if m.get('count')!=n or pair is None or u is None:return None
        t=sum(pair)+u
        if t<=0:return None
        return (100*pair[0]/t,100*pair[1]/t,100*u/t,t)
    r={n:ratio(n) for n in (1,5,10,20)}
    missing=[str(n) for n,x in r.items() if x is None]
    detail=('Thiếu dữ liệu khung '+', '.join(missing)+' phiên. ') if missing else ''
    if any(x is not None and x[2]>=10 for x in r.values()):
        detail+='Tỷ trọng gồm phần chưa xác định chiều. '
    now=r[1]
    if now is None:return 'CHƯA ĐỦ DỮ LIỆU ĐÚNG PHIÊN',detail.strip(),'neutral'
    if now[3]<10000:
        return 'THANH KHOẢN RẤT THẤP',detail+'Khớp dưới 10.000 CP; không kết luận lực cầu mạnh.', 'warning'
    if quote and quote.get('floor'):
        return 'GIÁ SÀN – CHƯA XÁC NHẬN LỰC CẦU',detail+'Ưu tiên theo dõi khả năng hấp thụ dư bán sàn.', 'sell'
    if any(x is not None and x[2]>=10 for x in r.values()):
        return 'CÓ KHỐI LƯỢNG CHƯA XÁC ĐỊNH CHIỀU',detail+'Có khung với ít nhất 10% chưa xác định; chưa kết luận xu hướng đa khung.', 'warning'
    if missing:
        return 'CHƯA ĐỦ LỊCH SỬ ĐÁNH GIÁ ĐA KHUNG',detail.strip(),'neutral'
    a,b,c,d=(r[n] for n in (1,5,10,20))
    # Require >50% of ALL matched volume, not just known trades.
    # A 5-point difference must remain after allowing for unknown sides.
    improve=a[0]>=b[0]+b[2]+5 and b[0]>=c[0]+c[2] and b[0]>=d[0]+d[2]+5
    weaken=a[1]>=b[1]+b[2]+5 and b[1]>=c[1]+c[2] and b[1]>=d[1]+d[2]+5
    if improve and a[0]>50 and any(x[1]>50 for x in (b,c,d)):
        title='LỰC MUA CẢI THIỆN – CHƯA XÁC NHẬN ĐẢO CHIỀU';tail='Lực mua ngắn hạn cải thiện, nhưng bán vẫn chiếm ưu thế ở ít nhất một khung lũy kế.';tone='warning'
    elif weaken and a[1]>50 and any(x[0]>50 for x in (b,c,d)):
        title='LỰC BÁN GIA TĂNG – CẦN THẬN TRỌNG';tail='Áp lực bán ngắn hạn gia tăng dù vẫn có khung lũy kế mua chiếm ưu thế.';tone='warning'
    elif all(x[0]>50 for x in (a,b,c,d)):
        title='MUA CHỦ ĐỘNG CHIẾM ƯU THẾ ĐA KHUNG';tail='Tỷ trọng mua vượt 50% ở cả bốn khung.';tone='buy'
    elif all(x[1]>50 for x in (a,b,c,d)):
        title='BÁN CHỦ ĐỘNG CHIẾM ƯU THẾ ĐA KHUNG';tail='Tỷ trọng bán vượt 50% ở cả bốn khung.';tone='sell'
    else:
        title='DÒNG TIỀN CHƯA ĐỒNG THUẬN';tail='Các khung chưa cùng xác nhận ưu thế mua hoặc bán.';tone='neutral'
    if price_warning:
        tail+=' '+str(price_warning)
        if tone=='buy':title='MUA CHỦ ĐỘNG CHIẾM ƯU THẾ – GIÁ CHƯA XÁC NHẬN';tone='warning'
    return title,detail+tail+' Theo dõi khả năng duy trì trong các phiên tới.',tone

def dnse_display_pct(p):
    return '&lt;0,01%' if 0<p<0.005 else f'{p:.2f}%'.replace('.',',')


def dnse_display_value(v):
    return '—' if v is None else f'{v/Decimal(1_000_000_000):,.2f}'.translate(str.maketrans({',':'.','.':','}))+' tỷ'


def dnse_net_html(models, green, red, muted):
    """Matched value difference, not net capital inflow; no partial-window totals."""
    parts=[]
    for n in (1,5,10,20):
        m=models.get(n,{})
        label='Phiên' if n==1 else f'{n} phiên'
        net=None
        if m.get('count')==n and m.get('total') is not None and m.get('est') is not None:
            try:
                b,s=map(lambda x:Decimal(str(x)),m['est'])
                if b.is_finite() and s.is_finite() and min(b,s)>=0:net=b-s
            except (ValueError,TypeError,InvalidOperation):pass
        if net is None:color=muted;value='—'
        else:
            color=green if net>0 else red if net<0 else muted
            value=f'{net/Decimal(1000000000):+,.2f}'.translate(str.maketrans({',':'.','.':','}))+' tỷ' if net else '0,00 tỷ'
            if net and abs(net)<Decimal(5000000):value=('+' if net>0 else '−')+'&lt;0,01 tỷ'
        parts.append(f'<div style="min-width:0"><div style="font-size:11px">{label}</div><b style="color:{color};font-size:15px;font-variant-numeric:tabular-nums">{value}</b></div>')
    return '<div class="dnse-net-values" title="Giá trị khớp mua chủ động trừ bán chủ động; không gồm phần chưa xác định chiều" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,120px),1fr));gap:4px 12px;margin:5px 0 7px;color:'+muted+'">'+''.join(parts)+'</div>'

def card_html(models, dark=True, price_warning=None, quote=None, code=None, date=None, prior_ma20=None, source="SSI"):
    fg,muted,border,tile=('#edf3fa','#a0b1c7','#29384d','#273445') if dark else ('#20324b','#586981','#d6e0eb','#eef3f9')
    green,red=('#21bd87','#f05e70') if dark else ('#087c56','#b4233c')
    blocks=[]
    unknown_notes=[]
    for n in (1,5,10,20):
        m=models[n]; pair=m['total']; v=pct(pair); label='Hiện tại' if n==1 else f'Lũy kế {n} phiên'
        if source=='DNSE' and pair is not None:
            vols=(*pair,m['unknown']); vals=(*m['est'],m['unknown_val']); total=sum(vols)
            f=dnse_display_pct
            percentages=[100*x/total for x in vols]
            labels=('Mua CĐ','Bán CĐ','Chưa xác định')
            backgrounds=('#178962','#c34154','#667085')
            sides=[]
            for i,c in enumerate((green,red)):
                align='left' if i==0 else 'right'
                small_pct=' · '+f(percentages[i]) if percentages[i]<13 else ''
                sides.append(f'<div style="min-width:0;text-align:{align};color:{c};font-size:12px"><span>{labels[i]} · {fmt_vol(vols[i])}{small_pct}</span> <b style="font-size:13px">{dnse_display_value(vals[i])}</b></div>')
            meta=''.join(sides)
            if vols[2]:
                unknown_notes.append((label,vols[2],vals[2],percentages[2]))
            bar='<div style="display:flex;height:22px;border-radius:5px;overflow:hidden" aria-label="'+html.escape('; '.join(f'{l}: {p:.6f}%' for l,p in zip(labels,percentages)),quote=True)+'">'+''.join(f'<div style="width:{p:.8f}%;background:{bg};color:white;line-height:22px;text-align:center;font-weight:700;font-size:12px;overflow:hidden;white-space:nowrap">{f(p) if p>=13 else ""}</div>' for p,bg in zip(percentages,backgrounds))+'</div>'
            blocks.append(f'<div style="margin:7px 0"><b style="color:{fg};font-size:12px">{label}</b><div style="display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:4px 12px;margin:2px 0 3px">{meta}</div>{bar}</div>')
            continue
        elif v is None:
            meta=f'<span style="color:{muted}">Chưa đủ dữ liệu · {m["count"]}/{n} phiên</span>';bar=f'<div style="height:20px;background:{tile};border-radius:5px;text-align:center;color:{muted};font-size:11px;line-height:20px">—</div>'
            if n==1 and quote and source=="SSI":
                meta=f'<span style="color:{green}">Mua CĐ {fmt_vol_exact(quote.get("bu"))}</span><span style="color:{red}">Bán CĐ {fmt_vol_exact(quote.get("sd"))}</span>'
                if quote.get('value') is not None:meta+=f'<span style="color:{muted}">Tổng GT {quote["value"]/1e9:.3f} tỷ</span>'
        else:
            buy=round(v,2);sell=round(100-buy,2);est=m.get('est') or (None,None)
            f=lambda x:f'{x:.2f}%'.replace('.',',')
            meta=f'<span style="color:{green};white-space:nowrap" title="{pair[0]:,} CP">Mua CĐ {fmt_vol(pair[0])} · {fmt_val(est[0])}</span><span style="color:{red};white-space:nowrap" title="{pair[1]:,} CP">Bán CĐ {fmt_vol(pair[1])} · {fmt_val(est[1])}</span>'
            bar='<div style="display:flex;height:20px;border-radius:5px;overflow:hidden" aria-label="Mua '+f(buy)+'; bán '+f(sell)+'">'
            for value,background in ((buy,'#178962'),(sell,'#c34154')):
                bar+=f'<div style="width:{value}%;background:{background};color:white;line-height:20px;text-align:center;font-weight:700;font-size:11px;overflow:hidden;white-space:nowrap">'+(f(value) if value>=13 else '')+'</div>'
            bar+='</div>'
            if min(buy,sell)<13:
                meta+=f'<span style="color:{muted};white-space:nowrap">{f(buy)} / {f(sell)}</span>'
        blocks.append(f'<div style="margin:5px 0"><div style="display:flex;align-items:center;justify-content:space-between;gap:6px;flex-wrap:wrap;margin-bottom:3px;font-size:11px"><b style="color:{fg}">{label}</b>{meta}</div>{bar}</div>')
    if source=='DNSE' and unknown_notes:
        notes='; '.join(f'{label}: {fmt_vol_exact(q)} · {dnse_display_value(v)} · {dnse_display_pct(p)}' for label,q,v,p in unknown_notes)
        blocks.append(f'<div style="font-size:11px;color:{muted};margin:4px 0">Chưa xác định chiều — {notes}</div>')
    title,desc,tone=conclusion(models,price_warning,quote);purple='#d946ef' if dark else '#a21caf';color={'buy':green,'sell':red,'neutral':muted,'ceiling':purple}[tone]
    if source=='DNSE' and any(m.get('unknown',0) for m in models.values()) and not (quote and (quote.get('floor') or quote.get('ceiling'))) and not price_warning:
        title,desc,tone='CÓ KHỐI LƯỢNG CHƯA XÁC ĐỊNH CHIỀU','Tỷ trọng tính trên toàn bộ khối lượng khớp G1; không suy đoán chiều của phần chưa xác định.','neutral'
        color=muted
    # Presentation only: keep the validated quantity and existing conclusion logic.
    risk_line=''
    queue_qty=None
    queue_volume=None
    queue_color=red
    if title.startswith('CẢNH BÁO GIÁ SÀN'):
        if quote and quote.get('floor'):
            qty=quote.get('offer')
            suffix=' Dư bán sàn: '+fmt_vol_exact(qty)+'.' if qty is not None else ''
        else:
            qty=models[1].get('floor_offer')
            suffix=f' Dư bán mức sàn (ảnh SSI): {qty:,} CP.'.replace(',','.') if qty is not None else ''
        if suffix and desc.endswith(suffix):
            desc=desc[:-len(suffix)]
            risk_color='#ff6478' if dark else '#b4233c'
            queue_qty=qty
            queue_volume=quote.get('volume') if quote and quote.get('floor') else (sum(models[1]['total']) if models[1].get('total') is not None else None)
            queue_color=risk_color
            risk_line=(f'<div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-top:4px">'
                       f'<span style="color:{fg};font-size:11px">Dư bán sàn:</span>'
                       f'<strong class="active-floor-offer" style="color:{risk_color};font-size:20px;font-weight:800;line-height:1.2;font-variant-numeric:tabular-nums">{html.escape(fmt_vol_exact(qty))}</strong></div>')
    if tone=='ceiling' and quote and quote.get('bid') is not None:
        queue_qty=quote['bid'];queue_volume=quote.get('volume');queue_color=purple
        risk_line=(f'<div style="display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-top:4px">'
                   f'<span style="color:{fg};font-size:11px">Dư mua trần:</span>'
                   f'<strong class="active-ceiling-bid" style="color:{purple};font-size:20px;font-weight:800;line-height:1.2;font-variant-numeric:tabular-nums">{html.escape(fmt_vol_exact(quote["bid"]))}</strong></div>')
    if queue_qty is not None:
        risk_line+=queue_comparison_html(queue_qty,prior_ma20,queue_volume,fg,muted,queue_color)
    detail_color=red if title.startswith('CẢNH BÁO GIÁ SÀN') else fg
    header=(f'<div style="font-size:14px;font-weight:800;color:{fg}">DÒNG TIỀN CHỦ ĐỘNG · {html.escape(str(code))}</div>' if code else '')
    if source=='DNSE':
        header=header.replace('font-size:14px','font-size:16px')
        if date and len(str(date))==10 and str(date)[4]=='-' and str(date)[7]=='-':
            date='/'.join(reversed(str(date).split('-')))
    source_label='DNSE · G1 · GT tính từ giá khớp · Cảnh báo hàng chờ SSI' if source=='DNSE' else 'SSI · Mua/Bán CĐ tham khảo (chưa xác minh chiều BU/SD) · ≈ GT ước tính'
    assessment=''
    def finish(content):
        if source!='DNSE':return content
        bg='#111b2b' if dark else '#f5f8fc'
        return f'<div style="background:{bg};border-radius:10px;padding:10px 12px;color:{fg};font-variant-numeric:tabular-nums">{content}</div>'
    if source=='DNSE':
        at,ad,ak=dnse_flow_assessment(models,price_warning,quote)
        ac={'buy':green,'sell':red,'neutral':muted,'warning':'#efb65b' if dark else '#986000'}[ak]
        assessment=(f'<div class="dnse-flow-assessment" style="border-top:1px solid {border};padding-top:6px;margin-top:6px;font-size:11px;color:{fg}">'
                    f'<div style="font-weight:800;margin-bottom:3px">ĐÁNH GIÁ DÒNG TIỀN CHỦ ĐỘNG</div>'
                    +dnse_net_html(models,green,red,muted)+f'<b style="color:{ac}">{html.escape(at)}</b><div style="margin-top:2px">{html.escape(ad)}</div></div>')
        # Keep independent ceiling/floor warnings, including queue comparisons.
        if not (title.startswith('CẢNH BÁO GIÁ SÀN') or tone=='ceiling'):
            return finish(header+f'<div style="font-size:10px;color:{muted};margin-bottom:4px">{source_label} · {html.escape(str(date or "—"))}</div>'+''.join(blocks)+assessment)
    return finish(header+f'<div style="font-size:10px;color:{muted};margin-bottom:4px">{source_label} · {html.escape(str(date or '—'))}</div>'+''.join(blocks)+assessment+f'<div style="border-top:1px solid {border};padding-top:5px;margin-top:6px;font-size:11px;color:{fg}"><b style="color:{color}">{html.escape(title)}</b>{risk_line}<div style="margin-top:2px;color:{detail_color}">{html.escape(desc)}</div></div>')

def price_warning(daily,code,dates):
    import pandas as pd
    if len(dates)<6:return None
    g=daily.loc[daily['Mã'].astype(str).str.upper().eq(str(code).upper())].copy()
    g['_day']=pd.to_datetime(g['Ngày'],errors='coerce').dt.strftime('%Y-%m-%d')
    g=g.loc[g['_day'].isin(dates)].sort_values('_day')
    if g['_day'].tolist()!=dates:return None
    c=pd.to_numeric(g['Giá đóng cửa'],errors='coerce').tolist()
    if any(not 0<x<float('inf') for x in c):return None
    down=0
    for i in range(len(c)-1,0,-1):
        if c[i]>=c[i-1]:break
        down+=1
    r5=c[-1]/c[-6]-1
    r10=c[-1]/c[-11]-1 if len(c)>=11 else None
    if down>=3 or r5<=-.03 or (r10 is not None and r10<=-.05) or (r5<0 and r10 is not None and r10<0):
        return f'Giá giảm {down} phiên liên tiếp; biến động 5 phiên {r5:+.2%}. Mua CĐ cao không xác nhận lực cầu mạnh.' if down>=3 else f'Giá 5 phiên {r5:+.2%}; xu hướng giá chưa xác nhận lực mua.'
    return None
