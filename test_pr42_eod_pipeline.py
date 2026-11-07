# -*- coding: utf-8 -*-
"""Regression checks for PR #42 against the real chart-price construction path.

Synthetic EOD OHLCV; no market data files or external services read/written.
"""
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import engine as E
import waiting_buy as WB


class TestPr42EodMarketPlan(unittest.TestCase):
    @staticmethod
    def frame(low10=16.7):
        d = pd.DataFrame({
            "Mã": ["SYN"] * 80,
            "Giá đóng cửa": [17.0] * 80,
            "Giá thấp nhất": [low10] * 80,
            "Giá cao nhất": [17.2] * 80,
            "ATR": [.5] * 80,
        })
        return d

    @staticmethod
    def features(res=19.04):
        return {
            "c": 17.0, "res": res, "hi60": res, "hi52": res,
            "has_week": True, "up": True, "up_d": True, "up_w": True,
            "ema10": 16.6, "ema20": 16.0, "ema20_5": 15.8,
            "vol20": 1_200_000.0, "vol_now": 1.2,
            "pv_recent": set(), "score": 7.0, "rs20": 1.10,
            "chg": 1.0, "drop5": 1.0,
        }

    @staticmethod
    def original():
        return {
            "Trạng thái": WB.GOOD_ENTRY, "Danh sách": WB.G1,
            "Lý do": "Xác nhận điểm mua",
            "Vùng mua từ": 15.7, "Vùng mua đến": 16.3,
            "Giá vào": 16.0, "Cắt lỗ": 14.88,
            "Mục tiêu 1": 19.04, "Mục tiêu 2": np.nan,
            "Cản gần": 19.04, "_ma20_zone": True,
        }

    def test_old_ma20_stop_would_always_fail_but_market_plan_can_pass(self):
        price = 17.0
        f = self.features()
        fc = E.forecast_levels(price, .5, 1)
        old = WB._chart_levels({"Cản gần": 19.04}, fc, ma20=16.0, f=f)
        self.assertTrue(old["_ma20_zone"])
        old["Trạng thái"] = WB.GOOD_ENTRY
        self.assertGreater((1 - old["Cắt lỗ"] / price) * 100, 8.0)
        self.assertFalse(WB._eod_entry_check(old, price)[0])
        with mock.patch.object(WB, "_features", return_value=f):
            candidate, label = WB._eod_market_plan(self.frame(), pd.Series({"Giá": price}), self.original())
        self.assertIsNotNone(candidate, label)
        self.assertEqual(candidate["Mục tiêu 1"], 19.04)
        self.assertAlmostEqual(candidate["Cắt lỗ"], 16.4)
        yes, note = WB._eod_entry_check(candidate, price)
        self.assertTrue(yes, note)
        self.assertGreater((candidate["Mục tiêu 1"] / price - 1) * 100, 10.0)
        self.assertGreater(WB._final_rr(price, candidate["Cắt lỗ"], candidate["Mục tiêu 1"]), 2.5)

    def test_missing_resistance_never_uses_atr_2r_target(self):
        with mock.patch.object(WB, "_features", return_value=self.features(res=np.nan)):
            candidate, note = WB._eod_market_plan(self.frame(), pd.Series({"Giá": 17}), self.original())
        self.assertIsNone(candidate)
        self.assertIn("kháng cự", note)

    def test_technical_stop_too_far_fails_eight_percent_guard(self):
        with mock.patch.object(WB, "_features", return_value=self.features(res=21.0)):
            candidate, _ = WB._eod_market_plan(self.frame(low10=15.2), pd.Series({"Giá": 17}), self.original())
        self.assertIsNotNone(candidate)
        self.assertFalse(WB._eod_entry_check(candidate, 17)[0])

    def test_never_promote_below_or_within_original_buy_zone(self):
        for price in (15.5, 16.0, 16.3):
            with self.subTest(price=price):
                candidate, _ = WB._eod_market_plan(self.frame(), pd.Series({"Giá": price}), self.original())
                self.assertIsNone(candidate)

    def test_full_build_uses_eod_target_stop_and_keeps_original_zone(self):
        daily = self.frame()
        weekly = pd.DataFrame({"Mã": ["SYN"], "Giá đóng cửa": [17.0]})
        screened = pd.DataFrame([{ "Mã": "SYN", "Giá": 17.0, "Chg_%": 1.,
                                   "Score": 7.0, "RS20": 1.10, "Nhóm": "Synthetic" }])
        with (mock.patch.object(WB, "classify", return_value=self.original()),
              mock.patch.object(WB, "_features", return_value=self.features()),
              mock.patch.object(WB, "_rsi_bearish", return_value=None)):
            result = WB.build_waiting_buy({"D": daily, "W": weekly}, screened)
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["Hành động"], "Vào ngay")
        self.assertTrue(row["Vào theo EOD"])
        self.assertEqual((row["Vùng mua từ"], row["Vùng mua đến"]), (15.7, 16.3))
        self.assertEqual(row["Giá vào"], 17)
        self.assertAlmostEqual(row["Cắt lỗ"], 16.4)
        self.assertAlmostEqual(row["Mục tiêu 1"], 19.04)
        self.assertGreater(row["R:R EOD"], 2.5)
        self.assertIn("đáy 10 phiên", row["Ghi chú hành động"])
        self.assertNotEqual(row["Hành động bán"], "BÁN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
