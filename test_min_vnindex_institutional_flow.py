"""Offline tests for isolated flow card."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd
from vnindex_institutional_flow import net_flow_sections, PERIODS

class InstitutionalFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.dates=pd.bdate_range("2026-09-01",periods=90)
        days=self.dates[-70:]
        rows=[]; prop=[]
        for day in days:
            ds=day.strftime("%Y-%m-%d")
            rows.extend([dict(trading_date=ds,symbol="ABC",net_value_vnd=2e9,source_scope="FLOW_VERIFIED_FULL"),
                         dict(trading_date=ds,symbol="XYZ",net_value_vnd=-3e9,source_scope="FLOW_VERIFIED_FULL")])
            prop.extend([dict(trading_date=ds,symbol="ABC",net_val=1e9),
                         dict(trading_date=ds,symbol="XYZ",net_val=-2e9)])
        pd.DataFrame(rows).to_csv(self.root/"foreign_net_flow.csv",index=False)
        pd.DataFrame(prop).to_csv(self.root/"proprietary_flow.csv",index=False)
    def tearDown(self): self.tmp.cleanup()
    def test_timeframes_all(self):
        for tf,n in [("D",1),("W",5),("M",21),("Q",63)]:
            with self.subTest(tf=tf):
                sec=net_flow_sections(self.dates,tf,self.root)
                self.assertEqual(sec["name"],"KHỐI NGOẠI – TỰ DOANH")
                self.assertEqual(sum("Mua ròng:" in x["text"] for x in sec["items"]),2)
                self.assertEqual(sum(f"{n}/{n} phiên" in x["text"] for x in sec["items"]),2)
    def test_missing_source_not_invented(self):
        (self.root/"proprietary_flow.csv").unlink()
        texts=[x["text"] for x in net_flow_sections(self.dates,"W",self.root)["items"]]
        self.assertTrue(any("Chưa có dữ liệu tự doanh" in x for x in texts))
    def test_partial_period_is_labeled(self):
        p=self.root/"foreign_net_flow.csv"
        df=pd.read_csv(p)
        df=df[df.trading_date==self.dates[-1].strftime("%Y-%m-%d")]
        df.to_csv(p,index=False)
        texts=[x["text"] for x in net_flow_sections(self.dates,"W",self.root)["items"]]
        self.assertTrue(any("CHƯA ĐỦ KỲ: 1/5 phiên" in x for x in texts))
    def test_duplicates_do_not_double(self):
        p=self.root/"proprietary_flow.csv"
        df=pd.read_csv(p)
        pd.concat([df,df.tail(2)],ignore_index=True).to_csv(p,index=False)
        s=net_flow_sections(self.dates,"D",self.root)
        self.assertTrue(any(x["text"]=="Mua ròng: ABC" for x in s["items"]))
    def test_future_rows_ignored(self):
        p=self.root/"foreign_net_flow.csv"; df=pd.read_csv(p)
        df.loc[len(df)]=dict(trading_date="2028-01-01",symbol="FUT",net_value_vnd=1e14,source_scope="FLOW_VERIFIED_FULL")
        df.to_csv(p,index=False)
        self.assertNotIn("FUT",str(net_flow_sections(self.dates,"Q",self.root)))
    def test_top_only_marked(self):
        p=self.root/"foreign_net_flow.csv"; df=pd.read_csv(p);df["source_scope"]="RANKING_TOP_ONLY";df.to_csv(p,index=False)
        self.assertIn("mẫu TOP",str(net_flow_sections(self.dates,"D",self.root)))

if __name__=="__main__": unittest.main()
