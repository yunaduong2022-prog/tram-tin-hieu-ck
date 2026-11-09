"""Regression tests for flow-first VNINDEX HÀNH ĐỘNG wording and heat."""
from __future__ import annotations

from pathlib import Path
import unittest
import pandas as pd

from vnindex_flow_actions import (
    heat_check, weak_groups_from_flow, flow_action_items,
    replace_action_section, unavailable_action,
)

END = pd.Timestamp("2026-11-06")
DAYS = pd.bdate_range(end=END, periods=60)


def panel():
    rising = [100 + 32 * i / 59 for i in range(60)]
    cool = [100 + 10 * i / 59 for i in range(60)]
    corrected = [100 + 60 * i / 48 for i in range(49)] + [160 - 30 * i / 11 for i in range(1, 12)]
    return pd.DataFrame({"VND": rising, "VIX": cool, "SHS": corrected,
                         "CTD": cool, "TCH": cool}, index=DAYS)


def sections():
    return [{"name": "DÒNG TIỀN", "items": [
        {"tone": "xanh", "text": "TOP 3 NHÓM DẪN SÓNG (1 tuần):", "subs": []},
        {"tone": "xanh", "text": "Chứng khoán: VND, VIX, SHS", "subs": []},
        {"tone": "do", "text": "TOP 3 NHÓM YẾU:", "subs": []},
        {"tone": "", "text": "Nhận định tuần: các nhóm yếu.", "subs": []},
        {"tone": "do", "text": "Dầu khí: GAS, BSR", "subs": []},
        {"tone": "do", "text": "Bán lẻ: DGW, MWG", "subs": []},
        {"tone": "do", "text": "Họ Vingroup: VIC, VRE", "subs": []}]},
        {"name": "HÀNH ĐỘNG", "items": [{"tone": "do", "text": "CHIỀU BÁN VNINDEX", "subs": []}]},
        {"name": "LƯU Ý", "items": [{"tone": "do", "text": "Tránh FOMO trên 30%", "subs": []}]}]


def leaders():
    return [{"group": "Chứng khoán", "codes": ["VND", "VIX", "SHS"], "return": 5.6},
            {"group": "Đầu tư công", "codes": ["CTD"], "return": 4.4},
            {"group": "Bất động sản", "codes": ["TCH"], "return": 4.0}]


class TestFlowAction(unittest.TestCase):
    def test_hot_still_25pct_and_current_pullback_below_8(self):
        res = heat_check(panel(), "VND", END)
        self.assertTrue(res["hot"])
        self.assertGreater(res["rise_pct"], 25)
        self.assertLess(res["pullback_pct"], 8)

    def test_hot_boundary_25pct(self):
        p = panel()
        p["BND"] = [100 + 25 * i / 59 for i in range(60)]
        self.assertTrue(heat_check(p, "BND", END)["hot"])

    def test_not_hot_below_25pct(self):
        p = panel()
        p["COOL"] = [100 + 24 * i / 59 for i in range(60)]
        self.assertFalse(heat_check(p, "COOL", END)["hot"])

    def test_not_hot_after_current_8pct_pullback(self):
        res = heat_check(panel(), "SHS", END)
        self.assertGreater(res["pullback_pct"], 8)
        self.assertFalse(res["hot"])

    def test_does_not_scan_historical_drawdowns(self):
        # A prior 12% pullback is irrelevant if the current price is back at a
        # new high. The user chose current distance from the post-low peak.
        p = panel()
        seq = [100] + [100 + 45*i/20 for i in range(1, 21)]
        seq += [145 - 18*i/5 for i in range(1, 6)]
        seq += [127 + 35*i/34 for i in range(1, 35)]
        self.assertEqual(len(seq), 60)
        p["RECOVER"] = seq
        self.assertTrue(heat_check(p, "RECOVER", END)["hot"])

    def test_unknown_when_no_history(self):
        p = panel()
        p["NEW"] = [float("nan")] * 16 + [10.0] * 44
        self.assertIsNone(heat_check(p, "NEW", END))
        self.assertIsNone(heat_check(p, "UNKNOWN", END))

    def test_stale_close_rejected(self):
        p = panel()
        p.loc[END, "VIX"] = float("nan")
        self.assertIsNone(heat_check(p, "VIX", END))

    def test_future_prices_ignored(self):
        p = panel()
        future = p.iloc[[-1]].copy()
        future.index = [END + pd.Timedelta(days=3)]
        future.loc[:, "VND"] = 5.0
        self.assertTrue(heat_check(pd.concat([p, future]), "VND", END)["hot"])

    def test_groups_match_flow_card(self):
        self.assertEqual(weak_groups_from_flow(sections()),
                         ["Dầu khí", "Bán lẻ", "Họ Vingroup"])
        msg = " | ".join(x["text"] for x in flow_action_items(sections(), leaders(), panel(), END, "W"))
        self.assertIn("Chứng khoán, Đầu tư công, Bất động sản", msg)
        self.assertIn("Dầu khí, Bán lẻ, Họ Vingroup", msg)

    def test_requested_action_wording(self):
        msg = " | ".join(x["text"] for x in flow_action_items(sections(), leaders(), panel(), END, "W"))
        self.assertIn("canh mua khi rung lắc, giá đỏ", msg)
        self.assertIn("HẠN CHẾ MUA MỚI VÀ TRUNG BÌNH GIÁ NHÓM YẾU", msg)
        self.assertIn("HẠN CHẾ MUA ĐUỔI NHỮNG MÃ ĐÃ TĂNG NÓNG: VND.", msg)
        self.assertNotIn("CHIỀU BÁN", msg)

    def test_hot_not_in_leaders_must_not_be_printed(self):
        p = panel()
        p["NKG"] = p["VND"]  # hot, but NKG is not in visible strong groups
        text = " | ".join(x["text"] for x in flow_action_items(sections(), leaders(), p, END, "W"))
        self.assertNotIn("NKG", text)

    def test_hot_in_leaders_is_printed(self):
        p = panel()
        p["NKG"] = p["VND"]
        rows = leaders() + [{"group": "Thép", "codes": ["NKG"], "return": 3.5}]
        text = " | ".join(x["text"] for x in flow_action_items(sections(), rows, p, END, "W"))
        self.assertIn("NKG", text)

    def test_no_missing_data_lines_even_with_missing_panel(self):
        res = flow_action_items(sections(), leaders(), None, END, "W")
        text = " | ".join(x["text"] for x in res)
        self.assertIn("canh mua khi rung lắc, giá đỏ", text)
        self.assertNotIn("CHƯA ĐỦ", text)
        self.assertNotIn("Chưa có mã", text)
        self.assertNotIn("HẠN CHẾ MUA ĐUỔI NHỮNG MÃ", text)

    def test_no_weak_groups_no_fabricated_weakness(self):
        only_strong = [{"name": "DÒNG TIỀN", "items": [
            {"tone": "xanh", "text": "TOP 1 NHÓM DẪN SÓNG (1 tuần):", "subs": []}]}]
        text = " | ".join(x["text"] for x in flow_action_items(only_strong, leaders(), panel(), END, "W"))
        self.assertNotIn("HẠN CHẾ MUA MỚI", text)

    def test_no_verified_leaders_hides_action(self):
        self.assertEqual(unavailable_action(), [])
        self.assertEqual(flow_action_items(sections(), [], panel(), END, "W"), [])
        out = replace_action_section(sections(), unavailable_action())
        self.assertEqual([x["name"] for x in out], ["DÒNG TIỀN", "LƯU Ý"])

    def test_all_timeframes(self):
        for tf, title in (("D", "phiên"), ("W", "tuần"), ("M", "tháng"), ("Q", "quý")):
            result = flow_action_items(sections(), leaders(), panel(), END, tf)
            self.assertIn(title, result[0]["text"])

    def test_only_action_modified_luu_y_remains(self):
        before = sections()
        result = replace_action_section(before, flow_action_items(before, leaders(), panel(), END, "W"))
        self.assertEqual(result[0], before[0])
        self.assertEqual(result[2], before[2])
        self.assertEqual(before[1]["items"][0]["text"], "CHIỀU BÁN VNINDEX")

    def test_missing_action_created_when_items_exist(self):
        x = replace_action_section(sections()[:1], [{"tone": "xanh", "text": "Mạnh", "subs": []}])
        self.assertEqual(x[-1]["name"], "HÀNH ĐỘNG")

    def test_fomo_rule_unchanged_in_vnindex_auto(self):
        s = (Path(__file__).resolve().parent / "vnindex_auto.py").read_text(encoding="utf-8")
        self.assertIn("pct > 30.0 + 1e-8", s)
        self.assertIn("refresh_fomo_sections", s)

    def test_main_integration_unchanged(self):
        src = (Path(__file__).resolve().parent / "vnindex_view.py").read_text(encoding="utf-8")
        self.assertIn("replace_action_section(sections, action_lines)", src)
        self.assertIn("action_lines = unavailable_action()", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
