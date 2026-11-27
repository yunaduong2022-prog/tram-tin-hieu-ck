import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import shipping_fa as s
import port_fa as p
import reference_fa as rf
import steel_fa as steel
import oil_fa as oil

class Shipping(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows=s.read_rows()
    def test_weights_and_universe(self):
        self.assertEqual(sum(s.WEIGHTS.values()),100);self.assertEqual(len(self.rows),10)
        self.assertEqual(len(s.TANKER),6);self.assertEqual(len(s.CARGO),4);self.assertNotIn('PPH',rf.SYMBOLS)
        self.assertEqual(rf.SYMBOLS,p.SYMBOLS|s.SYMBOLS|steel.SYMBOLS|oil.SYMBOLS)
        self.assertFalse(oil.SYMBOLS & (p.SYMBOLS|s.SYMBOLS|steel.SYMBOLS))
        self.assertFalse(p.SYMBOLS&s.SYMBOLS)
        self.assertFalse(steel.SYMBOLS&p.SYMBOLS)
        self.assertFalse(steel.SYMBOLS&s.SYMBOLS)
        self.assertEqual(steel.SYMBOLS,frozenset("HPG TVN TIS POM VGS HSG NKG GDA DTL SMC TLH HMC".split()))
    def test_reference(self):
        a=s.results(self.rows);self.assertEqual(len(a),8)
        for k,v in {'PVT':89.6,'PVP':91.,'VTO':89.,'VIP':67.4,'GSP':63.,'HAH':90.6,'VOS':73.6,'VNA':63.2}.items():
            self.assertEqual(a[k]['score'],v);self.assertEqual(a[k]['coverage'],100)
        self.assertEqual(a['PVP']['rank'],1);self.assertEqual(a['HAH']['rank'],1)
        self.assertNotIn('PDV',a);self.assertNotIn('VST',a)
        self.assertIn('Định giá ZIP không có ngày phiên xác nhận',s.notes(a['PVT'])[0]);self.assertIn('Cảnh báo:',s.notes(a['PVT'])[1])
        self.assertTrue(any('TB 3 năm (quý)' in x for x in s.notes(a['PVT'])))
    def test_current_price_guard(self):
        prices={k:20000 for k in self.rows};shares={k:p.num(v,'shares') for k,v in self.rows.items()}
        a=s.results(self.rows,prices,shares,s.ASOF);self.assertEqual(len(a),8);self.assertEqual(a['PVT']['mode'],'eod')
        prices['PVT']=8999;shares['PVP']=100000;self.assertNotIn('PVT',s.results(self.rows,prices,shares,s.ASOF));self.assertNotIn('PVP',s.results(self.rows,prices,shares,s.ASOF))
        self.assertEqual(s.results(self.rows,prices,shares,'2027-04-01'),{})
    def test_missing(self):
        r=dict(self.rows['PVT'],cfo_ratio='');a=s.evaluate(r,s.valuation(r,18400,516918938),.85,s.ASOF,'snapshot');self.assertEqual(a['coverage'],90);self.assertIsNone(a['score'])
        self.assertEqual(s.tier('cfo_ratio',-.1),0);self.assertIsNone(s.tier('pe',-1))
    def test_failed_and_duplicate(self):
        with TemporaryDirectory() as d:
            e=Path(d)/'p.csv';m=Path(d)/'m.json';e.write_text('Mã,Ngày,Giá đóng cửa\nPVT,2026-11-26,18\nPVP,2026-11-26,16\nHAH,2026-11-26,45\nHAH,2026-11-26,45\n',encoding='utf8');m.write_text('{"latest_date":"2026-11-26","failed":["PVP: TARGET_MISSING"]}')
            self.assertEqual(s.latest_prices(e,m)[1],{'PVT':18000})
    def test_reference_total(self):
        self.assertIsNone(rf.reference_total(lambda *_:0,90,60,60,'Dài hạn',stale=True));self.assertIsNone(rf.reference_total(lambda *_:0,None,60,60,'Dài hạn'))
        self.assertEqual(rf.reference_total(lambda *x:71,90,60,60,'Dài hạn'),71)
    def test_integration_source(self):
        root=Path(__file__).resolve().parents[1]
        if not (root/'vip_picks.py').is_file():self.skipTest('requires full repository')
        import ast
        for f in ['vip_picks.py','vip_score_bridge.py','live_peer_fa.py','watchlist.py']:
            ast.parse((root/f).read_text(encoding='utf8'))
        v=(root/'vip_picks.py').read_text(encoding='utf8');b=(root/'vip_score_bridge.py').read_text(encoding='utf8');l=(root/'live_peer_fa.py').read_text(encoding='utf8');w=(root/'watchlist.py').read_text(encoding='utf8')
        self.assertIn('shipping_fa.for_symbol(code)',v);self.assertIn('port_fa.for_symbol(code)',v);self.assertIn('reference_fa").SYMBOLS',v)
        self.assertIn('shipping_fa.detail',b);self.assertIn('port_fa.detail',b);self.assertIn('reference_fa").SYMBOLS',b);self.assertIn('reference_fa.SYMBOLS',l)
        self.assertIn('"May mặc": ["VGT", "PPH"]',w);self.assertIn('"GSP", "PDV", "VNA", "VST"',w)
if __name__=='__main__':unittest.main()
