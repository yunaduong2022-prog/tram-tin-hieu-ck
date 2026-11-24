"""No-network tests for score cards under plots; VIP scoring math must not change."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vip_score_bridge import _panel_html, compute_vip_scores


class FakeVIP:
    FA_WEAK = 30

    @staticmethod
    def fa_score_fd(fd):
        return (93, ['P/E rẻ (9.00)', 'P/B dưới sổ sách (0.80)']) if fd else (None, [])

    @staticmethod
    def ta_score(g):
        return 81, ['Trên MA20 (+5.07%)', 'Trên MA50 và MA200', 'KL 0.9x TB20']

    @staticmethod
    def total_score(fa, ta, sys_pts, frame='Trung hạn'):
        weights = {'Trung hạn': (0.35, 0.35, 0.30), 'Dài hạn': (0.50, 0.20, 0.30)}[frame]
        known = [(w, x) for w, x in zip(weights, (fa, ta, sys_pts)) if x is not None]
        return sum(w*x for w, x in known)/sum(w for w, _ in known) if known else None

    @staticmethod
    def grade_of(score):
        return 'A' if score >= 75 else 'B' if score >= 60 else 'C' if score >= 40 else 'D'

    @staticmethod
    def weights_of(frame):
        return {'Trung hạn': (0.35,0.35,0.30), 'Dài hạn': (0.50,0.20,0.30)}[frame]


def values():
    dates = pd.bdate_range('2026-10-01', periods=30)
    daily = pd.DataFrame({'Mã': ['HPG']*30, 'Ngày': dates,
        'RSI': [63.1]*30, 'Giá đóng cửa': [28.0]*30,
        'Khối lượng khớp lệnh': [80000]*30})
    return daily, pd.DataFrame({'Mã':['HPG'], 'Score':[8.0]}), {'HPG':{'P/E':9.0}}


class TestVisual(unittest.TestCase):
    def setUp(self):
        daily, screener, fund = values()
        self.result = compute_vip_scores('HPG',daily,screener,fund,asof=daily['Ngày'].iloc[-1],vip_module=FakeVIP)

    def test_calculated_total_unmodified(self):
        self.assertAlmostEqual(self.result['total'],93*.35+81*.35+80*.30)
        self.assertEqual(self.result['grade'],'A')

    def test_vip_style_three_columns_and_grades(self):
        html = _panel_html(self.result,mode='stock')
        for marker in ('Điểm cơ bản (FA)', 'Điểm kỹ thuật (TA)', 'Tổng điểm',
                       'mvs-grid', 'mvs-bar', 'mvs-badge', 'Hạng A'):
            self.assertIn(marker,html)
        self.assertEqual(html.count('class="mvs-item"'),3)

    def test_score_counts_and_hover_decimal(self):
        html = _panel_html(self.result,mode='stock')
        self.assertIn('93.0/100',html)
        self.assertIn('81.0/100',html)
        self.assertIn('RSI 63.1',html)
        self.assertIn('P/E rẻ (9.00)',html)
        self.assertIn('Trên MA20 (+5.07%)',html)

    def test_tags_escape_user_supplied_text(self):
        r=dict(self.result,tags_fa=['<script>alert(1)</script>'])
        html = _panel_html(r,mode='live')
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)

    def test_responsive_and_bar_bounded(self):
        r=dict(self.result, fa=200, ta=-20)
        html = _panel_html(r,mode='stock')
        self.assertIn('@media(max-width:760px)',html)
        self.assertIn('width:100.0%',html)
        self.assertIn('width:0.0%',html)

    def test_missing_does_not_become_zero(self):
        r=dict(self.result,fa=None,ta=None,total=None,grade=None)
        html = _panel_html(r,mode='stock')
        self.assertIn('Chưa đủ chỉ tiêu FA',html)
        self.assertIn('Chưa đủ dữ liệu TA',html)
        self.assertNotIn('Hạng A',html)
        self.assertIn('—',html)

    def test_dark_theme_livestream_and_light_theme_stock(self):
        self.assertIn('background:#102620',_panel_html(self.result,mode='live'))
        self.assertIn('var(--card',_panel_html(self.result,mode='stock'))

    def test_index_never_scores(self):
        d,sc,f=values()
        result=compute_vip_scores('VNINDEX',d,sc,f,asof=d['Ngày'].iloc[-1],vip_module=FakeVIP)
        self.assertIsNone(result['total'])

    def test_old_eod_no_fake_total(self):
        d,sc,f=values()
        result=compute_vip_scores('HPG',d,sc,f,asof='2026-12-30',vip_module=FakeVIP)
        self.assertIsNone(result['total'])
        self.assertIsNone(result['ta'])


class TestAppHooks(unittest.TestCase):
    def test_existing_repo_chart_positions_when_installed(self):
        app = ROOT/'app.py'
        if not app.is_file():
            self.skipTest('Full repo only')
        text = app.read_text(encoding='utf-8-sig')
        ast.parse(text)
        marker='MIN_VIP_SCORE_CARDS_BELOW_CHART_V2_20261124'
        self.assertEqual(text.count(marker),2)
        self.assertEqual(text.count('MIN_VIP_SCORE_BRIDGE_CHART_LIVE_20261124'),2)
        stock=text.split('def page_stock():',1)[1].split('\ndef page_stock_tab(sub):',1)[0]
        live=text.split('def page_livestream():',1)[1]
        self.assertEqual(stock.count('_stock_score_panel_below_chart()'),5)  # 4 branch calls + 1 definition
        self.assertLess(stock.index('DT.inject(code, tf)'),stock.index('_stock_score_panel_below_chart()',stock.index('DT.inject(code, tf)')))
        self.assertLess(live.index('range_bar_ui("W"'),live.index('key="vip_scores_livestream"'))
        self.assertLess(live.index('key="vip_scores_livestream"'),live.index('    with right:'))

    def test_no_vip_formula_modifications(self):
        src=(ROOT/'vip_score_bridge.py').read_text('utf-8')
        for fn in ('vip.fa_score_fd(', 'vip.ta_score(', 'vip.total_score(', 'vip.grade_of('):
            self.assertIn(fn,src)
        self.assertNotIn('requests.get(',src)
        self.assertNotIn('to_csv(',src)


if __name__=='__main__':
    unittest.main()
