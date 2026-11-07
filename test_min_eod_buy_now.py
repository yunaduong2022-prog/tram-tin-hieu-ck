# -*- coding: utf-8 -*-
"""EOD entry exception tests; synthetic prices only, never reads/writes market data."""
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import waiting_buy as WB


class TestEodBuyNow(unittest.TestCase):
    @staticmethod
    def plan(price=17.0, stop=16.32, tp1=19.04, near=19.04, state=WB.GOOD_ENTRY):
        return {
            "Trạng thái": state, "Danh sách": WB.STATE_GROUP.get(state, WB.L_NONE),
            "Lý do": "Test MA50 / cạn cung", "Hành động": "Chờ mua",
            "Vùng mua từ": 15.8, "Vùng mua đến": 16.3,
            "Giá vào": 16.0, "Cắt lỗ": stop, "Mục tiêu 1": tp1,
            "Mục tiêu 2": 21.0, "Cản gần": near, "R:R": 2.0,
        }

    @staticmethod
    def features():
        return {
            "c": 17.0, "has_week": True, "up": True, "up_d": True, "up_w": True,
            "ema10": 16.6, "ema20": 16.0, "ema20_5": 15.8,
            "vol20": 1_200_000.0, "vol_now": 1.2,
            "pv_recent": set(), "score": 7.0, "rs20": 1.10,
        }

    def test_example_current_price_12_percent_and_rr_3_is_eligible(self):
        yes, note = WB._eod_entry_check(self.plan(), 17)
        self.assertTrue(yes, note)
        self.assertIn("12.0%", note)
        self.assertIn("3.00", note)

    def test_dont_overwrite_zone_when_buying_from_eod(self):
        p = self.plan()
        yes, note = WB._eod_entry_check(p, 17)
        self.assertTrue(yes)
        WB._apply_eod_entry(p, 17, note, "xác nhận kỹ thuật")
        self.assertEqual(p["Hành động"], "Vào ngay")
        self.assertTrue(p["Vào theo EOD"])
        self.assertEqual((p["Vùng mua từ"], p["Vùng mua đến"]), (15.8, 16.3))
        self.assertEqual(p["Giá vào"], 17)
        self.assertAlmostEqual(p["Lời 1 %"], 12)
        self.assertAlmostEqual(p["Cắt lỗ %"], -4)
        self.assertAlmostEqual(p["R:R"], 3)
        self.assertEqual(WB._rr_label(p, "Mục tiêu 1"), "R:R 1:3.0")
        self.assertIn("EOD", p["Ghi chú hành động"])

    def test_upside_alone_cannot_trigger(self):
        p = self.plan(stop=15.8)
        yes, _ = WB._eod_entry_check(p, 17)
        self.assertFalse(yes)  # R:R only 1.7

    def test_rr_alone_cannot_trigger(self):
        p = self.plan(tp1=18.5, stop=16.5, near=18.5)
        yes, _ = WB._eod_entry_check(p, 17)
        self.assertFalse(yes)  # R:R 3 but upside < 10%

    def test_near_resistance_blocks_good_far_tp(self):
        p = self.plan(near=17.7)
        yes, note = WB._eod_entry_check(p, 17)
        self.assertFalse(yes)
        self.assertIn("Cản gần", note)

    def test_missing_real_resistance_rejected(self):
        yes, _ = WB._eod_entry_check(self.plan(near=np.nan), 17)
        self.assertFalse(yes)

    def test_risk_more_than_8_percent_rejected(self):
        p = self.plan(stop=15.5, tp1=22, near=22)
        yes, note = WB._eod_entry_check(p, 17)
        self.assertFalse(yes)
        self.assertIn("cắt lỗ", note)

    def test_inside_zone_stays_under_old_entry_logic(self):
        yes, _ = WB._eod_entry_check(self.plan(), 16.2)
        self.assertFalse(yes)

    def test_below_zone_rejected_even_if_target_is_far(self):
        yes, _ = WB._eod_entry_check(self.plan(), 15.5)
        self.assertFalse(yes)

    def test_bad_or_missing_stop_target_rejected(self):
        for bad in (np.nan, -5, 17, 19.5):
            with self.subTest(stop=bad):
                yes, _ = WB._eod_entry_check(self.plan(stop=bad), 17)
                self.assertFalse(yes)

    def tech(self, state=WB.GOOD_ENTRY, feature_overrides=None, recent=None, bearish=None):
        f = self.features()
        f.update(feature_overrides or {})
        r = pd.Series({"Giá": 17.0})
        g = pd.DataFrame({"Giá đóng cửa": [17.0]})
        p = self.plan(state=state)
        with (mock.patch.object(WB, "_features", return_value=f),
              mock.patch.object(WB, "_rsi_bearish", return_value=bearish),
              mock.patch.object(WB, "_recent_buy_signal", return_value=recent)):
            return WB._eod_technical_check(g, None, r, p)

    def test_confirmed_entry_with_trend_liquidity_and_no_rsi_warning(self):
        yes, _ = self.tech()
        self.assertTrue(yes)

    def test_bearish_rsi_blocks_promotion(self):
        yes, _ = self.tech(bearish={"dir": "down"})
        self.assertFalse(yes)

    def test_recovery_or_overbought_never_auto_promoted(self):
        for state in (WB.RECOVERING, WB.OVERBOUGHT, WB.WEAKENING, WB.NO_BUY):
            with self.subTest(state=state):
                yes, _ = self.tech(state=state, recent={"close": 16})
                self.assertFalse(yes)

    def test_no_weekly_trend_or_insufficient_liquidity_rejected(self):
        for overrides in ({"has_week": False}, {"up": False}, {"vol20": 1500},
                          {"vol_now": 0}, {"ema20": 15, "ema20_5": 16}):
            with self.subTest(overrides=overrides):
                yes, _ = self.tech(feature_overrides=overrides)
                self.assertFalse(yes)

    def test_g2_requires_real_signal_and_strength(self):
        yes, _ = self.tech(state=WB.WATCH)
        self.assertFalse(yes)
        yes, _ = self.tech(state=WB.WATCH, recent={"close": 16.7})
        self.assertTrue(yes)
        yes, _ = self.tech(state=WB.WATCH, recent={"close": 16.7}, feature_overrides={"score": 4})
        self.assertFalse(yes)
        yes, _ = self.tech(state=WB.WATCH, recent={"close": 16.7}, feature_overrides={"rs20": .9})
        self.assertFalse(yes)

    def test_nonbuy_signal_in_recent_pv_blocks(self):
        yes, _ = self.tech(feature_overrides={"pv_recent": {"UPTHRUST"}})
        self.assertFalse(yes)

    def test_current_falling_day_or_five_day_leg_rejected(self):
        for overrides in ({"chg": -2.0}, {"drop5": -4.0}):
            with self.subTest(overrides=overrides):
                yes, _ = self.tech(feature_overrides=overrides)
                self.assertFalse(yes)

    def test_old_zone_gate_remains_fail_closed(self):
        p = self.plan()
        ok, _ = WB._final_entry_check(p, 17)
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main(verbosity=2)
