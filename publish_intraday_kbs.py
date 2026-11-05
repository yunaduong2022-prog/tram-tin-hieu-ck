"""Windows-only licensed KBS quote snapshot -> private R2 object.

One-shot on demand. No GitHub push, no writes to EOD/1H/VIP files.
Existing user credentials never printed; requires R2 [market_sync] secrets.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import tomllib
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

TZ = ZoneInfo('Asia/Ho_Chi_Minh')
R2_KEY_SUFFIX = '/intraday/kbs_quotes_v1.json'
EXCLUDED = {'VNINDEX', 'VN30', 'VN100', 'VNMIDCAP', 'VNSMALLCAP'}
NUMERIC_MAP = {
    'price_vnd': 'Giá đóng cửa',
    'reference_vnd': 'reference_price',
    'open_vnd': 'Giá mở cửa',
    'high_vnd': 'Giá cao nhất',
    'low_vnd': 'Giá thấp nhất',
}


def symbols_from_eod(path: Path) -> tuple[list[str], dict[str, float]]:
    # First column is the symbol (Mã), avoids legacy PowerShell stdin encoding.
    df = pd.read_csv(path, encoding='utf-8-sig', dtype=str)
    if not len(df.columns) or df.columns[0] != 'Mã' or 'Giá đóng cửa' not in df or 'Ngày' not in df:
        raise ValueError('EOD_SCHEMA_MISMATCH')
    s = df.iloc[:, 0].fillna('').astype(str).str.strip().str.upper()
    dt = pd.to_datetime(df['Ngày'], format='%d/%m/%Y', errors='coerce')
    closes = pd.to_numeric(df['Giá đóng cửa'], errors='coerce')
    ordered = pd.DataFrame({'symbol': s, 'day': dt, 'close': closes}).dropna()
    ordered = ordered.sort_values(['symbol', 'day']).drop_duplicates('symbol', keep='last')
    known = {row.symbol: float(row.close) for row in ordered.itertuples(index=False)}
    symbols = sorted({x for x in s if re.fullmatch(r'[A-Z0-9]{2,9}', x) and x not in EXCLUDED})
    if not symbols:
        raise ValueError('NO_STOCKS_IN_EOD')
    return symbols, known


def build_snapshot(quotes: pd.DataFrame, expected_symbols: list[str], eod_closes: dict[str, float], *, captured_at=None) -> dict:
    if quotes is None or quotes.empty:
        raise ValueError('KBS_QUOTES_EMPTY')
    if not {'symbol', 'source', *NUMERIC_MAP.values()}.issubset(quotes.columns):
        raise ValueError('KBS_COLUMNS_MISSING')
    if not quotes['source'].astype(str).eq('KBS').all():
        raise ValueError('ONLY_KBS_PRICE_UNIT_VERIFIED')
    rows = []
    want = set(expected_symbols)
    got = set()
    for r in quotes.to_dict('records'):
        sym = str(r['symbol']).strip().upper()
        if sym not in want or sym in got:
            raise ValueError('QUOTE_SYMBOL_MISSING_OR_DUPLICATE')
        got.add(sym)
        item = {'symbol': sym}
        for key, source_key in NUMERIC_MAP.items():
            p = float(r[source_key])
            if not math.isfinite(p) or p <= 0 or p > 2_000_000:
                raise ValueError('INVALID_QUOTE_PRICE')
            item[key] = p
        if not item['low_vnd'] <= min(item['open_vnd'], item['price_vnd']) or not item['high_vnd'] >= max(item['open_vnd'], item['price_vnd']):
            raise ValueError('INVALID_KBS_OHLC')
        historical = eod_closes.get(sym)
        if historical is None or not (0.5 <= (item['price_vnd'] / 1000) / historical <= 2.0):
            # Prevent accidentally showing 21,500 VND as 21,500k VND.
            raise ValueError('PRICE_UNIT_MISMATCH_WITH_EOD')
        rows.append(item)
    if got != want:
        raise ValueError('INCOMPLETE_QUOTE_UNIVERSE')
    stamp = captured_at or datetime.now(TZ)
    if stamp.tzinfo is None:
        raise ValueError('NAIVE_CAPTURE_TIME')
    return {'version': 1, 'source': 'KBS/VNStock', 'price_unit': 'vnd',
            'fetched_at_vn': stamp.astimezone(TZ).isoformat(timespec='seconds'),
            'total_symbols': len(rows), 'quotes': sorted(rows, key=lambda r: r['symbol'])}


def fetch_kbs_all(symbols: list[str]) -> pd.DataFrame:
    from realtime_data import fetch_quote_board
    frames = []
    for n, i in enumerate(range(0, len(symbols), 20), start=1):
        batch = symbols[i:i+20]
        df, source = fetch_quote_board(batch)
        if source != 'KBS':
            raise ValueError('KBS_UNAVAILABLE_BATCH_' + str(n))
        if df is None or len(df) != len(batch) or 'Mã' not in df.columns:
            raise ValueError('INCOMPLETE_KBS_BATCH_' + str(n))
        part = df.rename(columns={'Mã': 'symbol'}).copy()
        part['source'] = source
        frames.append(part)
        print(f'BATCH {n}: {len(part)}/{len(batch)} KBS')
    return pd.concat(frames, ignore_index=True)


def config_from_file(path: Path):
    if not path.is_file():
        raise FileNotFoundError('R2_CONFIG_FILE_MISSING')
    with path.open('rb') as f:
        raw = tomllib.load(f)
    from r2_bridge import config_from_mapping
    sect = raw.get('market_sync', {})
    if sect.get('distribution_rights_confirmed') is not True:
        raise PermissionError('DATA_DISTRIBUTION_RIGHTS_NOT_CONFIRMED')
    if sect.get('intraday_quotes_enabled') is not True:
        raise PermissionError('INTRADAY_CLOUD_DISABLED')
    conf = config_from_mapping(raw)
    if conf is None:
        raise ValueError('MARKET_SYNC_CONFIG_MISSING')
    return conf


def publish(conf, payload):
    from r2_bridge import client
    from botocore.exceptions import ClientError
    s3 = client(conf)
    key = conf['prefix'] + R2_KEY_SUFFIX
    # Refuse a conflicting newer remote object. Absence is a normal first upload.
    try:
        remote = s3.get_object(Bucket=conf['bucket'], Key=key)
        previous = json.loads(remote['Body'].read(2_000_001))
        prev_time = datetime.fromisoformat(previous['fetched_at_vn'])
        new_time = datetime.fromisoformat(payload['fetched_at_vn'])
        if prev_time.tzinfo is None or prev_time > new_time:
            raise ValueError('REMOTE_SNAPSHOT_NEWER_OR_INVALID')
    except ClientError as exc:
        code = str(exc.response.get('Error', {}).get('Code', ''))
        if code not in ('404', 'NoSuchKey', 'NotFound'):
            raise RuntimeError('R2_READ_PERMISSION_OR_NETWORK_ERROR') from None
    content = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(content) > 2_000_000:
        raise ValueError('SNAPSHOT_TOO_LARGE')
    s3.put_object(Bucket=conf['bucket'], Key=key, Body=content,
                  ContentType='application/json', CacheControl='no-store')
    return {'status': 'R2_SNAPSHOT_PUBLISHED', 'quotes': payload['total_symbols'], 'at': payload['fetched_at_vn']}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default=str(Path(__file__).resolve().parent))
    ap.add_argument('--config', default='')
    ap.add_argument('--dry-run', action='store_true', help='Check fetching/format, NEVER upload')
    ap.add_argument('--loop-minutes', type=int, default=0, help='Repeat periodically while Vietnam market is active; 0=once')
    args = ap.parse_args(argv)
    root = Path(args.repo).resolve()
    config_path = Path(args.config).expanduser() if args.config else Path.home() / '.streamlit' / 'secrets.toml'
    sys.path.insert(0, str(root))
    if not args.dry_run:
        # Fail closed before collecting any market quote if permissions are unverified.
        conf = config_from_file(config_path)
    if args.loop_minutes and not (5 <= args.loop_minutes <= 60):
        raise ValueError('LOOP_MINUTES_MUST_BE_5_TO_60')
    symbols, eod = symbols_from_eod(root / 'data/eod_prices.csv')
    print('EXPECTED_SYMBOLS:', len(symbols), flush=True)

    def one_cycle():
        # Code loaded from user's local repo; Cloud never calls VNStock.
        df = fetch_kbs_all(symbols)
        payload = build_snapshot(df, symbols, eod)
        print('CAPTURED_AT_VN:', payload['fetched_at_vn'], flush=True)
        print('VALIDATED_QUOTES:', payload['total_symbols'], flush=True)
        if args.dry_run:
            print('DRY_RUN_OK | NO_UPLOAD | NO_EOD_CHANGE | NO_GIT', flush=True)
        else:
            print(publish(conf, payload)['status'], flush=True)

    if not args.loop_minutes:
        one_cycle()
        return
    print('AUTO_PUBLISH_ENABLED: Ctrl+C to stop | weekdays only | no holiday calendar',flush=True)
    while True:
        n = datetime.now(TZ)
        # Includes 11:30 snapshot once after morning trading closes.
        active = n.weekday() < 5 and ((9, 0) <= (n.hour, n.minute) <= (11, 35) or
                                       (13, 0) <= (n.hour, n.minute) <= (15, 0))
        if active:
            try:
                one_cycle()
            except Exception as exc:
                print('CYCLE_BLOCK:',type(exc).__name__,flush=True)
        time.sleep(args.loop_minutes * 60)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        # Do not leak full botocore exceptions, signed URLs or credentials.
        print('BLOCK:', type(e).__name__, str(e) if isinstance(e, (ValueError, FileNotFoundError, PermissionError)) else 'SEE_R2_CONFIGURATION')
        raise SystemExit(1)
