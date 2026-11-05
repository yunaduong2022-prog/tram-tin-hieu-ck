"""Read-only KBS/VNStock intraday quote board from a private Cloudflare R2 object.

Market EOD, technical indicators, trading signals, VIP and backtests are NOT changed.
The publisher must have independently verified redistribution permissions before use.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from r2_bridge import client, config_from_mapping

TZ = ZoneInfo('Asia/Ho_Chi_Minh')
KEY_SUFFIX = '/intraday/kbs_quotes_v1.json'
MAX_BYTES = 2_000_000
MAX_QUOTES = 1200


def parse_snapshot(blob: bytes, *, now: datetime | None = None) -> tuple[pd.DataFrame, datetime]:
    """Strict data-only parser; no eval or pickle; rejects wrong units/duplicates."""
    if not isinstance(blob, bytes) or not (0 < len(blob) <= MAX_BYTES):
        raise ValueError('SNAPSHOT_SIZE_INVALID')
    p = json.loads(blob)
    if not isinstance(p, dict) or p.get('version') != 1 or p.get('source') != 'KBS/VNStock' or p.get('price_unit') != 'vnd':
        raise ValueError('SNAPSHOT_SCHEMA_INVALID')
    stamp = datetime.fromisoformat(p['fetched_at_vn'])
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(hours=7):
        raise ValueError('SNAPSHOT_TIMEZONE_INVALID')
    now = now or datetime.now(TZ)
    if stamp > now.astimezone(TZ) + timedelta(minutes=3):
        raise ValueError('SNAPSHOT_FROM_FUTURE')
    rows = p.get('quotes')
    if not isinstance(rows, list) or not (0 < len(rows) <= MAX_QUOTES):
        raise ValueError('SNAPSHOT_EMPTY_OR_TOO_LARGE')
    if p.get('total_symbols') != len(rows):
        raise ValueError('SNAPSHOT_COUNT_MISMATCH')
    out = []
    seen = set()
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError('SNAPSHOT_BAD_ROW')
        symbol = r.get('symbol')
        if not isinstance(symbol, str) or not re.fullmatch(r'[A-Z0-9]{2,9}', symbol) or symbol in seen:
            raise ValueError('SNAPSHOT_DUPLICATE_OR_INVALID_SYMBOL')
        seen.add(symbol)
        px = {}
        for k in ('price_vnd', 'reference_vnd', 'open_vnd', 'high_vnd', 'low_vnd'):
            n = r.get(k)
            if not isinstance(n, (int, float)) or isinstance(n, bool) or not math.isfinite(n) or n <= 0 or n > 2_000_000:
                raise ValueError('SNAPSHOT_PRICE_INVALID')
            px[k] = float(n)
        if not (px['low_vnd'] <= min(px['open_vnd'], px['price_vnd']) and
                px['high_vnd'] >= max(px['open_vnd'], px['price_vnd'])):
            raise ValueError('SNAPSHOT_OHLC_INVALID')
        out.append({
            'Mã': symbol,
            'Giá (nghìn)': px['price_vnd'] / 1000,
            'Tham chiếu': px['reference_vnd'] / 1000,
            '% thay đổi': (px['price_vnd'] / px['reference_vnd'] - 1) * 100,
            'Mở cửa': px['open_vnd'] / 1000,
            'Cao nhất': px['high_vnd'] / 1000,
            'Thấp nhất': px['low_vnd'] / 1000,
        })
    return pd.DataFrame(out).sort_values('Mã').reset_index(drop=True), stamp


def _read_r2_snapshot(conf: dict) -> bytes:
    s3 = client(conf)
    key = conf['prefix'] + KEY_SUFFIX
    resp = s3.get_object(Bucket=conf['bucket'], Key=key)
    payload = resp['Body'].read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError('SNAPSHOT_EXCEEDS_LIMIT')
    return payload


def render():
    st.title('Bảng giá KBS trong phiên')
    st.caption('Giá chỉ để quan sát, KHÔNG thay thế nến EOD xác nhận, dữ liệu VIP hoặc tín hiệu Backtest.')
    try:
        cfg = st.secrets.get('market_sync', {})
        # Explicit opt-in: an access token is not equivalent to distribution rights.
        if cfg.get('intraday_quotes_enabled') is not True or cfg.get('distribution_rights_confirmed') is not True:
            st.info('Bảng giá trong phiên chưa được bật. Cần xác nhận quyền dữ liệu và cấu hình R2 trong Streamlit Secrets.')
            return
        conf = config_from_mapping(st.secrets)
        if conf is None:
            st.info('Chưa có cấu hình R2 trên Streamlit Cloud.')
            return
        # Read-only, called only when this tab is opened or auto-refreshed.
        data, stamp = parse_snapshot(_read_r2_snapshot(conf))
    except Exception:
        st.warning('Chưa đọc được snapshot KBS hợp lệ từ R2. Dữ liệu EOD và các trang khác vẫn hoạt động.')
        return
    now = datetime.now(TZ)
    age = max(0, int((now - stamp).total_seconds() // 60))
    st.caption(f'Nguồn: KBS qua VNStock · Lần thu thập hoàn tất: {stamp:%d/%m/%Y %H:%M:%S} (VN) · {len(data)} mã')
    if age >= 15:
        st.warning(f'Ảnh chụp báo giá đã cũ khoảng {age} phút; không xem như giá realtime.')
    else:
        st.success(f'Có dữ liệu phiên gần đây ({age} phút trước). Thời điểm là lúc lấy dữ liệu, không phải timestamp khớp lệnh của sở.')
    c1, c2, c3 = st.columns(3)
    c1.metric('Tổng mã', str(len(data)))
    c2.metric('Mã tăng', str(int((data['% thay đổi'] > 0).sum())))
    c3.metric('Mã giảm', str(int((data['% thay đổi'] < 0).sum())))
    symbols = st.text_input('Tìm mã', placeholder='HPG, MBB, VIX...', key='kbs_r2_filter').upper().strip()
    if symbols:
        selected = {x.strip() for x in symbols.replace(';', ',').split(',') if x.strip()}
        data = data[data['Mã'].isin(selected)]
    st.dataframe(data, hide_index=True, use_container_width=True, column_config={
        'Giá (nghìn)': st.column_config.NumberColumn(format='%.2f'),
        'Tham chiếu': st.column_config.NumberColumn(format='%.2f'),
        '% thay đổi': st.column_config.NumberColumn(format='%+.2f%%'),
        'Mở cửa': st.column_config.NumberColumn(format='%.2f'),
        'Cao nhất': st.column_config.NumberColumn(format='%.2f'),
        'Thấp nhất': st.column_config.NumberColumn(format='%.2f'),
    })
    st.caption('Snapshot không chứa tổng khối lượng khớp; không dùng tính Vol/Avg10 hoặc tạo nến giả.')


if hasattr(st, 'fragment'):
    render = st.fragment(run_every='60s')(render)
