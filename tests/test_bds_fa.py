import unittest
import bds_fa as b

class BdsFA(unittest.TestCase):
    def test_data_and_scores(self):
        rows=b.load(); self.assertEqual(set(rows),b.SYMBOLS)
        self.assertEqual(sum(b.WEIGHTS.values()),100)
        self.assertTrue(all(r['coverage']==100 and 0<=r['score']<=100 for r in rows.values()))
        self.assertAlmostEqual(rows['VRE']['industry_pb'],1.2360500618333334)
        self.assertEqual(rows['VRE']['score'],89.4); self.assertEqual(rows['HDG']['score'],89.8)
        self.assertEqual(rows['NBB']['points']['Nợ vay/VCSH'],0)
        self.assertEqual(rows['NTL']['points']['P/E'],0)
        self.assertEqual(rows['NVL']['points']['Tăng trưởng LNST'],6)
        self.assertEqual(rows['LDG']['points']['Tăng trưởng LNST'],6)
        self.assertEqual(rows['VRE']['points']['HTK'],10)
        self.assertEqual(rows['VRE']['points']['MNTTT'],6)
        self.assertEqual(rows['VHM']['points']['MNTTT'],9)
        self.assertEqual(rows['KDH']['points']['HTK'],3)
        self.assertEqual(rows['KDH']['points']['MNTTT'],6.5)
        self.assertTrue(all(len(b.notes(e))<=12 for e in rows.values()))
        self.assertTrue(all(e['project']['MNTTT tỷ'] is not None for e in rows.values()))
        self.assertEqual(rows['VHM']['ranks']['ROE'],1)
        self.assertTrue(any('TOP 1 Ngành BĐS' in t for t in b.notes(rows['VHM'])))
        self.assertTrue(any('CFO TTM âm' in t for t in b.notes(rows['HHS'])))
        self.assertTrue(all(b.for_symbol(s)[0]==r['score'] for s,r in rows.items()))
    def test_equity_weight_and_ranking(self):
        import csv
        rows=b.load()
        self.assertEqual(b.WEIGHTS['VCSH/TTS'],10)
        self.assertEqual(b.WEIGHTS['Nợ vay/VCSH'],10)
        self.assertEqual((b.WEIGHTS['P/B lịch sử'],b.WEIGHTS['P/B ngành'],b.WEIGHTS['P/E']),(4,4,2))
        with b.PATH.open(encoding='utf-8-sig',newline='') as f:
            for raw in csv.DictReader(f):
                e=rows[raw['Mã']]
                expected=float(raw['VCSH Q3 (tỷ)'])/float(raw['Tổng tài sản Q3 (tỷ)'])*100
                self.assertAlmostEqual(e['values']['VCSH/TTS'],expected)
                points=next((p for threshold,p in ((50,10),(40,8),(30,6),(20,4),(10,2)) if expected>=threshold),0)
                self.assertEqual(e['points']['VCSH/TTS'],points)
                self.assertEqual(e['ranks']['VCSH/TTS'],1+sum(other['values']['VCSH/TTS']>expected for other in rows.values()))
                self.assertTrue(any('VCSH/Tổng tài sản' in n for n in b.notes(e)))
                self.assertTrue(any('Hạng ' in n for n in b.notes(e)))
                if e['warnings']:self.assertTrue(any('Cảnh báo:' in n for n in b.notes(e)))
                self.assertAlmostEqual(e['score'],sum(e['points'].values()))
        with (b.PATH.parent/'bds_fa_rankings.csv').open(encoding='utf-8-sig',newline='') as f:
            rankings=list(csv.DictReader(f))
        self.assertEqual(len(rankings),33)
        for r in rankings:
            e=rows[r['Mã']]; self.assertEqual(float(r['FA /100']),e['score']);self.assertEqual(float(r['VCSH/TTS điểm']),e['points']['VCSH/TTS']); self.assertEqual(int(r['Hạng']),e['rank'])
        with (b.PATH.parent/'bds_fa_top5.csv').open(encoding='utf-8-sig',newline='') as f:
            top=[r for r in csv.DictReader(f) if r['Chỉ tiêu']=='VCSH/TTS']
        self.assertEqual({r['Mã'] for r in top},{c for c,e in rows.items() if e['ranks']['VCSH/TTS']<=5})

    def test_equity_boundaries(self):
        for ratio, factor in [(50,1),(49.99,.8),(40,.8),(39.99,.6),(30,.6),(29.99,.4),(20,.4),(19.99,.2),(10,.2),(9.99,0),(0,0),(-1,0)]:
            self.assertEqual(b.equity_factor(ratio),factor)
        self.assertIsNone(b.equity_ratio(None,100))
        self.assertIsNone(b.equity_ratio(40,0))
        self.assertIsNone(b.equity_ratio(40,-100))
        self.assertIsNone(b.equity_factor(None))
        self.assertEqual(b.equity_ratio(40,100),40)
        self.assertEqual(b.equity_ratio(-10,100),-10)

    def test_boundaries(self):
        self.assertEqual(b.levels(.3,(.3,.5,1,1.5),True),1)
        self.assertEqual(b.levels(.5,(.3,.5,1,1.5),True),.8)
        self.assertEqual(b.pb_level(.7,1),1); self.assertEqual(b.pb_level(.85,1),.8)
        self.assertEqual(b.pb_level(1.15,1),.6); self.assertEqual(b.pb_level(1.3,1),.3)
        self.assertEqual(b.growth(1,-1)[0],.6); self.assertEqual(b.growth(-1,-2)[0],0)
        self.assertEqual(b.cfo_level([1,1,-3]),.4); self.assertEqual(b.cfo_level([1,-1,-1]),.2)
        self.assertIsNone(b.cfo_level([1,None,1]))
        self.assertIsNone(b.evaluate({'Mã':'X'},1)['score'])
        def project(inv,assets,adv,prior):
            return b.project_metrics({'HTK ròng Q3 (tỷ)':inv,'Tổng tài sản Q3 (tỷ)':assets,'Người mua trả tiền trước NH Q3/2026 (tỷ)':adv,'Người mua trả tiền trước NH Q3/2025 (tỷ)':prior})
        self.assertEqual(project(20,100,10,5)['inventory_factor'],1)
        self.assertEqual(project(75,100,10,5)['inventory_factor'],.3)
        self.assertEqual(project(9,100,.9,1)['advance_factor'],.6)
        self.assertEqual(project(20,100,10,0)['advance_factor'],.8)
        self.assertEqual(project(20,100,0,0)['advance_factor'],0)
        self.assertIsNone(project(20,100,10,None)['advance_factor'])
        self.assertIsNone(project(20,0,10,1)['inventory_factor'])
        self.assertEqual(project(20,100,10,10)['coverage_factor'],1)
        self.assertEqual(project(20,100,10,10)['growth_factor'],.6)

if __name__=='__main__':unittest.main()
