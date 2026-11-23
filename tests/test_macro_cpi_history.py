"""Offline tests for sourced CPI histories, no network and no Streamlit needed."""
import ast
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_cpi_history import (DATA_PATH, COLUMNS, METRICS, read_history,
                               parse_row, change_pp, fmt)

TODAY = max(date.today(), date(2026, 11, 24))


def source_rows():
    with DATA_PATH.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def temp_file(rows):
    tmp = tempfile.TemporaryDirectory()
    target = Path(tmp.name) / "cpi.csv"
    with target.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return tmp, target


class TestCPIHistory(unittest.TestCase):
    def test_ten_contiguous_months(self):
        rows = read_history(today=TODAY)
        self.assertGreaterEqual(len(rows), 10)
        self.assertEqual(rows[0]["month"], date(2026, 1, 1))
        self.assertGreaterEqual(rows[-1]["month"], date(2026, 10, 1))

    def test_real_latest_cpi_values(self):
        last = next(r for r in read_history(today=TODAY) if r["month"] == date(2026, 10, 1))
        self.assertEqual((last['cpi_yoy_pct'], last['cpi_mom_pct']), (Decimal('5.09'), Decimal('0.20')))
        self.assertEqual(last['cpi_ytd_avg_yoy_pct'], Decimal('4.57'))
        self.assertEqual(last['core_ytd_avg_yoy_pct'], Decimal('4.24'))

    def test_july_and_august_values(self):
        rows = read_history(today=TODAY)
        self.assertEqual(rows[6]['cpi_yoy_pct'], Decimal('4.45'))
        self.assertEqual(rows[6]['cpi_mom_pct'], Decimal('-0.12'))
        self.assertEqual(rows[7]['cpi_yoy_pct'], Decimal('4.89'))
        self.assertEqual(rows[7]['cpi_mom_pct'], Decimal('0.47'))

    def test_cpi_core_ytd_is_not_monthly_core(self):
        code = (ROOT / 'macro_cpi_history.py').read_text(encoding='utf-8')
        self.assertNotIn('core_mom_pct', code)
        self.assertNotIn('core_monthly_yoy', code)
        self.assertIn('core_ytd_avg_yoy_pct', code)

    def test_yoy_differences_are_percentage_points(self):
        r = read_history(today=TODAY)
        self.assertEqual(change_pp(r[9]['cpi_yoy_pct'], r[8]['cpi_yoy_pct']), Decimal('0.01'))
        self.assertEqual(change_pp(r[9]['cpi_mom_pct'], r[8]['cpi_mom_pct']), Decimal('-0.42'))

    def test_source_links_are_official_domain(self):
        self.assertTrue(all(r['url'].startswith('https://www.nso.gov.vn/') for r in read_history(today=TODAY)))

    def test_duplicate_month_rejected(self):
        rows = source_rows(); rows.append(rows[-1].copy())
        tmp, path = temp_file(rows)
        with tmp, self.assertRaisesRegex(ValueError, 'DUPLICATE'):
            read_history(path, TODAY)

    def test_gap_month_rejected(self):
        rows = source_rows(); del rows[5]
        tmp, path = temp_file(rows)
        with tmp, self.assertRaisesRegex(ValueError, 'GAP'):
            read_history(path, TODAY)

    def test_unsorted_month_rejected(self):
        rows = source_rows(); rows[0], rows[1] = rows[1], rows[0]
        tmp, path = temp_file(rows)
        with tmp, self.assertRaisesRegex(ValueError, 'UNSORTED'):
            read_history(path, TODAY)

    def test_future_month_rejected(self):
        row=source_rows()[-1].copy();row['year_month'] = f'{TODAY.year + 1}-01'
        with self.assertRaisesRegex(ValueError, 'FUTURE'):
            parse_row(row, TODAY)

    def test_wrong_domain_rejected(self):
        row = source_rows()[0].copy();row['source_url'] = 'https://nso.gov.vn.evil.com/fake'
        with self.assertRaisesRegex(ValueError, 'SOURCE_DOMAIN'):
            parse_row(row, TODAY)

    def test_non_https_rejected(self):
        row = source_rows()[0].copy();row['source_url'] = 'http://www.nso.gov.vn/cpi'
        with self.assertRaisesRegex(ValueError, 'SOURCE_DOMAIN'):
            parse_row(row, TODAY)

    def test_wrong_source_rejected(self):
        row = source_rows()[0].copy();row['source'] = ''
        with self.assertRaisesRegex(ValueError, 'SOURCE_MISSING'):
            parse_row(row, TODAY)

    def test_non_numeric_rejected(self):
        for bad in ('NaN','Infinity','abc','999',''):
            row=source_rows()[0].copy();row['cpi_yoy_pct']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                parse_row(row, TODAY)

    def test_coverage_for_all_metrics(self):
        self.assertTrue(all(all(isinstance(r[k],Decimal) for k in METRICS) for r in read_history(today=TODAY)))

    def test_missing_file_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'UNREADABLE'):
            read_history(Path('/missing/file_cpi_history.csv'), TODAY)

    def test_missing_schema_fails_closed(self):
        tmp = tempfile.TemporaryDirectory()
        with tmp:
            p=Path(tmp.name)/'cpi.csv';p.write_text('year_month,cpi_yoy_pct\n2026-01,2.53\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'SCHEMA'):
                read_history(p,TODAY)

    def test_invalid_month_date(self):
        row=source_rows()[0].copy();row['year_month']='2026-13'
        with self.assertRaises(ValueError):parse_row(row,TODAY)

    def test_format_vietnamese(self):
        self.assertEqual(fmt(Decimal('4.57')), '4,57')

    def test_dashboard_inflation_integration(self):
        s=(ROOT/'macro_vn_dashboard.py').read_text(encoding='utf-8')
        tree=ast.parse(s)
        inflation=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_inflation')
        body=ast.get_source_segment(s,inflation)
        self.assertIn('from macro_cpi_history import render_cpi_history',body)
        self.assertIn('render_cpi_history()',body)
        self.assertNotIn('Chưa có chuỗi CPI nhiều tháng',body)

    def test_no_market_pipelines_changed(self):
        src=(ROOT/'macro_cpi_history.py').read_text(encoding='utf-8')
        for banned in ('git push', 'update_eod', 'redis', 'dnse', 'to_csv(', 'subprocess.run'):
            self.assertNotIn(banned,src.lower() if banned!='to_csv(' else src)


if __name__ == '__main__':
    unittest.main()
