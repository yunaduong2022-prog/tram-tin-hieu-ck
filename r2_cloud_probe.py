"""Read-only Streamlit diagnostic for one synthetic R2 object.

Never loads market-data manifests, price CSVs, portfolios or credentials into UI.
The sole public output is a PASS/FAIL status for a harmless synthetic marker.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

PROBE_OBJECT = 'healthchecks/synthetic_transport_v1.json'
PROBE_MARKER = 'MIN_R2_SYNTHETIC_TEST_ONLY_V1'
MAX_BYTES = 4096


def probe_key(conf):
    return conf['prefix'] + '/' + PROBE_OBJECT


def canonical_bytes(info):
    return json.dumps(info, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('utf-8')


def build_payload():
    import secrets
    body = dict(marker=PROBE_MARKER, created_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                nonce=secrets.token_hex(12), content='SYNTHETIC ONLY / NO MARKET DATA')
    return canonical_bytes(dict(body=body, sha256=hashlib.sha256(canonical_bytes(body)).hexdigest()))


def verify_bytes(raw, *, now=None):
    """Validate size, integrity, marker and freshness; never execute remote content."""
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError('Unexpected synthetic probe size')
    wrapper = json.loads(raw)
    if not isinstance(wrapper, dict) or set(wrapper) != {'body', 'sha256'}:
        raise ValueError('Invalid probe envelope')
    body = wrapper['body']
    if not isinstance(body, dict) or set(body) != {'marker','created_utc','nonce','content'}:
        raise ValueError('Invalid probe fields')
    if body['marker'] != PROBE_MARKER or body['content'] != 'SYNTHETIC ONLY / NO MARKET DATA':
        raise ValueError('Probe is not synthetic')
    if not isinstance(body['nonce'], str) or len(body['nonce']) != 24 or any(c not in '0123456789abcdef' for c in body['nonce']):
        raise ValueError('Invalid probe nonce')
    if wrapper['sha256'] != hashlib.sha256(canonical_bytes(body)).hexdigest():
        raise ValueError('Synthetic data integrity failed')
    stamp = datetime.fromisoformat(body['created_utc'])
    if stamp.tzinfo is None:
        raise ValueError('Naive probe timestamp')
    now = now or datetime.now(timezone.utc)
    age = (now - stamp).total_seconds()
    if age < -180 or age > 7*86400:
        raise ValueError('Probe timestamp outside test window')
    return {'status':'PASS', 'created_utc':body['created_utc']}


def read_probe(s3, conf):
    response = s3.get_object(Bucket=conf['bucket'], Key=probe_key(conf))
    raw = response['Body'].read(MAX_BYTES + 1)
    return verify_bytes(raw)


def render_probe():
    import streamlit as st
    st.title('Kiểm tra đường kết nối Cloudflare R2')
    st.caption('Chỉ sử dụng dữ liệu thử nghiệm. Không tải hoặc công bố dữ liệu VNStock.')
    try:
        from r2_bridge import config_from_mapping, client
        conf = config_from_mapping(st.secrets)
        if conf is None:
            st.error('CLOUD_R2_PROBE: CONFIG_MISSING')
            return
        # No R2 market mirror, no customer data, no secret values in output.
        result = read_probe(client(conf), conf)
        st.success('CLOUD_R2_PROBE: PASS')
        st.write('Windows đã ghi và Streamlit Cloud đã đọc dữ liệu mô phỏng hợp lệ.')
        st.caption('Thời điểm file thử (UTC): ' + result['created_utc'])
        st.info('Đồng bộ dữ liệu thị trường vẫn tắt. Kiểm tra này không cấp quyền phân phối dữ liệu.')
    except Exception:
        # No raw botocore errors: response URLs/metadata may be sensitive.
        st.error('CLOUD_R2_PROBE: FAIL')
        st.write('Cloud chưa đọc được file mô phỏng. Kiểm tra khóa Read-only, bucket và prefix trong Secrets.')
