import unittest
import bds_fa as b

class BdsFA(unittest.TestCase):
    def test_data_and_scores(self):
        rows=b.load(); self.assertEqual(set(rows),b.SYMBOLS)
        self.assertEqual(sum(b.WEIGHTS.values()),100)
        self.assertTrue(all(r['coverage']==100 and 0<=r['score']<=100 for r in rows.values()))
        self.assertAlmostEqual(rows['VRE']['industry_pb'],1.2360500618333334)
        self.assertEqual(rows['VRE']['score'],90); self.assertEqual(rows['HDG']['score'],89.5)
        self.assertEqual(rows['NBB']['points']['Nợ vay/VCSH'],0)
        self.assertEqual(rows['NTL']['points']['P/E'],0)
        self.assertEqual(rows['NVL']['points']['Tăng trưởng LNST'],6)
        self.assertEqual(rows['LDG']['points']['Tăng trưởng LNST'],6)
        self.assertEqual(rows['TCH']['rank'],rows['AGG']['rank'])
        self.assertEqual(rows['VHM']['ranks']['ROE'],1)
        self.assertTrue(any('TOP 1 Ngành BĐS' in t for t in b.notes(rows['VHM'])))
        self.assertTrue(any('CFO TTM âm' in t for t in b.notes(rows['HHS'])))
        self.assertTrue(all(b.for_symbol(s)[0]==r['score'] for s,r in rows.items()))
    def test_boundaries(self):
        self.assertEqual(b.levels(.3,(.3,.5,1,1.5),True),1)
        self.assertEqual(b.levels(.5,(.3,.5,1,1.5),True),.8)
        self.assertEqual(b.pb_level(.7,1),1); self.assertEqual(b.pb_level(.85,1),.8)
        self.assertEqual(b.pb_level(1.15,1),.6); self.assertEqual(b.pb_level(1.3,1),.3)
        self.assertEqual(b.growth(1,-1)[0],.6); self.assertEqual(b.growth(-1,-2)[0],0)
        self.assertEqual(b.cfo_level([1,1,-3]),.4); self.assertEqual(b.cfo_level([1,-1,-1]),.2)
        self.assertIsNone(b.cfo_level([1,None,1]))
        self.assertIsNone(b.evaluate({'Mã':'X'},1)['score'])

if __name__=='__main__':unittest.main()
