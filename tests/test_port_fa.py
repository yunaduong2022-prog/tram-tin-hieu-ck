import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import port_fa as p

class PortFA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows=p.read_rows(p.PATH)
    def test_universe(self):
        self.assertEqual(len(self.rows),33);self.assertEqual(sum(p.WEIGHTS.values()),100)
    def test_pb(self):
        self.assertEqual(p.pb_factor(.7,1),1);self.assertEqual(p.pb_factor(.85,1),.8);self.assertEqual(p.pb_factor(1.15,1),.6);self.assertEqual(p.pb_factor(1.30,1),.3);self.assertIsNone(p.pb_factor(0,1))
    def test_missing(self):
        self.assertIsNone(p.tier(None,'roe'));self.assertIsNone(p.tier(-1,'ev_ebitda'));self.assertIsNone(p.evaluate(self.rows['CCP'],30,1,5,1.97,p.ASOF,'snapshot')['score'])
    def test_snapshot(self):
        a=p.snapshot(self.rows);self.assertNotIn('CCP',a);self.assertNotIn('PAP',a);self.assertNotIn('CAG',a);self.assertEqual(a['CDN']['score'],92);self.assertEqual(sum(e['score'] is not None for e in a.values()),21)
        self.assertTrue(all(e['score'] is None or 0<=e['score']<=100 for e in a.values()))
    def test_rank(self):
        a=p.snapshot(self.rows);self.assertEqual(a['CDN']['rank'],1);self.assertEqual(a['ILB']['rank'],1);self.assertIn('tham khảo',p.notes(a['CDN'])[0]);self.assertEqual(p.score_grade(75),'A');self.assertEqual(p.score_grade(60),'B')
    def test_eod(self):
        prices={s:20000 for s in self.rows};shares={s:p.num(r,'shares') for s,r in self.rows.items()};a=p.dynamic(self.rows,p.ASOF,prices,shares)
        self.assertTrue(a);self.assertNotIn('GMD',a);self.assertNotIn('DXP',a);self.assertNotIn('PAP',a)
        prices['CDN']=8999;self.assertNotIn('CDN',p.dynamic(self.rows,p.ASOF,prices,shares));self.assertEqual(p.dynamic(self.rows,'2027-04-01',prices,shares),{})
    def test_duplicate_and_failed(self):
        with TemporaryDirectory() as d:
            root=Path(d);e=root/'e.csv';m=root/'m.json';e.write_text('Mã,Ngày,Giá đóng cửa\nCDN,2026-11-26,25\nDXP,2026-11-26,12\nVSC,2026-11-26,12\nVSC,2026-11-26,12\n',encoding='utf8');m.write_text('{"latest_date":"2026-11-26","failed":["DXP: PRICE_BASELINE_MISMATCH"]}')
            # pandas <2 does not implement format=mixed; ISO lines remain valid
            self.assertEqual(p.latest_prices(e,m)[1],{'CDN':25000})
    def test_source_hooks(self):
        # Test when installed in full repo; the local isolated smoke test skips absent originals.
        root=Path(__file__).resolve().parents[1]
        if not (root/'vip_picks.py').exists():return
        v=(root/'vip_picks.py').read_text(encoding='utf8');b=(root/'vip_score_bridge.py').read_text(encoding='utf8')
        self.assertIn('port_fa.for_symbol(code)',v);self.assertIn('None if is_port else total_score_for_symbol',v);self.assertIn('None if is_port else vip.total_score_for_symbol',b);self.assertIn('port_fa.detail',b)
if __name__=='__main__':unittest.main()
