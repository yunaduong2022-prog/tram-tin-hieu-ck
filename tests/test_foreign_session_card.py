import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import pandas as pd
from foreign_session_card import build_summary,calendar_sessions,card_html,flow_conclusion

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
if __name__=='__main__':unittest.main()
