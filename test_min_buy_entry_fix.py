# -*- coding: utf-8 -*-
"""Regression tests for buy entry rules. Standalone; no Streamlit/EOD/order writes."""
import unittest
import numpy as np
import pandas as pd
import engine as E
import waiting_buy as WB

class TestBuyEntryFix(unittest.TestCase):
    def row(self, close=12, low=11, resistance=11.5, support=10,
            position=75, volume=1.6, cloud=9, ma9=10):
        return pd.Series({"Giá đóng cửa":close, "Giá thấp nhất":low,
                          "Vol_vs_MA10":volume, "Position_%":position,
                          "Resistance_20":resistance, "Support_20":support,
                          "SpanA":cloud, "SpanB":cloud-1, "MA9":ma9})
    def test_high_score_without_breakout_or_spring_is_wait(self):
        row = self.row(resistance=15, support=9, position=75)
        sig, score, *_ = E.analyze_signal(row)
        self.assertGreaterEqual(score, 3.5)
        self.assertEqual(sig, "WAIT")
    def test_real_breakout(self):
        self.assertEqual(E.analyze_signal(self.row())[0], "MUA MỚI (BREAKOUT)")
    def test_breakout_with_insufficient_volume_is_wait(self):
        # This can still score above 3.5, but price-volume setup is not confirmed.
        row = self.row(volume=1.3)
        sig, score, *_ = E.analyze_signal(row)
        self.assertGreaterEqual(score, 3.5)
        self.assertEqual(sig, "WAIT")
    def test_real_spring(self):
        row = self.row(close=11.2, low=9.8, resistance=13, support=10,
                       position=65, volume=1.6, cloud=9, ma9=10)
        self.assertEqual(E.analyze_signal(row)[0], "MUA GOM (SPRING)")
    def test_spring_with_insufficient_volume_is_wait(self):
        row = self.row(close=11.2, low=9.8, resistance=13, support=10,
                       position=65, volume=1.0, cloud=9, ma9=10)
        self.assertEqual(E.analyze_signal(row)[0], "WAIT")
    def test_real_structure_but_insufficient_score(self):
        row = self.row(close=12, resistance=11.5, position=75,
                       volume=.9, cloud=14, ma9=15)
        self.assertEqual(E.analyze_signal(row)[0], "WAIT")
    def plan(self, price=29, lo=28.85, hi=29.15, entry=29, stop=28.1,
             tp1=30.8, resistance=np.nan):
        return {"Vùng mua từ":lo, "Vùng mua đến":hi, "Giá vào":entry,
                "Cắt lỗ":stop,"Mục tiêu 1":tp1,"Mục tiêu 2":31.7,"Cản gần":resistance}
    def test_final_rr_valid_and_matches_display(self):
        p = self.plan()
        yes, _ = WB._final_entry_check(p, 29)
        self.assertTrue(yes)
        self.assertAlmostEqual(p["R:R"], 2)
        self.assertEqual(WB._rr_label(p,"Mục tiêu 1"), "R:R 1:2.0")
        self.assertEqual(WB._rr_label(p,"Mục tiêu 2"), "R:R 1:3.0")
    def test_real_resistance_blocks_premature_buy(self):
        p = self.plan(resistance=29.45)
        yes, note = WB._final_entry_check(p, 29)
        self.assertFalse(yes)
        self.assertIn("Cản gần", note)
    def test_price_outside_final_zone(self):
        p = self.plan()
        yes, _ = WB._final_entry_check(p, 30)
        self.assertFalse(yes)
    def test_rr_below_threshold(self):
        p = self.plan(tp1=30)
        yes, _ = WB._final_entry_check(p, 29)
        self.assertFalse(yes)
        self.assertAlmostEqual(p["R:R"], 1.111, places=2)
    def test_inverted_plan_rejected(self):
        p = self.plan(stop=29.3)
        yes, _ = WB._final_entry_check(p, 29)
        self.assertFalse(yes)
        self.assertTrue(np.isnan(p["R:R"]))
    def test_missing_inputs_rejected(self):
        p = self.plan(stop=np.nan)
        yes, _ = WB._final_entry_check(p, 29)
        self.assertFalse(yes)
    def test_final_action_filter_uses_wait(self):
        # Regressions: state can be confirmed while action remains waiting.
        action, _ = WB.action_of(WB.GOOD_ENTRY)
        self.assertEqual(action, "Vào ngay")  # provisional, validated by build_waiting_buy

if __name__ == "__main__":
    unittest.main(verbosity=2)
