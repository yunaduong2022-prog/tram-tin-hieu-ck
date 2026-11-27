import unittest, tempfile, json
from pathlib import Path
from datetime import datetime,timezone,timedelta
import steel_fa as f
PATH=Path(__file__).resolve().parent/'steel_fa_inputs.csv'
if not PATH.exists():PATH=Path(__file__).resolve().parents[1]/'data/steel_fa_inputs.csv'
class Steel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows=f.read_rows(PATH);cls.results=f.snapshot(cls.rows)
    def test_weights(self):self.assertEqual(sum(f.WEIGHTS.values()),100)
    def test_snapshot(self):
        for s,score in {'HPG':83,'TVN':66,'VGS':59,'HSG':49.5,'HMC':49.5,'NKG':43,'GDA':44,'TIS':37.5,'POM':23,'DTL':19}.items():self.assertEqual(self.results[s]['score'],score,s)
    def test_missing(self):
        for s,cov in [('SMC',90),('TLH',97.5)]:self.assertIsNone(self.results[s]['score']);self.assertEqual(self.results[s]['coverage'],cov)
        self.assertEqual(self.results['TLH']['subtotal'],45)
    def test_loss(self):
        p=self.results['POM']['points'];self.assertEqual(p['pb_hist'],0);self.assertEqual(p['pe_hist'],0);self.assertEqual(p['roe'],0);self.assertEqual(p['debt_eq'],0)
    def test_negative_history(self):self.assertIsNone(f.valpoint(26.7,-19.8,2.5));self.assertEqual(f.valpoint(-1,-2,2.5),0)
    def test_rank(self):
        self.assertNotIn('roe',self.results['SMC']['ranks']);self.assertEqual(self.results['HPG']['ranks']['roe'],2);self.assertNotIn('margin',self.results['HPG']['ranks'])
    def test_dynamic(self):
        shares={s:float(r['shares_m'])*1e6 for s,r in self.rows.items()};prices={s:20000 for s in shares};a=f.dynamic(self.rows,'2026-11-27',prices,shares);self.assertIn('HPG',a);self.assertEqual(a['HPG']['mode'],'eod');self.assertAlmostEqual(a['HPG']['v']['pb'],20000*shares['HPG']/1e9/float(self.rows['HPG']['parent_equity']));self.assertNotEqual(a['HPG']['v']['sector_pb'],1.03)
        shares['HPG']*=1.1;self.assertNotIn('HPG',f.dynamic(self.rows,'2026-11-27',prices,shares));self.assertEqual(f.dynamic(self.rows,'2026-11-26',prices,shares),{});self.assertEqual(f.dynamic(self.rows,'2026-11-27',{'HPG':20000},shares),{})
    def test_notes(self):self.assertTrue(any('TB 3 năm' in x and 'TB ngành (ảnh)' in x for x in f.notes(self.results['HPG'])));self.assertTrue(any('Rủi ro:' in x for x in f.notes(self.results['SMC'])))
    def test_eod_reader(self):
        day=datetime.now(timezone(timedelta(hours=7))).date().isoformat()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'meta.json').write_text(json.dumps({'latest_date':day,'failed':['NKG:missing']}));(p/'eod.csv').write_text(f'Mã,Ngày,Giá đóng cửa\nHPG,{day},20\nNKG,{day},21\nVGS,{day},11\nVGS,{day},12\n',encoding='utf-8');self.assertEqual(f.latest_prices(p/'eod.csv',p/'meta.json'),(day,{'HPG':20000}))
            (p/'meta.json').write_text(json.dumps({'latest_date':'2000-01-01'}));self.assertRaises(ValueError,f.latest_prices,p/'eod.csv',p/'meta.json')
if __name__=='__main__':unittest.main()
