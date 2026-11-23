"""Offline tests: explicit weekly source validation, strict components, zero != unknown."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import csv
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_omo_weekly import (DATA_PATH, COLUMNS, money, parse, latest_verified_week,
                              fmt_bn, fmt_pct, repo_direction)

TODAY = date(2026, 11, 24)


def valid_row():
    with DATA_PATH.open('r', encoding='utf-8', newline='') as f:
        return next(csv.DictReader(f))


class OMOUnitTests(unittest.TestCase):
    def test_verified_week_actual_values(self):
        row = latest_verified_week(today=TODAY)
        self.assertEqual(row['repo_net'], Decimal('-10825.96'))
        self.assertEqual(row['awarded'], Decimal('22788.71'))
        self.assertEqual(row['matured'], Decimal('33614.67'))

    def test_do_not_fabricate_full_omo_net(self):
        row = latest_verified_week(today=TODAY)
        self.assertIsNone(row['full_net'])
        self.assertIsNone(row['bills_issued'])
        self.assertIsNone(row['bills_matured'])

    def test_money_blank_differs_from_zero(self):
        self.assertIsNone(money(''))
        self.assertEqual(money('0'), Decimal('0'))

    def test_bill_both_known_computes_full_net(self):
        r = valid_row(); r.update(bills_issued_bn='700', bills_matured_bn='100')
        self.assertEqual(parse(r,TODAY)['full_net'], Decimal('-11425.96'))

    def test_bill_only_one_is_not_full_net(self):
        r = valid_row(); r['bills_issued_bn']='0'
        self.assertIsNone(parse(r,TODAY)['full_net'])
        r = valid_row(); r['bills_matured_bn']='0'
        self.assertIsNone(parse(r,TODAY)['full_net'])

    def test_rate_is_omo_repo_rate_not_overnight(self):
        row = parse(valid_row(), TODAY)
        self.assertEqual(row['rate'], Decimal('4.50'))
        self.assertEqual(fmt_pct(row['rate']), '4,50%/năm')

    def test_format_and_direction(self):
        self.assertEqual(fmt_bn(Decimal('10825.96')), '10.825,96 tỷ')
        self.assertEqual(fmt_bn(None), '—')
        self.assertEqual(repo_direction(Decimal('-100')), 'Hút ròng')
        self.assertEqual(repo_direction(Decimal('100')), 'Bơm ròng')
        self.assertEqual(repo_direction(Decimal('0')), 'Cân bằng')

    def test_source_must_be_https(self):
        r = valid_row();r['source_url']='http://example.com'
        with self.assertRaises(ValueError):parse(r, TODAY)
        r = valid_row();r['crosscheck_url']='javascript:bad'
        with self.assertRaises(ValueError):parse(r, TODAY)

    def test_future_period_blocked(self):
        r=valid_row();r['end_date']='2026-12-01'
        with self.assertRaises(ValueError):parse(r, TODAY)

    def test_publication_before_end_blocked(self):
        r=valid_row();r['source_date']='2026-11-15'
        with self.assertRaises(ValueError):parse(r, TODAY)

    def test_invalid_period_range_blocked(self):
        r=valid_row();r['start_date']='2026-11-01'
        with self.assertRaises(ValueError):parse(r, TODAY)

    def test_missing_repo_component_blocked(self):
        r=valid_row();r['repo_matured_bn']=''
        with self.assertRaises(ValueError):parse(r, TODAY)

    def test_negative_and_outlier_blocked(self):
        for bad in ['-0.5','NaN','Infinity','99999999','x']:
            r=valid_row();r['repo_awarded_bn']=bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):parse(r, TODAY)

    def test_rate_bounds(self):
        r=valid_row();r['repo_rate_pct']='35'
        with self.assertRaises(ValueError):parse(r, TODAY)

    def test_old_week_stale(self):
        row=latest_verified_week(today=date(2026,12,15))
        self.assertTrue(row['stale'])
        self.assertFalse(latest_verified_week(today=TODAY)['stale'])

    def test_duplicate_week_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'data.csv'
            with out.open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=COLUMNS)
                writer.writeheader();writer.writerow(valid_row());writer.writerow(valid_row())
            self.assertIsNone(latest_verified_week(out,TODAY))

    def test_invalid_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'data.csv'
            out.write_text('start_date,end_date\n2026-11-16,2026-11-20\n',encoding='utf-8')
            self.assertIsNone(latest_verified_week(out,TODAY))

    def test_missing_file_fails_closed(self):
        self.assertIsNone(latest_verified_week(Path('/nonexistent/omo_data_123.csv'),TODAY))

    def test_latest_week_selected_without_mixing(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'data.csv'
            older=valid_row().copy()
            older['start_date']='2026-11-09';older['end_date']='2026-11-13'
            older['source_date']='2026-11-16';older['repo_awarded_bn']='500';older['repo_matured_bn']='300'
            with out.open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=COLUMNS)
                writer.writeheader();writer.writerow(older);writer.writerow(valid_row())
            self.assertEqual(latest_verified_week(out,TODAY)['repo_net'],Decimal('-10825.96'))

if __name__=='__main__':unittest.main()
