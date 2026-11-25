import unittest, tempfile, csv, json
from pathlib import Path
import ck_fa as c
class CKFA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.raw=c.read_rows(c.PATH);cls.rows=c.snapshot(cls.raw)
    def test_data(self):
        self.assertEqual(len(self.rows),40);self.assertEqual(sum(c.WEIGHTS.values()),100)
        self.assertTrue(all(e['coverage']==100 and 0<=e['score']<=100 for e in self.rows.values()))
        self.assertNotIn('Tỷ lệ vốn khả dụng',c.WEIGHTS)
        self.assertEqual(self.rows['LPS']['points']['P/B lịch sử'],3)
        self.assertEqual(self.rows['HCM']['points']['Margin/VCSH'],0)
        self.assertTrue(any('đối chiếu' in w for w in self.rows['HCM']['warnings']))
        self.assertEqual(self.rows['VDS']['points']['P/E'],0)
        self.assertTrue(all(len(c.notes(e))<=12 for e in self.rows.values()))
    def test_weights_and_boundaries(self):
        for v,expected in [(0,.6),(29.99,.6),(30,.8),(60,1),(120,1),(120.01,.8),(150,.8),(150.01,.4),(180,.4),(180.01,.2),(200,.2),(200.01,0)]:self.assertEqual(c.margin_factor(v),expected)
        self.assertIsNone(c.margin_factor(None));self.assertIsNone(c.margin_factor(-1))
        self.assertEqual(c.pb_factor(.7,1),1);self.assertEqual(c.pb_factor(.85,1),.8);self.assertEqual(c.pb_factor(1.15,1),.6);self.assertEqual(c.pb_factor(1.30,1),.3);self.assertEqual(c.pb_factor(1.31,1),.1)
        self.assertEqual(c.growth(1,-1)[0],.6);self.assertEqual(c.growth(-1,-2)[0],0)
        self.assertIsNone(c.growth(1,None)[0])
        for ratio,p in [(50,15),(40,12),(30,9),(20,6),(10,3),(9.9,0)]:
            raw=dict(self.raw['SSI']);raw['VCSH/TTS (%)']=ratio
            self.assertEqual(c.evaluate(raw,1,10,1)['points']['VCSH/TTS'],p)
    def test_eod_reprice(self):
        prices={s:float(r['BVPS tham chiếu (đ)']) for s,r in self.raw.items()}
        a=c.build(self.raw,'2026-11-25',prices)
        self.assertEqual(a['peers'],40);self.assertAlmostEqual(a['results']['SSI']['industry'],1)
        prices['SSI']*=2;b=c.build(self.raw,'2026-11-26',prices)
        self.assertAlmostEqual(b['results']['SSI']['v']['P/B'],2)
        self.assertAlmostEqual(b['results']['SSI']['industry'],41/40)
        self.assertAlmostEqual(b['results']['SSI']['v']['P/E'],2*a['results']['SSI']['v']['P/E'])
        self.assertLess(b['results']['SSI']['score'],a['results']['SSI']['score'])
        for k in c.WEIGHTS:
            if k not in ('P/B lịch sử','P/B ngành','P/E'):self.assertEqual(a['results']['SSI']['points'][k],b['results']['SSI']['points'][k])
        self.assertTrue(any('2026-11-26' in n for n in c.notes(b['results']['SSI'],b)))
    def test_missing_and_dates(self):
        prices={s:10000 for s in self.raw};prices.pop('SSI')
        a=c.build(self.raw,'2026-11-25',prices);self.assertNotIn('SSI',a['results']);self.assertEqual(a['peers'],39)
        self.assertFalse(c.build(self.raw,'2026-09-30',prices)['results'])
        self.assertFalse(c.build(self.raw,'2026-11-25',{'SSI':10000})['results'])
        raw=dict(self.raw['SSI']);raw['ROA TTM (%)']='';self.assertIsNone(c.evaluate(raw,1,10,1)['score'])
        self.assertIn('không xếp hạng EOD',c.notes(self.rows['SSI'])[-1])
    def test_same_session_and_duplicates(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);e=p/'e.csv';m=p/'m.json'
            with e.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f);w.writerow(['Mã','Ngày','Giá đóng cửa']);w.writerows([['SSI','2026-11-25',20],['VND','24/11/2026',13],['VIX','25/11/2026',12],['VIX','25/11/2026',13]])
            m.write_text(json.dumps({'latest_date':'2026-11-25'}));day,px=c.latest_prices(e,m)
            self.assertEqual(day,'2026-11-25');self.assertEqual(px,{'SSI':20000})
            m.write_text(json.dumps({'latest_date':'2026-11-24'}))
            with self.assertRaises(ValueError):c.latest_prices(e,m)
    def test_snapshot_exports(self):
        with (c.PATH.parent/'ck_fa_rankings.csv').open(encoding='utf-8-sig') as f:
            data=list(csv.DictReader(f))
        self.assertEqual(len(data),40)
        for r in data:self.assertEqual(float(r['FA /100']),self.rows[r['Mã']]['score']);self.assertEqual(int(r['Hạng']),self.rows[r['Mã']]['rank'])
        with (c.PATH.parent/'ck_fa_top5.csv').open(encoding='utf-8-sig') as f:
            top=list(csv.DictReader(f))
        self.assertEqual({(r['Chỉ tiêu'],r['Mã'],int(r['Hạng'])) for r in top},{(k,s,n) for s,e in self.rows.items() for k,n in e['ranks'].items() if n<=5})
if __name__=='__main__':unittest.main()
