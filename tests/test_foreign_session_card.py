import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import pandas as pd
from foreign_session_card import build_summary,calendar_sessions,card_html,flow_conclusion,multi_horizon,assessment_html

class ForeignCard(unittest.TestCase):
    def setUp(self):
        self.days=list(pd.bdate_range('2025-11-03',periods=10)); self.end=self.days[-1]
        self.data=pd.DataFrame([dict(trading_date=d.strftime('%Y-%m-%d'),symbol='BSR',data_source='SSI_IBOARD_PUBLIC_FOREIGN',buy_vol=100,sell_vol=60,net_vol=40,buy_val=5e9,sell_val=2e9,net_val=3e9) for d in self.days])
    def m(self,d=None,days=None):return build_summary(self.data if d is None else d,'BSR',self.end,self.days if days is None else days)
    def test_exact10(self):
        m=self.m();self.assertEqual(m['coverage'],10);self.assertEqual(m['totals']['net_val'],30e9);self.assertEqual(m['totals']['buy_vol'],1000);self.assertEqual(m['today']['net_vol'],40)
    def test_missing_middle(self):
        m=self.m(self.data.drop(index=3));self.assertEqual(m['coverage'],9);self.assertIsNone(m['totals']['net_val']);self.assertIsNotNone(m['today'])
    def test_stale(self):
        m=self.m(self.data.iloc[:-1]);self.assertIsNone(m['today']);self.assertEqual(m['coverage'],9)
    def test_partial_gross(self):
        d=self.data.copy();d.loc[2,'buy_val']=float('nan');m=self.m(d);self.assertIsNone(m['totals']['buy_val']);self.assertEqual(m['totals']['net_val'],30e9)
    def test_duplicate(self):self.assertEqual(self.m(pd.concat([self.data,self.data.iloc[:1]]))['coverage'],9)
    def test_bad_reconciliation(self):
        d=self.data.copy();d.loc[2,'net_val']=9e9;self.assertEqual(self.m(d)['coverage'],9)
    def test_future(self):
        d=self.data.copy();r=d.iloc[-1].copy();r.trading_date='2025-11-20';m=self.m(pd.concat([d,pd.DataFrame([r])]));self.assertEqual(m['totals']['net_val'],30e9)
    def test_other_source(self):
        d=self.data.copy();d.loc[2,'data_source']='RANKING_TOP_ONLY';self.assertEqual(self.m(d)['coverage'],9)
    def test_other_symbol(self):
        d=self.data.copy();d.loc[2,'symbol']='GAS';self.assertEqual(self.m(d)['coverage'],9)
    def test_no_calendar(self):
        m=self.m(days=[]);self.assertIsNotNone(m['today']);self.assertIsNone(m['totals']['net_val'])
    def test_zero(self):
        d=self.data.copy();d.loc[:,['buy_vol','sell_vol','net_vol','buy_val','sell_val','net_val']]=0;m=self.m(d);self.assertEqual(m['totals']['net_val'],0)
    def test_calendar(self):
        with TemporaryDirectory() as t:
            p=Path(t)/'index.csv';pd.DataFrame({'Mã':'VNINDEX','Ngày':[d.strftime('%d/%m/%Y') for d in self.days]}).to_csv(p,index=False)
            self.assertEqual(calendar_sessions(None,self.end,p),self.days)
            self.assertEqual(calendar_sessions(None,self.end+pd.Timedelta(days=3),p),[])
    def test_html(self):
        a=card_html(self.m(),dark=False);self.assertIn('LŨY KẾ 10 PHIÊN LIỀN KỀ',a);self.assertIn('30.00 tỷ',a);self.assertIn('Mua ròng',a)
        self.assertIn('Chưa đủ 10 phiên',card_html(self.m(self.data.iloc[:-1])))
    def test_conclusion_buy(self):
        q=flow_conclusion(self.m());self.assertEqual((q['buy'],q['sell'],q['streak']), (10,0,10));self.assertEqual(q['direction'],'Mua ròng')
    def test_conclusion_mixed(self):
        d=self.data.copy()
        d.loc[7:9,['buy_val','sell_val','net_val']]=[2e9,5e9,-3e9]
        d.loc[7:9,['buy_vol','sell_vol','net_vol']]=[60,100,-40]
        q=flow_conclusion(self.m(d));self.assertEqual((q['buy'],q['sell'],q['streak']),(7,3,3));self.assertIn('Bán ròng 3 phiên',q['chain']);self.assertEqual(q['direction'],'Mua ròng')
    def test_conclusion_flat(self):
        d=self.data.copy();d.loc[9,['buy_val','sell_val','net_val']]=[2e9,2e9,0];d.loc[9,['buy_vol','sell_vol','net_vol']]=[60,60,0]
        q=flow_conclusion(self.m(d));self.assertEqual((q['flat'],q['streak']),(1,0))
    def test_conclusion_missing(self):
        self.assertIsNone(flow_conclusion(self.m(self.data.iloc[:-1])))
        self.assertNotIn('Lũy kế:',card_html(self.m(self.data.iloc[:-1])))
    def test_conclusion_html(self):
        self.assertIn('10 phiên mua ròng',card_html(self.m()));self.assertIn('Mua ròng 10 phiên liên tiếp',card_html(self.m()))
    def test_twenty(self):
        days=list(pd.bdate_range('2025-10-20',periods=20)); end=days[-1]
        d=pd.concat([self.data]*2,ignore_index=True);d['trading_date']=[x.strftime('%Y-%m-%d') for x in days]
        m=build_summary(d,'BSR',end,days,period=20)
        self.assertEqual(m['coverage'],20);self.assertEqual(m['totals']['net_val'],60e9)
        self.assertEqual(flow_conclusion(m)['streak'],20)
        self.assertIn('LŨY KẾ 20 PHIÊN LIỀN KỀ',card_html(m))
        self.assertIn('60.00 tỷ',card_html(m))
        self.assertEqual(build_summary(d,'BSR',end,days)['coverage'],10)
        self.assertIsNone(build_summary(d.drop(index=2),'BSR',end,days,period=20)['totals']['net_val'])
    def test_twenty_calendar(self):
        days=list(pd.bdate_range('2025-10-20',periods=20)); d=pd.DataFrame({'Mã':'VNINDEX','Ngày':days})
        with TemporaryDirectory() as t:
            p=Path(t)/'missing.csv';self.assertEqual(calendar_sessions(d,days[-1],p,period=20),days)
    def test_compact_table(self):
        a=card_html(self.m());self.assertEqual(a.count('<tr>'),3);self.assertIn('Phiên hiện tại',a);self.assertIn('overflow-x:auto',a)
    def test_invalid_period(self):
        with self.assertRaises(ValueError):build_summary(self.data,'BSR',self.end,self.days,period=15)
class MultiHorizon(unittest.TestCase):
    def models(self, values, missing=()):
        days=list(pd.bdate_range('2025-10-20',periods=20))
        rows=[]
        for i,(day,v) in enumerate(zip(days,values)):
            if i in missing: continue
            rows.append(dict(symbol='BSR',trading_date=day.strftime('%Y-%m-%d'),data_source='SSI_IBOARD_PUBLIC_FOREIGN',net_val=v*1e9))
        d=pd.DataFrame(rows)
        return tuple(build_summary(d,'BSR',days[-1],days,period=n) for n in (10,20))
    def assessment(self, values, missing=()):
        return multi_horizon(*self.models(values,missing))
    def test_bsr_pattern(self):
        a=self.assessment([-20]*10+[-10]*9+[55.5]);self.assertEqual(a['values'],(55.5e9,-34.5e9,-234.5e9));self.assertIn('QUAY LẠI MUA RÒNG',a['title']);self.assertIn('thu hẹp',a['body']);self.assertEqual(a['tone'],'mixed')
    def test_sell_day_buy_windows(self):
        a=self.assessment([10]*19+[-5]);self.assertIn('LŨY KẾ VẪN DƯƠNG',a['title'])
    def test_all_buy(self):self.assertEqual(self.assessment([1]*20)['tone'],'buy')
    def test_all_sell(self):self.assertEqual(self.assessment([-1]*20)['tone'],'sell')
    def test_improve(self):self.assertIn('CẢI THIỆN',self.assessment([-5]*10+[1]*10)['title'])
    def test_weaken(self):self.assertIn('SUY YẾU',self.assessment([5]*10+[-1]*10)['title'])
    def test_zero(self):self.assertEqual(self.assessment([0]*20)['title'],'CÂN BẰNG CẢ BA KHUNG')
    def test_missing_twenty(self):
        a=self.assessment([1]*20,(0,));self.assertEqual(a['values'],(1e9,10e9,None));self.assertIn('Thiếu 20 phiên',a['body'])
    def test_missing_today(self):
        a=self.assessment([1]*20,(19,));self.assertEqual(a['values'],(None,None,None));self.assertEqual(a['tone'],'neutral')
    def test_increasing_sales(self):self.assertIn('bán ròng 10 phiên gần đây tăng',self.assessment([-1]*10+[-2]*10)['body'])
    def test_mismatch(self):
        a,b=self.models([1]*20);b['code']='GAS';self.assertIn('ĐỒNG NHẤT',multi_horizon(a,b)['title'])
    def test_selection_independent(self):
        m10,m20=self.models([-20]*10+[-10]*9+[55.5]);a=multi_horizon(m10,m20)
        for dark in (True,False):
            for m in (m10,m20):
                h=card_html(m,dark=dark,assessment=a)
                self.assertIn(assessment_html(a,dark),h);self.assertIn('+55.50 tỷ',h);self.assertIn('-234.50 tỷ',h);self.assertEqual(h.count('ĐÁNH GIÁ DÒNG TIỀN KHỐI NGOẠI'),1)

if __name__=='__main__':unittest.main()
