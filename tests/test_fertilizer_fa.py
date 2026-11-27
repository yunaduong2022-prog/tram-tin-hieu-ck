import unittest, tempfile, json
from pathlib import Path
import fertilizer_fa as f
class Fertilizer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows=f.read_rows();cls.px={s:round(float(r['cap'])*1e9/float(r['shares'])) for s,r in cls.rows.items()};cls.shares={s:float(r['shares']) for s,r in cls.rows.items()}
    def test_universe(self):self.assertEqual(set(self.rows),{'DCM','DPM','BFC','DDV'});self.assertEqual(f.EXCLUDED,{'LAS','SFG','VAF'});self.assertNotIn('CSV',f.SYMBOLS)
    def test_weights(self):self.assertEqual(sum(f.WEIGHTS.values()),100)
    def test_snapshot(self):self.assertEqual({s:e['score'] for s,e in f.snapshot(self.rows).items()},{'DCM':88.5,'DPM':80.5,'BFC':51,'DDV':68})
    def test_excluded(self):
        for s in f.EXCLUDED:self.assertIsNone(f.for_symbol(s)[0]);self.assertIn('loại khỏi V1',' '.join(f.for_symbol(s)[1]))
    def test_dynamic(self):
        res=f.resolve(self.rows,f.ASOF,self.px,self.shares);self.assertEqual(set(res),f.SCORED);self.assertTrue(all(x['coverage']==100 and x['mode']=='eod' for x in res.values()))
        self.assertAlmostEqual(res['DPM']['v']['pe'],self.px['DPM']*self.shares['DPM']/1e9/float(self.rows['DPM']['parent_profit']))
    def test_three_peers(self):
        p=dict(self.px);p['DDV']=8999;res=f.resolve(self.rows,f.ASOF,p,self.shares);self.assertEqual(len(res),3);self.assertNotIn('DDV',res);self.assertIn('TB 3 mã EOD',' '.join(f.notes(res['DPM'])))
    def test_bad_shares(self):
        sh=dict(self.shares);sh['DPM']=391400000;res=f.resolve(self.rows,'2026-11-30',self.px,sh);self.assertNotIn('DPM',res)
    def test_snapshot_date(self):
        self.assertTrue(f.resolve(self.rows,f.ASOF,self.px,{}));self.assertEqual(f.resolve(self.rows,'2026-11-30',self.px,{}),{})
    def test_snapshot_bad_price(self):
        p=dict(self.px);p['DPM']*=2;self.assertNotIn('DPM',f.resolve(self.rows,f.ASOF,p,{}))
    def test_expiry(self):self.assertEqual(f.resolve(self.rows,'2027-04-01',self.px,self.shares),{})
    def test_missing(self):
        r=dict(self.rows['DCM'],cfo='');e=f.evaluate(r,5,1,16000,*f.BENCH,'snapshot');self.assertIsNone(e['score']);self.assertEqual(e['coverage'],90)
    def test_rank_scope(self):
        e=f.ranked(f.snapshot(self.rows));self.assertEqual(e['DCM']['ranks']['roe'],(1,4));self.assertNotIn('margin',e['BFC']['ranks']);self.assertEqual(e['DCM']['ranks']['margin'],(1,2))
    def test_notes(self):
        e=f.ranked(f.snapshot(self.rows))['DDV'];s=' '.join(f.compact_notes(f.notes(e)));self.assertIn('CFO/LNST dưới 50%',s);self.assertIn('TB Phân bón & BVTV',s);self.assertNotIn('Chi tiết:',s);self.assertIn('TOP 1/4',s)
    def test_dpm_shares(self):self.assertEqual(self.shares['DPM'],679925021)
    def test_eod_guard(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'e.csv').write_text('Mã,Ngày,Giá đóng cửa\nDCM,2026-11-27,30\nDPM,2026-11-27,18\n',encoding='utf8');(p/'m.json').write_text(json.dumps({'latest_date':'2026-11-27','failed':['DPM: TARGET_MISSING']}));day,px=f.latest_prices(p/'e.csv',p/'m.json');self.assertEqual(px,{'DCM':30000})
if __name__=='__main__':unittest.main()
