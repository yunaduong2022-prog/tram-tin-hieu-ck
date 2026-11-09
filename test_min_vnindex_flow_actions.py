"""Regression tests: flow-driven action, hot-stocks, and fail closed."""
from __future__ import annotations

import unittest
import pandas as pd
from pathlib import Path
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
        {"tone": "xanh", "text": "Chứng khoán: VND, VIX", "subs": []},
        {"tone": "do", "text": "TOP 3 NHÓM YẾU:", "subs": []},
        {"tone": "", "text": "Nhận định tuần: một số nhóm yếu.", "subs": []},
        {"tone": "do", "text": "Dầu khí: GAS, BSR", "subs": []},
        {"tone": "do", "text": "Bán lẻ: DGW, MWG", "subs": []},
        {"tone": "do", "text": "Họ Vingroup: VIC, VRE", "subs": []}]},
        {"name": "HÀNH ĐỘNG", "items": [{"tone": "do", "text": "CHIỀU BÁN VNINDEX", "subs": []}]},
        {"name": "LƯU Ý", "items": [{"tone": "do", "text": "FOMO", "subs": []}]}]


def leaders():
    return [{"group": "Chứng khoán", "codes": ["VND", "VIX", "SHS"], "return": 5.6},
            {"group": "Đầu tư công", "codes": ["CTD"], "return": 4.4},
            {"group": "Bất động sản", "codes": ["TCH"], "return": 4.0}]


class TestFlowAction(unittest.TestCase):
    def test_hot_threshold_and_no_pullback(self):
        v = heat_check(panel(), "VND", END)
        self.assertTrue(v["hot"])
        self.assertGreater(v["rise_pct"], 30)

    def test_25pct_also_flagged(self):
        p = panel()
        p["CEO"] = [100 + 26 * i / 59 for i in range(60)]
        self.assertTrue(heat_check(p, "CEO", END)["hot"])

    def test_corrected_8pct_not_flagged(self):
        v = heat_check(panel(), "SHS", END)
        self.assertGreater(v["rise_pct"], 25)
        self.assertGreater(v["pullback_pct"], 8)
        self.assertFalse(v["hot"])

    def test_unknown_when_no_history(self):
        p = panel()
        p["NEW"] = [float("nan")] * 16 + [10.0] * 44
        self.assertIsNone(heat_check(p, "NEW", END))
        self.assertIsNone(heat_check(p, "UNKNOWN", END))

    def test_stale_close_rejected(self):
        p = panel()
        p.loc[END, "VIX"] = float("nan")
        self.assertIsNone(heat_check(p, "VIX", END))

    def test_future_prices_never_used(self):
        p = panel()
        later = p.iloc[[-1]].copy()
        later.index = [END + pd.Timedelta(days=3)]
        later.loc[:, "VND"] = 5.0
        p = pd.concat([p, later])
        self.assertTrue(heat_check(p, "VND", END)["hot"])

    def test_weak_groups_follow_screen(self):
        self.assertEqual(weak_groups_from_flow(sections()),
                         ["Dầu khí", "Bán lẻ", "Họ Vingroup"])

    def test_actions_match_strong_and_weak_groups(self):
        original = sections()
        out = flow_action_items(original, leaders(), panel(), END, "W")
        msg = " | ".join(x["text"] for x in out)
        for word in ("Chứng khoán", "Đầu tư công", "Bất động sản", "Dầu khí", "Bán lẻ", "Họ Vingroup"):
            self.assertIn(word, msg)
        self.assertIn("VND (+32%)", msg)
        self.assertIn("VIX", msg)
        self.assertNotIn("CANH CHỈNH, KHÔNG MUA ĐUỔI: Chứng khoán: VND", msg)
        self.assertNotIn("CHIỀU BÁN", msg)
        self.assertEqual(original[1]["items"][0]["text"], "CHIỀU BÁN VNINDEX")

    def test_no_fabricated_buy_when_leaders_missing(self):
        out = flow_action_items(sections(), [], panel(), END, "W")
        self.assertIn("Chưa xác minh", out[0]["text"])
        self.assertNotIn("Chứng khoán", out[0]["text"])

    def test_no_fabricated_buy_when_panel_missing(self):
        out = flow_action_items(sections(), leaders(), None, END, "W")
        msg = " | ".join(x["text"] for x in out)
        self.assertIn("CHƯA ĐỦ DỮ LIỆU", msg)
        self.assertNotIn("CANH CHỈNH, KHÔNG MUA ĐUỔI", msg)

    def test_timeframes_no_ranking_invention(self):
        for tf in ("D", "W", "M", "Q"):
            out = flow_action_items(sections(), leaders(), panel(), END, tf)
            self.assertIn("Chứng khoán", out[0]["text"])

    def test_replace_only_action_section(self):
        before = sections()
        items = flow_action_items(before, leaders(), panel(), END, "W")
        after = replace_action_section(before, items)
        self.assertEqual(after[0], before[0]); self.assertEqual(after[2], before[2])
        self.assertEqual(after[1]["items"], items)
        self.assertEqual(before[1]["items"][0]["text"], "CHIỀU BÁN VNINDEX")

    def test_missing_action_section_created(self):
        out = replace_action_section(sections()[:1], unavailable_action())
        self.assertEqual(out[-1]["name"], "HÀNH ĐỘNG")

    def test_main_integration_hook(self):
        src = (Path(__file__).resolve().parent / "vnindex_view.py").read_text(encoding="utf-8")
        self.assertIn("from vnindex_flow_actions import flow_action_items", src)
        self.assertIn("replace_action_section(sections, action_lines)", src)
        self.assertIn("action_lines = unavailable_action()", src)
        self.assertNotIn("sections = replace_action_section(sections, view[", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
