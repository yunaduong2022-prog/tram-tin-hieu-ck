"""Vietnam national price-pressure snapshots, with explicit source, period & CPI scope.

Read-only presentation. Never mixes provincial CPI with nationwide, group with
subgroup contributions, cumulative producer-input inflation with consumer CPI,
or a qualitative fuel driver with a numeric fuel contribution.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

DATA_PATH = Path(__file__).resolve().parent / 'data' / 'macro_price_pressures.csv'
COLUMNS = ('category','metric_name','period','asof','basis','rate_pct',
           'contribution_pp','contribution_scope','source','source_url','description')
GROUPS = (
    ('food', 'Thực phẩm', 'Nhóm con trong CPI'),
    ('fuel', 'Xăng dầu', 'Giá xăng và bối cảnh thị trường'),
    ('power', 'Điện sinh hoạt', 'Nhóm con thuộc nhà ở'),
    ('housing', 'Nhà ở & vật liệu xây dựng', 'Nhóm CPI bao gồm điện'),
    ('inputs', 'Nguyên vật liệu sản xuất', 'Chỉ số giá đầu vào, KHÔNG phải CPI'),
)
CATEGORIES = {g[0] for g in GROUPS}
BASIS = {'mom', 'ytd_yoy', 'qualitative'}
SCOPES = {'same_group', 'not_published', 'not_cpi'}


def _period_end(period: str, basis: str) -> date:
    import re
    if basis == 'ytd_yoy':
        match = re.fullmatch(r'(\d{1,2})T/(\d{4})', period)
    else:
        match = re.fullmatch(r'(\d{2})/(\d{4})', period)
    if not match:
        raise ValueError('PRICE_INVALID_PERIOD')
    m, y = int(match.group(1)), int(match.group(2))
    if m < 1 or m > 12 or y < 2020:
        raise ValueError('PRICE_INVALID_PERIOD')
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def _pct(text: str, label: str, *, required: bool) -> Decimal | None:
    if text == '':
        if required:
            raise ValueError('PRICE_REQUIRED_' + label)
        return None
    try:
        x = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError('PRICE_BAD_' + label) from exc
    if not x.is_finite() or not Decimal('-50') <= x <= Decimal('100'):
        raise ValueError('PRICE_BAD_' + label)
    return x


def _official_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname in ('nso.gov.vn', 'www.nso.gov.vn')
            and parsed.username is None and parsed.password is None
            and parsed.port in (None, 443) and not parsed.fragment)


def parse_price_row(row: dict[str, str], *, today: date) -> dict:
    if tuple(row) != COLUMNS:
        raise ValueError('PRICE_SCHEMA_MISMATCH')
    if row['category'] not in CATEGORIES or row['basis'] not in BASIS:
        raise ValueError('PRICE_CATEGORY_OR_BASIS')
    if row['source'] != 'Cục Thống kê' or not _official_url(row['source_url']):
        raise ValueError('PRICE_UNVERIFIED_SOURCE')
    if row['contribution_scope'] not in SCOPES:
        raise ValueError('PRICE_CONTRIBUTION_SCOPE')
    end = _period_end(row['period'], row['basis'])
    try:
        asof = date.fromisoformat(row['asof'])
    except ValueError as exc:
        raise ValueError('PRICE_INVALID_ASOF') from exc
    if asof != end or end > today:
        raise ValueError('PRICE_PERIOD_MISMATCH_OR_FUTURE')
    rate = _pct(row['rate_pct'], 'RATE', required=row['basis'] != 'qualitative')
    if row['basis'] == 'qualitative' and rate is not None:
        raise ValueError('PRICE_QUALITATIVE_CANNOT_HAVE_RATE')
    contrib = _pct(row['contribution_pp'], 'CONTRIBUTION', required=False)
    if contrib is not None and (row['contribution_scope'] != 'same_group'
                                or abs(contrib) > Decimal('10')
                                or row['basis'] != 'mom'):
        raise ValueError('PRICE_WRONG_CONTRIBUTION_ATTRIBUTION')
    if row['category'] == 'inputs':
        if row['basis'] != 'ytd_yoy' or row['contribution_scope'] != 'not_cpi':
            raise ValueError('PRICE_INPUTS_MUST_NOT_BE_CPI')
    elif row['basis'] == 'ytd_yoy' or row['contribution_scope'] == 'not_cpi':
        raise ValueError('PRICE_WRONG_CPI_BASIS')
    if not row['metric_name'].strip() or not row['description'].strip():
        raise ValueError('PRICE_EMPTY_METADATA')
    return {**row, 'date': end, 'rate': rate, 'contribution': contrib}


def read_prices(path: Path = DATA_PATH, *, today: date | None = None) -> list[dict]:
    now = today or date.today()
    try:
        with path.open('r', encoding='utf-8-sig', newline='') as fh:
            reader = csv.DictReader(fh)
            if tuple(reader.fieldnames or ()) != COLUMNS:
                raise ValueError('PRICE_SCHEMA_MISMATCH')
            rows = [parse_price_row(row, today=now) for row in reader]
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError('PRICE_DATA_UNREADABLE') from exc
    if not rows:
        raise ValueError('PRICE_EMPTY_DATA')
    keys = [(r['category'], r['period'], r['basis']) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('PRICE_DUPLICATE_CATEGORY_PERIOD')
    for group in CATEGORIES:
        if not any(r['category'] == group for r in rows):
            raise ValueError('PRICE_MISSING_GROUP_' + group)
    return rows


def latest_for(rows: list[dict], category: str, basis: str | None = None) -> dict | None:
    r = [x for x in rows if x['category'] == category and (basis is None or x['basis'] == basis)]
    return max(r, key=lambda x: x['date'], default=None)


def fmt(value: Decimal | None) -> str:
    return '—' if value is None else f'{value:+.2f}'.replace('.', ',') + '%'


def render_price_pressures() -> None:
    import streamlit as st
    import pandas as pd
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    st.caption('Dữ liệu CẢ NƯỚC theo từng kỳ, không phải bảng giá thời gian thực. '
               'Số tháng 5 chỉ dùng làm mốc công bố lịch sử; không coi là số tháng 10.')
    try:
        rows = read_prices(today=today)
    except ValueError as exc:
        st.error(f'Chưa thể đọc dữ liệu giá hàng hóa có kiểm chứng ({exc}); không điền số giả.')
        return
    cols = st.columns(3)
    for index, (category, label, kind) in enumerate(GROUPS):
        numeric = latest_for(rows, category, 'ytd_yoy' if category == 'inputs' else 'mom')
        with cols[index % 3]:
            with st.container(border=True):
                st.markdown(f'**{label}**')
                if numeric is None:
                    st.metric('Chưa có nguồn số phù hợp', '—')
                    continue
                st.metric(numeric['metric_name'], fmt(numeric['rate']))
                basis = 'MoM so tháng trước' if numeric['basis'] == 'mom' else 'Bình quân lũy kế YoY'
                st.caption(f"{numeric['period']} · {basis}")
                st.caption(kind)
                if numeric['contribution'] is not None:
                    st.write(f"Đóng góp CPI **{fmt(numeric['contribution']).replace('%', ' điểm %')}** (chính nhóm được công bố)")
                else:
                    st.caption('Đóng góp CPI riêng: — chưa công bố hoặc không áp dụng')
                st.caption(numeric['description'])
                st.markdown(f"[Nguồn Cục Thống kê]({numeric['source_url']})")
                if (today - numeric['date']).days > 60:
                    st.caption('⚠️ Số lịch sử trên 60 ngày; cần tìm kỳ chi tiết mới hơn')
    qual = latest_for(rows, 'fuel', 'qualitative')
    if qual:
        st.info(f"**Diễn biến mới hơn ({qual['period']}) · Xăng dầu:** {qual['description']} "
                f"[Báo cáo gốc]({qual['source_url']})")
    st.caption('**Không cộng chồng đóng góp:** Điện là thành phần của nhóm nhà ở; '
               'đóng góp nhóm giao thông không phải đóng góp riêng của xăng. '
               'Chỉ số giá nguyên vật liệu đầu vào không phải cấu phần CPI tiêu dùng.')
    with st.expander('Kiểm tra số liệu, kỳ, phương pháp đo và nguồn', expanded=False):
        display = []
        for row in sorted(rows, key=lambda r: (r['category'], r['date'])):
            display.append({'Nhóm': row['category'], 'Chỉ tiêu': row['metric_name'],
                            'Kỳ nguồn': row['period'], 'Cách đo': row['basis'],
                            'Biến động (%)': float(row['rate']) if row['rate'] is not None else None,
                            'Đóng góp (điểm %)': float(row['contribution']) if row['contribution'] is not None else None,
                            'Ghi chú': row['description'], 'Báo cáo gốc': row['source_url']})
        st.dataframe(pd.DataFrame(display), use_container_width=True, hide_index=True,
                     column_config={'Báo cáo gốc': st.column_config.LinkColumn('Nguồn Cục Thống kê')})
