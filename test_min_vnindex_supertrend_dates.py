# -*- coding: utf-8 -*-
"""Regression: weekly/monthly category labels must not be fed to pd.Timestamp."""
from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

import vnindex_view as VV


class TestVnindexSupertrendDateLabels(unittest.TestCase):
    def _chart(self, tf):
        freq = {'D': 'B', 'W': 'W-FRI', 'M': 'ME', 'Q': 'QE'}[tf]
        days = pd.date_range('2023-01-01', periods=8, freq=freq)
        labels = [VV._label(pd.Timestamp(t), tf) for t in days]
        close = np.arange(8, dtype=float) + 102.0
        rows = pd.DataFrame({
            'Ngày': days,
            VV.O: close - .5,
            VV.H: close + 1,
            VV.L: close - 1,
            VV.C: close,
            VV.V: np.full(8, 10_000_000),
            'ST_trend': np.ones(8, dtype=int),
            'ST_ohlc4': close,
            'ST_up': close - 1.5,
            'ST_dn': np.full(8, np.nan),
            'ST_buy': [False] * 7 + [True],
            'ST_sell': [False] * 8,
            'ST_close': close,
        })
        chart = VV.build_chart({'g': rows, 'tf': tf, 'labels': labels, 'mas': [], 'ticks': []},
                               supertrend=True, hull=False)
        trade_labels = [a for a in chart.layout.annotations if str(a.text).startswith('Buy ')]
        self.assertEqual(len(trade_labels), 1, f'Missing Buy annotation for {tf}')
        self.assertEqual(trade_labels[0].x, labels[-1], f'Wrong category position for {tf}')
        self.assertIn(f'{days[-1]:%d/%m}', str(trade_labels[0].text))

    def test_week_supertrend_annotations(self):
        self._chart('W')

    def test_day_supertrend_annotations(self):
        self._chart('D')

    def test_month_supertrend_annotations(self):
        self._chart('M')

    def test_quarter_supertrend_annotations(self):
        self._chart('Q')


if __name__ == '__main__':
    unittest.main(verbosity=2)
