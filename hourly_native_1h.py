"""Read only the 1H OHLCV provided natively by VCI/VNStock.

Do NOT aggregate 15-minute candles or substitute daily prices. The public
Streamlit process reads this file only; VNStock runs on a registered Windows PC.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

FILE = Path('data/hourly_native_1h.csv')
COLUMNS = ['Mã', 'Ngày', 'Giá mở cửa', 'Giá cao nhất', 'Giá thấp nhất',
           'Giá đóng cửa', 'Khối lượng khớp lệnh', 'source', 'interval']
PRICE_COLS = ['Giá mở cửa', 'Giá cao nhất', 'Giá thấp nhất', 'Giá đóng cửa']
TRADING_HOURS = {9, 10, 11, 13, 14}


def validate_store(data: pd.DataFrame) -> pd.DataFrame:
    """Fail closed on malformed data; times remain Asia/Ho_Chi_Minh timestamps."""
    if not set(COLUMNS).issubset(data.columns):
        raise ValueError('NATIVE_1H_REQUIRED_COLUMNS_MISSING')
    if data.empty:
        return pd.DataFrame(columns=COLUMNS)
    d = data[COLUMNS].copy()
    d['Mã'] = d['Mã'].astype(str).str.strip().str.upper()
    # Require explicit timezone offsets. Never guess UTC vs Vietnam wall time.
    stamps = d['Ngày'].astype(str).str.strip()
    if not stamps.str.contains(r'(?:Z|[+-]\d{2}:?\d{2})$', case=False, regex=True).all():
        raise ValueError('NATIVE_1H_TIMEZONE_REQUIRED')
    ts = pd.to_datetime(stamps, errors='coerce', utc=True)
    if ts.isna().any():
        raise ValueError('NATIVE_1H_INVALID_TIME')
    vn = ts.dt.tz_convert('Asia/Ho_Chi_Minh')
    if not (vn.dt.hour.isin(TRADING_HOURS) & vn.dt.minute.eq(0) & vn.dt.second.eq(0) & (vn.dt.weekday < 5)).all():
        raise ValueError('NATIVE_1H_EXCHANGE_CLOCK_INVALID')
    d['Ngày'] = vn.dt.strftime('%Y-%m-%dT%H:%M:%S%z')
    for col in PRICE_COLS + ['Khối lượng khớp lệnh']:
        d[col] = pd.to_numeric(d[col], errors='coerce')
    if d[PRICE_COLS + ['Khối lượng khớp lệnh']].isna().any().any():
        raise ValueError('NATIVE_1H_NON_NUMERIC_VALUE')
    if not ((d[PRICE_COLS] > 0).all(axis=1)
            & (d['Giá cao nhất'] >= d[PRICE_COLS].max(axis=1))
            & (d['Giá thấp nhất'] <= d[PRICE_COLS].min(axis=1))
            & (d['Khối lượng khớp lệnh'] >= 0)).all():
        raise ValueError('NATIVE_1H_OHLCV_INVALID')
    if not (d['source'].astype(str).str.lower().eq('vci')
            & d['interval'].astype(str).eq('1H')).all():
        raise ValueError('NATIVE_1H_SOURCE_OR_INTERVAL_MISMATCH')
    if (d['Mã'].eq('') | d['Mã'].eq('NAN')).any():
        raise ValueError('NATIVE_1H_INVALID_SYMBOL')
    if d.duplicated(['Mã', 'Ngày']).any():
        raise ValueError('NATIVE_1H_DUPLICATE_CANDLE')
    return d.sort_values(['Mã', 'Ngày']).reset_index(drop=True)


def read_symbol(path, code: str) -> pd.DataFrame:
    """Return historical hourly OHLCV in the same shape as app.engine expects."""
    p = Path(path)
    result_columns = ['Mã', 'Ngày'] + PRICE_COLS + ['Khối lượng khớp lệnh']
    if not p.is_file():
        return pd.DataFrame(columns=result_columns)
    raw = pd.read_csv(p, dtype={'Mã': str}, encoding='utf-8-sig', low_memory=False)
    raw = validate_store(raw)
    chosen = raw.loc[raw['Mã'].eq(str(code).strip().upper()), result_columns].copy()
    if chosen.empty:
        return chosen
    chosen['Ngày'] = (pd.to_datetime(chosen['Ngày'], utc=True)
                     .dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None))
    # Consistent engine input; all indicator computations use 1H source bars.
    return chosen.sort_values('Ngày').reset_index(drop=True)
