"""Read-only CafeF row-level sanity checks; no correction or imputation."""
from pathlib import Path
import pandas as pd
import numpy as np


def read_prices(path):
    d=pd.read_csv(path,encoding='utf-8-sig',usecols=['Mã','Ngày','Giá đóng cửa'])
    d=d.rename(columns={'Mã':'symbol','Ngày':'date','Giá đóng cửa':'close'})
    d['symbol']=d.symbol.astype(str).str.strip().str.upper()
    d['date']=pd.to_datetime(d.date,format='mixed',dayfirst=True,errors='coerce').dt.normalize()
    d['close']=pd.to_numeric(d.close,errors='coerce')
    d=d[d.date.notna() & d.close.gt(0) & np.isfinite(d.close)].copy()
    d.loc[d.close.lt(1000),'close'] *= 1000
    # Ambiguous duplicate closes cannot be used as a reference.
    d=d.drop_duplicates(['symbol','date','close'])
    return d.drop_duplicates(['symbol','date'],keep=False)


def audit(data, prices):
    d=data.copy()
    if 'date' not in d: d['date']=pd.to_datetime(d.trading_date,format='%Y-%m-%d',errors='coerce')
    d=d.merge(prices[['symbol','date','close']],on=['symbol','date'],how='left',validate='many_to_one')
    cafef=d.data_source.astype(str).str.startswith('CAFEF_')
    reasons=pd.Series('',index=d.index,dtype='object')
    def flag(mask,reason):
        mask=mask & cafef
        reasons.loc[mask]=reasons.loc[mask].map(lambda x: (x+'; ' if x else '')+reason)
    flag(d.close.isna(),'Thiếu giá EOD')
    for side,label in [('buy','mua'),('sell','bán')]:
        vol=pd.to_numeric(d[side+'_vol'],errors='coerce')
        val=pd.to_numeric(d[side+'_val'],errors='coerce')
        ratio=val.div(vol.where(vol.gt(0))).div(d.close)
        d[side+'_ratio']=ratio
        flag(~np.isfinite(vol)|~np.isfinite(val)|vol.lt(0)|val.lt(0),'Thiếu hoặc sai số liệu '+label)
        flag((vol.eq(0)&val.ne(0))|(vol.gt(0)&val.le(0)),'Giá trị/KL không khớp '+label)
        flag(vol.gt(0)&d.close.notna()&~ratio.between(.7,1.3),'Giá bình quân bất thường '+label)
    flag((d.buy_val-d.sell_val-d.net_val).abs().gt(1),'Sai đối chiếu giá trị ròng')
    flag((d.buy_vol-d.sell_vol-d.net_vol).abs().gt(1),'Sai đối chiếu KL ròng')
    d['quality_reason']=reasons
    return d.loc[reasons.eq('')].copy(),d.loc[reasons.ne('')].copy()
