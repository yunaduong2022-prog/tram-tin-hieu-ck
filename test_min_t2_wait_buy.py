# -*- coding: utf-8 -*-
"""Synthetic, no network, no EOD data edits. Verify split classification and barriers."""
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import min_t2_buy_now as B


class TestT2Waiting(unittest.TestCase):
    @staticmethod
    def setup_case(code='CTS', price=23.35, stop=22.84, tp1=27.95, vol=2.14):
        days = pd.bdate_range('2026-09-01', periods=62)
        g = pd.DataFrame({
            'Mã': [code] * 62, 'Ngày': days,
            'Giá mở cửa': [price - .20] * 62,
            'Giá cao nhất': [price + .1] * 62,
            'Giá thấp nhất': [price - .5] * 62,
            'Giá đóng cửa': [price] * 62,
            'Khối lượng khớp lệnh': [2_000_000] * 62,
        })
        g.loc[g.index[-2], 'Giá đóng cửa'] = price - .3
        sig = pd.Series({
            'Mã': code, 'Ngày tín hiệu': days[-1], 'Phiên từ tín hiệu': 0,
            'Giá tín hiệu': price, 'Giá EOD': price,
            'Cắt lỗ tham khảo': stop, 'Cắt lỗ gốc': stop,
            'Mục tiêu 1': tp1, 'Mục tiêu 2': tp1 + 1.10,
            'TP1 gốc': tp1, 'TP2 gốc': tp1 + 1.10,
            'Tín hiệu': 'Tiếp diễn ngắn hạn', 'Ghi chú': 'Tín hiệu EOD',
        })
        ind = g.copy()
        ind['MA9'] = price - .5
        ind['MA20'] = price - 1
        ind['RSI14'] = 66.0
        ind['VolRatio'] = vol
        ind['ClosePos'] = .86
        return g, sig, ind

    def classified(self, warning='Cản gần: 23.65 (Đỉnh 20P), 23.85 (Đỉnh 11/08)',
                   lifecycle='CHƯA CHẠM CẮT LỖ/TP GỐC', code='CTS', vol=2.14):
        bars, signal, indicator = self.setup_case(code, vol=vol)
        with (mock.patch.object(B.T2, '_add_dynamic_targets', side_effect=lambda h,d,threshold:h) as dyn,
              mock.patch.object(B.T2, '_indicators', return_value=indicator),
              mock.patch.object(B.T2, '_dynamic_resistance_eod', return_value=(27.95, 'đỉnh', 29.06, 'đỉnh', warning)) as near,
              mock.patch.object(B.GUARD, 'signal_lifecycle', return_value={'status':lifecycle}),
              mock.patch.object(B.GUARD, 'exit_condition', return_value={'status':'THEO DÕI GIỮ'})):
            buy, wait, notes = B.split_from_scanned_history(pd.DataFrame([signal]), bars, bars['Ngày'].iat[-1])
        return buy, wait, notes, dyn.call_count, near.call_count

    def test_cts_moves_from_buy_to_wait_on_23_65_near_resistance(self):
        buy, wait, _, _, _ = self.classified()
        self.assertTrue(buy.empty)
        self.assertEqual(wait['Mã'].tolist(), ['CTS'])
        r = wait.iloc[0]
        self.assertAlmostEqual(r['Cản cần vượt'], 23.65)
        self.assertAlmostEqual(r['R:R đến cản'], .30 / .51, places=4)
        self.assertIn('vượt 23.65', r['Điều kiện kích hoạt'])
        self.assertIn('KHÔNG NẮM GIỮ DÀI HẠN', r['Ghi chú'])

    def test_no_near_resistance_means_buy(self):
        buy, wait, _, _, _ = self.classified(warning='')
        self.assertTrue(wait.empty)
        self.assertEqual(buy['Mã'].tolist(), ['CTS'])
        self.assertAlmostEqual(buy['R:R EOD'].iloc[0], (27.95-23.35)/(.51), places=5)

    def test_ceo_finished_tp2_is_neither_buy_nor_wait(self):
        buy, wait, notes, _, near_calls = self.classified(code='CEO', lifecycle='ĐÃ CHẠM TP2 GỐC')
        self.assertTrue(buy.empty)
        self.assertTrue(wait.empty)
        self.assertIn('ĐÃ CHẠM TP2 GỐC', notes['CEO'][0])
        self.assertEqual(near_calls, 0)

    def test_mild_volume_1_10_must_wait_and_not_buy(self):
        buy, wait, _, _, _ = self.classified(vol=1.10, warning='')
        self.assertTrue(buy.empty)
        self.assertEqual(wait['Mã'].tolist(), ['CTS'])
        self.assertIn('khối lượng', wait.iloc[0]['Điều kiện kích hoạt'])

    def test_weak_volume_below_one_is_neither(self):
        buy, wait, notes, _, _ = self.classified(vol=.9, warning='')
        self.assertTrue(buy.empty)
        self.assertTrue(wait.empty)
        self.assertIn('Cần nến tăng', notes['CTS'][0])

    def test_unreadable_caution_never_produces_mua_ngay(self):
        buy, wait, _, _, _ = self.classified(warning='Cản gần: dữ liệu lạ')
        self.assertTrue(buy.empty)
        self.assertEqual(wait['Mã'].tolist(), ['CTS'])
        self.assertIn('Xác minh lại kháng cự', wait.iloc[0]['Điều kiện kích hoạt'])

    def test_one_dynamic_target_recalc_one_barrier_lookup(self):
        _, _, _, dynamic_calls, resistance_calls = self.classified()
        self.assertEqual(dynamic_calls, 1)
        self.assertEqual(resistance_calls, 1)

    def test_no_signals_returns_two_empty_dataframes(self):
        g, _, _ = self.setup_case()
        buy, wait, notes = B.split_from_scanned_history(pd.DataFrame(), g, g['Ngày'].iat[-1])
        self.assertTrue(buy.empty)
        self.assertTrue(wait.empty)
        self.assertIn('Điều kiện kích hoạt', wait.columns)
        self.assertEqual(notes,{})

    def test_guard_sell_rejects_not_wait(self):
        bars, signal, indicator = self.setup_case()
        with (mock.patch.object(B.T2, '_add_dynamic_targets', side_effect=lambda h,d,t:h),
              mock.patch.object(B.GUARD, 'signal_lifecycle', return_value={'status':'CHƯA CHẠM CẮT LỖ/TP GỐC'}),
              mock.patch.object(B.GUARD, 'exit_condition', return_value={'status':'CẢNH BÁO BÁN'}),
              mock.patch.object(B.T2, '_indicators', return_value=indicator)):
            buy, wait, notes = B.split_from_scanned_history(pd.DataFrame([signal]), bars, bars['Ngày'].iat[-1])
        self.assertTrue(buy.empty)
        self.assertTrue(wait.empty)
        self.assertIn('cảnh báo MA20', notes['CTS'][0])

    def test_no_ticker_hardcoding(self):
        buy, wait, _, _, _ = self.classified(code='AAA', warning='')
        self.assertEqual(buy['Mã'].tolist(), ['AAA'])
        self.assertTrue(wait.empty)

    def test_only_latest_signal_per_ticker_even_if_duplicate(self):
        bars, signal, indicator = self.setup_case()
        history = pd.DataFrame([signal, signal])
        with (mock.patch.object(B.T2, '_add_dynamic_targets', side_effect=lambda h,d,t:h),
              mock.patch.object(B.GUARD, 'signal_lifecycle', return_value={'status':'CHƯA CHẠM CẮT LỖ/TP GỐC'}),
              mock.patch.object(B.GUARD, 'exit_condition', return_value={'status':'THEO DÕI GIỮ'}),
              mock.patch.object(B.T2, '_indicators', return_value=indicator),
              mock.patch.object(B.T2, '_dynamic_resistance_eod', return_value=(27.95,'',29.06,'','')) as lev):
            buy,wait,_ = B.split_from_scanned_history(history,bars,bars['Ngày'].iat[-1])
        self.assertEqual(len(buy),1)
        self.assertEqual(len(wait),0)
        self.assertEqual(lev.call_count,1)

    def test_candidate_pair_makes_one_scan(self):
        bars, _, _ = self.setup_case()
        with (mock.patch.object(B.T2, 'prepare', return_value=bars),
              mock.patch.object(B.T2, 'scan', return_value=(pd.DataFrame(),pd.DataFrame())) as scan,
              mock.patch.object(B, 'split_from_scanned_history', return_value=(pd.DataFrame(columns=B.COLUMNS),pd.DataFrame(columns=B.WAIT_COLUMNS),{}))):
            buy,wait=B.candidates_both(bars,bars['Ngày'].iat[-1])
        self.assertEqual(scan.call_count,1)
        self.assertTrue(buy.empty)
        self.assertTrue(wait.empty)


if __name__=='__main__':
    unittest.main(verbosity=2)
