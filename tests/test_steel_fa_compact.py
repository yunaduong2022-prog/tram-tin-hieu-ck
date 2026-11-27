import unittest
import steel_fa as s
import reference_fa as ref
import port_fa as p
from unittest.mock import patch

class CompactSteel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=s.read_rows(s.PATH); cls.results=s.snapshot(cls.rows)
    def test_hpg(self):
        e=self.results['HPG']; full=s.notes(e); compact=ref.compact_notes(full)
        self.assertEqual(e['score'],83)
        self.assertTrue(any('8,00/10' in x for x in full))
        self.assertTrue(any('ROE 19,95% – Tốt | TOP 2 nhóm khảo sát'==x for x in compact))
        self.assertTrue(any('P/B 1,13x' in x and 'TB 3 năm: 1,53' in x and 'TB ngành: 1,03' in x for x in compact))
        self.assertTrue(any('P/E 6,12x' in x and 'TB ngành: 6,45' in x for x in compact))
        self.assertFalse(any('8,00/10' in x or x.startswith('Định giá:') or x.startswith('FA tham khảo |') for x in compact))
    def test_date(self):
        full=s.notes(self.results['HPG'])
        self.assertIn('27/11/2026',full[0]);self.assertIn('chưa xác nhận phiên giá',full[0])
        with patch.object(s,'lookup',return_value=(self.results['HPG'],full)):
            self.assertIn('27/11/2026',s.detail('HPG'))
    def test_missing_and_risk(self):
        for code in ('SMC','TLH'):
            e=self.results[code];c=ref.compact_notes(s.notes(e))
            self.assertIsNone(e['score']);self.assertTrue(any(x.startswith('Chưa đủ dữ liệu FA:') for x in c));self.assertTrue(any(x.startswith('Rủi ro:') for x in c))
        self.assertTrue(any('thiếu tham chiếu' in x for x in ref.compact_notes(s.notes(self.results['TLH']))))
    def test_other_industries(self):
        for tags in ([],None,['FA tham khảo | BCTC Q3/2026','Cảnh báo: ví dụ','P/B 1,50 lần | TB 3N (ảnh): 1,00']):
            self.assertEqual(ref.compact_notes(tags),p.compact_notes(tags))
    def test_eod_provenance(self):
        sh={k:float(r['shares_m'])*1e6 for k,r in self.rows.items()};px={k:20000 for k in sh}
        e=s.dynamic(self.rows,'2026-11-27',px,sh)['HPG'];full=s.notes(e);c=ref.compact_notes(full)
        self.assertIn('EOD ước tính 2026-11-27',full[0]);self.assertTrue(any('TB nhóm EOD' in x for x in c))
    def test_price_guard(self):
        with patch.object(s,'stamp',return_value=('x',)),patch.object(s,'ref_cached',return_value=self.results),patch.object(s,'eod_cached',return_value=('2026-11-26',{'TVN':8600},{})):
            self.assertIsNone(s.for_symbol('TVN')[0]);self.assertIn('dưới 9.000',s.for_symbol('TVN')[1][0])
        with patch.object(s,'stamp',return_value=('x',)),patch.object(s,'ref_cached',return_value=self.results),patch.object(s,'eod_cached',return_value=('2026-11-26',{'TVN':9000},{})):
            self.assertEqual(s.for_symbol('TVN')[0],66)
