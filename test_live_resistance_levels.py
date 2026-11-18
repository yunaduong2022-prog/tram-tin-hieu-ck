"""Offline regression tests for three distinct price level concepts."""
from __future__ import annotations

import math

import pandas as pd

from live_resistance_levels import build_ladder, spoken_summary


def scenario(close=16.15, res20=16.0, high=20.0, low=14.7, days=130, enough=True):
    g = pd.DataFrame({
        'Giá đóng cửa': [close] * days,
        'Giá cao nhất': [high] * days,
        'Giá thấp nhất': [low] * days,
        'Resistance_20': [res20] * days,
    })
    return {'D': {'g': g, 'enough': enough}}


def test_kdh_three_distinct_levels():
    r = build_ladder(scenario())
    assert r['res20'] == 16.0
    assert r['kijun129'] == 17.35
    assert round(r['hyp15'], 2) == 18.57
    assert r['overhead_kijun'] == 17.35
    assert [row['Giá'] for row in r['rows']] == ['16.00', '17.35', '18.57']
    assert 'Giá đã vượt' in r['rows'][0]['Ý nghĩa']
    assert 'Không phải kháng cự' in r['rows'][2]['Ý nghĩa']


def test_no_129_bars_no_kijun_invented():
    r = build_ladder(scenario(days=50))
    assert r['kijun129'] is None and r['overhead_kijun'] is None
    assert r['rows'][1]['Giá'] == '—'
    assert 'Chưa đủ dữ liệu Kijun' in spoken_summary(r)


def test_kijun_below_price_is_not_next_resistance():
    r = build_ladder(scenario(close=21.0))
    assert r['overhead_kijun'] is None
    assert 'dưới giá' in spoken_summary(r)


def test_missing_daily_never_creates_levels():
    r = build_ladder({'D': {'enough': False, 'g': scenario()['D']['g']}})
    assert r['res20'] is None and r['kijun129'] is None and r['hyp15'] is None
    assert 'Chưa đủ' in spoken_summary(r)


def test_nan_levels_rejected():
    r = build_ladder(scenario(close=16.15, res20=float('nan')))
    assert r['res20'] is None
    r = build_ladder(scenario(close=-1, res20=16))
    assert r['hyp15'] is None
    r = build_ladder(scenario(high=float('inf')))
    assert r['kijun129'] is None


def test_touch_is_not_a_breakout():
    r = build_ladder(scenario(close=16))
    assert r['rows'][0]['Ý nghĩa'] == 'Đang chạm mốc'
    assert 'chưa vượt' in spoken_summary(r)


def test_value_15pct_never_technical_target_in_spoken():
    t = spoken_summary(build_ladder(scenario()))
    assert '16.00' in t and '17.35' in t and '18.57' in t
    assert 'không phải mục tiêu đã xác nhận' in t


if __name__ == '__main__':
    tests = sorted((name, obj) for name, obj in globals().items()
                   if name.startswith('test_') and callable(obj))
    for name, fn in tests:
        fn()
        print('PASS', name)
    print('LIVE_RESISTANCE_TESTS_PASS:', len(tests))
