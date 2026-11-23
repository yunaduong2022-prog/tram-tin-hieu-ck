"""Pure offline tests for price -> sector bridge; never calls live pricing or network."""
import ast
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from macro_sector_cost_bridge import (PRICE_FACTORS, EXPOSURES, bridge_rows, latest_factor,
                                      _number, MAX_PRICE_AGE_DAYS)

T = date(2026, 11, 24)
PRICES = [
    {'category': 'food', 'basis': 'mom', 'rate': Decimal('-0.32'), 'date': date(2026,10,31), 'period': '10/2026', 'source_url': 'https://www.nso.gov.vn/report'},
    {'category': 'food', 'basis': 'mom', 'rate': Decimal('-0.05'), 'date': date(2026,6,30), 'period': '06/2026', 'source_url': 'https://www.nso.gov.vn/report'},
    {'category': 'fuel', 'basis': 'qualitative', 'rate': None, 'date': date(2026,10,31)},
    {'category': 'fuel', 'basis': 'mom', 'rate': Decimal('6.86'), 'date': date(2026,10,31), 'period': '10/2026', 'source_url': 'https://www.nso.gov.vn/report'},
    {'category': 'inputs', 'basis': 'ytd_yoy', 'rate': Decimal('5.12'), 'date': date(2026,9,30), 'period': '9T/2026', 'source_url': 'https://www.nso.gov.vn/report'},
]
SECTOR = {'Nhóm ngành': 'Dầu khí', 'Số mã có dữ liệu': 5, 'Hiệu suất 1 tháng (%)': 4.0,
          'RS 1 tháng (điểm %) ': 1.5, 'Độ rộng tăng giá (%)': 60,
          'GTGD so TB20 (%)': 135}
INFO = {'latest_date': date(2026,11,20), 'sessions': 100, 'has_index': False,
        'benchmark': {'1 tháng': (0.0, 'trung vị rổ cổ phiếu (proxy, không phải VN-Index)')}}

class TestBridge(unittest.TestCase):
    def test_mapping_to_real_universe(self):
        self.assertEqual(len(PRICE_FACTORS),5)
        self.assertEqual(len({x[0] for x in EXPOSURES}),5)
        self.assertEqual(len({(x[0],x[1]) for x in EXPOSURES}),len(EXPOSURES))
        # Existing watchlist group keys, no invented sector.
        allowed = {'Nông nghiệp & thực phẩm','Thịt & chăn nuôi','Bán lẻ','Dầu khí','Vận tải',
                   'Vận tải biển hàng hóa','Điện','Hàng công nghiệp','Xây dựng','Vật liệu xây dựng',
                   'Thép','Bất động sản','Phân bón'}
        self.assertTrue({x[1] for x in EXPOSURES} <= allowed)

    def test_selects_correct_basis_not_qualitative(self):
        self.assertEqual(latest_factor(PRICES,'fuel')['rate'],Decimal('6.86'))
        self.assertEqual(latest_factor(PRICES,'inputs')['basis'],'ytd_yoy')
    def test_no_invented_category(self):
        with self.assertRaises(ValueError): latest_factor(PRICES,'fake')
    def test_does_not_default_missing_to_zero(self):
        for x in ('NaN',float('inf'),None,'xx',True): self.assertIsNone(_number(x))
    def test_proxy_is_never_called_vnindex(self):
        rows,ctx=bridge_rows(PRICES,[SECTOR],INFO,'fuel',today=T)
        self.assertEqual(ctx['rs_label'],'RS so proxy trung vị cổ phiếu')
        self.assertNotIn('VN-Index',ctx['rs_label'])
        self.assertEqual(next(r for r in rows if r['Ngành']=='Dầu khí')['RS 1 tháng (điểm %)'],1.5)
    def test_actual_index_label_when_available(self):
        actual_benchmark = {'1 tháng': (0.8, 'VN-Index (VNINDEX)')}
        _,ctx=bridge_rows(PRICES,[SECTOR],{**INFO,'has_index':True,'benchmark':actual_benchmark},'fuel',today=T)
        self.assertEqual(ctx['rs_label'],'RS so VN-Index')
    def test_index_ticker_present_but_one_month_benchmark_uses_proxy(self):
        rows,ctx=bridge_rows(PRICES,[SECTOR],{**INFO,'has_index':True},'fuel',today=T)
        self.assertEqual(ctx['rs_label'],'RS so proxy trung vị cổ phiếu')
        self.assertEqual(next(r for r in rows if r['Ngành']=='Dầu khí')['RS 1 tháng (điểm %)'],1.5)
    def test_missing_benchmark_provenance_fails_closed(self):
        rows,ctx=bridge_rows(PRICES,[SECTOR],{**INFO,'benchmark':{}},'fuel',today=T)
        self.assertEqual(ctx['rs_label'],'RS chưa xác định nguồn tham chiếu')
        self.assertIsNone(next(r for r in rows if r['Ngành']=='Dầu khí')['RS 1 tháng (điểm %)'])
        self.assertIn('thiếu nguồn tham chiếu RS',next(r for r in rows if r['Ngành']=='Dầu khí')['Trạng thái bằng chứng'])
    def test_strength_and_activity_are_distinct(self):
        rows,_=bridge_rows(PRICES,[SECTOR],INFO,'fuel',today=T)
        r=next(x for x in rows if x['Ngành']=='Dầu khí')
        self.assertEqual(r['Quan sát sức mạnh giá'],'Giá mạnh tương đối')
        self.assertEqual(r['Quan sát giao dịch'],'GTGD cao hơn TB20')
        self.assertIn('chưa chứng minh',r['Trạng thái bằng chứng'])
    def test_missing_sector_fails_closed(self):
        rows,_=bridge_rows(PRICES,[],INFO,'fuel',today=T)
        self.assertTrue(all(r['Hiệu suất 1 tháng (%)'] is None for r in rows))
        self.assertTrue(all('Thiếu xác nhận' in r['Trạng thái bằng chứng'] for r in rows))
    def test_old_market_fails_closed(self):
        rows,_=bridge_rows(PRICES,[SECTOR],{**INFO,'latest_date':date(2026,11,10)},'fuel',today=T)
        self.assertIsNone(next(r for r in rows if r['Ngành']=='Dầu khí')['RS 1 tháng (điểm %)'])
    def test_old_price_fails_closed(self):
        rows,ctx=bridge_rows(PRICES,[SECTOR],INFO,'inputs',today=T)
        self.assertFalse(ctx['price_ok'])
        self.assertTrue(all(r['Hiệu suất 1 tháng (%)'] is None for r in rows))
    def test_missing_liquidity_fails_closed(self):
        rows,_=bridge_rows(PRICES,[{**SECTOR,'GTGD so TB20 (%)':None}],INFO,'fuel',today=T)
        self.assertEqual(next(r for r in rows if r['Ngành']=='Dầu khí')['Quan sát giao dịch'],'Chưa kết luận')
    def test_missing_sessions_fails_closed(self):
        rows,_=bridge_rows(PRICES,[SECTOR],{**INFO,'sessions':20},'fuel',today=T)
        self.assertIsNone(next(r for r in rows if r['Ngành']=='Dầu khí')['Hiệu suất 1 tháng (%)'])
    def test_small_sector_fails_closed(self):
        rows,_=bridge_rows(PRICES,[{**SECTOR,'Số mã có dữ liệu':2}],INFO,'fuel',today=T)
        self.assertIsNone(next(r for r in rows if r['Ngành']=='Dầu khí')['Hiệu suất 1 tháng (%)'])
    def test_source_dates_not_aligned(self):
        rows,ctx=bridge_rows(PRICES,[SECTOR],INFO,'fuel',today=T)
        self.assertEqual(ctx['price_date'],date(2026,10,31))
        self.assertEqual(ctx['market_date'],date(2026,11,20))
    def test_no_price_rate_fails_closed(self):
        rows,ctx=bridge_rows([],[],INFO,'fuel',today=T)
        self.assertEqual(rows,[])
        self.assertIsNotNone(ctx['reason'])
    def test_no_side_effects_or_direct_picks(self):
        src=Path(__file__).resolve().parents[1].joinpath('macro_sector_cost_bridge.py').read_text(encoding='utf-8').lower()
        for forbidden in ['git push','subprocess','write_bytes','to_csv','requests.get','mua ngay','bán ngay']:
            self.assertNotIn(forbidden,src)
    def test_bridge_pure_static_compiles(self):
        tree=ast.parse(Path(__file__).resolve().parents[1].joinpath('macro_sector_cost_bridge.py').read_text(encoding='utf-8'))
        self.assertTrue(any(isinstance(x,ast.FunctionDef) and x.name=='render_sector_cost_bridge' for x in tree.body))

if __name__ == '__main__': unittest.main()

class TestIntegrationGuard(unittest.TestCase):
    def test_existing_macro_call_and_sector_route_when_installed(self):
        root = Path(__file__).resolve().parents[1]
        app = root / 'app.py'
        dashboard = root / 'macro_vn_dashboard.py'
        if not app.is_file() or not dashboard.is_file():
            self.skipTest('Standalone offline package; integration is checked in cloned repo')
        a, d = app.read_text(encoding='utf-8'), dashboard.read_text(encoding='utf-8')
        ast.parse(a)
        ast.parse(d)
        self.assertIn('MVN.render(UOM.render, sector_prices=raw)', a)
        self.assertIn('render_sector_cost_bridge(sector_prices)',d)
        self.assertIn('_sector_impact(df, sector_prices)',d)
        self.assertIn('def render(international_render, sector_prices=None)', d)
