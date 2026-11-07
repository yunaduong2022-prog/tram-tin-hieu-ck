# -*- coding: utf-8 -*-
"""Synthetic tests; no market-data reads or writes."""
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import min_t2_buy_now as B


class TestT2BuyNow(unittest.TestCase):
    @staticmethod
    def bars(close=12.3, pos=.556, vol=2.003):
        dates = pd.bdate_range("2026-10-01", periods=65)
        g = pd.DataFrame({
            "Mã": ["CEO"] * 65, "Ngày": dates,
            "Giá mở cửa": [11.95] * 65, "Giá cao nhất": [13.05] * 65,
            "Giá thấp nhất": [11.7] * 65, "Giá đóng cửa": [close] * 65,
            "Khối lượng khớ lệnh": [2_000_000] * 65,
        })
        g["Khối lượng khớp lệnh"] = g.pop("Khối lượng khớ lệnh")
        g["Ngày tín hiệu"] = dates[-3]  # unused by model, represents T+2
        g["Giá mở cửa"] = 12.0
        g["Giá thấp nhất"] = 11.9
        g["Giá cao nhất"] = 12.62
        g.loc[g.index[-2], "Giá đóng cửa"] = 12.1
        return g, dates[-3], dates[-1]

    @staticmethod
    def signal(day):
        return pd.Series({"Mã": "CEO", "Ngày tín hiệu": day,
                          "Phiên từ tín hiệu": 2, "Giá tín hiệu": 11.9,
                          "Giá EOD": 12.3, "Cắt lỗ tham khảo": 11.9,
                          "Cắt lỗ gốc": 11.4, "Mục tiêu 1": 13.7,
                          "TP1 gốc": 12.5, "Mục tiêu 2": 14.31,
                          "Tín hiệu": "Dòng tiền vào sớm"})

    @staticmethod
    def technical(bars, pos=.556, volume=2.0, ma9=11.8, ma20=11.6):
        ind = bars.copy()
        ind["MA9"] = ma9
        ind["MA20"] = ma20
        ind["RSI14"] = 62.44
        ind["VolRatio"] = volume
        ind["ClosePos"] = pos
        return ind

    def qualify(self, signal=None, pos=.556, volume=2.0,
                lifecycle="ĐÃ CHẠM TP1 GỐC", risk="THEO DÕI GIỮ"):
        bars, day, asof = self.bars()
        row = signal if signal is not None else self.signal(day)
        with (mock.patch.object(B.GUARD, "signal_lifecycle", return_value={"status": lifecycle}),
              mock.patch.object(B.GUARD, "exit_condition", return_value={"status": risk}),
              mock.patch.object(B.T2, "_indicators", return_value=self.technical(bars, pos, volume))):
            return B._qualify(row, bars, asof)

    def test_ceo_t2_rr_350_upside_1138_position_55_passes(self):
        result, reason = self.qualify()
        self.assertIsNotNone(result, reason)
        self.assertEqual(result["Mã"], "CEO")
        self.assertAlmostEqual(result["R:R EOD"], 3.5)
        self.assertAlmostEqual(result["Dư địa TP1 %"], 11.382113821, places=6)
        self.assertIn("CHỈ TRADING T+2", result["Ghi chú"])
        self.assertIn("KHÔNG NẮM GIỮ DÀI HẠN", result["Ghi chú"])
        self.assertIn("Position dưới 60%", result["Ghi chú"])

    def test_stale_signal_does_not_enter_buy_now(self):
        bars, day, asof = self.bars()
        s = self.signal(day)
        s["Phiên từ tín hiệu"] = 6
        self.assertIsNone(self.qualify(signal=s)[0])

    def test_low_reward_rr_rejected(self):
        bars, day, asof = self.bars()
        s = self.signal(day)
        s["Mục tiêu 1"] = 13.0
        self.assertIsNone(self.qualify(signal=s)[0])

    def test_t2_stop_at_entry_is_allowed_if_current_above(self):
        result, _ = self.qualify()
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["Rủi ro SL %"], (1 - 11.9 / 12.3)*100)

    def test_stop_touch_blocks_candidate(self):
        self.assertIsNone(self.qualify(lifecycle="ĐÃ CHẠM CẮT LỖ GỐC")[0])

    def test_no_bullish_candle_blocks(self):
        self.assertIsNone(self.qualify(pos=.48)[0])
        self.assertIsNone(self.qualify(volume=.9)[0])

    def test_ma_sell_blocks(self):
        self.assertIsNone(self.qualify(risk="CẢNH BÁO BÁN")[0])

    def test_original_tp_touched_without_new_target_blocks(self):
        bars, day, asof = self.bars()
        s = self.signal(day)
        s["Mục tiêu 1"] = s["TP1 gốc"]
        self.assertIsNone(self.qualify(signal=s)[0])

    def test_raised_stop_touched_after_arming_blocks(self):
        bars, day, asof = self.bars()
        s = self.signal(day)
        s["Phiên từ tín hiệu"] = 3
        s["Ngày tín hiệu"] = bars["Ngày"].iloc[-4]
        # T+3 low below the raised stop 11.9.
        bars.at[bars.index[-1], "Giá thấp nhất"] = 11.8
        with (mock.patch.object(B.GUARD, "signal_lifecycle", return_value={"status": "CHƯA CHẠM CẮT LỖ/TP GỐC"}),
              mock.patch.object(B.GUARD, "exit_condition", return_value={"status": "THEO DÕI GIỮ"}),
              mock.patch.object(B.T2, "_indicators", return_value=self.technical(bars))):
            self.assertIsNone(B._qualify(s, bars, asof)[0])

    def test_missing_market_day_rejected(self):
        bars, day, asof = self.bars()
        s = self.signal(day)
        all_days = set(bars["Ngày"]) | {pd.Timestamp(day) + pd.Timedelta(hours=12)}
        with (mock.patch.object(B.GUARD, "signal_lifecycle", return_value={"status": "CHƯA CHẠM CẮT LỖ/TP GỐC"}),
              mock.patch.object(B.GUARD, "exit_condition", return_value={"status": "THEO DÕI GIỮ"}),
              mock.patch.object(B.T2, "_indicators", return_value=self.technical(bars))):
            self.assertIsNone(B._qualify(s, bars, asof, all_days)[0])

    def test_missing_input_fails_closed(self):
        bars, day, asof = self.bars()
        s = self.signal(day)
        s["Cắt lỗ tham khảo"] = np.nan
        self.assertIsNone(self.qualify(signal=s)[0])


    def test_scanned_history_does_not_force_rejected_ticker(self):
        bars, day, asof = self.bars()
        signals = pd.DataFrame([self.signal(day), self.signal(day)])
        signals.at[1, "Mã"] = "SYN"
        other = bars.copy()
        other["Mã"] = "SYN"
        daily = pd.concat([bars, other], ignore_index=True)
        def check(row, _, __, ___):
            if row["Mã"] == "CEO":
                return None, "Đã chạm cắt lỗ gốc"
            return {col: ("SYN" if col == "Mã" else "ok") for col in B.COLUMNS}, "OK"
        with (mock.patch.object(B.T2, "_add_dynamic_targets", side_effect=lambda h, d, gap: h),
              mock.patch.object(B, "_qualify", side_effect=check)):
            accepted, reasons = B.from_scanned_history(signals, daily, asof)
        self.assertEqual(list(accepted["Mã"]), ["SYN"])
        self.assertIn("CEO", reasons)
        self.assertIn("cắt lỗ", reasons["CEO"][0])

    def test_scanned_history_zero_candidates_stays_empty(self):
        bars, day, asof = self.bars()
        signals = pd.DataFrame([self.signal(day)])
        with (mock.patch.object(B.T2, "_add_dynamic_targets", side_effect=lambda h, d, gap: h),
              mock.patch.object(B, "_qualify", return_value=(None, "Hết hiệu lực"))):
            accepted, reasons = B.from_scanned_history(signals, bars, asof)
        self.assertTrue(accepted.empty)
        self.assertEqual(reasons["CEO"], ["T+2: Hết hiệu lực"])

    def test_lifecycle_reject_reason_contains_exact_status(self):
        item, reason = self.qualify(lifecycle="ĐÃ CHẠM CẮT LỖ GỐC")
        self.assertIsNone(item)
        self.assertIn("ĐÃ CHẠM CẮT LỖ GỐC", reason)


if __name__ == "__main__":
    unittest.main(verbosity=2)
