import unittest
import retail_fa as f

class RetailTests(unittest.TestCase):
    def test_scores(self):
        expected={'MWG':84,'DGW':79.5,'MSN':74.5,'PNJ':63,'FRT':60,'PET':40.5}
        self.assertEqual(sum(f.WEIGHTS.values()),100)
        self.assertEqual({s:e['score'] for s,e in f.all_scores().items()},expected)
        for s,score in expected.items():
            actual,tags=f.for_symbol(s)
            self.assertEqual(actual,score)
            self.assertIn('28/11/2026',' '.join(tags))
            self.assertTrue(any('Định giá: snapshot' in x for x in f.compact_notes(tags)))
    def test_missing_not_zero(self):
        row=dict(f.all_scores()['MWG']['raw'],roe='')
        e=f.evaluate(row);self.assertIsNone(e['score']);self.assertEqual(e['coverage'],90)
    def test_frt(self):
        e=f.all_scores()['FRT'];self.assertTrue(e['substituted']);self.assertEqual(e['v']['positive_pe_count'],8)
        self.assertAlmostEqual(e['ph'],65.29,places=1)
        row=dict(e['raw'],positive_pe_count='0');self.assertIsNone(f.evaluate(row)['score'])
    def test_msn_and_ranks(self):
        self.assertEqual(f.all_scores()['MSN']['v']['sector_pe'],12.9)
        self.assertIn('TB ngành Đa ngành',' '.join(f.for_symbol('MSN')[1]))
        self.assertNotIn('TOP ',' '.join(f.compact_notes(f.for_symbol('MSN')[1])))
    def test_no_unknown_score(self):self.assertEqual(f.for_symbol('ZZZ'),(None,[]))
    def test_date(self):
        with self.assertRaises(ValueError):f.evaluate(dict(f.all_scores()['MWG']['raw'],pub='2026-11-29'))
    def test_reference_route_if_installed(self):
        from pathlib import Path
        if not Path('reference_fa.py').exists():self.skipTest('repo integration not in standalone package')
        import reference_fa
        self.assertTrue(f.SYMBOLS <= reference_fa.SYMBOLS)
        self.assertEqual(reference_fa.compact_notes(f.for_symbol('MWG')[1]),f.compact_notes(f.for_symbol('MWG')[1]))
        for s in f.SYMBOLS:self.assertEqual(reference_fa.score_grade(f.for_symbol(s)[0]),'A' if s in ('MWG','DGW') else 'C' if s=='PET' else 'B')
if __name__=='__main__':unittest.main()
