import unittest
import pandas as pd
from proprietary_quality import audit
class QualityTest(unittest.TestCase):
    def test_sanity(self):
        rows=[]
        for sym,val,source in [('HPG',200000,'CAFEF_PUBLIC'),('LPB',20000000,'CAFEF_PUBLIC'),('AAA',200000,'CAFEF_PUBLIC'),('OLD',20000000,'VNSTOCK5')]:
            rows.append(dict(symbol=sym,trading_date='2026-11-23',buy_vol=10,buy_val=val,sell_vol=0,sell_val=0,net_vol=10,net_val=val,data_source=source))
        prices=pd.DataFrame({'symbol':['HPG','LPB','OLD'],'date':pd.to_datetime(['2026-11-23']*3),'close':[20000]*3})
        good,bad=audit(pd.DataFrame(rows),prices)
        self.assertEqual(set(good.symbol),{'HPG','OLD'})
        self.assertEqual(set(bad.symbol),{'LPB','AAA'})
        self.assertEqual(len(good)+len(bad),len(rows))
        self.assertEqual(bad.loc[bad.symbol.eq('LPB'),'buy_val'].iloc[0],20000000)
if __name__=='__main__':unittest.main()
