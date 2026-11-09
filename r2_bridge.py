"""Private Cloudflare R2 data bridge for Streamlit and the Windows publisher.

Transport only. Never calls vnstock, never reads/writes customer portfolio data,
and NEVER deserializes pickles from the network.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from datetime import datetime, timezone

VERSION = 1
ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
STATE_DIR = DATA / '.cloud_sync'
MANIFEST_FILE = 'current.json'
# Public market feeds only. Do NOT sync user portfolios, client lists, orders,
# Telegram tokens, .env, secrets, logs, backups or local pickle caches.
ALLOWLIST = (
    'data/eod_prices.csv',
    'data/index_prices.csv',
    'data/eod_meta.json',
    'data/stock_metadata.csv',
    'data/shares_outstanding.csv',
    'data/fundamentals.csv',
    'data/nhom_von_hoa_gia.csv',
    'data/thong_tin_chung.csv',
    'data/intraday_15m.csv',
    'data/hourly_native_1h.csv',
    'data/proprietary_flow.csv',
    'data/foreign_stock_flow.csv',
    'data/foreign_net_flow.csv',
)
REQUIRED = ('data/eod_prices.csv', 'data/index_prices.csv')
LOCK = threading.RLock()
_LAST_CHECK = 0.0
_LAST_OUTCOME = None


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for blob in iter(lambda: f.read(1024 * 1024), b''):
            h.update(blob)
    return h.hexdigest()


def config_from_mapping(raw):
    """Return complete, normalized config or None; never log credentials."""
    try:
        conf = raw.get('market_sync', None)
        if conf is None:
            return None
        result = {k: str(conf[k]).strip() for k in ('account_id', 'bucket', 'access_key_id', 'secret_access_key')}
        result['prefix'] = str(conf.get('prefix', 'min-stock-data')).strip().strip('/')
        result['distribution_rights_confirmed'] = (conf.get('distribution_rights_confirmed') is True)
    except (KeyError, TypeError, AttributeError):
        raise ValueError('Thiếu thông số market_sync. Kiểm tra Secrets trên Windows hoặc Cloud.') from None
    if any(not result[k] for k in ('account_id', 'bucket', 'access_key_id', 'secret_access_key')):
        raise ValueError('market_sync chưa đủ Account ID, bucket hoặc Access Key.')
    if not re.fullmatch(r'[0-9a-fA-F]{32}', result['account_id']):
        raise ValueError('Account ID Cloudflare phải gồm 32 ký tự hex.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,62}', result['bucket']):
        raise ValueError('Tên bucket không hợp lệ.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/_-]{0,80}', result['prefix']):
        raise ValueError('Prefix R2 không hợp lệ.')
    return result


def windows_config():
    import tomllib
    config_path = Path.home() / '.streamlit' / 'secrets.toml'
    if not config_path.is_file():
        return None
    with config_path.open('rb') as f:
        return config_from_mapping(tomllib.load(f))


def client(conf):
    import boto3
    from botocore.config import Config
    return boto3.client(
        's3',
        endpoint_url='https://' + conf['account_id'] + '.r2.cloudflarestorage.com',
        region_name='auto',
        aws_access_key_id=conf['access_key_id'],
        aws_secret_access_key=conf['secret_access_key'],
        config=Config(connect_timeout=8, read_timeout=35, retries={'max_attempts': 2, 'mode': 'standard'}),
    )


def manifest_key(conf):
    return conf['prefix'] + '/' + MANIFEST_FILE


def object_key(conf, filename, digest):
    if filename not in ALLOWLIST:
        raise ValueError('File not allowlisted')
    return conf['prefix'] + '/objects/' + filename.removeprefix('data/') + '/' + digest


def validate_manifest(manifest, conf):
    if not isinstance(manifest, dict) or manifest.get('version') != VERSION:
        raise ValueError('Manifest version không hợp lệ.')
    files = manifest.get('files')
    if not isinstance(files, list) or not files or len(files) > len(ALLOWLIST):
        raise ValueError('Manifest không có danh sách dữ liệu hợp lệ.')
    records = {}
    for obj in files:
        if not isinstance(obj, dict):
            raise ValueError('Định dạng mục trong manifest không hợp lệ.')
        path = obj.get('path')
        digest = obj.get('sha256')
        size = obj.get('size')
        key = obj.get('key')
        if path not in ALLOWLIST or path in records or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Manifest chứa đường dẫn hoặc checksum không được phép.')
        if type(size) is not int or size <= 0 or size > 1_000_000_000:
            raise ValueError('Dung lượng file không hợp lệ.')
        if key != object_key(conf, path, digest):
            raise ValueError('R2 object key không khớp nội dung file.')
        records[path] = obj
    if not all(p in records for p in REQUIRED):
        # Legacy R2 manifests may contain EOD + intraday but no index.
        # They remain readable during migration to EOD + index.
        if not ('data/eod_prices.csv' in records and 'data/intraday_15m.csv' in records):
            raise ValueError('Manifest thiếu EOD cổ phiếu và EOD chỉ số.')
    return records


def _validate_headers(path, name):
    if name.endswith('.json'):
        if not isinstance(json.loads(Path(path).read_text(encoding='utf-8-sig')), dict):
            raise ValueError('JSON data not object: ' + name)
        return
    with open(path, newline='', encoding='utf-8-sig') as f:
        headers = next(csv.reader(f), [])
    if name == 'data/foreign_stock_flow.csv':
        required = {'trading_date','symbol','net_val','data_source'}
    elif name == 'data/proprietary_flow.csv':
        required = {'trading_date','symbol','net_val','data_source'}
    elif name == 'data/foreign_net_flow.csv':
        required = {'trading_date', 'symbol', 'net_value_vnd', 'source_scope'}
    elif name == 'data/intraday_15m.csv':
        required = {'symbol', 'time', 'open', 'high', 'low', 'close', 'volume'}
    elif name == 'data/hourly_native_1h.csv':
        required = {'Mã', 'Ngày', 'Giá mở cửa', 'Giá cao nhất', 'Giá thấp nhất', 'Giá đóng cửa', 'Khối lượng khớp lệnh', 'source', 'interval'}
    elif name in ('data/eod_prices.csv', 'data/index_prices.csv'):
        required = {'Mã', 'Ngày'}
    else:
        required = set()
    if not required.issubset(set(headers)):
        raise ValueError('CSV missing required headers: ' + name)


def publish(*, s3, conf, root=ROOT, dry_run=False):
    """Upload immutable, content-addressed objects then manifest LAST."""
    if not conf['distribution_rights_confirmed']:
        raise PermissionError('Chưa xác nhận quyền phân phối dữ liệu thị trường; không xuất dữ liệu.')
    root = Path(root)
    if not all((root / f).is_file() for f in REQUIRED):
        raise FileNotFoundError('Thiếu dữ liệu EOD cổ phiếu hoặc chỉ số trên Windows.')
    for lock in ('data/.intraday_state/session_15m.lock', 'data/.intraday_state/update.lock'):
        if (root / lock).exists():
            raise RuntimeError('Đang thu thập VNStock; đợi lượt cập nhật hoàn tất mới xuất dữ liệu.')
    # Keep legacy 15m readable but never republish it; optional native VCI
    # 1H goes to private R2 only after distribution rights confirmation.
    files = [p for p in ALLOWLIST if p != 'data/intraday_15m.csv' and (root / p).is_file()]
    with tempfile.TemporaryDirectory(prefix='r2_snap_') as temp:
        # Make a consistent local snapshot; never upload a CSV still being written.
        staged = []
        for name in files:
            src = root / name
            copied = Path(temp) / Path(name).name
            shutil.copy2(src, copied)
            digest = sha256(copied)
            if sha256(src) != digest:
                raise RuntimeError('Dữ liệu đổi trong lúc sao chụp: ' + name)
            _validate_headers(copied, name)
            staged.append((name, copied, digest, copied.stat().st_size))
        records = [dict(path=name, key=object_key(conf, name, digest), sha256=digest, size=size)
                   for name, _, digest, size in staged]
        manifest = dict(version=VERSION, created_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'), files=records)
        validate_manifest(manifest, conf)
        # Do not use remote pickle or any file outside allowlist.
        try:
            old = json.loads(s3.get_object(Bucket=conf['bucket'], Key=manifest_key(conf))['Body'].read())
            validate_manifest(old, conf)
            if old['files'] == manifest['files']:
                return {'status': 'NO_CHANGES', 'files': len(records), 'uploaded': 0}
        except Exception as exc:
            if not _is_missing_object(exc):
                # Never downgrade R2 access/permission errors to a fresh publish.
                raise
        if dry_run:
            return {'status': 'DRY_RUN', 'files': len(records), 'uploaded': 0}
        upload_count = 0
        for name, src, digest, _ in staged:
            key = object_key(conf, name, digest)
            try:
                s3.head_object(Bucket=conf['bucket'], Key=key)
                continue
            except Exception as exc:
                if not _is_missing_object(exc):
                    raise
            extra = {'ContentType': 'application/json' if name.endswith('.json') else 'text/csv'}
            s3.upload_file(str(src), conf['bucket'], key, ExtraArgs=extra)
            upload_count += 1
        # Check that no source changed while remote upload was running.
        for name, _, digest, _ in staged:
            if sha256(root / name) != digest:
                raise RuntimeError('Nguồn dữ liệu bị thay đổi khi upload; manifest chưa được xuất.')
        manifest_blob = json.dumps(manifest, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        s3.put_object(Bucket=conf['bucket'], Key=manifest_key(conf), Body=manifest_blob,
                      ContentType='application/json', CacheControl='no-store')
        return {'status': 'PUBLISHED', 'files': len(records), 'uploaded': upload_count,
                'created_utc': manifest['created_utc']}


def _is_missing_object(exc):
    try:
        return str(exc.response['Error']['Code']) in ('404', 'NoSuchKey', 'NotFound')
    except (AttributeError, KeyError, TypeError):
        return False


def _read_state(root):
    p = Path(root) / 'data' / '.cloud_sync' / 'synced.json'
    try:
        x = json.loads(p.read_text(encoding='utf-8'))
        return x if isinstance(x, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _atomic_json(path, item):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.state_', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(item, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


# TRAM_CK_R2_NEWER_EOD_GUARD_V1

def _preserve_newer_local_eod(local, downloaded, temp_dir):
    """Merge only real local EOD/index rows newer than R2's latest per symbol.

    GitHub EOD may be ahead for an individual ticker even if the overall R2
    snapshot has the same latest market date. R2 wins for all dates it already
    contains. No synthetic bars, no interpolation, no VNStock requests.
    """
    def day_key(value):
        s = str(value).strip()
        if re.fullmatch(r'\d{2}/\d{2}/\d{4}', s):
            # Validate date, not just string shape.
            from datetime import datetime as _datetime
            _datetime.strptime(s, '%d/%m/%Y')
            return int(s[6:10] + s[3:5] + s[:2])
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
            from datetime import datetime as _datetime
            _datetime.strptime(s, '%Y-%m-%d')
            return int(s.replace('-', ''))
        raise ValueError('Unexpected EOD date format in R2/GitHub: ' + s[:16])

    with open(downloaded, newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        remote_header = list(reader.fieldnames or [])
        if not {'Mã', 'Ngày'}.issubset(remote_header):
            raise ValueError('R2 EOD missing Ma/Ngay header')
        last_remote = {}
        for row in reader:
            sym = str(row['Mã']).strip().upper()
            d = day_key(row['Ngày'])
            if sym and d > last_remote.get(sym, 0):
                last_remote[sym] = d

    additions = []
    with open(local, newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        local_header = list(reader.fieldnames or [])
        if set(local_header) != set(remote_header):
            raise ValueError('GitHub and R2 EOD columns differ; safe stop')
        seen = set()
        for row in reader:
            sym = str(row['Mã']).strip().upper()
            d = day_key(row['Ngày'])
            if sym and d > last_remote.get(sym, 0):
                key = (sym, d)
                if key in seen:
                    raise ValueError('Duplicate new GitHub EOD key for ' + sym)
                seen.add(key)
                additions.append(row)

    if not additions:
        return downloaded
    # Local history is valid, and R2 has no candle this recent for those codes.
    # Append exactly these existing source rows; indicators will be recomputed.
    merged = Path(temp_dir) / 'r2_plus_newer_github_eod.csv'
    with open(merged, 'w', newline='', encoding='utf-8') as out:
        writer = csv.DictWriter(out, fieldnames=remote_header)
        writer.writeheader()
        with open(downloaded, newline='', encoding='utf-8-sig') as inp:
            for row in csv.DictReader(inp):
                writer.writerow(row)
        for row in additions:
            writer.writerow(row)
    return merged

def mirror(*, s3, conf, root=ROOT):
    """Read verified R2 snapshot into Streamlit's local data folder."""
    root = Path(root)
    response = s3.get_object(Bucket=conf['bucket'], Key=manifest_key(conf))
    manifest_bytes = response['Body'].read(1_000_001)
    if len(manifest_bytes) > 1_000_000:
        raise ValueError('Manifest unexpectedly large.')
    manifest = json.loads(manifest_bytes)
    records = validate_manifest(manifest, conf)
    old = _read_state(root)
    incoming_id = hashlib.sha256(manifest_bytes).hexdigest()
    if old.get('manifest_sha') == incoming_id and all((root / f).is_file() for f in records):
        return {'status': 'CURRENT', 'files': len(records), 'created_utc': manifest['created_utc']}
    incoming = []
    with tempfile.TemporaryDirectory(prefix='r2_download_') as temp:
        for name, rec in records.items():
            local = root / name
            if local.is_file() and local.stat().st_size == rec['size'] and sha256(local) == rec['sha256']:
                continue
            dest = Path(temp) / ('new_' + Path(name).name)
            with dest.open('wb') as stream:
                s3.download_fileobj(conf['bucket'], rec['key'], stream)
            if dest.stat().st_size != rec['size'] or sha256(dest) != rec['sha256']:
                raise ValueError('Tải dữ liệu bị hỏng hoặc checksum sai: ' + name)
            _validate_headers(dest, name)
            incoming.append((name, dest))
        # Changes are fully downloaded and verified before any published data is replaced.
        backup_dir = Path(temp) / 'previous'
        backup_dir.mkdir(exist_ok=True)
        replaced = []
        state_path = root / 'data' / '.cloud_sync' / 'synced.json'
        try:
            for name, staged in incoming:
                local = root / name
                if name in ('data/eod_prices.csv', 'data/index_prices.csv') and local.is_file():
                    staged = _preserve_newer_local_eod(local, staged, temp)
                local.parent.mkdir(parents=True, exist_ok=True)
                previous = backup_dir / Path(name).name
                existed = local.is_file()
                if existed: shutil.copy2(local, previous)
                # os.replace is atomic within one filesystem.
                fd, tmp_name = tempfile.mkstemp(prefix='.download_', dir=local.parent)
                os.close(fd)
                temp_local = Path(tmp_name)
                try:
                    shutil.copyfile(staged, temp_local)
                    os.replace(temp_local, local)
                finally:
                    temp_local.unlink(missing_ok=True)
                replaced.append((local, previous, existed))
            _atomic_json(state_path, {'manifest_sha': incoming_id, 'created_utc': manifest['created_utc'],
                                     'files': {n:r['sha256'] for n,r in records.items()},
                                     'checked_utc': datetime.now(timezone.utc).isoformat(timespec='seconds')})
        except Exception:
            for local, previous, existed in reversed(replaced):
                if existed:
                    shutil.copy2(previous, local)
                else:
                    local.unlink(missing_ok=True)
            raise
    return {'status': 'UPDATED' if incoming else 'CURRENT', 'files': len(records),
            'downloaded': len(incoming), 'created_utc': manifest['created_utc']}


def sync_for_streamlit(*, ttl_seconds=75):
    """Call only after st.set_page_config(); never VNStock or GitHub."""
    global _LAST_CHECK, _LAST_OUTCOME
    import streamlit as st
    try:
        conf = config_from_mapping(st.secrets)
    except (FileNotFoundError, ValueError) as exc:
        st.error('Cấu hình kho R2 chưa hợp lệ: ' + str(exc))
        st.stop()
        return None
    if conf is None:
        return None
    # Safe rollout: keep Cloud online until a licensed R2 snapshot is published.
    if st.secrets["market_sync"].get("sync_enabled") is not True:
        return None
    # Polling schedules a rerun, no VNStock access.
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=120_000, key='r2_market_refresh')
    except ImportError:
        pass
    with LOCK:
        now = time.monotonic()
        if _LAST_OUTCOME and now - _LAST_CHECK < ttl_seconds:
            return _LAST_OUTCOME
        try:
            out = mirror(s3=client(conf), conf=conf)
            _LAST_CHECK = now
            _LAST_OUTCOME = out
            return out
        except Exception:
            # Avoid leaking boto3's credential-containing URLs or exception strings.
            prev = _read_state(ROOT)
            if prev and (ROOT / 'data' / 'eod_prices.csv').is_file():
                st.warning('R2 tạm thời không truy cập được; đang dùng bản dữ liệu đồng bộ gần nhất. ' +
                           'Thời điểm bản lưu: ' + str(prev.get('created_utc', 'không rõ')))
                _LAST_CHECK = now
                _LAST_OUTCOME = {'status': 'STALE', 'created_utc': prev.get('created_utc')}
                return _LAST_OUTCOME
            st.error('Không thể tải dữ liệu thị trường từ kho R2. Kiểm tra Secrets và kết nối R2.')
            st.stop()
            return None
