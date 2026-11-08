# -*- coding: utf-8 -*-
"""Pure UI smoke tests for T+2 renderer; synthetic DataFrames, no market writes."""
import ast
import unittest
from pathlib import Path

import pandas as pd



class Context:
    def __init__(self, st, detail=False):
        self.st = st
        self.detail = detail
    def __enter__(self):
        if self.detail:
            self.st.detail += 1
        return self
    def __exit__(self, *_):
        if self.detail:
            self.st.detail -= 1
        return False


class FakeCol(Context):
    def metric(self, *args, **kwargs):
        self.st.metric(*args, **kwargs)


class FakeSt:
    def __init__(self, show_all=False):
        self.log = []
        self.detail = 0
        self.show_all = show_all
    def _emit(self, kind, *parts):
        self.log.append((kind, self.detail, *parts))
    def markdown(self, value):
        self._emit('markdown', value)
    def caption(self, value):
        self._emit('caption', value)
    def metric(self, label, value, *args, **kwargs):
        self._emit('metric', label, value, *args)
    def columns(self, n):
        return [FakeCol(self) for _ in range(n)]
    def container(self, **kwargs):
        return Context(self)
    def expander(self, label, expanded=False):
        self._emit('expander', label, expanded)
        return Context(self, detail=True)
    def checkbox(self, label, key):
        self._emit('checkbox', label, key)
        return self.show_all


def render(df, waiting, show_all=False):
    st = FakeSt(show_all)
    tree = ast.parse(Path(__file__).with_name('app.py').read_text(encoding='utf-8-sig'))
    node = next((item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == '_t2_opportunity_cards'), None)
    if node is None:
        raise AssertionError('No shared T+2 UI renderer in app.py')
    module = ast.Module(body=[node], type_ignores=[])
    namespace = {'pd': pd, 'st': st}
    exec(compile(module, '<renderer>', 'exec'), namespace)
    namespace['_t2_opportunity_cards'](df, waiting)
    return st


def example(waiting=True, code='CTS'):
    data = {'Mã':code, 'Tín hiệu':'Tiếp diễn ngắn hạn','Tuổi':'T+0',
            'Giá EOD':23.35,'Cắt lỗ T+2':22.84,'TP1 T+2':27.95,
            'TP2 T+2':29.06,'Dư địa TP1 %':19.7,'R:R EOD':9.01,
            'Rủi ro SL %':2.18,'Vol/TB20 EOD':2.14,
            'Position EOD %':86.0,
            'Ghi chú':'CHỈ TRADING T+2. Cản gần: 23.65 (Đỉnh 20P), 23.85 (Đỉnh 11/08). CHỜ MUA T+2: Cản gần: 23.65 (Đỉnh 20P), 23.85 (Đỉnh 11/08).'}
    if waiting:
        data.update({'Cản cần vượt':23.65,'R:R đến cản':.59,
                     'Điều kiện kích hoạt':'Chờ đóng cửa vượt 23.65 với nến tăng, Position ≥60% và Vol/TB20 ≥1.2x; Sau xác nhận: tính lại stop, TP, R:R và vòng đời tín hiệu'})
    return pd.DataFrame([data])


class TestCompactT2Cards(unittest.TestCase):
    def test_renderer_syntax(self):
        app = Path(__file__).with_name('app.py').read_text(encoding='utf-8-sig')
        self.assertIn('MIN_T2_COMPACT_CARDS_V1', app)
        self.assertEqual(app.count('def _t2_opportunity_cards('), 1)

    def test_wait_highlights_barrier_instead_of_distant_tp(self):
        st = render(example(), True)
        metrics = [(r[2],r[3]) for r in st.log if r[0]=='metric']
        self.assertIn(('Giá EOD','23.35'), metrics)
        self.assertIn(('Cản cần vượt','23.65'), metrics)
        self.assertNotIn(('TP1 T+2','27.95'), metrics)
        self.assertTrue(any('R:R đến cản: 0.59' in r[2] for r in st.log if r[0]=='caption' and r[1]==0))
        self.assertTrue(any('R:R đến TP1' in r[2] and 'tham khảo' in r[2] for r in st.log if r[0]=='caption' and r[1]==0))

    def test_wait_no_green_buy_label(self):
        st = render(example(), True)
        texts = [r[2] for r in st.log if r[0]=='markdown' and r[1]==0]
        self.assertIn('CTS · ⏳ CHỜ XÁC NHẬN T+2', texts[0])
        self.assertNotIn('MUA NGAY', texts[0])

    def test_wait_trigger_readable_once_and_caveat_retained(self):
        st = render(example(), True)
        labels = [r[2] for r in st.log if r[0]=='markdown' and r[1]==0]
        self.assertEqual(labels.count('**Điều kiện kích hoạt**'), 1)
        self.assertTrue(any('vượt 23.65' in r[2] for r in st.log if r[0]=='caption' and r[1]==0))
        self.assertTrue(any('KHÔNG nắm giữ dài hạn' in r[2] for r in st.log if r[0]=='caption' and r[1]==0))

    def test_long_repetitive_notes_only_in_collapsed_expander(self):
        st = render(example(), True)
        self.assertFalse(any('Cản gần: 23.65' in r[2] for r in st.log if r[0]=='caption' and r[1]==0))
        self.assertTrue(any('Cản gần: 23.65' in r[2] for r in st.log if r[0]=='caption' and r[1]==1))
        self.assertTrue(any(r[0]=='expander' and r[3] is False for r in st.log))

    def test_buy_retains_tp1_rr_in_metric_and_stop(self):
        st = render(example(False), False)
        metrics = [(r[2],r[3]) for r in st.log if r[0]=='metric']
        self.assertIn(('TP1 T+2','27.95'), metrics)
        self.assertFalse(any(a=='Cản cần vượt' for a,_ in metrics))
        self.assertTrue(any('Stoploss T+2' in r[2] and '22.84' in r[2] for r in st.log if r[0]=='caption'))
        self.assertTrue(any('MUA NGAY T+2' in r[2] for r in st.log if r[0]=='markdown'))

    def test_wait_missing_barrier_does_not_claim_buy(self):
        df = example()
        df.loc[0,'Cản cần vượt'] = float('nan')
        df.loc[0,'R:R đến cản'] = float('nan')
        df.loc[0,'Điều kiện kích hoạt'] = 'Chờ nến tăng và xác nhận khối lượng'
        st = render(df, True)
        self.assertIn(('Trạng thái','Chờ xác nhận'), [(r[2],r[3]) for r in st.log if r[0]=='metric'])

    def test_empty_is_no_op(self):
        self.assertEqual(render(pd.DataFrame(), True).log, [])
        self.assertEqual(render(pd.DataFrame(), False).log, [])

    def test_max_18_and_show_all(self):
        many = pd.concat([example(code=f'S{i:02d}') for i in range(19)], ignore_index=True)
        st = render(many, True, show_all=False)
        count = len([r for r in st.log if r[0]=='markdown' and 'CHỜ XÁC NHẬN' in r[2]])
        self.assertEqual(count,18)
        self.assertTrue(any(r[0]=='checkbox' for r in st.log))
        st2 = render(many, True, show_all=True)
        self.assertEqual(len([r for r in st2.log if r[0]=='markdown' and 'CHỜ XÁC NHẬN' in r[2]]),19)

    def test_no_data_mutation(self):
        data=example()
        prev=data.copy(deep=True)
        render(data,True)
        pd.testing.assert_frame_equal(data,prev)

    def test_no_engine_or_data_access_in_card_renderer(self):
        app = Path(__file__).with_name('app.py').read_text(encoding='utf-8-sig')
        tree = ast.parse(app)
        ui = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_t2_opportunity_cards')
        names = {n.id for n in ast.walk(ui) if isinstance(n, ast.Name)}
        self.assertNotIn('T2BUY', names)
        self.assertNotIn('T2S', names)
        self.assertNotIn('frames', names)



if __name__=='__main__':
    unittest.main(verbosity=2)
