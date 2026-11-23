"""Read-only official CPI release monitor for detailed national price groups.

Never scrapes numerical subgroup prices for automatic commit. The official CPI
article layout varies across months. New reports are flagged for human source
review; this script has no write path to the repository.
"""
from __future__ import annotations

import argparse
from datetime import date
import os
from urllib.parse import urlsplit

from macro_cpi_auto import INDEXES, candidates_from_index, read_url
from macro_price_pressures import read_prices


def next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def monitored_month(rows: list[dict]) -> date:
    cats = {'food', 'fuel', 'power', 'housing'}
    last_by_category = {}
    for cat in cats:
        dates = [r['date'] for r in rows if r['category'] == cat and r['basis'] == 'mom']
        if not dates:
            raise ValueError('PRICE_WATCH_MISSING_MONTHLY_CATEGORY_'+cat)
        last_by_category[cat] = max(dates)
    return min(last_by_category.values())


def look_for_report(month: date, *, fetch=read_url) -> tuple[str, list[str]]:
    links: set[str] = set()
    accessible = 0
    errors = []
    publication = next_month(month)
    for index in INDEXES:
        try:
            page = fetch(index)
            accessible += 1
            for url in candidates_from_index(page, index, month.year, month.month):
                if f'/{publication.year}/{publication.month:02d}/' in urlsplit(url).path:
                    links.add(url)
        except (OSError, ValueError, UnicodeError, TimeoutError) as exc:
            errors.append(type(exc).__name__)
    if not accessible:
        raise ValueError('PRICE_WATCH_OFFICIAL_INDEXES_UNAVAILABLE: ' + ','.join(errors))
    if not links:
        return 'NO_OFFICIAL_REPORT', []
    return 'REVIEW_REQUIRED', sorted(links)


def status(rows: list[dict], *, today: date, fetch=read_url) -> tuple[str, list[str], date]:
    target = next_month(monitored_month(rows))
    if target >= date(today.year, today.month, 1):
        return 'NOT_DUE', [], target
    state, links = look_for_report(target, fetch=fetch)
    return state, links, target


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    if not args.check:
        ap.error('This tool is read-only; pass --check')
    from zoneinfo import ZoneInfo
    from datetime import datetime
    today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    rows = read_prices(today=today)
    state, links, month = status(rows, today=today)
    label = month.strftime('%Y-%m')
    if state == 'NOT_DUE':
        msg = f'PRICE_WATCH_NOT_DUE | MONTH={label}'
    elif state == 'NO_OFFICIAL_REPORT':
        msg = f'PRICE_WATCH_NO_OFFICIAL_REPORT | MONTH={label} | NO_CSV_WRITE'
    else:
        msg = f'PRICE_WATCH_MANUAL_REVIEW_REQUIRED | MONTH={label} | SOURCES={len(links)} | NO_CSV_WRITE'
    print(msg)
    for link in links:
        print('PRICE_WATCH_OFFICIAL_SOURCE: '+link)
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write('## Vietnam national price-pressure report check\n\n')
            f.write(msg + '\n\n')
            for link in links:
                f.write('- '+link+'\n')
            f.write('\n**No numbers were imported or committed. Manual subgroup verification is required.**\n')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, UnicodeError, TimeoutError) as exc:
        print('PRICE_WATCH_BLOCKED_NO_WRITE: '+str(exc))
        raise SystemExit(1)
