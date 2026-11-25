"""Personal bank chart P/B references; no scoring or recommendation changes."""
import csv
import math
from pathlib import Path

REFERENCE_PATH = Path(__file__).resolve().parent / 'data' / 'bank_pb_reference.csv'

def positive(v):
    try:
        if isinstance(v,bool): return None
        n=float(v)
        return n if math.isfinite(n) and n>0 else None
    except (ValueError,TypeError,OverflowError):
        return None

def reference_for(symbol, path=None):
    try:
        with Path(path or REFERENCE_PATH).open(encoding='utf-8-sig',newline='') as f:
            matches=[r for r in csv.DictReader(f) if r.get('symbol')==symbol]
        if len(matches)!=1: return None,None
        row=matches[0]
        return positive(row.get('pb_avg3')), row.get('reference_date')
    except (OSError,ValueError,csv.Error):
        return None,None

def sector_pb(rows, current, prices, score_fn):
    """Aggregate market cap / aggregate candidate book equity, same quarter and price day."""
    if not rows or not current or not current.get('Phiên giá') or not positive(current.get('P/B ứng viên')):
        return None,0
    total_cap=total_book=0.0
    count=0
    for symbol,row in rows.items():
        if row.get('period_end') != current.get('Kỳ'): continue
        peer=score_fn(row,*prices.get(symbol,(None,None,False)))
        if peer.get('Phiên giá')!=current['Phiên giá']: continue
        pb=positive(peer.get('P/B ứng viên'))
        shares=positive(row.get('shares'))
        bvps=positive(row.get('bvps'))
        if pb is None or shares is None or bvps is None: continue
        book=shares*bvps
        cap=pb*book
        if not math.isfinite(book) or not math.isfinite(cap): continue
        total_book+=book; total_cap+=cap; count+=1
    if count<2 or not math.isfinite(total_book) or not math.isfinite(total_cap) or total_book<=0:
        return None,count
    return positive(total_cap/total_book),count

def fmt(v):
    return f'{v:.2f}'.replace('.',',')+'x'

def comparison(current, baseline, name):
    current,baseline=positive(current),positive(baseline)
    if current is None or baseline is None: return f'{name}: chưa có dữ liệu'
    delta=(current/baseline-1)*100
    if abs(delta)<0.05: return f'Ngang {name} ({fmt(baseline)})'
    amount=f'{abs(delta):.1f}'.replace('.',',')+'%'
    direction='Cao hơn' if delta>0 else 'Thấp hơn'
    return f'{direction} {name} {amount} ({fmt(baseline)})'

def chart_notes(rows,current,prices,score_fn,reference_path=None):
    pb=positive(current.get('P/B ứng viên')) if current else None
    if pb is None: return None,None
    hist,asof=reference_for(current.get('Mã'),reference_path)
    industry,count=sector_pb(rows,current,prices,score_fn)
    text=comparison(pb,hist,'TB 3 năm')+' | '+comparison(pb,industry,'TB ngành Ngân hàng')
    if industry is not None and count!=28: text+=f' ({count} mã)'
    detail=('P/B TB 3 năm: mốc ảnh bạn cung cấp '+str(asof or 'chưa có')+'; cập nhật khi có mốc mới. '
            'P/B ngành: tổng vốn hóa / tổng vốn chủ ước tính, cùng kỳ BCTC và phiên EOD'
            + (f' ({count} mã)' if industry is not None else ' (chưa đủ dữ liệu)')
            + '. P/B thấp hơn mốc tham chiếu không tự khẳng định cổ phiếu rẻ.')
    return text,detail
