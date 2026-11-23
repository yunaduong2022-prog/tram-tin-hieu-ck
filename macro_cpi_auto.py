"""Guarded, source-scoped monthly Vietnam CPI sync for Trạm Tín Hiệu.

The only writable files are data/macro_cpi_history.csv and data/macro_vn.csv.
Never infers MoM, annual/monthly core, or missing data; never overwrites a
previously published month with a revised value automatically.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
from html.parser import HTMLParser
import io
from pathlib import Path
import re
import sys
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from macro_cpi_history import read_history, parse_row, COLUMNS, vietnam_today

ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / 'data' / 'macro_cpi_history.csv'
MACRO = ROOT / 'data' / 'macro_vn.csv'
INDEXES = (
    'https://www.nso.gov.vn/cpi-vi/',
    'https://www.nso.gov.vn/tag/cpi-vi/',
    'https://www.nso.gov.vn/gia/thong-cao-bao-chi/',
    'https://www.nso.gov.vn/du-lieu-va-so-lieu-thong-ke/',
)
MONTHS = ('', 'một', 'hai', 'ba', 'tư', 'năm', 'sáu', 'bảy', 'tám', 'chín',
          'mười', 'mười một', 'mười hai')
METRICS = ('cpi_yoy_pct', 'cpi_mom_pct', 'cpi_ytd_avg_yoy_pct', 'core_ytd_avg_yoy_pct')
PERCENT = r'(\d{1,2}(?:[,.]\d{1,2})?)\s*%'
MEASURE = rf'(tăng|giảm)\s*{PERCENT}'
MACRO_IDS = ('CPI_OCT_YOY', 'CPI_OCT_MOM', 'CPI_10M', 'CORE_CPI_10M')
MACRO_COLUMNS = ('id','group','label','period','asof','value','unit',
                 'comparison','source','source_url','note')


def month_next(ym: str) -> str:
    current = datetime.strptime(ym, '%Y-%m').date()
    return f'{current.year + (current.month == 12):04d}-{current.month % 12 + 1:02d}'


def month_label(month: int) -> str:
    return rf'(?:0?{month}(?!\d)|{re.escape(MONTHS[month])}(?!\w))'


def safe_official_url(url: str) -> bool:
    p = urlsplit(url)
    return (p.scheme == 'https' and p.hostname in ('www.nso.gov.vn', 'nso.gov.vn')
            and p.username is None and p.password is None and p.port in (None, 443)
            and p.path.startswith('/') and not p.fragment)


def clean(s: str) -> str:
    return re.sub(r'\s+', ' ', s.replace('\xa0', ' ')).strip()


class NSOHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.paragraphs: list[str] = []
        self.headings: list[str] = []
        self._tags: list[str] = []
        self._buf: list[str] = []
        self._href = ''
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'):
            self._ignored += 1
        if self._ignored:
            return
        if tag in ('img', 'br', 'hr', 'input', 'meta', 'link', 'source'):
            return
        if tag in ('a', 'h1', 'p') and not self._tags:
            self._tags.append(tag)
            self._buf = []
            self._href = dict(attrs).get('href', '')
        elif self._tags:
            self._tags.append('nested:' + tag)

    def handle_data(self, data):
        if self._tags and not self._ignored:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag in ('script','style','noscript') and self._ignored:
            self._ignored -= 1
        if not self._tags or self._ignored:
            return
        current = self._tags.pop()
        if current.startswith('nested:'):
            return
        if current == tag:
            t = clean(''.join(self._buf))
            if t:
                if tag == 'a': self.links.append((self._href, t))
                if tag == 'h1': self.headings.append(t)
                if tag == 'p': self.paragraphs.append(t)
            self._buf = []


def parse_html(html: str) -> NSOHTML:
    obj = NSOHTML()
    obj.feed(html)
    return obj


def title_matches(title: str, year: int, month: int) -> bool:
    t = clean(title).lower()
    if str(year) not in t:
        return False
    if not ('chỉ số giá tiêu dùng' in t or 'tình hình giá' in t or 'cpi' in t):
        return False
    return bool(re.search(r'\btháng\s+' + month_label(month), t, re.I))


def candidates_from_index(html: str, base_url: str, year: int, month: int) -> list[str]:
    page = parse_html(html)
    found = set()
    for href, title in page.links:
        if not title_matches(title, year, month):
            continue
        link = urljoin(base_url, href).split('#', 1)[0]
        if safe_official_url(link) and re.search(r'/\d{4}/\d{2}/', urlsplit(link).path):
            found.add(link)
    return sorted(found)


def signed(measure: re.Match[str]) -> Decimal:
    # Groups 1,2: 'tăng|giảm', '4,57'
    val = Decimal(measure.group(2).replace(',', '.'))
    return -val if measure.group(1).lower() == 'giảm' else val


def one_match(pattern: str, text: str, context: str) -> Decimal:
    hits = list(re.finditer(pattern, text, flags=re.I))
    if len(hits) != 1:
        raise ValueError(f'CPI_{context}_AMBIGUOUS_{len(hits)}')
    return signed(hits[0])


def article_values(html: str, expected_year: int, expected_month: int) -> dict[str, Decimal]:
    page = parse_html(html)
    if len([t for t in page.headings if title_matches(t, expected_year, expected_month)]) != 1:
        raise ValueError('CPI_ARTICLE_TITLE_MONTH_UNVERIFIED')
    month_exp = month_label(expected_month)
    target = re.compile(r'(?:chỉ số giá tiêu dùng\s*\(\s*CPI\s*\)|\bCPI\b)\s*tháng\s+'
                        + month_exp, re.I)
    intro = [p for p in page.paragraphs if target.search(p)]
    intro = [p for p in intro if 'so với tháng trước' in p.lower()
             and 'so với cùng kỳ năm trước' in p.lower()]
    if len(intro) != 1:
        raise ValueError(f'CPI_MAIN_PARAGRAPH_AMBIGUOUS_{len(intro)}')
    intro_text = intro[0]
    # Require exact comparison phrases, not the intervening "so với tháng 12" value.
    mom = one_match(MEASURE + r'\s+so với tháng trước', intro_text, 'MOM')
    yoy = one_match(MEASURE + r'\s+so với cùng kỳ năm trước', intro_text, 'YOY')

    if expected_month == 12:
        av_pattern = rf'bình quân(?:\s+(?:12|mười hai)\s+tháng)?\s+năm\s+{expected_year}'
    else:
        av_pattern = rf'bình quân\s+{month_label(expected_month)}\s+tháng\s+năm\s+{expected_year}'
    avg = [p for p in page.paragraphs if re.search(av_pattern, p, re.I)
           and re.search(r'\blạm phát cơ bản\b', p, re.I)
           and re.search(r'\bCPI\b', p, re.I)]
    if len(avg) != 1:
        raise ValueError(f'CPI_AVERAGE_PARAGRAPH_AMBIGUOUS_{len(avg)}')
    av = avg[0]
    cpi_ytd = one_match(r'\bCPI\s+' + MEASURE + r'\s+so với cùng kỳ', av, 'YTD')
    core = one_match(r'lạm phát cơ bản\s+' + MEASURE, av, 'CORE')
    return dict(zip(METRICS, (yoy, mom, cpi_ytd, core)))


def read_url(url: str) -> str:
    if not safe_official_url(url):
        raise ValueError('CPI_NON_OFFICIAL_URL')
    req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; CPI-Verified-Sync/1.0)',
                                'Accept': 'text/html; charset=utf-8'})
    with urlopen(req, timeout=22) as r:
        if not safe_official_url(r.geturl()):
            raise ValueError('CPI_UNEXPECTED_REDIRECT')
        if 'text/html' not in r.headers.get('Content-Type', 'text/html').lower():
            raise ValueError('CPI_NOT_HTML')
        raw = r.read(3_000_001)
        if len(raw) > 3_000_000:
            raise ValueError('CPI_PAGE_TOO_LARGE')
        return raw.decode('utf-8-sig')


def find_verified_release(year: int, month: int, fetch=read_url):
    links = set()
    failures = []
    got_index = False
    for index in INDEXES:
        try:
            links.update(candidates_from_index(fetch(index), index, year, month))
            got_index = True
        except (OSError, ValueError, UnicodeError, TimeoutError) as exc:
            failures.append(f'{index}: {type(exc).__name__}')
    if not got_index:
        raise ValueError('CPI_ALL_OFFICIAL_INDEXES_UNAVAILABLE: ' + ';'.join(failures))
    if not links:
        return None
    valid = []
    for link in sorted(links):
        try:
            p = urlsplit(link).path
            # A reported November observation is normally published in December.
            release = date(year + (month == 12), month % 12 + 1, 1)
            if f'/{release.year}/{release.month:02d}/' not in p:
                continue
            valid.append((link, article_values(fetch(link), year, month)))
        except (OSError, ValueError, UnicodeError, TimeoutError) as exc:
            failures.append(f'{link}: {type(exc).__name__}: {str(exc)[:80]}')
    if not valid:
        raise ValueError('CPI_NEW_RELEASE_NEEDS_MANUAL_REVIEW: ' + ';'.join(failures[:4]))
    all_values = [tuple(pair[1][k] for k in METRICS) for pair in valid]
    if len(set(all_values)) != 1:
        raise ValueError('CPI_OFFICIAL_RELEASES_CONFLICT')
    # Prefer dedicated CPI press item rather than monthly economy overview.
    valid.sort(key=lambda t: ('chi-so-gia-tieu-dung' not in t[0], t[0]))
    return valid[0]


def newline_for(raw: bytes) -> str:
    return '\r\n' if b'\r\n' in raw else '\n'


def build_history(old: bytes, proposal: dict[str,str], today: date) -> bytes:
    prior = old.decode('utf-8-sig')
    if not prior.endswith(('\n', '\r')):
        raise ValueError('CPI_CSV_NEEDS_TERMINAL_NEWLINE')
    with io.StringIO(prior, newline='') as inp:
        reader = csv.DictReader(inp)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError('CPI_HISTORY_SCHEMA_MISMATCH')
        rows = list(reader)
    if proposal['year_month'] != month_next(rows[-1]['year_month']):
        raise ValueError('CPI_EXPECTED_NEXT_MONTH_ONLY')
    parse_row(proposal, today)
    end = newline_for(old)
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator=end)
    writer.writerow(proposal)
    result = old + stream.getvalue().encode('utf-8')
    return result


def build_macro(old: bytes, proposal: dict[str,str]) -> bytes:
    ym = proposal['year_month'];year,month=map(int,ym.split('-'))
    last_day = date(year+(month==12),month%12+1,1) - timedelta(days=1)
    new_date = str(last_day)
    period_month = f'{month:02d}/{year}'
    period_ytd = f'{month}T/{year}'
    new_source = proposal['source_url']
    metrics = (
        ('CPI_OCT_YOY', f'CPI tháng {month}',period_month,'cpi_yoy_pct','% YoY',f'So tháng {month:02d}/{year-1}'),
        ('CPI_OCT_MOM', f'CPI tháng {month} so tháng trước',period_month,'cpi_mom_pct','% MoM','So tháng trước'),
        ('CPI_10M',f'CPI bình quân {month} tháng',period_ytd,'cpi_ytd_avg_yoy_pct','% YoY bình quân','So bình quân cùng kỳ'),
        ('CORE_CPI_10M',f'Lạm phát cơ bản bình quân {month} tháng',period_ytd,'core_ytd_avg_yoy_pct','% YoY bình quân','So bình quân cùng kỳ'),
    )
    replaces = {r[0]:r for r in metrics}
    text = old.decode('utf-8-sig')
    if not text.endswith(('\r\n','\n')):
        raise ValueError('CPI_MACRO_CSV_NEEDS_TERMINAL_NEWLINE')
    source_lines = text.splitlines(keepends=True)
    if tuple(next(csv.reader([source_lines[0]]))) != MACRO_COLUMNS:
        raise ValueError('CPI_MACRO_SCHEMA_MISMATCH')
    matched = set();out = [source_lines[0]]
    for line in source_lines[1:]:
        row = next(csv.DictReader([source_lines[0],line]))
        key=row.get('id')
        if key not in replaces:
            out.append(line)
            continue
        if key in matched:
            raise ValueError('CPI_MACRO_DUPLICATE_INDICATOR')
        matched.add(key)
        if row.get('asof', '') >= new_date:
            raise ValueError('CPI_MACRO_REGRESSION_OR_REWRITE')
        _,label,period,metric,unit,comparison=replaces[key]
        row.update(label=label,period=period,asof=new_date,value=proposal[metric],unit=unit,
                   comparison=comparison,source='Cục Thống kê',source_url=new_source,
                   note='CPI toàn quốc; dữ liệu theo kỳ công bố, không phải giá thời gian thực')
        buf=io.StringIO(newline='')
        writer=csv.DictWriter(buf,fieldnames=MACRO_COLUMNS,lineterminator=newline_for(old))
        writer.writerow(row)
        out.append(buf.getvalue())
    if matched != set(MACRO_IDS):
        raise ValueError('CPI_MACRO_INCOMPLETE_SNAPSHOT_IDS')
    return ''.join(out).encode('utf-8')


def planned_update(history_path: Path, macro_path: Path, proposal: dict[str,str], now: date):
    # All checks and both new byte strings must succeed before either file is changed.
    history_old=history_path.read_bytes();macro_old=macro_path.read_bytes()
    history_new=build_history(history_old,proposal,now)
    macro_new=build_macro(macro_old,proposal)
    # Verify complete resulting history using existing stricter UI reader.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        test_path=Path(tmp)/'cpi.csv'
        test_path.write_bytes(history_new)
        read_history(test_path,today=now)
    return history_old,history_new,macro_old,macro_new


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--history',type=Path,default=HISTORY)
    p.add_argument('--macro',type=Path,default=MACRO)
    p.add_argument('--dry-run',action='store_true')
    args=p.parse_args(argv)
    now=vietnam_today()
    history=read_history(args.history,today=now)
    last=history[-1]['month'].strftime('%Y-%m')
    target=month_next(last)
    yr,mon=map(int,target.split('-'))
    if date(yr,mon,1)>now:
        print(f'CPI_AUTO_NO_NEW_RELEASE_YET | EXPECT={target} | LAST={last}')
        return 0
    result=find_verified_release(yr,mon)
    if result is None:
        print(f'CPI_AUTO_NO_OFFICIAL_NEW_REPORT | EXPECT={target} | LAST={last}')
        return 0
    url,values=result
    row={'year_month':target,'source':'Cục Thống kê','source_url':url}
    row.update({k:f'{values[k]:.2f}' for k in METRICS})
    a,b,c,d=planned_update(args.history,args.macro,row,now)
    if args.dry_run:
        print(f'CPI_AUTO_DRY_RUN_VERIFIED | DATE={target} | URL={url}')
        return 0
    # Keep the integrity invariant: if processing fails, neither data file changes.
    args.history.write_bytes(b)
    try:
        args.macro.write_bytes(d)
    except OSError:
        # Never leave the monthly history ahead of the four macro cards locally.
        args.history.write_bytes(a)
        raise
    print('CPI_AUTO_NEW_MONTH_APPENDED | DATE='+target+' | SOURCE='+url)
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (OSError, ValueError, UnicodeError) as exc:
        print('CPI_AUTO_BLOCKED_NO_COMMIT: '+str(exc),file=sys.stderr)
        sys.exit(1)
