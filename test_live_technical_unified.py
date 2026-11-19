"""Regression tests for technical outlook UI. No Streamlit server needed."""
import ast
import html
import unittest
from pathlib import Path
import pandas as pd
import ma_structure_view as MAV
import engine as E

SRC = Path(__file__).parent.joinpath('app.py').read_text(encoding='utf-8')
PANEL = Path(__file__).parent.joinpath('live_technical_panel.py').read_text(encoding='utf-8')
AST = ast.parse(SRC)
FN = next(node for node in AST.body if isinstance(node, ast.FunctionDef) and node.name == '_technical_horizon_html')
space = {'MAV': MAV, 'htmllib': html}
exec(compile(ast.Module(body=[FN], type_ignores=[]), 'app.py', 'exec'), space)

class TechnicalUI(unittest.TestCase):
    def test_consistent_ma_rules_and_mtf(self):
        row = pd.Series({'MA10':15.40, 'MA20':14.79, 'MA50':14.34, 'MA100':15.61, 'MA200':19.19})
        self.assertEqual([MAV.trend_state(row, k) for k in ('Ngắn hạn','Trung hạn','Dài hạn')],
                         ['TĂNG','CHƯA XÁC ĐỊNH','GIẢM'])
        a = {t: {'g':pd.DataFrame([row]),'enough':True,'dir':d} for t,d in [('D',1),('W',-1),('M',-1)]}
        markup = space['_technical_horizon_html'](a, True)
        for text in ('CẤU TRÚC MA', 'XU HƯỚNG ĐA CHỈ BÁO', 'CHƯA XÁC ĐỊNH',
                     'Nghiêng tăng', 'Nghiêng giảm'):
            self.assertIn(text, markup)
    def test_absent_data_safe(self):
        s = space['_technical_horizon_html']({'D':{'enough':False},'W':{},'M':{}}, True)
        self.assertIn('Chưa đủ dữ liệu', s)
        self.assertIn('CHƯA XÁC ĐỊNH', s)
    def test_shared_card_with_ma_structure(self):
        section = SRC.split('def mtf_card(',1)[1].split('\ndef ',1)[0]
        self.assertIn('_technical_horizon_html(A, show_frames=False)',section)
        self.assertIn('Kết luận kỹ thuật · D/W/M',section)
    def test_second_visible_verdict_removed(self):
        lower = SRC.split('    st.markdown("### Các thẻ phân tích hiện có")', 1)[1].split('\ndef ',1)[0]
        self.assertIn('CHI TIẾT ĐIỂM SỐ D/W/M',lower)
        self.assertNotIn('st.markdown(mtf_card(',lower)
    def test_confirmation_is_expander(self):
        self.assertIn('st.expander("📊 CHỈ BÁO XÁC NHẬN',PANEL)
        self.assertIn('expanded=False',PANEL)
        self.assertIn('BA KỊCH BẢN DIỄN BIẾN GIÁ',PANEL)
        self.assertIn('NGUỒN CÁC MỐC GIÁ',PANEL)
    def test_no_changes_to_engine(self):
        self.assertEqual(E.TF_WEIGHT, {'M':0.30,'W':0.30,'D':0.40})
    def test_eod_price_levels_labeled_as_reference(self):
        self.assertIn('MỐC DỰ PHÒNG −8% (KHÔNG PHẢI SL)',SRC)
        self.assertIn('KHÔNG PHẢI ĐIỂM MUA',SRC)

if __name__ == '__main__': unittest.main(verbosity=2)
