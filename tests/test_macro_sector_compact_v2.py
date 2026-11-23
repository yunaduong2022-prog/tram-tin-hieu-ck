"""Offline unit tests for compact evidence-based sector bridge. No network calls."""
from __future__ import annotations
from datetime import date
from pathlib import Path
import ast
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_sector_cost_bridge import (expected_market_sessions_since, bridge_rows,
    compact_rows, sector_evidence_summary, MAX_MISSED_EXPECTED_SESSIONS)

TODAY = date(2026, 11, 24)
PRICES = [
    {'category':'food', 'basis':'mom','rate':-.32, 'date':date(2026,10,31),'period':'10/2026','source_url':'https://www.nso.gov.vn/foo'},
    {'category':'fuel', 'basis':'mom','rate':6.86, 'date':date(2026,10,31),'period':'10/2026','source_url':'https://www.nso.gov.vn/foo'},
]
INFO = {'latest_date':date(2026,11,20),'sessions':90,
        'benchmark':{'1 tháng':(0.8, 'VN-Index (VNINDEX)')},'has_index':True}
ROWS = [
    {'Nhóm ngành':'Nông nghiệp & thực phẩm','Số mã có dữ liệu':9,'Hiệu suất 1 tháng (%)':-3.93,
     'RS 1 tháng (điểm %) ':-.26,'Độ rộng tăng giá (%)':0.0,'GTGD so TB20 (%)':95},
    {'Nhóm ngành':'Thịt & chăn nuôi','Số mã có dữ liệu':1,'Hiệu suất 1 tháng (%)':-4.5,
     'RS 1 tháng (điểm %) ':-1,'Độ rộng tăng giá (%)':12,'GTGD so TB20 (%)':100},
    {'Nhóm ngành':'Bán lẻ','Số mã có dữ liệu':15,'Hiệu suất 1 tháng (%)':-10.55,
     'RS 1 tháng (điểm %) ':-6.88,'Độ rộng tăng giá (%)':16.7,'GTGD so TB20 (%)':89},
]

class TestExpectedSessions(unittest.TestCase):
    def test_friday_to_sunday_zero(self):
        self.assertEqual(expected_market_sessions_since(date(2026,11,20),date(2026,11,22)),0)
    def test_friday_to_monday_one(self):
        self.assertEqual(expected_market_sessions_since(date(2026,11,20),date(2026,11,23)),1)
    def test_friday_to_tuesday_two(self):
        self.assertEqual(expected_market_sessions_since(date(2026,11,20),TODAY),2)
    def test_business_day_cutoff(self):
        self.assertEqual(expected_market_sessions_since(date(2026,11,20),TODAY,hour_vn=10),1)
        self.assertEqual(expected_market_sessions_since(date(2026,11,20),TODAY,hour_vn=17),2)
    def test_future_date_not_fresh(self):
        self.assertIsNone(expected_market_sessions_since(date(2026,11,25),TODAY))
    def test_not_calendar_days(self):
        self.assertEqual(expected_market_sessions_since(date(2026,11,13),date(2026,11,16)),1)
    def test_explicit_calendar_limit(self):
        self.assertEqual(MAX_MISSED_EXPECTED_SESSIONS,2)

class TestBridgeGuard(unittest.TestCase):
    def test_recent_expected_sessions_keep_values(self):
        rows,ctx=bridge_rows(PRICES,ROWS,INFO,'food',today=TODAY)
        self.assertEqual(ctx['market_lag_sessions'],2)
        self.assertTrue(ctx['market_ok'])
        self.assertEqual(rows[0]['RS 1 tháng (điểm %)'],-.26)
    def test_three_sessions_old_fail_closed(self):
        rows,ctx=bridge_rows(PRICES,ROWS,{**INFO,'latest_date':date(2026,11,19)},'food',today=TODAY)
        self.assertFalse(ctx['market_ok'])
        self.assertTrue(all(r['RS 1 tháng (điểm %)'] is None for r in rows))
    def test_future_market_date_fail_closed(self):
        rows,ctx=bridge_rows(PRICES,ROWS,{**INFO,'latest_date':date(2026,11,25)},'food',today=TODAY)
        self.assertFalse(ctx['market_ok'])
        self.assertTrue(all(r['RS 1 tháng (điểm %)'] is None for r in rows))
    def test_weekday_calendar_disclosure(self):
        _,ctx=bridge_rows(PRICES,ROWS,INFO,'food',today=TODAY)
        self.assertIn('T2–T6',ctx['market_calendar_note'])
    def test_no_fake_zero_on_inadequate_sector(self):
        rows,_=bridge_rows(PRICES,ROWS,INFO,'food',today=TODAY)
        self.assertIsNone(rows[1]['RS 1 tháng (điểm %)'])

class TestCompactRows(unittest.TestCase):
    def setUp(self):
        self.rows,self.ctx=bridge_rows(PRICES,ROWS,INFO,'food',today=TODAY)
        self.compact=compact_rows(self.rows)
    def test_six_columns_only(self):
        self.assertEqual(list(self.compact[0]),['Ngành','1 tháng','RS (điểm %)','Độ rộng','GTGD/TB20','Trạng thái'])
    def test_missing_values_are_em_dash_not_none(self):
        rec=self.compact[1]
        self.assertEqual(rec['1 tháng'],'—')
        self.assertEqual(rec['RS (điểm %)'],'—')
        self.assertEqual(rec['Độ rộng'],'—')
        self.assertEqual(rec['GTGD/TB20'],'—')
        self.assertEqual(rec['Trạng thái'],'Thiếu dữ liệu')
        self.assertNotIn('None',str(rec))
    def test_valid_zero_not_conflated_with_missing(self):
        self.assertEqual(self.compact[0]['Độ rộng'],'0.0%')
    def test_signed_values(self):
        self.assertEqual(self.compact[0]['1 tháng'],'-3.93%')
        self.assertEqual(self.compact[0]['RS (điểm %)'],'-0.26')
        self.assertEqual(self.compact[0]['GTGD/TB20'],'0.95x')
    def test_long_details_not_in_table(self):
        self.assertNotIn('Kênh chi phí',str(self.compact))
        self.assertNotIn('Cần xác nhận tại doanh nghiệp',str(self.compact))
    def test_compact_does_not_mutate_original(self):
        self.assertIn('Kênh chi phí / doanh thu cần kiểm tra',self.rows[0])

class TestNarrative(unittest.TestCase):
    def test_only_adequate_rows(self):
        rows,ctx=bridge_rows(PRICES,ROWS,INFO,'food',today=TODAY)
        txt=sector_evidence_summary(rows,ctx)
        self.assertIn('2 ngành đủ dữ liệu',txt)
        self.assertIn('2 RS âm',txt)
        self.assertIn('1 ngành thiếu xác nhận',txt)
        self.assertNotIn('Thịt & chăn nuôi:',txt)
        self.assertIn('0.95x',txt)
    def test_no_causality_or_buy_signal(self):
        rows,ctx=bridge_rows(PRICES,ROWS,INFO,'food',today=TODAY)
        txt=sector_evidence_summary(rows,ctx)
        self.assertIn('chưa thể kết luận CPI gây ra',txt)
        self.assertIn('KHÔNG phải dòng tiền mua ròng',txt)
        self.assertNotIn('MUA NGAY',txt)
    def test_no_valid_rows_no_numbers(self):
        rows,ctx=bridge_rows(PRICES,ROWS,{**INFO,'latest_date':date(2026,11,3)},'food',today=TODAY)
        txt=sector_evidence_summary(rows,ctx)
        self.assertIn('Chưa đủ dữ liệu',txt)
        self.assertNotIn('-3.93',txt)
    def test_never_infers_price_beneficiary(self):
        rows,ctx=bridge_rows(PRICES,ROWS,INFO,'food',today=TODAY)
        txt=sector_evidence_summary(rows,ctx)
        self.assertNotIn('hưởng lợi',txt.lower())
    def test_render_hook_static(self):
        p=Path(__file__).resolve().parents[1]/'macro_sector_cost_bridge.py'
        src=p.read_text('utf-8')
        ast.parse(src)
        self.assertIn('pd.DataFrame(compact_rows(rows))',src)
        self.assertIn('sector_evidence_summary(rows, ctx)',src)
        self.assertIn("st.selectbox('Chọn ngành để xem chi tiết bằng chứng'",src)
        self.assertIn('st.expander(f\'Chi tiết ngành:',src)


class TestRenderSmoke(unittest.TestCase):
    def test_compact_table_detail_and_summary_render_without_live_streamlit(self):
        import types
        from unittest.mock import patch
        import pandas as pd
        import macro_sector_cost_bridge as bridge
        captured={'tables':[],'info':[],'detail':[]}
        fake_st=types.ModuleType('streamlit')
        fake_st.cache_data=lambda **kw: (lambda fn: fn)
        fake_st.markdown=lambda *a,**kw: None
        fake_st.caption=lambda *a,**kw: None
        fake_st.warning=lambda *a,**kw: None
        fake_st.info=lambda msg,*a,**kw: captured['info'].append(msg)
        fake_st.write=lambda msg,*a,**kw: captured['detail'].append(msg)
        fake_st.dataframe=lambda df,**kw: captured['tables'].append(df)
        fake_st.selectbox=lambda text,options,**kw: options[0]
        class FakeExpander:
            def __enter__(self): return self
            def __exit__(self,*a): return False
        fake_st.expander=lambda *a,**kw: FakeExpander()
        fake_source=types.ModuleType('macro_price_pressures')
        fake_source.read_prices=lambda **kw: PRICES
        fake_sectors=types.ModuleType('sector_dashboard')
        fake_sectors.calculate_sector_metrics=lambda data: (pd.DataFrame(ROWS),INFO)
        class Clock:
            @classmethod
            def now(cls, timezone=None):
                from datetime import datetime
                return datetime(2026,11,24,10)
        with patch.dict(sys.modules, {'streamlit':fake_st,
                                      'macro_price_pressures':fake_source,
                                      'sector_dashboard':fake_sectors}):
            with patch.object(bridge,'datetime',Clock):
                bridge.render_sector_cost_bridge(pd.DataFrame({'dummy':[1]}))
        self.assertEqual(len(captured['tables']),1)
        table=captured['tables'][0]
        self.assertEqual(len(table.columns),6)
        self.assertEqual(table.iloc[1]['RS (điểm %)'],'—')
        self.assertTrue(any('RS âm' in x for x in captured['info']))
        self.assertTrue(any('Điều kiện cần xác nhận' in x for x in captured['detail']))

if __name__=='__main__': unittest.main()
