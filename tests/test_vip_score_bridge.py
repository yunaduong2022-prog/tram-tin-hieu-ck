"""Safe read-only score bridge tests; reference module may be mocked offline."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch
import ast
import importlib.util
import math
import sys
import tempfile
import subprocess
import types
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vip_score_bridge import compute_vip_scores, _panel_html, _finite, _daily_for, render_vip_scores


class FakeVIP:
    FRAMES = ('Trung hạn','Dài hạn')
    WEIGHTS = {'Trung hạn':(0.35,0.35,0.30), 'Dài hạn':(0.5,0.2,0.3)}
    calls=[]

    @classmethod
    def fa_score_fd(cls, fd):
        cls.calls.append(('fa',fd))
        return (70, ['ROE 18.0%']) if fd else (None,[])

    @classmethod
    def ta_score(cls, g):
        cls.calls.append(('ta',len(g),str(g['Ngày'].iloc[-1])))
        return (60,['MA20 OK'])

    @classmethod
    def total_score(cls, fa, ta, sys_pts, frame='Trung hạn'):
        cls.calls.append(('total',fa,ta,sys_pts,frame))
        vals=[(w,p) for w,p in zip(cls.WEIGHTS[frame],(fa,ta,sys_pts)) if p is not None]
        return sum(w*p for w,p in vals)/sum(w for w,p in vals) if vals else None

    @classmethod
    def grade_of(cls,score):
        cls.calls.append(('grade',score))
        return 'A' if score>=75 else 'B' if score>=60 else 'C' if score>=40 else 'D'

    @classmethod
    def weights_of(cls,frame):
        return cls.WEIGHTS[frame]


def fixture_frames():
    dates=pd.bdate_range('2026-10-09',periods=31)
    return pd.DataFrame({'Mã':['HPG']*31,'Ngày':dates,
                         'Giá đóng cửa':[20+i/10 for i in range(31)],
                         'Khối lượng khớp lệnh':[1000]*31,
                         'MA20':[19]*31,'MA50':[18]*31,'MA200':[17]*31,'RSI':[57]*31})


class TestScores(unittest.TestCase):
    def setUp(self):
        FakeVIP.calls=[]
        self.d=fixture_frames()
        self.last=self.d['Ngày'].iloc[-1]
        self.screen=pd.DataFrame({'Mã':['HPG'],'Score':[8.0]})
        self.fund={'HPG':{'P/E':10, 'ROE':18, 'P/B':1.2}}

    def score(self,frame='Trung hạn',**kwargs):
        return compute_vip_scores('HPG',self.d,self.screen,self.fund,frame,
                                  asof=self.last,vip_module=FakeVIP,**kwargs)

    def test_uses_exact_vip_functions(self):
        x=self.score()
        self.assertEqual(x['fa'],70)
        self.assertEqual(x['ta'],60)
        self.assertEqual(x['system'],80)
        self.assertAlmostEqual(x['total'],.35*70+.35*60+.3*80)
        self.assertEqual(x['grade'],'B')
        self.assertEqual(FakeVIP.calls[0][0],'fa')
        self.assertEqual(FakeVIP.calls[1][0],'ta')
        self.assertEqual(FakeVIP.calls[1][1],30)
        self.assertIn(('total',70,60,80.0,'Trung hạn'),FakeVIP.calls)

    def test_long_term_uses_vip_long_weights(self):
        x=self.score(frame='Dài hạn')
        self.assertAlmostEqual(x['total'],.50*70+.20*60+.30*80)
        self.assertIn(('total',70,60,80.0,'Dài hạn'),FakeVIP.calls)

    def test_missing_system_redistributes_weight_same_as_vip(self):
        self.screen=pd.DataFrame({'Mã':['HPG'],'Score':[float('nan')]})
        x=self.score()
        self.assertEqual(x['system'],None)
        self.assertAlmostEqual(x['total'],(.35*70+.35*60)/(.35+.35))
        self.assertIn('Thiếu Score hệ thống',x['status'])

    def test_no_fake_zero_for_missing(self):
        self.screen=pd.DataFrame({'Mã':['HPG'],'Score':[float('nan')]})
        self.fund={}
        x=self.score()
        self.assertIsNone(x['fa'])
        self.assertIsNone(x['system'])
        self.assertAlmostEqual(x['total'],60)

    def test_stale_symbol_block_total_and_technical(self):
        x=compute_vip_scores('HPG',self.d,self.screen,self.fund,asof='2026-12-31',vip_module=FakeVIP)
        self.assertIsNone(x['ta'])
        self.assertIsNone(x['total'])
        self.assertEqual(x['fa'],70)
        self.assertIn('chưa tính TA',x['status'])
        self.assertFalse(any(c[0]=='ta' for c in FakeVIP.calls))

    def test_indexes_never_scored(self):
        x=compute_vip_scores('VNINDEX',self.d,self.screen,self.fund,asof=self.last,vip_module=FakeVIP)
        self.assertIsNone(x['total'])
        self.assertFalse(FakeVIP.calls)

    def test_missing_eod_no_made_up_ta(self):
        x=compute_vip_scores('SSI',self.d,self.screen,{},asof=self.last,vip_module=FakeVIP)
        self.assertIsNone(x['total'])
        self.assertIsNone(x['ta'])

    def test_infinite_score_not_treated_as_zero(self):
        self.screen=pd.DataFrame({'Mã':['HPG'],'Score':[float('inf')]})
        self.assertIsNone(self.score()['system'])

    def test_zero_is_valid_score(self):
        self.screen=pd.DataFrame({'Mã':['HPG'],'Score':[0]})
        self.assertEqual(self.score()['system'],0)

    def test_rejected_horizon(self):
        with self.assertRaisesRegex(ValueError,'UNSUPPORTED_VIP_SCORE_FRAME'):
            self.score(frame='1H')

    def test_30_daily_rows_sorted(self):
        self.d=self.d.sample(frac=1.0,random_state=4)
        self.score()
        self.assertEqual(FakeVIP.calls[1][1],30)
        self.assertEqual(pd.Timestamp(FakeVIP.calls[1][2]),self.last)

    def test_does_not_mutate_inputs(self):
        d=self.d.copy(deep=True);s=self.screen.copy(deep=True);f=self.fund.copy()
        self.score()
        pd.testing.assert_frame_equal(d,self.d)
        pd.testing.assert_frame_equal(s,self.screen)
        self.assertEqual(f,self.fund)

    def test_html_displays_missing_dash_and_grade(self):
        x=self.score()
        h=_panel_html(x,mode='live')
        self.assertIn('Điểm cơ bản (FA)',h)
        self.assertIn('Điểm kỹ thuật (TA)',h)
        self.assertIn('Tổng điểm',h)
        self.assertIn('Hạng B',h)
        self.assertIn('70.0',h)
        self.assertNotIn('None',h)
        x['total']=None
        self.assertIn('—',_panel_html(x,mode='stock'))

    def test_date_only_normalized(self):
        x=compute_vip_scores('HPG',self.d,self.screen,self.fund,
                             asof=self.last.strftime('%Y-%m-%d')+' 15:00:00',vip_module=FakeVIP)
        self.assertIsNotNone(x['total'])

    def test_component_count(self):
        self.assertEqual(_daily_for('HPG',self.d)[0].shape[0],30)

    def test_nonfinite(self):
        for bad in ('a',None,False,float('nan'),float('inf')):
            self.assertIsNone(_finite(bad))


class TestRender(unittest.TestCase):
    def test_ui_is_consistent_with_vip_and_no_writes(self):
        captured={'markup':[],'caption':[],'writes':[]}
        st=types.ModuleType('streamlit')
        st.selectbox=lambda label,options,**kw:'Dài hạn'
        st.markdown=lambda m,**kw:captured['markup'].append(m)
        st.caption=lambda m:captured['caption'].append(m)
        st.write=lambda m:captured['writes'].append(m)
        class Context:
            def __enter__(self):return self
            def __exit__(self,*args):return False
        st.expander=lambda *a,**kw:Context()
        with patch.dict(sys.modules,{'streamlit':st,'vip_picks':FakeVIP}):
            render_vip_scores('HPG',fixture_frames(),pd.DataFrame({'Mã':['HPG'],'Score':[8.0]}),
                              {'HPG':{'ROE':18}},fixture_frames()['Ngày'].iloc[-1],key='test',mode='live')
        self.assertIn('Tổng điểm',''.join(captured['markup']))
        self.assertIn('50%',''.join(captured['caption']))
        self.assertIn('Điểm hệ thống',''.join(captured['writes']))
        src=(ROOT/'vip_score_bridge.py').read_text('utf8')
        for bad in ('requests.', 'to_csv(', 'git push', 'VP.load(', 'vip.load('):
            self.assertNotIn(bad,src)


class TestPatch(unittest.TestCase):
    def test_guarded_integration_lf_crlf_and_idempotence(self):
        script=ROOT/'patch_vip_scores.py'
        with tempfile.TemporaryDirectory() as tmp:
            for eol in ('\n','\r\n'):
                dir_=Path(tmp)/('lf' if eol=='\n' else 'crlf')
                dir_.mkdir()
                text='''import vip_picks as VP

def page_stock():
    tf = c2.selectbox("Khung thời gian", ["1H", "D", "W", "M"], index=1, format_func=TF_LABEL.get)
    if True:
        return

def page_livestream():
    with right:
        # MA and D/W/M are displayed together, but their scores are NOT mixed.
        pass
'''
                (dir_/'app.py').write_bytes(text.replace('\n',eol).encode('utf8'))
                completed=subprocess.run([sys.executable,str(script),str(dir_)],capture_output=True,text=True)
                self.assertEqual(completed.returncode,0,completed.stderr)
                actual=(dir_/'app.py').read_bytes()
                self.assertIn(b'MIN_VIP_SCORE_BRIDGE_CHART_LIVE_20261124',actual)
                self.assertEqual(actual.count(b'MIN_VIP_SCORE_BRIDGE_CHART_LIVE_20261124'),2)
                self.assertEqual(actual.count(eol.encode()),len(actual.split(eol.encode()))-1)
                ast.parse(actual.decode('utf8'))
                again=subprocess.run([sys.executable,str(script),str(dir_)],capture_output=True,text=True)
                self.assertNotEqual(again.returncode,0)

    def test_real_repo_hook_when_present(self):
        root=ROOT
        if not (root/'app.py').exists():
            self.skipTest('Full repo integration runs in fresh Git clone')
        app=(root/'app.py').read_text('utf-8-sig')
        ast.parse(app)
        self.assertEqual(app.count('MIN_VIP_SCORE_BRIDGE_CHART_LIVE_20261124'),2)
        self.assertIn('key="vip_scores_stock_chart", mode="stock"',app)
        self.assertIn('key="vip_scores_livestream", mode="live"',app)


if __name__=='__main__':
    unittest.main()
