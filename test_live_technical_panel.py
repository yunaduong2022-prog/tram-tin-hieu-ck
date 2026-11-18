"""Offline regressions for Livestream EOD scenario classification."""
import pandas as pd
from live_technical_panel import build_commentary, summary_frame


def frame(close=16.15, support=12.75, resistance=16.00, vol=1.40):
    return pd.DataFrame({
        "Giá đóng cửa": [close], "MA20": [14.79], "Vol_vs_MA10": [vol],
        "Support_20": [support], "Resistance_20": [resistance],
    })


def a(close=16.15, support=12.75, resistance=16.00, vol=1.40, direction=1,
      enough=True, df=None):
    return {"g": frame(close, support, resistance, vol) if df is None else df,
            "dir": direction, "enough": enough}


def test_kdh_above_resistance_uses_present_tense_and_correct_state():
    m = build_commentary("KDH", {"D": a(), "W": a(direction=-1), "M": a(direction=-1)})
    assert m["state"] == "above"
    assert "đã trên kháng cự 16.00" in m["scenarios"][0][1]
    assert "không còn trong vùng dao động" in m["scenarios"][1][1]
    assert "Khung tuần/tháng còn nghiêng giảm" in m["scenarios"][0][1]
    assert "đã trên kháng cự" in m["script"]
    assert "Nếu đóng cửa vượt 16.00" not in str(m)


def test_in_range_keeps_conditional_breakout_and_range_narrative():
    m = build_commentary("NLG", {"D": a(close=14.0)})
    assert m["state"] == "inside"
    assert "Chờ đóng cửa vượt 16.00" in m["scenarios"][0][1]
    assert "còn trong vùng 12.75–16.00" in m["scenarios"][1][1]


def test_below_support_switches_to_risk_and_no_false_range():
    m = build_commentary("KDH", {"D": a(close=12.5)})
    assert m["state"] == "below"
    assert "đã đóng cửa dưới hỗ trợ 12.75" in m["scenarios"][2][1]
    assert "không còn nằm trong vùng tích lũy" in m["scenarios"][1][1]
    assert "đã đóng cửa dưới hỗ trợ" in m["script"]


def test_exact_touch_is_not_called_a_breakout():
    assert build_commentary("X", {"D": a(close=16.00)})["state"] == "inside"
    assert build_commentary("X", {"D": a(close=12.75)})["state"] == "inside"


def test_invalid_pair_withheld_no_synthetic_levels():
    m = build_commentary("KDH", {"D": a(support=19.0, resistance=18.0)})
    assert m["state"] == "unknown"
    assert "Chưa đủ cặp hỗ trợ/kháng cự" in m["scenarios"][1][1]
    assert "19.00" not in str(m["scenarios"])


def test_nan_missing_and_nonpositive_levels_are_withheld():
    m = build_commentary("X", {"D": a(support=float('nan'), resistance=float('inf'))})
    assert m["state"] == "unknown"
    assert "kháng cự 20 phiên hợp lệ" in m["scenarios"][0][1]
    n = build_commentary("X", {"D": a(support=0, resistance=-1)})
    assert n["state"] == "unknown"


def test_missing_daily_does_not_hallucinate():
    m = build_commentary("X", {"D": a(enough=False), "W": a(), "M": a()})
    assert m["scenarios"] == []
    assert m["script"] is None


def test_missing_month_is_explicit_in_script():
    m = build_commentary("NLG", {"D": a(), "W": a(direction=-1), "M": a(enough=False)})
    assert m["frames"]["M"]["ready"] is False
    assert "tháng chưa đủ dữ liệu" in m["script"]


def test_weekly_monthly_volume_flagged_provisional():
    assert "tạm tính" in summary_frame(a(), "W")["details"]
    assert "tạm tính" in summary_frame(a(), "M")["details"]
    assert "tạm tính" not in summary_frame(a(), "D")["details"]


def test_empty_dataframe_with_enough_true_is_safe():
    assert summary_frame(a(df=pd.DataFrame()))["ready"] is False


def test_single_missing_level_never_invents_range():
    m = build_commentary("X", {"D": a(support=float('nan'), resistance=16)})
    assert m["state"] == "above"
    assert "không còn trong vùng dao động" in m["scenarios"][1][1]
    assert "hỗ trợ 20 phiên hợp lệ" in m["scenarios"][2][1]


if __name__ == '__main__':
    tests = sorted((k, v) for k, v in globals().items() if k.startswith('test_') and callable(v))
    for name, fn in tests:
        fn()
        print('PASS', name)
    print('LIVE_PANEL_FIX_TESTS_OK:', len(tests))
