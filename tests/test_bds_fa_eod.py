import unittest, tempfile, csv, json
from pathlib import Path
import bds_fa as b
import bds_fa_eod as d

class DynamicBds(unittest.TestCase):
    def setUp(self):
        self.rows=d.read_rows(b.PATH); self.basis=d.read_rows(d.BASIS)
        self.prices={s:20000 for s in self.rows}
    def test_all_peers_and_financial_points(self):
        state=d.build(self.rows,self.basis,'2026-11-25',self.prices)
        self.assertEqual(state['peers'],33)
        old=b.load();self.assertTrue(all(x['coverage']==100 for x in state['results'].values()))
        for s,e in state['results'].items():
            self.assertAlmostEqual(e['values']['P/B'],20000/float(self.basis[s]['BVPS tham chiếu (VND)']))
            for k in b.WEIGHTS:
                if k not in ('P/B lịch sử','P/B ngành','P/E'):self.assertEqual(e['points'][k],old[s]['points'][k])
            self.assertEqual(e['rank'],1+sum(x['score']>e['score'] for x in state['results'].values()))
            notes=d.display_notes(e,state);self.assertLessEqual(len(notes),12);self.assertIn('25/11/2026',notes[-1]);self.assertNotIn('ngày giá ZIP chưa xác định',notes[-1])
        self.assertAlmostEqual(state['results']['HDG']['industry_pb'],sum(v['pb'] for v in state['valuations'].values())/33)
        self.assertEqual(state['results']['NTL']['points']['P/E'],0)
    def test_price_change_reprices_all(self):
        a=d.build(self.rows,self.basis,'2026-11-25',self.prices)
        p=dict(self.prices,HDG=40000)
        c=d.build(self.rows,self.basis,'2026-11-26',p)
        self.assertAlmostEqual(c['valuations']['HDG']['pb'],a['valuations']['HDG']['pb']*2)
        self.assertAlmostEqual(c['valuations']['HDG']['pe'],a['valuations']['HDG']['pe']*2)
        self.assertGreater(c['results']['VRE']['industry_pb'],a['results']['VRE']['industry_pb'])
    def test_missing_and_prior_publication(self):
        p=dict(self.prices);p.pop('HDG')
        c=d.build(self.rows,self.basis,'2026-11-25',p);self.assertNotIn('HDG',c['results']);self.assertEqual(c['peers'],32)
        self.assertEqual(d.build(self.rows,self.basis,'2026-09-30',self.prices)['results'],{})
        self.assertEqual(d.build(self.rows,self.basis,'2026-11-25',{'HDG':20000})['results'],{})
        self.assertIn('FA tham chiếu',d.display_notes(b.load()['HDG'],c,fallback=True)[-1])
    def test_eod_session_duplicate_and_units(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);e=p/'eod.csv';m=p/'meta.json'
            with e.open('w',encoding='utf-8',newline='') as f:
                w=csv.writer(f);w.writerows([['Mã','Ngày','Giá đóng cửa'],['HDG','2026-11-24',10],['HDG','2026-11-25',16.8],['VRE','25/11/2026',23],['VRE','25/11/2026',23],['VHM','2026-11-24',50]])
            m.write_text(json.dumps({'latest_date':'2026-11-25'}));day,prices=d.latest_prices(e,m)
            self.assertEqual(day,'2026-11-25');self.assertEqual(prices,{'HDG':16800})
            m.write_text(json.dumps({'latest_date':'2026-11-26'}))
            with self.assertRaises(ValueError):d.latest_prices(e,m)
    def test_basis_is_complete(self):
        for s,q in self.basis.items():
            self.assertGreater(float(q['BVPS tham chiếu (VND)']),0)
            self.assertAlmostEqual(float(q['EPS tham chiếu (VND)']),float(q['LNST công ty mẹ TTM (VND)'])/float(q['CP tham chiếu ZIP']))
            self.assertAlmostEqual(float(q['LNST công ty mẹ TTM (VND)'])/1e9,float(self.rows[s]['LNST TTM (tỷ đồng)']))
if __name__=='__main__':unittest.main()
