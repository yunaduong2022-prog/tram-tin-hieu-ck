"""Regression checks for brief technical sector reasons in VNINDEX."""
import unittest
import pandas as pd
import numpy as np
from vnindex_auto import sector_flow_reason, flow_lines, TF_BARS

class SectorReasonTests(unittest.TestCase):
    def test_positive_reason_has_supported_language(self):
        rows=[("Thép", .25, 4.5, ["NKG","HPG","HSG"])]
        for tf in ("D", "W", "M", "Q"):
            s=sector_flow_reason(rows, True, tf)
            self.assertIn("Thép",s)
            self.assertIn("giá trị giao dịch",s)
            self.assertNotIn("lãi suất",s)
            self.assertNotIn("định giá",s)

    def test_negative_reason_volume_not_inflow(self):
        rows=[("Thép", .31, -1.7, ["NKG","HPG","HSG"])]
        s=sector_flow_reason(rows, False, "D")
        self.assertIn("áp lực bán",s)
        self.assertNotIn("hút tiền",s)

    def test_negative_reason_no_volume_expansion(self):
        s=sector_flow_reason([("Bán lẻ", -.2, -2.4, ["MWG","FRT","DGW"])],False,"W")
        self.assertIn("chưa thấy xác nhận",s)

    def test_empty_sections_keep_general_report(self):
        days=pd.bdate_range("2026-01-01",periods=250)
        close=pd.DataFrame({"AAA":[10]*250,"BBB":[10]*250,"CCC":[10]*250},index=days)
        value=close.copy()
        for tf in ("D","W","M","Q"):
            lines=flow_lines({"close":close,"value":value},{"Test":["AAA","BBB","CCC"]},days[-1],tf)
            self.assertFalse(any("TOP 3 NHÓM" in item[1] for item in lines))

    def test_group_lines_have_only_name_and_tickers(self):
        days=pd.bdate_range("2026-01-01",periods=270)
        close={}; value={}; groups={}
        for label, growth in (("CK",1.002),("STEEL",.998)):
            groups[label]=[]
            for n in range(4):
                sym=f"{label}{n}"; groups[label].append(sym)
                close[sym]=[10*growth**t for t in range(len(days))]
                value[sym]=[100*1.03**t for t in range(len(days))]
        p={"close":pd.DataFrame(close,index=days),"value":pd.DataFrame(value,index=days)}
        for tf in ("D","W","M","Q"):
            lines=flow_lines(p,groups,days[-1],tf)
            joined="\n".join(x[1] for x in lines)
            self.assertIn("TOP 3 NHÓM HÚT TIỀN:",joined)
            self.assertIn("TOP 3 NHÓM YẾU:",joined)
            self.assertIn("CK: CK0",joined)
            self.assertIn("STEEL: STEEL0",joined)
            self.assertNotIn("CK (GTGD",joined)
            self.assertNotIn("STEEL (GTGD",joined)

if __name__ == '__main__':
    unittest.main()
