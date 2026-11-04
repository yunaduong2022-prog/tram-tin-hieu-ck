"""Windows-only, resumable direct VCI 1H collector for every EOD symbol.

No 15m resampling, no DNSE snapshots, no changes to EOD/portfolio/VIP. The
result is local-only pending confirmed market-data redistribution rights.
Example: python update_native_1h.py --max-symbols 40
Rerun until REMAINING is zero; then publish to private R2 only if licensed.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import hourly_native_1h as NH

TZ = ZoneInfo('Asia/Ho_Chi_Minh')
STATE = Path('data/.native_hourly_1h_state.json')
EOD = Path('data/eod_prices.csv')


def _atomic_csv(df, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.native_1h_', suffix='.csv', dir=path.parent)
    os.close(fd)
    try:
        df.to_csv(tmp, index=False, encoding='utf-8')
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _atomic_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.native_1h_state_', suffix='.json', dir=STATE.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _read_state():
    try:
        data = json.loads(STATE.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _target_closed_bucket(now: datetime):
    """Latest completed VCI hourly bucket, incl. VN lunch and ATC schedule."""
    slots = ((14, 15, 0), (13, 14, 0), (11, 11, 30),
             (10, 11, 0), (9, 10, 0))
    if now.weekday() < 5:
        for opened, close_hour, close_minute in slots:
            if (now.hour, now.minute) >= (close_hour, close_minute):
                return now.replace(hour=opened, minute=0, second=0, microsecond=0)
    prior = now.date() - timedelta(days=1)
    while prior.weekday() >= 5:
        prior -= timedelta(days=1)
    return datetime(prior.year, prior.month, prior.day, 14, tzinfo=TZ)


def _source_rows(market, symbol: str, length: str, now: datetime):
    if symbol in {'VNINDEX', 'VN30', 'HNXINDEX', 'UPCOMINDEX'}:
        source = market.index(symbol)
    else:
        source = market.equity(symbol)
    fetched = source.ohlcv(length=length, interval='1H', source='vci')
    if fetched is None or fetched.empty:
        raise ValueError('PROVIDER_EMPTY')
    attrs = getattr(fetched, 'attrs', {}) or {}
    if attrs.get('source') != 'vci' or attrs.get('interval') != '1H':
        raise ValueError('PROVIDER_NOT_DIRECT_VCI_1H')
    fields = ['time', 'open', 'high', 'low', 'close', 'volume']
    if not set(fields).issubset(fetched.columns):
        raise ValueError('PROVIDER_COLUMNS_MISSING')
    time_col = fetched['time']
    if isinstance(time_col.dtype, pd.DatetimeTZDtype):
        pass
    elif not time_col.astype(str).str.contains(r'(?:Z|[+-]\d{2}:?\d{2})$', case=False, regex=True).all():
        raise ValueError('PROVIDER_EXPLICIT_TIMEZONE_REQUIRED')
    date = pd.to_datetime(time_col, utc=True, errors='coerce')
    if date.isna().any():
        raise ValueError('PROVIDER_TIMESTAMP_INVALID')
    vietnam = date.dt.tz_convert('Asia/Ho_Chi_Minh')
    out = pd.DataFrame({
        'Mã': symbol,
        'Ngày': vietnam.dt.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'Giá mở cửa': fetched['open'].to_numpy(),
        'Giá cao nhất': fetched['high'].to_numpy(),
        'Giá thấp nhất': fetched['low'].to_numpy(),
        'Giá đóng cửa': fetched['close'].to_numpy(),
        'Khối lượng khớp lệnh': fetched['volume'].to_numpy(),
        'source': 'vci', 'interval': '1H',
    })
    # Provider timestamps represent hour-bucket START. Keep only finished bars,
    # including the special short bucket 11:00-11:30 on Vietnam exchanges.
    end_hour = {9: (10, 0), 10: (11, 0), 11: (11, 30),
                13: (14, 0), 14: (15, 0)}
    completed = []
    for ts in vietnam:
        pair = end_hour.get(ts.hour)
        if pair is None:
            completed.append(False)
            continue
        end = ts.to_pydatetime().replace(hour=pair[0], minute=pair[1], second=0, microsecond=0)
        completed.append(end <= now)
    out = out.loc[completed]
    if out.empty:
        raise ValueError('NO_COMPLETED_1H_BAR')
    return NH.validate_store(out)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--max-symbols', type=int, default=40)
    cli.add_argument('--length', default='120d', help='Initial backfill window (calendar days)')
    cli.add_argument('--incremental-length', default='10d')
    cli.add_argument('--sleep', type=float, default=1.25)
    cli.add_argument('--checkpoint-every', type=int, default=10)
    cli.add_argument('--retry-failed', action='store_true')
    args = cli.parse_args()
    if not 1 <= args.max_symbols <= 80 or not 0.5 <= args.sleep <= 20:
        raise ValueError('SAFE_LIMITS_INVALID')
    if not EOD.is_file():
        raise FileNotFoundError('Missing data/eod_prices.csv; run on the GitHub clone with EOD history')
    symbols = sorted(set(pd.read_csv(EOD, usecols=['Mã'], dtype={'Mã': str})['Mã']
                         .dropna().astype(str).str.strip().str.upper()) - {'', 'NAN'})
    now = datetime.now(TZ)
    target = _target_closed_bucket(now)
    if NH.FILE.is_file():
        store = NH.validate_store(pd.read_csv(NH.FILE, dtype={'Mã': str}, encoding='utf-8-sig'))
    else:
        store = pd.DataFrame(columns=NH.COLUMNS)
    last_time = {}
    if not store.empty:
        last = pd.to_datetime(store['Ngày'], utc=True).dt.tz_convert('Asia/Ho_Chi_Minh')
        last_time = {s: t for s, t in zip(store['Mã'], last)}
    state = _read_state()
    failed = state.get('failed', {})
    today = now.date().isoformat()
    remaining = [s for s in symbols if last_time.get(s) is None or last_time[s] < target]
    if not args.retry_failed:
        remaining = [s for s in remaining if failed.get(s, {}).get('date') != today]
    todo = remaining[:args.max_symbols]
    print(f'EOD_UNIVERSE: {len(symbols)} | TARGET_CLOSED_HOUR: {target:%d/%m/%Y %H:%M} | REQUEST_THIS_RUN: {len(todo)}')
    print(f'REMAINING_BEFORE_THIS_RUN: {len(remaining)} | PRICE_SOURCE: direct VCI 1H')
    if not todo:
        print('NO_NETWORK_REQUESTS | NOTHING_TO_UPDATE')
        return
    from vnstock import Market
    market = Market()
    ok = 0
    def checkpoint():
        nonlocal store
        store = NH.validate_store(store)
        _atomic_csv(store, NH.FILE)
        _atomic_state(state)
    for index, symbol in enumerate(todo, 1):
        length = args.incremental_length if symbol in last_time else args.length
        try:
            chunk = _source_rows(market, symbol, length, now)
            store = pd.concat([store.loc[store['Mã'].ne(symbol)],
                               store.loc[store['Mã'].eq(symbol) & ~store['Ngày'].isin(chunk['Ngày'])],
                               chunk], ignore_index=True)
            store = NH.validate_store(store)
            ok += 1
            failed.pop(symbol, None)
            ts = pd.to_datetime(chunk['Ngày'].iloc[-1], utc=True).tz_convert('Asia/Ho_Chi_Minh')
            print(f'[{index}/{len(todo)}] {symbol}: OK {len(chunk)} source bars, latest {ts:%d/%m/%Y %H:%M}')
        except Exception as exc:
            etype = type(exc).__name__
            err_code = str(getattr(exc, 'code', ''))[:60]
            failed[symbol] = {'date': today, 'type': etype, 'code': err_code}
            print(f'[{index}/{len(todo)}] {symbol}: NO_NEW_BARS ({etype} {err_code})')
            # Preserve existing source records; stop on tier or daily quota exhaustion.
            if any(k in (err_code + ' ' + str(exc)).upper() for k in ('DAY_LIMIT','MONTH_LIMIT','RATE_LIMIT')):
                print('SOURCE_LIMIT_REACHED: stopping safely')
                break
        if index % args.checkpoint_every == 0:
            checkpoint()
        time.sleep(args.sleep)
    state['failed'] = failed
    state['last_run'] = datetime.now(TZ).isoformat()
    checkpoint()
    all_last = (pd.to_datetime(store['Ngày'], utc=True).dt.tz_convert('Asia/Ho_Chi_Minh')
                if not store.empty else pd.Series(dtype='datetime64[ns, Asia/Ho_Chi_Minh]'))
    newest = {s: t for s, t in zip(store['Mã'], all_last)}
    complete = sum(newest.get(s) is not None and newest[s] >= target for s in symbols)
    print('=== DIRECT 1H UPDATE RESULT ===')
    print('SOURCE: VCI 1H (NOT 15M RESAMPLED)')
    print(f'SYMBOLS_WITH_HISTORY: {store["Mã"].nunique()} / {len(symbols)}')
    print(f'SYMBOLS_AT_TARGET: {complete} / {len(symbols)}')
    print(f'UPDATED_THIS_RUN: {ok}')
    print(f'REMAINING_TO_TARGET: {len(symbols) - complete}')
    print('EOD_VIP_REDIS_NOT_WRITTEN | DATA_LOCAL_ONLY')


if __name__ == '__main__':
    main()
