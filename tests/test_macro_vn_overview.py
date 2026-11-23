"""Standard-library unit tests; no network, Streamlit, pandas, or credentials."""
from datetime import date
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_vn_overview import (as_date, old, last, fmt, gdp_yoy_trend,
                               build_overview, _card_html)

TODAY = date(2026, 11, 24)
URL = 'https://sbv.gov.vn/vi/test'


def row(key, day, value, unit='% YoY', period='11/2026', label=None, source='Nguồn kiểm chứng'):
    return {'id': key, 'label': label or key, 'group':'macro', 'period':period,
            'asof':day, 'value':value, 'unit':unit, 'source':source,
            'source_url':URL, 'comparison':'Theo kỳ', 'note':''}


def fixture():
    return [
        row('GDP_Q','2026-03-31',8.15, period='Q1/2026'),
        row('GDP_Q','2026-06-30',8.81, period='Q2/2026'),
        row('GDP_Q','2026-09-30',9.95, period='Q3/2026'),
        row('IIP_10M','2026-10-31',12.40, period='10T/2026'),
        row('CPI_OCT_YOY','2026-10-31',5.09, period='10/2026'),
        row('CORE_CPI_10M','2026-10-31',4.24, period='10T/2026'),
        row('INTERBANK_ON','2026-08-07',5.97, unit='%/năm',period='07/08/2026'),
        row('INTERBANK_ON','2026-11-20',5.26, unit='%/năm',period='20/11/2026'),
        row('CREDIT_YTD','2026-11-13',13.26,unit='% YTD',period='13/11/2026'),
        row('USDVND_CENTRAL','2026-11-23',25668,unit='VND/USD',period='23/11/2026'),
        row('PUBLIC_INV_10M','2026-10-31',74.10,unit='% kế hoạch TTCP',period='10T/2026'),
    ]


class TestMacroSmartOverview(unittest.TestCase):
    def test_four_pillars(self):
        m = build_overview(fixture(), TODAY)
        self.assertEqual(len(m['pillars']), 4)
        self.assertEqual(len(m['source_rows']), 8)
        self.assertEqual(m['missing'], [])

    def test_gdp_yoy_trend_only_three_consecutive_quarters(self):
        self.assertIn('tăng qua 3 quý', gdp_yoy_trend(fixture(), TODAY))

    def test_no_cycle_claim_with_two_quarters(self):
        rows = [r for r in fixture() if r['period'] != 'Q2/2026']
        self.assertIn('Chưa đủ 3 quý', gdp_yoy_trend(rows, TODAY))

    def test_current_date_gap_without_same_year_gdp(self):
        rows = [row('GDP_Q','2025-12-31',7.1,period='Q4/2025')]
        self.assertIn('Chưa đủ', gdp_yoy_trend(rows, TODAY))

    def test_latest_not_cross_id(self):
        m = build_overview(fixture(), TODAY)
        self.assertEqual(m['records']['INTERBANK_ON']['value'], 5.26)
        self.assertEqual(m['records']['USDVND_CENTRAL']['value'], 25668)
        self.assertEqual(m['pillars'][3]['name'], 'Quốc tế & tỷ giá')
        self.assertIn('khác', m['pillars'][3]['evidence'])

    def test_no_auto_policy_direction(self):
        m = build_overview(fixture(), TODAY)
        self.assertIn('Thiếu OMO', m['pillars'][2]['limit'])
        self.assertNotIn('nới lỏng', m['pillars'][2]['status'])

    def test_observations_do_not_mix_periods(self):
        m = build_overview(fixture(), TODAY)
        self.assertIn('bình quân', m['pillars'][1]['evidence'])
        self.assertIn('13/11/2026', m['pillars'][2]['metrics'][1][2])

    def test_date_windows_differ(self):
        self.assertFalse(old(row('INTERBANK_ON','2026-11-20',5.26), TODAY))
        self.assertTrue(old(row('INTERBANK_ON','2026-11-10',5.26), TODAY))
        self.assertFalse(old(row('CREDIT_YTD','2026-11-13',13.26), TODAY))

    def test_future_and_invalid_rates_rejected(self):
        rows = fixture()+[row('INTERBANK_ON','2026-12-01',9.99), row('INTERBANK_ON','2026-11-23',float('nan'))]
        self.assertEqual(last(rows, 'INTERBANK_ON', TODAY)['value'], 5.26)

    def test_empty_data_fails_closed(self):
        m = build_overview([], TODAY)
        self.assertEqual(len(m['missing']), 8)
        self.assertTrue(all(x['status'] != 'Có dữ liệu theo kỳ' for x in m['pillars']))

    def test_duplicate_same_day_fails_closed(self):
        rows = [row('INTERBANK_ON', '2026-11-20', 5.26),
                row('INTERBANK_ON', '2026-11-20', 5.87)]
        self.assertIsNone(last(rows, 'INTERBANK_ON', TODAY))

    def test_gdp_old_cannot_claim_current_trend(self):
        self.assertIn('quá kỳ', gdp_yoy_trend(fixture(), date(2027, 4, 1)))

    def test_no_source_discarded(self):
        r = row('GDP_Q','2026-09-30',9.95, period='Q3/2026',source='')
        self.assertIsNone(last([r], 'GDP_Q', TODAY))

    def test_number_format(self):
        self.assertEqual(fmt(row('USDVND_CENTRAL','2026-11-23',25668)), '25.668 VND/USD')
        self.assertIn('5,26', fmt(row('INTERBANK_ON','2026-11-20',5.26,unit='%/năm')))

    def test_html_escaped(self):
        model = build_overview(fixture(), TODAY)['pillars'][0]
        model['name'] = '<script>hello</script>'
        html = _card_html(model)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_naive_timestamp_handled(self):
        self.assertEqual(as_date('2026-11-23 00:00:00'), date(2026,11,23))
        self.assertIsNone(as_date('invalid'))

    def test_data_stale_warning(self):
        m = build_overview(fixture(), date(2026,12,20))
        self.assertIn('Lãi suất qua đêm', m['outdated'])
        self.assertIn('Tỷ giá trung tâm', m['outdated'])


if __name__ == '__main__':
    unittest.main()
