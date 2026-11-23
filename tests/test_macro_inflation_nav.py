"""Offline AST contract checks for split mindmap navigation; no app dependencies."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def module(name):
    return ast.parse(source(name))


def literal(name, var):
    for node in module(name).body:
        if isinstance(node, ast.Assign) and any(isinstance(k, ast.Name) and k.id == var for k in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(var)


def fn(name, function):
    return next(n for n in module(name).body if isinstance(n, ast.FunctionDef) and n.name == function)


class TestMacroInflationSplit(unittest.TestCase):
    def test_six_mindmap_branches(self):
        self.assertEqual(len(literal("macro_vn_mindmap.py", "BRANCHES")), 6)

    def test_separate_targets(self):
        b = literal("macro_vn_mindmap.py", "BRANCHES")
        self.assertEqual(b[0][3], "Chu kỳ kinh tế")
        self.assertEqual(b[1][3], "Lạm phát")

    def test_targets_exist_in_sections(self):
        sections = literal("macro_vn_dashboard.py", "SECTIONS")
        self.assertIn("Chu kỳ kinh tế", sections)
        self.assertIn("Lạm phát", sections)

    def test_all_mindmap_targets_valid(self):
        sections = literal("macro_vn_dashboard.py", "SECTIONS")
        self.assertTrue(all(x[3] in sections for x in literal("macro_vn_mindmap.py", "BRANCHES")))

    def test_no_combined_tab(self):
        self.assertNotIn("Chu kỳ & Lạm phát", literal("macro_vn_dashboard.py", "SECTIONS"))

    def test_distinct_view_functions(self):
        fn("macro_vn_dashboard.py", "_cycle")
        fn("macro_vn_dashboard.py", "_inflation")

    def test_growth_not_used(self):
        self.assertNotIn("def _growth(df:", source("macro_vn_dashboard.py"))

    def test_inflation_indicators_present(self):
        body = ast.get_source_segment(source("macro_vn_dashboard.py"), fn("macro_vn_dashboard.py", "_inflation"))
        for key in ("CPI_OCT_MOM", "CPI_OCT_YOY", "CPI_10M", "CORE_CPI_10M"):
            self.assertIn(key, body)

    def test_cycle_indicators_present(self):
        body = ast.get_source_segment(source("macro_vn_dashboard.py"), fn("macro_vn_dashboard.py", "_cycle"))
        for key in ("GDP_Q", "GDP_9M", "IIP_10M"):
            self.assertIn(key, body)

    def test_no_cpi_in_cycle_cards(self):
        body = ast.get_source_segment(source("macro_vn_dashboard.py"), fn("macro_vn_dashboard.py", "_cycle"))
        self.assertNotIn('_cards(df, [("CPI_', body)

    def test_router_has_both(self):
        body = ast.get_source_segment(source("macro_vn_dashboard.py"), fn("macro_vn_dashboard.py", "render"))
        self.assertIn('selected == "Chu kỳ kinh tế"', body)
        self.assertIn('selected == "Lạm phát"', body)

    def test_other_core_sections_preserved(self):
        sections = literal("macro_vn_dashboard.py", "SECTIONS")
        for sec in ("Tổng quan", "Tiền tệ & Thanh khoản", "Tài khóa", "Quốc tế", "Tác động ngành"):
            self.assertIn(sec, sections)

    def test_legacy_widget_reset(self):
        body = ast.get_source_segment(source("macro_vn_dashboard.py"), fn("macro_vn_dashboard.py", "render"))
        self.assertIn('== "Chu kỳ & Lạm phát"', body)

    def test_no_data_mutation_added(self):
        view = ast.get_source_segment(source("macro_vn_dashboard.py"), fn("macro_vn_dashboard.py", "_inflation"))
        for bad in ("to_csv(", ".write_text(", "os.remove", "subprocess"):
            self.assertNotIn(bad, view)


if __name__ == "__main__":
    unittest.main()
