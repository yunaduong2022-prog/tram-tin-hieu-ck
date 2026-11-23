"""Offline source/basis/contribution tests; no network or external services."""
import ast
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_price_pressures import (DATA_PATH, COLUMNS, read_prices, parse_price_row,
                                   latest_for, fmt, GROUPS)

TODAY = date(2026, 11, 24)


def source_rows():
    with DATA_PATH.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def temporary(rows):
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / 'price.csv'
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)
    return tmp, path


class TestNationalPriceEvidence(unittest.TestCase):
    def test_official_rows_and_five_categories(self):
        rows = read_prices(today=TODAY)
        self.assertEqual(set(r['category'] for r in rows), {x[0] for x in GROUPS})
        self.assertEqual(len(rows), 6)

    def test_food_national_may(self):
        r = latest_for(read_prices(today=TODAY), 'food')
        self.assertEqual((r['rate'],r['contribution'],r['basis']),
                         (Decimal('-0.25'),Decimal('-0.06'),'mom'))

    def test_housing_contribution_is_own_group(self):
        r = latest_for(read_prices(today=TODAY), 'housing')
        self.assertEqual(r['contribution'],Decimal('0.22'))
        self.assertEqual(r['contribution_scope'],'same_group')

    def test_fuel_does_not_inherit_transport_contribution(self):
        r = latest_for(read_prices(today=TODAY),'fuel','mom')
        self.assertEqual(r['rate'],Decimal('2.12'))
        self.assertIsNone(r['contribution'])

    def test_electric_does_not_inherit_housing_contribution(self):
        self.assertIsNone(latest_for(read_prices(today=TODAY),'power')['contribution'])

    def test_material_input_is_not_cpi(self):
        r=latest_for(read_prices(today=TODAY),'inputs')
        self.assertEqual((r['rate'],r['basis'],r['contribution_scope']),
                         (Decimal('5.12'),'ytd_yoy','not_cpi'))
        self.assertIsNone(r['contribution'])

    def test_october_fuel_is_only_qualitative(self):
        r=latest_for(read_prices(today=TODAY),'fuel')
        self.assertEqual(r['period'],'10/2026')
        self.assertIsNone(r['rate'])
        self.assertEqual(r['basis'],'qualitative')

    def test_prohibits_fake_fuel_contribution(self):
        r=source_rows()[1].copy();r['contribution_pp']='0.08'
        with self.assertRaisesRegex(ValueError,'ATTRIBUTION'):
            parse_price_row(r,today=TODAY)

    def test_prohibits_fake_electric_contribution(self):
        r=source_rows()[2].copy();r['contribution_pp']='0.22'
        with self.assertRaisesRegex(ValueError,'ATTRIBUTION'):
            parse_price_row(r,today=TODAY)

    def test_prohibits_input_as_cpi(self):
        r=source_rows()[4].copy();r['contribution_scope']='same_group'
        with self.assertRaisesRegex(ValueError,'INPUTS'):
            parse_price_row(r,today=TODAY)

    def test_non_official_domain_rejected(self):
        r=source_rows()[0].copy();r['source_url']='https://www.nso.gov.vn.fake.com/price'
        with self.assertRaisesRegex(ValueError,'SOURCE'):
            parse_price_row(r,today=TODAY)

    def test_http_rejected(self):
        r=source_rows()[0].copy();r['source_url']='http://www.nso.gov.vn/price'
        with self.assertRaisesRegex(ValueError,'SOURCE'):
            parse_price_row(r,today=TODAY)

    def test_future_month_rejected(self):
        r=source_rows()[0].copy();r['period']='12/2026';r['asof']='2026-12-31'
        with self.assertRaisesRegex(ValueError,'FUTURE'):
            parse_price_row(r,today=TODAY)

    def test_period_mismatch_rejected(self):
        r=source_rows()[0].copy();r['asof']='2026-06-30'
        with self.assertRaisesRegex(ValueError,'MISMATCH'):
            parse_price_row(r,today=TODAY)

    def test_missing_numeric_blocked(self):
        r=source_rows()[0].copy();r['rate_pct']=''
        with self.assertRaisesRegex(ValueError,'REQUIRED'):
            parse_price_row(r,today=TODAY)

    def test_qualitative_cannot_carry_rate(self):
        r=source_rows()[-1].copy();r['rate_pct']='2.12'
        with self.assertRaisesRegex(ValueError,'QUALITATIVE'):
            parse_price_row(r,today=TODAY)

    def test_nan_rejected(self):
        r=source_rows()[0].copy();r['rate_pct']='NaN'
        with self.assertRaisesRegex(ValueError,'BAD'):
            parse_price_row(r,today=TODAY)

    def test_duplicate_same_category_period_basis_rejected(self):
        rows=source_rows();rows.append(rows[0].copy())
        tmp,path=temporary(rows)
        with tmp,self.assertRaisesRegex(ValueError,'DUPLICATE'):
            read_prices(path,today=TODAY)

    def test_missing_category_rejected(self):
        rows=[r for r in source_rows() if r['category']!='power']
        tmp,path=temporary(rows)
        with tmp,self.assertRaisesRegex(ValueError,'MISSING_GROUP'):
            read_prices(path,today=TODAY)

    def test_reject_schema_change(self):
        rows=source_rows();rows[0].pop('contribution_scope')
        with self.assertRaisesRegex(ValueError,'SCHEMA'):
            parse_price_row(rows[0],today=TODAY)

    def test_pct_format(self):
        self.assertEqual(fmt(Decimal('-0.25')),'-0,25%')
        self.assertEqual(fmt(None),'—')

    def test_dashboard_integration(self):
        src=(ROOT/'macro_vn_dashboard.py').read_text(encoding='utf-8')
        tree=ast.parse(src)
        f=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_inflation')
        body=ast.get_source_segment(src,f)
        self.assertIn('render_price_pressures()',body)
        self.assertIn('render_cpi_history()',body)

    def test_no_market_pipeline_mutations(self):
        s=(ROOT/'macro_price_pressures.py').read_text(encoding='utf-8').lower()
        for forbidden in ('git push','subprocess','write_bytes','to_csv','redis','dnse','update_eod'):
            self.assertNotIn(forbidden,s)

if __name__=='__main__': unittest.main()
