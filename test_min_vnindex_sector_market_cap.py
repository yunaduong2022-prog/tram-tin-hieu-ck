"""Checks the market-cap policy without depending on Streamlit or VNStock."""
from __future__ import annotations
import tempfile
from datetime import date
from pathlib import Path
import unittest
from vnindex_market_cap import (
    threshold_for_group, load_shares, capitalization_bil,
    filtered_top_codes,
)


class TestSectorMarketCap(unittest.TestCase):
    def test_sector_thresholds(self):
        self.assertEqual(threshold_for_group("Ngân hàng", 29), 20000)
        self.assertEqual(threshold_for_group("Chứng khoán", 31), 5000)
        self.assertEqual(threshold_for_group("Bất động sản", 26), 5000)
        self.assertEqual(threshold_for_group("Thép", 9), 3000)
        self.assertEqual(threshold_for_group("Đầu tư công", 10), 3000)
        self.assertEqual(threshold_for_group("Dầu khí", 16), 3000)
        self.assertEqual(threshold_for_group("Bán lẻ", 6), 3000)
        self.assertEqual(threshold_for_group("Vận tải", 6), 2000)
        self.assertEqual(threshold_for_group("Cảng biển", 15), 2000)
        self.assertEqual(threshold_for_group("Khai khoáng", 7), 2000)
        self.assertEqual(threshold_for_group("Đồ uống", 2), 1000)

    def test_other_small_groups(self):
        self.assertEqual(threshold_for_group("Thịt & chăn nuôi", 1), 1000)
        self.assertEqual(threshold_for_group("Họ Gelex", 6), 2000)

    def test_bms_real_share_count_does_not_reach_broker_cutoff(self):
        # 215,148,036 outstanding shares x 11,900 VND = about 2,560 ty VND.
        self.assertAlmostEqual(capitalization_bil(11.9, 215148036), 2560.261628, places=5)
        self.assertLess(capitalization_bil(11.9, 215148036), 5000)

    def test_choose_next_eligible_by_price_rank_not_first_five(self):
        rows = [{"Mã": code, "Giá": price} for code, price in [
            ("VND", 14.95), ("BMS", 11.9), ("VIX", 13.35),
            ("CTS", 23.35), ("SHS", 13.5), ("BSI", 22.0), ("MBS", 27.0)]]
        shares = {"VND": 1_500_000_000, "BMS": 215148036,
                  "VIX": 1_500_000_000, "CTS": 500_000_000,
                  "SHS": 1_000_000_000, "BSI": 400_000_000,
                  "MBS": 300_000_000}
        codes = filtered_top_codes(rows, shares, 5000)
        self.assertEqual(codes, ["VND", "VIX", "CTS", "SHS", "BSI"])
        self.assertNotIn("BMS", codes)

    def test_missing_cap_never_passes(self):
        self.assertEqual(filtered_top_codes([{"Mã": "AAA", "Giá": 9999}], {}, 1000), [])
        self.assertIsNone(capitalization_bil(float("nan"), 1_000_000_000))
        self.assertIsNone(capitalization_bil(10, None))

    def test_do_not_pad_to_five(self):
        rows = [{"Mã": "AAA", "Giá": 10}, {"Mã": "BBB", "Giá": 10}]
        self.assertEqual(filtered_top_codes(rows, {"AAA": 1_000_000_000, "BBB": 5_000_000}, 5000), ["AAA"])

    def test_skip_future_updates(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "shares.csv"
            p.write_text("Mã,Số CP lưu hành,Cập nhật\nAAA,500000000,10/11/2026\nBBB,1000000000,tay\n", encoding="utf-8")
            self.assertEqual(load_shares(p, as_of=date(2026, 11, 6)), {"BBB": 1_000_000_000})

    def test_conflicting_share_rows_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "shares.csv"
            p.write_text("Mã,Số CP lưu hành,Cập nhật\nAAA,100000000,tay\nAAA,200000000,tay\n", encoding="utf-8")
            self.assertEqual(load_shares(p), {})

    def test_empty_qualifying_group_is_not_dropped(self):
        from vnindex_leading_sync import leading_items, replace_strong_sector_block
        leaders = [{"group": "Chứng khoán", "return": 5.6, "codes": [],
                    "rank": 1, "min_cap_bil": 5000}]
        lines = leading_items(leaders, "W")
        self.assertIn("TOP 1 NHÓM DẪN SÓNG", lines[0]["text"])
        self.assertIn("≥5.000 tỷ", lines[-1]["text"])
        sections = [{"name": "DÒNG TIỀN", "items": [
            {"text": "TOP 3 NHÓM DẪN SÓNG:", "tone": "xanh", "subs": []},
            {"text": "TOP 3 NHÓM YẾU:", "tone": "do", "subs": []},
            {"text": "Thép: HPG", "tone": "do", "subs": []}]}]
        out = replace_strong_sector_block(sections, leaders, "W")
        self.assertIn("TOP 3 NHÓM YẾU", [x["text"] for x in out[0]["items"]][3])
        self.assertEqual(out[0]["items"][-1]["text"], "Thép: HPG")

    def test_repo_shares_bms_if_present(self):
        p = Path(__file__).resolve().parent / "data" / "shares_outstanding.csv"
        if not p.is_file():
            self.skipTest("Shares CSV is optional in offline test fixture")
        shares = load_shares(p, as_of=date(2026, 11, 6))
        self.assertEqual(shares.get("BMS"), 215148036)


if __name__ == "__main__":
    unittest.main(verbosity=2)
