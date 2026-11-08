"""Regression tests for VNINDEX/Dong dan song synchronization."""
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from vnindex_leading_sync import PERIOD_FOR_TF, leading_items, replace_strong_sector_block, leading_from_eod

class SyncTests(unittest.TestCase):
    def test_period_mapping(self):
        self.assertEqual([PERIOD_FOR_TF[x][1] for x in 'DWMQ'], [5,5,21,63])
    def test_week_ranks_with_real_estate_third(self):
        data = [{'group':'Chứng khoán','return':5.6,'codes':['VND','VIX'],'rank':1},
                {'group':'Đầu tư công','return':4.4,'codes':['VCG','CTD'],'rank':2},
                {'group':'Bất động sản','return':4.0,'codes':['HDC','TCH','CEO'],'rank':3}]
        items=leading_items(data,'W')
        self.assertIn('Bất động sản', items[1]['text'])
        self.assertEqual(items[-1]['text'], 'Bất động sản: HDC, TCH, CEO')
        self.assertIn('không phải dòng tiền mua ròng',items[1]['text'])
    def test_replace_preserves_weak_and_other_sections(self):
        sections=[{'name':'TIN TỨC','items':[{'text':'news'}]},
                  {'name':'DÒNG TIỀN','items':[
                      {'text':'Độ rộng','tone':'','subs':[]},
                      {'text':'TOP 3 NHÓM HÚT TIỀN:','tone':'xanh','subs':[]},
                      {'text':'Nhận định cũ','tone':'','subs':[]},
                      {'text':'Họ Gelex: VIX','tone':'xanh','subs':[]},
                      {'text':'TOP 3 NHÓM YẾU:','tone':'do','subs':[]},
                      {'text':'Dầu khí: PVS','tone':'do','subs':[]}]},
                  {'name':'LƯU Ý','items':[{'text':'FOMO'}]}]
        got=replace_strong_sector_block(sections,[{'group':'Bất động sản','return':4.0,'codes':['CEO'],'rank':3}],'W')
        lines=[x['text'] for x in got[1]['items']]
        self.assertTrue(any('Bất động sản: CEO' == x for x in lines))
        self.assertFalse(any('Họ Gelex:' in x for x in lines))
        self.assertIn('TOP 3 NHÓM YẾU:',lines)
        self.assertIn('Dầu khí: PVS',lines)
        self.assertEqual(got[0],sections[0]); self.assertEqual(got[2],sections[2])
    def test_no_group(self):
        self.assertIn('Chưa có nhóm',leading_items([], 'D')[0]['text'])
    def test_no_old_block(self):
        s=[{'name':'DÒNG TIỀN','items':[{'text':'GTGD','tone':'','subs':[]},{'text':'TOP 3 NHÓM YẾU:','tone':'do','subs':[]}]}]
        x=replace_strong_sector_block(s,[],'D')[0]['items']
        self.assertEqual(x[0]['text'],'GTGD'); self.assertIn('DẪN SÓNG',x[1]['text']); self.assertIn('YẾU',x[2]['text'])
    def test_actual_rank_bridge_uses_third_real_estate(self):
        import sys
        from types import SimpleNamespace
        dates = pd.bdate_range('2026-07-01', periods=85)
        c = pd.DataFrame({'VND': range(85,170), 'VCG': range(90,175),
                          'HDC': range(100,185), 'TCH': range(105,190),
                          'CEO': range(110,195)}, index=dates).astype(float)
        raw = pd.DataFrame({'Ngày':dates, 'Mã':['VND']*85, 'Giá đóng cửa':c['VND'].values})
        idx = pd.DataFrame({'Ngày':dates, 'Giá đóng cửa':range(1000,1085)})
        board = pd.DataFrame({'Dòng':['Chứng khoán','Đầu tư công','Bất động sản'],
                              '#':[1,2,3], 'Dẫn sóng':[True,True,True],
                              'Giai đoạn':[5.6,4.4,4.0]})
        groups={'Chứng khoán':['VND'], 'Đầu tư công':['VCG'],
                'Bất động sản':['HDC','TCH','CEO']}
        got_periods=[]
        def fake_period(p, group, market, n):
            got_periods.append(n)
            self.assertEqual(list(p['c'].index)[-1],dates[-1])
            return board, {}
        def fake_rep(p, members, n, leaders=None, top=None):
            return pd.DataFrame({'Mã':members[:top]})
        fake_nd = SimpleNamespace(load_groups=lambda fallback:(groups, {}),
                                  period_stats=fake_period,rep_stocks=fake_rep)
        fake_srt = SimpleNamespace(_prep=lambda unused:{'c':c,'v':pd.DataFrame()})
        with patch.dict(sys.modules, {'nhom_nganh_data':fake_nd,'sector_rotation':fake_srt}):
            result=leading_from_eod(raw,idx,'W',groups)
        self.assertEqual(got_periods,[5])
        self.assertEqual([x['group'] for x in result],list(board['Dòng']))
        self.assertEqual(result[2]['codes'],['HDC','TCH','CEO'])

    def test_no_mutation(self):
        sec=[{'name':'DÒNG TIỀN','items':[{'text':'abc'}]}]
        replace_strong_sector_block(sec,[],'D')
        self.assertEqual(sec,[{'name':'DÒNG TIỀN','items':[{'text':'abc'}]}])

if __name__=='__main__': unittest.main()
