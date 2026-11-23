"""Offline integration and fail-closed tests for detailed national price groups."""
from __future__ import annotations

import ast
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from macro_price_pressures import read_prices, latest_for
from macro_price_trends import monthly_grid, consecutive_change, contribution_rows
from price_pressure_watch import status, look_for_report

TODAY = date(2026, 11, 24)
SOURCE_JUNE = 'chi-so-gia-tieu-dung-chi-so-gia-vang-va-chi-so-gia-do-la-my-thang-sau'
SOURCE_OCT = 'CPI-chi-so-gia-vang-va-chi-so-gia-do-la-My-thang-Muoi'

class TestPriceTrendV2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_prices(today=TODAY)

    def test_existing_five_groups_unchanged(self):
        self.assertEqual({r['category'] for r in self.rows}, {'food','fuel','power','housing','inputs'})

    def test_national_numeric_may_june_oct(self):
        for key in ('food','fuel','power','housing'):
            observed = {r['period'] for r in self.rows if r['category'] == key and r['basis'] == 'mom'}
            self.assertEqual(observed, {'05/2026','06/2026','10/2026'})

    def test_june_verified_prices(self):
        expected={'food':('-0.05','-0.01'),'fuel':('-10.05',None),
                  'power':('2.00',None),'housing':('0.46','0.10')}
        for key, (val, contrib) in expected.items():
            with self.subTest(category=key):
                r=next(r for r in self.rows if r['category']==key and r['period']=='06/2026')
                self.assertEqual(r['rate'],Decimal(val))
                self.assertEqual(r['contribution'], Decimal(contrib) if contrib else None)
                self.assertIn(SOURCE_JUNE,r['source_url'])

    def test_october_verified_prices(self):
        expected={'food':('-0.32','-0.07'),'fuel':('6.86',None),
                  'power':('-1.99',None),'housing':('0.04',None)}
        for key, (val, contrib) in expected.items():
            with self.subTest(category=key):
                r=next(r for r in self.rows if r['category']==key and r['period']=='10/2026' and r['basis']=='mom')
                self.assertEqual(r['rate'],Decimal(val))
                self.assertEqual(r['contribution'], Decimal(contrib) if contrib else None)
                self.assertIn(SOURCE_OCT,r['source_url'])

    def test_preserve_original_may_row_and_input(self):
        self.assertEqual(latest_for(self.rows,'inputs')['rate'],Decimal('5.12'))
        self.assertEqual(next(r for r in self.rows if r['category']=='food' and r['period']=='05/2026')['rate'],Decimal('-0.25'))

    def test_october_is_latest_mom_in_each_category(self):
        for key in ('food','fuel','power','housing'):
            self.assertEqual(latest_for(self.rows,key,'mom')['period'],'10/2026')

    def test_gap_july_august_september_is_explicit(self):
        for key in ('food','fuel','power','housing'):
            g=monthly_grid(self.rows,key)
            self.assertEqual([x['month'].strftime('%m/%Y') for x in g],['05/2026','06/2026','07/2026','08/2026','09/2026','10/2026'])
            self.assertEqual([x['rate'] for x in g[2:5]],[None,None,None])
            self.assertIsNone(consecutive_change(g))

    def test_non_adjacent_october_never_classified_as_momentum(self):
        g=monthly_grid(self.rows,'fuel')
        self.assertIsNone(consecutive_change(g))

    def test_consecutive_change_may_june_only(self):
        g=monthly_grid(self.rows,'food')[:2]
        self.assertEqual(consecutive_change(g),Decimal('0.20'))

    def test_only_exact_group_contributions_exposed(self):
        table=contribution_rows(self.rows)
        self.assertTrue(table)
        self.assertFalse(any(t['Nhóm'] in ('Giá xăng','Điện sinh hoạt') for t in table))
        self.assertEqual([r['Đóng góp (điểm %)'] for r in table if r['Kỳ']=='10/2026'],[-0.07])

    def test_no_factory_input_cpi_contribution(self):
        self.assertFalse(any('nguyên vật liệu' in row['Nhóm'].lower() for row in contribution_rows(self.rows)))

    def test_unknown_group_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNKNOWN_CATEGORY'):
            monthly_grid(self.rows,'diesel')

    def test_watcher_not_due_in_november(self):
        state,links,target=status(self.rows,today=date(2026,11,24),fetch=lambda _: (_ for _ in ()).throw(AssertionError('should not fetch')))
        self.assertEqual((state,links,target),('NOT_DUE',[],date(2026,11,1)))

    def test_watcher_fails_closed_when_official_unreachable(self):
        with self.assertRaisesRegex(ValueError,'UNAVAILABLE'):
            status(self.rows,today=date(2026,12,3),fetch=lambda _: (_ for _ in ()).throw(OSError('offline')))

    def test_watcher_official_index_review_only(self):
        url='https://www.nso.gov.vn/cpi-vi/'
        link='https://www.nso.gov.vn/tin-tuc-thong-ke/2026/12/chi-so-gia-tieu-dung-thang-muoi-mot-va-11-thang-nam-2026/'
        fake=f'<a href="{link}">Chỉ số giá tiêu dùng tháng Mười Một và 11 tháng năm 2026</a>'
        state,links,target=status(self.rows,today=date(2026,12,4),fetch=lambda _:fake)
        self.assertEqual((state,links,target),('REVIEW_REQUIRED',[link],date(2026,11,1)))

    def test_watcher_rejects_wrong_release_year(self):
        fake='<a href="https://www.nso.gov.vn/tin-tuc-thong-ke/2025/12/chi-so-gia-tieu-dung-thang-muoi-mot-va-11-thang-nam-2026/">Chỉ số giá tiêu dùng tháng Mười Một và 11 tháng năm 2026</a>'
        state,links=look_for_report(date(2026,11,1),fetch=lambda _:fake)
        self.assertEqual((state,links),('NO_OFFICIAL_REPORT',[]))

    def test_watcher_does_not_write_prices(self):
        body=(ROOT/'price_pressure_watch.py').read_text(encoding='utf-8').lower()
        for key in ('git push','subprocess','write_bytes','to_csv','write_text','open(data_path','subprocess.run'):
            self.assertNotIn(key,body)

    def test_workflow_read_only_permissions(self):
        y=(ROOT/'.github/workflows/price_pressure_watch.yml').read_text(encoding='utf-8')
        self.assertIn('contents: read',y)
        self.assertIn('python price_pressure_watch.py --check',y)
        self.assertNotIn('contents: write',y)

    def test_dashboard_integration_preserves_existing_page(self):
        code=(ROOT/'macro_price_pressures.py').read_text(encoding='utf-8')
        ast.parse(code)
        self.assertIn('render_price_trends(rows)',code)
        self.assertIn('st.metric(numeric[',code)
        self.assertIn('st.dataframe(pd.DataFrame(display)',code)

    def test_no_market_pipeline_mutations(self):
        content=(ROOT/'macro_price_trends.py').read_text(encoding='utf-8').lower()
        for bad in ('git push','update_eod','redis','dnse','write_bytes','to_csv('):
            self.assertNotIn(bad,content)

if __name__=='__main__':unittest.main()
