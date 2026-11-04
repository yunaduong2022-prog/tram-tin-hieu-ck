"""Safely publish ONLY native 1H source to an existing licensed private R2 snapshot.

Never replace EOD/index/auxiliary records: preserves their immutable object SHA
and manifest entries exactly as published by the normal EOD updater. Fails closed
on concurrent changes or missing redistribution rights.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import sys

import hourly_native_1h as NH


def main():
    if not NH.FILE.is_file():
        print('PUBLISH_BLOCKED: NATIVE_HOURLY_FILE_MISSING')
        return 2
    try:
        import pandas as pd
        rows = NH.validate_store(pd.read_csv(NH.FILE, dtype={'Mã':str}, encoding='utf-8-sig'))
    except (OSError, ValueError, KeyError) as exc:
        print('PUBLISH_BLOCKED: NATIVE_SOURCE_INVALID_'+type(exc).__name__)
        return 2
    if rows.empty:
        print('PUBLISH_BLOCKED: NO_NATIVE_1H_CANDLES')
        return 2
    try:
        import r2_bridge as R2
        conf = R2.windows_config()
        if conf is None:
            print('PUBLISH_BLOCKED: WINDOWS_R2_CONFIG_NOT_PRESENT')
            print('Check $HOME\\.streamlit\\secrets.toml locally; NEVER paste credentials.')
            return 2
        if not conf['distribution_rights_confirmed']:
            print('PUBLISH_BLOCKED: REDISTRIBUTION_RIGHTS_NOT_CONFIRMED')
            print('Access to VNStock Bronze data does not itself grant website redistribution rights.')
            return 2
        s3 = R2.client(conf)
        bucket, mkey = conf['bucket'], R2.manifest_key(conf)
        # Existing snapshot is REQUIRED. Do not create/replace EOD data here.
        response = s3.get_object(Bucket=bucket, Key=mkey)
        original = response['Body'].read(1_000_001)
        if len(original)>1_000_000:
            raise ValueError('R2_MANIFEST_SIZE_REJECTED')
        old_manifest = json.loads(original)
        old_records = R2.validate_manifest(old_manifest, conf)
        label = 'data/hourly_native_1h.csv'
        R2._validate_headers(NH.FILE, label)
        initial_sha = R2.sha256(NH.FILE)
        size = NH.FILE.stat().st_size
        obj = {'path': label, 'key': R2.object_key(conf, label, initial_sha),
               'sha256': initial_sha, 'size': size}
        # Don't touch any original record except an earlier version of hourly 1H.
        unchanged = [dict(entry) for entry in old_manifest['files'] if entry['path'] != label]
        updated = dict(version=R2.VERSION, created_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                       files=unchanged+[obj])
        R2.validate_manifest(updated, conf)
        old = old_records.get(label)
        if old and old['sha256'] == initial_sha:
            print('R2_NATIVE_1H_ALREADY_CURRENT')
            print('EOD_MANIFEST_RECORDS_UNCHANGED')
            return 0
        # Write content-addressed object first; if manifest write fails, old
        # snapshot remains intact and the unused object is harmless.
        try:
            s3.head_object(Bucket=bucket, Key=obj['key'])
        except Exception as exc:
            if not R2._is_missing_object(exc):
                raise
            s3.upload_file(str(NH.FILE), bucket, obj['key'], ExtraArgs={'ContentType':'text/csv'})
        if R2.sha256(NH.FILE) != initial_sha or NH.FILE.stat().st_size != size:
            raise ValueError('SOURCE_CHANGED_DURING_UPLOAD')
        verify = s3.get_object(Bucket=bucket, Key=mkey)['Body'].read(1_000_001)
        if verify != original:
            raise ValueError('R2_MANIFEST_CHANGED_CONCURRENTLY_ABORT')
        blob = json.dumps(updated, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        s3.put_object(Bucket=bucket, Key=mkey, Body=blob,
                      ContentType='application/json', CacheControl='no-store')
    except Exception as exc:
        # Never print HTTP/provider exceptions: credentials can occur in URLs.
        print('PUBLISH_BLOCKED: PRIVATE_R2_'+type(exc).__name__)
        return 2
    print('=== PRIVATE R2 NATIVE 1H RESULT ===')
    print('VCI_DIRECT_HOURLY_SYMBOLS: '+str(rows['Mã'].nunique()))
    print('ONLY_OPTIONAL_NATIVE_1H_MANIFEST_RECORD_CHANGED')
    print('EOD_INDEX_AUX_RECORDS_PRESERVED')
    print('NO_GITHUB_DATA_COMMIT | NO_CLIENT_OR_PORTFOLIO_WRITES')
    return 0


if __name__ == '__main__':
    sys.exit(main())
