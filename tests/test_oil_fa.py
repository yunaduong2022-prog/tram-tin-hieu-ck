import unittest, json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import oil_fa as o

class OilFA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=o.read_rows();cls.snap=o.snapshot(cls.rows)
    def test_universe(self):
        self.assertEqual(sum(o.WEIGHTS.values()),100);self.assertEqual(len(self.rows),15)
        self.assertEqual(set(o.BENCH),{'oil','distribution'})
    def test_snapshot(self):
        expected={'BSR':90,'GAS':81.5,'PGD':78,'PLX':70,'OIL':56,'POS':82,'PVB':74,'PVS':70.5,'PVD':66,'PVC':39.5,'PXS':54}
        for s,v in expected.items():self.assertEqual(self.snap[s]['score'],v,s)
        for s in ('PPT','PVE','PVM','PTV'):self.assertIsNone(self.snap[s]['score'])
    def test_hist(self):
        for s,n in [('BSR',9),('PVB',10),('PVC',11)]:
            self.assertEqual(int(self.rows[s]['pe_hist_n']),n);self.assertGreater(self.snap[s]['v']['pe_hist'],0)
        self.assertIsNone(self.snap['PTV']['v']['pe_hist'])
    def test_group_benchmark(self):
        self.assertEqual(self.snap['BSR']['v']['sector_pe'],4.64);self.assertEqual(self.snap['GAS']['v']['sector_pe'],11)
        self.assertEqual(self.snap['PGD']['v']['sector_pb'],1.93)
    def test_ev(self):
        e=self.snap['BSR'];v=e['v'];self.assertAlmostEqual(v['ev'],(120676+v['debt']+v['nci']-v['cash'])/v['ebitda']);self.assertNotEqual(v['ev'],float(self.rows['BSR']['zip_ev']))
        self.assertIsNone(o.ev_of(dict(self.rows['BSR'],ebitda='-1'),120676))
        a=o.evaluate(dict(self.rows['BSR'],cash='999999'),4,1,1,4.64,1.22,'snapshot');self.assertIsNone(a['points']['ev']);self.assertIsNone(a['score'])
    def test_missing(self):
        a=o.evaluate(dict(self.rows['BSR'],cfo=''),4,1,120676,4.64,1.22,'snapshot');self.assertEqual(a['coverage'],90);self.assertIsNone(a['score'])
        self.assertEqual(self.snap['PVC']['points']['cfo_ratio'],0)
    def inputs(self):
        return {s:20000 for s in self.rows},{s:o.num(r,'zip_shares') for s,r in self.rows.items()}
    def test_dynamic(self):
        px,sh=self.inputs();a=o.dynamic(self.rows,'2026-11-27',px,sh)
        self.assertIn('GAS',a);self.assertIn('BSR',a);self.assertNotIn('PVS',a);self.assertNotIn('POS',a)
        self.assertAlmostEqual(a['GAS']['v']['pe'],px['GAS']*sh['GAS']/1e9/float(self.rows['GAS']['parent_profit']))
        self.assertEqual(a['GAS']['mode'],'eod');self.assertEqual(o.dynamic(self.rows,'2027-04-01',px,sh),{})
        sh['BSR']=1;self.assertNotIn('BSR',o.dynamic(self.rows,'2026-11-27',px,sh))
    def test_guard_rank(self):
        px,sh=self.inputs();px['PPT']=4000;px['PVE']=1500;px['PXS']=2000;px.pop('PVC');a=o.resolve(self.rows,'2026-11-27',px,sh)
        for s in ('PPT','PVE','PXS','PVC'):self.assertNotIn(s,a)
        self.assertEqual(a['PVS']['mode'],'snapshot');self.assertTrue(any('Số CP' in x for x in a['PVS']['warnings']))
        self.assertEqual(a['BSR']['ranks']['roe'],1);self.assertNotIn('margin',a['BSR']['ranks'])
        with patch.object(o,'stamp',return_value=('x',)),patch.object(o,'cached',return_value=('2026-11-27',px,a)):
            self.assertIn('dưới 9.000',o.for_symbol('PPT')[1][0]);self.assertIsNone(o.for_symbol('PPT')[0]);self.assertIn('chưa có giá',o.for_symbol('PVC')[1][0])
    def test_snapshot_expiry(self):
        px,sh=self.inputs();self.assertNotIn('PVS',o.resolve(self.rows,'2026-12-05',px,sh))
    def test_compact(self):
        px,sh=self.inputs();e=o.resolve(self.rows,'2026-11-27',px,sh)['BSR'];full=o.notes(e);c=o.compact_notes(full)
        self.assertTrue(any('TOP 1 Ngành Dầu khí' in x for x in c));self.assertTrue(any('P/E' in x and 'TB 3 năm' in x for x in c));self.assertTrue(any('không phải toàn bộ ngành' in x for x in full))
        self.assertTrue(any('10,00/10' in x for x in full));self.assertFalse(any('10,00/10' in x for x in c));self.assertTrue(any('Nghiên cứu tham khảo:' in x for x in full));self.assertFalse(any('Nghiên cứu tham khảo:' in x for x in c))
    def test_eod_duplicate_failed(self):
        with TemporaryDirectory() as d:
            e=Path(d)/'p.csv';m=Path(d)/'m.json';e.write_text('Mã,Ngày,Giá đóng cửa\nBSR,2026-11-26,24\nPVD,2026-11-26,17\nPVS,2026-11-26,27\nPVS,2026-11-26,27\nPPT,2026-11-26,4\n',encoding='utf8');m.write_text(json.dumps({'latest_date':'2026-11-26','failed':['PVD: TARGET_MISSING']}))
            self.assertEqual(o.latest_prices(e,m)[1],{'BSR':24000,'PPT':4000})
            m.write_text('{"latest_date":"2026-11-25"}');self.assertRaises(ValueError,o.latest_prices,e,m)
    def test_no_missing_fallback(self):
        with patch.object(o,'stamp',side_effect=OSError):self.assertIsNone(o.for_symbol('GAS')[0])

if __name__=='__main__':unittest.main()
