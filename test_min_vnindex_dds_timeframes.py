"""VNINDEX leading sectors must match the timeframe selected by user."""
import unittest
from unittest.mock import patch
import sys
from types import SimpleNamespace
import pandas as pd
from vnindex_leading_sync import PERIOD_FOR_TF, leading_from_eod, leading_items

class TimeframeTests(unittest.TestCase):
    def test_exact_mapping(self):
        self.assertEqual(PERIOD_FOR_TF, {'D': ('1 phiên',1), 'W': ('1 tuần',5), 'M': ('1 tháng',21), 'Q': ('3 tháng',63)})

    def test_distinct_labels_and_bars(self):
        rows=[{'group':'Bất động sản','return':4.0,'codes':['HDC','TCH','CEO'],'rank':1}]
        for tf, label, count in [('D','1 phiên','1 phiên'),('W','1 tuần','5 phiên'),('M','1 tháng','21 phiên'),('Q','3 tháng','63 phiên')]:
            with self.subTest(tf=tf):
                result=leading_items(rows,tf)
                self.assertIn(label,result[0]['text'])
                self.assertIn(count,result[1]['text'])

    def test_period_stats_called_with_matching_period_for_each_tf(self):
        dates=pd.bdate_range('2026-01-01', periods=180)
        raw=pd.DataFrame({'Ngày':dates,'Mã':['HDC']*len(dates),'Giá đóng cửa':range(100,100+len(dates))})
        idx=pd.DataFrame({'Ngày':dates,'Giá đóng cửa':range(1000,1000+len(dates))})
        prices=pd.DataFrame({'HDC':range(100,100+len(dates))},index=dates)
        called=[]
        def period_stats(p,groups,mkt,n):
            called.append(n)
            return pd.DataFrame({'Dòng':['Bất động sản'],'#':[1],'Dẫn sóng':[True], 'Giai đoạn':[float(n)]}),{}
        nd=SimpleNamespace(load_groups=lambda default:({'Bất động sản':['HDC']},{}),
                           period_stats=period_stats,
                           rep_stocks=lambda p,members,n,leaders=None,top=None:pd.DataFrame({'Mã':['HDC']}))
        srt=SimpleNamespace(_prep=lambda data: {'c':prices,'v':pd.DataFrame()})
        with patch.dict(sys.modules,{'nhom_nganh_data':nd,'sector_rotation':srt}):
            results=[leading_from_eod(raw,idx,tf,{'Bất động sản':['HDC']}) for tf in 'DWMQ']
        self.assertEqual(called,[1,5,21,63])
        self.assertEqual([x[0]['return'] for x in results],[1.0,5.0,21.0,63.0])

    def test_no_future_data_used(self):
        dates=pd.bdate_range('2026-01-01', periods=90)
        cutoff=dates[-3]
        raw=pd.DataFrame({'Ngày':dates,'Mã':['HDC']*len(dates),'Giá đóng cửa':range(100,190)})
        idx=pd.DataFrame({'Ngày':dates[:-2], 'Giá đóng cửa':range(1000,1088)})
        def prep(data):
            self.assertEqual(pd.Timestamp(data['Ngày'].max()),cutoff)
            return {'c':pd.DataFrame({'HDC':[1.0]*88},index=dates[:-2])}
        nd=SimpleNamespace(load_groups=lambda default:({'Bất động sản':['HDC']},{}),
                           period_stats=lambda p,gs,mkt,n:(pd.DataFrame(),{}))
        with patch.dict(sys.modules,{'nhom_nganh_data':nd,'sector_rotation':SimpleNamespace(_prep=prep)}):
            self.assertEqual(leading_from_eod(raw,idx,'D',{'Bất động sản':['HDC']}),[])

if __name__=='__main__': unittest.main()
