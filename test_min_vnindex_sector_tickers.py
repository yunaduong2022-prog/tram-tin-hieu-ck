"""Smoke regression tests: VNINDEX sector leaders by current timeframe."""
import unittest
import numpy as np
import pandas as pd
from vnindex_auto import _sector_flow_details, _window_sum, TF_BARS


def sample_data():
    days = pd.bdate_range('2026-01-01', periods=170)
    cols = {}
    vol = {}
    for sector, mult, val_mult in [('CK', 1.002, 1.4), ('BDS', 1.0015, 1.3),
                                   ('BANK', 1.001, 1.2), ('OIL', 0.998, 1.4),
                                   ('RETAIL', 0.997, 1.2), ('STEEL', 0.996, 1.1)]:
        for j in range(4):
            name = f'{sector}{j}'
            cols[name] = np.array([20 * (mult ** t) for t in range(len(days))])
            vol[name] = np.array([100 * (1.15 ** t) for t in range(len(days))])
    close = pd.DataFrame(cols, index=days)
    value = pd.DataFrame(vol, index=days)
    groups = {g: [f'{g}{j}' for j in range(4)] for g in ['CK', 'BDS', 'BANK', 'OIL', 'RETAIL', 'STEEL']}
    return close, value, groups


class TopSectorTests(unittest.TestCase):
    def test_all_timeframes_three_up_three_down_with_tickers(self):
        close, value, groups = sample_data()
        for tf in ('D', 'W', 'M', 'Q'):
            with self.subTest(tf=tf):
                i = len(close) - 1
                k = TF_BARS[tf]
                ret = close.iloc[i] / close.iloc[i-k] - 1
                up, down = _sector_flow_details({'close':close,'value':value}, groups, i, k, 2, ret, value.iloc[i-k+1:i+1].sum().sum())
                self.assertEqual(len(up), 3)
                self.assertEqual(len(down), 3)
                self.assertTrue(all(3 <= len(x[3]) <= 5 for x in up + down))
                self.assertTrue(all(x[2] > 0 for x in up))
                self.assertTrue(all(x[2] < 0 for x in down))

    def test_missing_and_incomplete_groups_ignored(self):
        close, value, groups = sample_data()
        groups['TINY'] = ['CK0', 'CK1']
        i = len(close) - 1
        ret = close.iloc[i]/close.iloc[i-5]-1
        up, down = _sector_flow_details({'close':close,'value':value}, groups, i, 5, 2, ret, value.iloc[i-4:i+1].sum().sum())
        self.assertFalse(any(row[0] == 'TINY' for row in up + down))

    def test_no_future_data(self):
        close, value, groups = sample_data()
        i = len(close) - 4
        k = 5
        ret = close.iloc[i] / close.iloc[i-k] - 1
        total = value.iloc[i-k+1:i+1].sum().sum()
        base = _sector_flow_details({'close':close,'value':value}, groups, i, k, 2, ret, total)
        close.iloc[i+1:] *= 100
        value.iloc[i+1:] *= 100
        again = _sector_flow_details({'close':close,'value':value}, groups, i, k, 2, ret, total)
        self.assertEqual(base, again)

    def test_high_volume_selloff_not_inflow(self):
        close, value, groups = sample_data()
        i = len(close)-1
        ret = close.iloc[i]/close.iloc[i-5]-1
        up, down = _sector_flow_details({'close':close,'value':value}, groups, i, 5, 2, ret, value.iloc[i-4:i+1].sum().sum())
        self.assertNotIn('OIL', [x[0] for x in up])
        self.assertIn('OIL', [x[0] for x in down])

    def test_no_groups_if_no_value(self):
        close, value, groups = sample_data()
        i=len(close)-1
        ret=close.iloc[i]/close.iloc[i-5]-1
        up,down=_sector_flow_details({'close':close,'value':value}, groups, i,5,2,ret,0)
        self.assertEqual((up,down), ([],[]))


if __name__ == '__main__':
    unittest.main()
