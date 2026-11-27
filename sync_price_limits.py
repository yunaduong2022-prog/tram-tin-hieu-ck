"""Fetch official session limits into a separate snapshot. No EOD writes."""
import argparse,csv,json,os,sys
from pathlib import Path
from price_colors import valid_row,day_key,number
ROOT=Path(__file__).resolve().parent
FIELDS=['trading_date','symbol','exchange','reference_price','ceiling_price','floor_price','source']

def eod_day(root):
    m=json.loads((root/'data/eod_meta.json').read_text(encoding='utf-8-sig'))
    d=day_key(m.get('latest_date'))
    if not d: raise RuntimeError('EOD_DATE_MISSING')
    return d

def latest_prices(root,day):
    out={}; duplicates=set(); last=''
    meta=json.loads((root/'data/eod_meta.json').read_text(encoding='utf-8-sig'))
    failed={str(x).split(':',1)[0].strip().upper() for x in meta.get('failed',[])}
    with (root/'data/eod_prices.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            d=day_key(r.get('Ngày')); last=max(d,last)
            if d==day:
                try:
                    s=str(r['Mã']).strip().upper(); p=float(r['Giá đóng cửa'])
                    if s in out: duplicates.add(s)
                    if p>0: out[s]=p
                except (ValueError,TypeError,KeyError): pass
    if last!=day: raise RuntimeError('EOD_META_DATE_MISMATCH')
    return {s:p for s,p in out.items() if s not in duplicates and s not in failed}

def normalize(frame,day,source,prices):
    out={}; bad=set(); matched=0
    for r in frame.to_dict('records'):
        v=valid_row(r)
        if v is None or v[0]!=day: continue
        d,s,ex,ref,hi,lo=v; k=(d,s); value=(d,s,ex,ref,hi,lo,source)
        if k in out and out[k]!=value: bad.add(k)
        out[k]=value
    for k in bad: out.pop(k,None)
    for (_,s),v in out.items():
        p=prices.get(s)
        if p is not None and v[5]-1e-7<=p<=v[4]+1e-7: matched+=1
    # Fail closed for wrong date/units, partial or unrelated market response.
    if matched<max(1,int(len(prices)*.60)) or len(out)<100:
        raise RuntimeError(f'LIMIT_COVERAGE_TOO_LOW rows={len(out)} matched={matched} eod={len(prices)}')
    return out,matched

def save(root,day,source,rows,matched,prices):
    dest=root/'data/price_limits_daily.csv'; old={}
    if dest.exists():
        with dest.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                v=valid_row(r)
                if v and v[0]!=day: old[(v[0],v[1])]=(*v,r.get('source',''))
    old.update(rows); days=sorted({k[0] for k in old})[-10:]
    tmp=dest.with_suffix('.tmp')
    with tmp.open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f,lineterminator='\n');w.writerow(FIELDS);w.writerows(old[k] for k in sorted(old) if k[0] in days)
    os.replace(tmp,dest)
    print(f'PRICE_LIMITS_SYNC_OK | {day} | {source} | {matched}/{len(prices)} EOD matching | {len(rows)} limits',flush=True)
    if (day,'BSR') in rows: print('BSR_LIMITS |',rows[(day,'BSR')][3:6],flush=True)


# Direct SSI only. Public iBoard first, documented FastConnect v2 if configured.
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from datetime import datetime
from math import ceil
from price_colors import exchange

class Records:
    def __init__(self,rows): self.rows=rows
    def to_dict(self,mode): return self.rows

def ssi_date(value):
    s=str(value).strip()
    if len(s)==8 and s.isdigit():
        try: return datetime.strptime(s,'%Y%m%d').date().isoformat()
        except ValueError: return ''
    return day_key(value)

def request_json(url,params=None,body=None,token=None):
    if params: url+='?'+urlencode(params)
    headers={'Accept':'application/json','User-Agent':'Mozilla/5.0','Origin':'https://iboard.ssi.com.vn','Referer':'https://iboard.ssi.com.vn/'}
    if body is not None: headers['Content-Type']='application/json'
    if token: headers['Authorization']='Bearer '+token
    req=Request(url,headers=headers,data=json.dumps(body).encode() if body is not None else None)
    with urlopen(req,timeout=25) as resp:
        raw=resp.read(20_000_001)
        if len(raw)>20_000_000: raise RuntimeError('SSI_RESPONSE_TOO_LARGE')
        return json.loads(raw)

def api_rows(payload):
    if not isinstance(payload,dict): raise RuntimeError('SSI_RESPONSE_SCHEMA')
    status=payload.get('code',payload.get('status'))
    if str(status).upper() not in ('SUCCESS','200'): raise RuntimeError('SSI_RESPONSE_NOT_SUCCESS')
    data=payload.get('data')
    if isinstance(data,dict):
        for key in ('stockData','stocks','stockList','items','data','stockGroupData','stockInfo','stockInfos'):
            if isinstance(data.get(key),list): data=data[key];break
    if not isinstance(data,list) or not all(isinstance(r,dict) for r in data): raise RuntimeError('SSI_ROWS_SCHEMA')
    return data

def normalize_ssi_row(raw,day,market,prices,source):
    # SSI iBoard board and FastConnect daily raw prices are in VND, not thousands.
    # Never infer unit using a rounded percentage; validate exact raw close against EOD.
    r={str(k).lower():v for k,v in raw.items()}
    s=str(r.get('stocksymbol',r.get('symbol',''))).strip().upper()
    if s not in prices or ssi_date(r.get('tradingdate'))!=day: return None
    ex=exchange(r.get('exchange',r.get('market',r.get('board',market))))
    if not ex or (market!='VNALL' and ex!=market): return None
    if source=='SSI_IBOARD_PUBLIC':
        close=number(r.get('matchedprice'))
        hi,lo,ref=(number(r.get(k)) for k in ('ceiling','floor','refprice'))
    else:
        close=number(r.get('closeprice'))
        hi,lo,ref=(number(r.get(k)) for k in ('ceilingprice','floorprice','refprice'))
    if None in (close,hi,lo,ref) or abs(close/1000-prices[s])>1e-7: return None
    if not lo<=close<=hi: return None
    q=dict(trading_date=day,symbol=s,exchange=ex,reference_price=ref/1000,ceiling_price=hi/1000,floor_price=lo/1000)
    return q if valid_row(q) else None

def collect_public(day,prices):
    rows=[]
    print(f'SSI_TARGET | {day} | EOD={len(prices)}',flush=True)
    for market in ('VNALL','HOSE','HNX','UPCOM'):
        try:
            payload=request_json('https://iboard-query.ssi.com.vn/stock/group/'+market)
            if isinstance(payload,dict):
                d=payload.get('data')
                shape=','.join(sorted(map(str,d.keys()))) if isinstance(d,dict) else type(d).__name__
                print(f'SSI_PAYLOAD | {market} | data={shape}',flush=True)
            data=api_rows(payload)
            if data:
                print('SSI_SCHEMA | '+market+' | '+','.join(sorted(str(k) for k in data[0])),flush=True)
                dates=sorted({ssi_date(r.get('tradingDate',r.get('TradingDate'))) for r in data})
                print('SSI_DATES | '+market+' | '+','.join(dates[:10]),flush=True)
                for raw in data:
                    if str(raw.get('stockSymbol',raw.get('symbol',''))).upper()=='BSR':
                        keys=('stockSymbol','symbol','tradingDate','exchange','market','board','refPrice','ceiling','floor','matchedPrice')
                        print('SSI_BSR_RAW | '+json.dumps({k:raw[k] for k in keys if k in raw},ensure_ascii=True),flush=True)
                        break
            good=[q for raw in data if (q:=normalize_ssi_row(raw,day,market,prices,'SSI_IBOARD_PUBLIC')) is not None]
            rows.extend(good)
            print(f'SSI_BOARD | {market} | raw={len(data)} matched={len(good)}',flush=True)
            # Early exit only after full validation, including conflicting duplicates and BSR if applicable.
            try:
                valid,_=normalize(Records(rows),day,'SSI_IBOARD_PUBLIC',prices)
                if day=='2026-11-27' and prices.get('BSR')==24.1:
                    b=valid.get((day,'BSR'))
                    if not b or abs(b[4]-24.1)>1e-7: continue
                return Records(rows)
            except RuntimeError: pass
        except Exception as e:
            print('SSI_BOARD_FAILED | '+market+' | '+type(e).__name__+' | '+str(e)[:200],flush=True)
    return Records(rows)

def collect_fastconnect(day,prices):
    key=os.environ.get('SSI_API_KEY') or os.environ.get('SSI_CONSUMER_ID')
    secret=os.environ.get('SSI_API_SECRET') or os.environ.get('SSI_CONSUMER_SECRET')
    if not key or not secret: raise RuntimeError('SSI_FASTCONNECT_KEYS_NOT_SET')
    url='https://fc-data.ssi.com.vn/api/v2/Market/'
    auth=request_json(url+'AccessToken',body={'consumerID':key,'consumerSecret':secret})
    token=(auth.get('data') or {}).get('accessToken')
    if not token: raise RuntimeError('SSI_FASTCONNECT_AUTH_FAILED')
    dt=datetime.strptime(day,'%Y-%m-%d').strftime('%d/%m/%Y');rows=[]
    for market in ('HOSE','HNX','UPCOM'):
        for page in range(1,11):
            payload=request_json(url+'DailyStockPrice',{'market':market,'fromDate':dt,'toDate':dt,'pageIndex':page,'pageSize':1000},token=token)
            data=api_rows(payload)
            rows.extend(q for raw in data if (q:=normalize_ssi_row(raw,day,market,prices,'SSI_FASTCONNECT_DIRECT')) is not None)
            total=number(payload.get('totalRecord'))
            if total is not None and page*1000>=total: break
            if len(data)<1000 and (total is None or page*1000>=total): break
        else: raise RuntimeError('SSI_FASTCONNECT_PAGINATION_LIMIT')
    return Records(rows)

def sync(root=ROOT,day=None):
    root=Path(root);day=day or eod_day(root);prices=latest_prices(root,day)
    if not prices: raise RuntimeError('EOD_SESSION_NOT_FOUND')
    errors=[]
    for source,fetch in [('SSI_IBOARD_PUBLIC',collect_public),('SSI_FASTCONNECT_DIRECT',collect_fastconnect)]:
        try:
            frame=fetch(day,prices);rows,matched=normalize(frame,day,source,prices)
            # only rows with a matched unadjusted EOD close enter storage
            if day=='2026-11-27' and prices.get('BSR')==24.1:
                b=rows.get((day,'BSR'))
                if not b or abs(b[4]-24.1)>1e-7: raise RuntimeError('BSR_CEILING_NOT_VERIFIED')
            save(root,day,source,rows,matched,prices);return True
        except Exception as e:
            msg=type(e).__name__
            if type(e) is RuntimeError and str(e).startswith(('SSI_','LIMIT_COVERAGE_TOO_LOW','BSR_CEILING_NOT_VERIFIED')): msg+=':'+str(e)
            errors.append(source+':'+msg);print('PRICE_LIMITS_SOURCE_FAILED | '+errors[-1],flush=True)
    raise RuntimeError('SSI_LIMITS_UNAVAILABLE | '+'; '.join(errors))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--date');a=ap.parse_args()
    try: sync(day=a.date)
    except Exception as e: print(type(e).__name__+': '+str(e));sys.exit(1)
