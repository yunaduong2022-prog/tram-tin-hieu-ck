"""DNSE OpenAPI OHLCV for the stock chart only; no EOD/VIP writes.

Supported native intervals: 1H, 1D, 1W. Monthly = 1D DNSE resampled.
Credentials are passed only at call time and never printed or persisted.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

VN = ZoneInfo('Asia/Ho_Chi_Minh')
INDEX = {'VNINDEX', 'VN30', 'VN100', 'VNMIDCAP', 'VNSMALLCAP', 'HNXINDEX', 'UPCOMINDEX', 'HNX30'}
HISTORY_DAYS = {'1H': 185, 'D': 2200, 'W': 3700, 'M': 4400}
FIELDS = ['Mã', 'Ngày', 'Giá mở cửa', 'Giá cao nhất', 'Giá thấp nhất', 'Giá đóng cửa', 'Khối lượng khớp lệnh']

class CandleSourceError(ValueError):
    pass


def enabled(secrets) -> bool:
    try:
        cfg = secrets.get('dnse_chart', {})
        return str(cfg.get('enabled', False)).lower() == 'true'
    except Exception:
        return False


def _row_data(payload):
    """Accept list[dict] and documented time/price arrays; fail on unknown response."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError as exc:
            raise CandleSourceError('DNSE_NON_JSON_RESPONSE') from exc
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise CandleSourceError('DNSE_UNRECOGNIZED_PAYLOAD')
    # tradingview-like array contract: t/o/h/l/c/v
    aliases = [('t', 'o', 'h', 'l', 'c', 'v'), ('time', 'open', 'high', 'low', 'close', 'volume')]
    for keys in aliases:
        if all(isinstance(payload.get(k), list) for k in keys):
            lengths = {len(payload[k]) for k in keys}
            if len(lengths) != 1:
                raise CandleSourceError('DNSE_MISMATCHED_OHLC_ARRAYS')
            return [dict(zip(('time', 'open', 'high', 'low', 'close', 'volume'), values))
                    for values in zip(*(payload[k] for k in keys))]
    for key in ('data', 'result', 'candles', 'bars', 'items'):
        if key in payload:
            return _row_data(payload[key])
    if all(k in payload for k in ('time','open','high','low','close','volume')):
        return [payload]
    raise CandleSourceError('DNSE_OHLC_SHAPE_UNRECOGNIZED')


def _clock(value):
    if isinstance(value, (int, float)) or (isinstance(value, str) and re.fullmatch(r'\d{10,13}', value.strip())):
        num = float(value)
        if not 1e9 <= num <= 1e13:
            raise CandleSourceError('DNSE_TIMESTAMP_OUT_OF_RANGE')
        ts = pd.to_datetime(num, unit='ms' if num > 1e11 else 's', utc=True, errors='coerce')
        return ts.tz_convert(VN).tz_localize(None)
    s = str(value)
    dt = pd.to_datetime(s, errors='coerce')
    if pd.isna(dt):
        raise CandleSourceError('DNSE_BAD_TIMESTAMP')
    if getattr(dt, 'tzinfo', None):
        return dt.tz_convert(VN).tz_localize(None)
    # Date-only is a VN trading session label. Time-of-day without an offset
    # is ambiguous and must not be silently shifted.
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s.strip()):
        return dt
    raise CandleSourceError('DNSE_TIMEZONE_MISSING')


def normalize(payload, symbol: str, resolution: str) -> pd.DataFrame:
    rows = _row_data(payload)
    if not rows:
        raise CandleSourceError('DNSE_EMPTY_HISTORY')
    if not all(isinstance(x, dict) for x in rows):
        raise CandleSourceError('DNSE_MALFORMED_ROW')
    renames = {'time': 'Ngày', 't': 'Ngày', 'open': 'Giá mở cửa', 'o': 'Giá mở cửa',
               'high': 'Giá cao nhất', 'h': 'Giá cao nhất', 'low': 'Giá thấp nhất',
               'l': 'Giá thấp nhất', 'close': 'Giá đóng cửa', 'c': 'Giá đóng cửa',
               'volume': 'Khối lượng khớp lệnh', 'v': 'Khối lượng khớp lệnh'}
    out = pd.DataFrame(rows).rename(columns=renames)
    needed = FIELDS[1:]
    if not set(needed).issubset(out.columns):
        raise CandleSourceError('DNSE_REQUIRED_OHLCV_FIELDS_MISSING')
    out = out[needed].copy()
    out['Ngày'] = out['Ngày'].map(_clock)
    for col in needed[1:]:
        out[col] = pd.to_numeric(out[col], errors='coerce')
    if out.isna().any().any():
        raise CandleSourceError('DNSE_NULL_OR_BAD_VALUE')
    o, h, l, c = (out[k] for k in needed[1:5])
    v = out['Khối lượng khớp lệnh']
    if not ((o > 0) & (h >= o) & (h >= c) & (l <= o) & (l <= c) &
            (h >= l) & (l > 0) & (v >= 0)).all():
        raise CandleSourceError('DNSE_INVALID_OHLCV')
    out.insert(0, 'Mã', symbol)
    out = out.sort_values('Ngày').drop_duplicates('Ngày', keep='last').reset_index(drop=True)
    if resolution == 'M':
        # ONLY DNSE daily candles; no VCI or EOD substitution.
        g = out.groupby(out['Ngày'].dt.to_period('M'), sort=True)
        out = g.agg({'Mã': 'first', 'Ngày': 'last', 'Giá mở cửa': 'first',
                     'Giá cao nhất': 'max', 'Giá thấp nhất': 'min',
                     'Giá đóng cửa': 'last', 'Khối lượng khớp lệnh': 'sum'}).reset_index(drop=True)
        out['Số phiên'] = g.size().to_numpy()
    else:
        out['Số phiên'] = 1
    return out


def fetch(symbol: str, tf: str, api_key: str, api_secret: str, base_url='https://openapi.dnse.com.vn') -> pd.DataFrame:
    sym = str(symbol).strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{2,15}', sym):
        raise CandleSourceError('DNSE_INVALID_SYMBOL')
    if tf not in HISTORY_DAYS:
        raise CandleSourceError('DNSE_INVALID_TIMEFRAME')
    if not api_key or not api_secret:
        raise CandleSourceError('DNSE_CREDENTIALS_MISSING')
    if base_url != 'https://openapi.dnse.com.vn':
        raise CandleSourceError('DNSE_NONPRODUCTION_ENDPOINT_BLOCKED')
    # Import lazily: the old EOD site keeps working before SDK installation.
    try:
        from dnse import DNSEClient
    except ImportError as exc:
        raise CandleSourceError('DNSE_SDK_NOT_INSTALLED') from exc
    client = DNSEClient(api_key=api_key, api_secret=api_secret, base_url=base_url)
    now = int(time.time())
    query = {'symbol': sym, 'resolution': '1D' if tf == 'M' else ('1D' if tf == 'D' else ('1W' if tf == 'W' else '1H')),
             'from': now - HISTORY_DAYS[tf] * 86400, 'to': now}
    try:
        status, body = client.get_ohlc(bar_type='INDEX' if sym in INDEX else 'STOCK', query=query)
    except Exception as exc:
        raise CandleSourceError('DNSE_REQUEST_FAILED') from exc
    if status != 200:
        raise CandleSourceError(f'DNSE_HTTP_{status}')
    return normalize(body, sym, tf)
