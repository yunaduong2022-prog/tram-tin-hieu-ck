"""Offline tests for the Livestream technical panel; no Streamlit needed."""
import math

import pandas as pd

from live_technical_panel import build_commentary, summary_frame


def frame(close=16.15, support=14.86, resistance=18.57):
    return pd.DataFrame({
        "Giá đóng cửa": [close], "MA20": [14.79], "Vol_vs_MA10": [1.40],
        "Support_20": [support], "Resistance_20": [resistance],
    })


def a(df=None, direction=1, enough=True):
    return {"g": frame() if df is None else df, "dir": direction, "enough": enough}


def test_all_frames_use_engine_direction_not_new_trading_signal():
    result = build_commentary("KDH", {"D": a(), "W": a(direction=-1), "M": a(direction=0)})
    assert result["frames"]["D"]["trend"] == "Nghiêng tăng"
    assert result["frames"]["W"]["trend"] == "Nghiêng giảm"
    assert result["frames"]["M"]["trend"] == "Chưa rõ xu hướng"
    assert "KDH" in result["script"]
    assert "18.57" in result["script"]
    assert "14.86" in result["script"]


def test_missing_month_is_not_invented():
    result = build_commentary("NLG", {"D": a(), "W": a(direction=-1), "M": a(enough=False)})
    assert result["frames"]["M"]["ready"] is False
    assert "chưa đủ dữ liệu" in result["script"]
    assert "NLG" in result["script"]


def test_missing_daily_blocks_conditional_scenarios_and_script():
    result = build_commentary("KDH", {"D": a(enough=False), "W": a(), "M": a()})
    assert result["scenarios"] == []
    assert result["script"] is None


def test_invalid_levels_are_not_synthetic():
    result = build_commentary("KDH", {"D": a(frame(support=float('nan'), resistance=float('inf')))})
    assert "18.57" not in str(result["scenarios"])
    assert "kháng cự 20 phiên hợp lệ" in result["scenarios"][0][1]
    assert "kháng cự chưa được xác nhận" in result["script"]


def test_crossed_support_resistance_are_withheld():
    result = build_commentary("KDH", {"D": a(frame(support=19.0, resistance=18.0))})
    assert result["scenarios"][1][1].startswith("Chưa có đủ")


def test_empty_dataframe_with_enough_flag_does_not_crash():
    assert summary_frame(a(pd.DataFrame()))["ready"] is False

if __name__ == "__main__":
    checks = sorted((name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn))
    for name, fn in checks:
        fn()
        print("PASS", name)
    print(f"LIVE_PANEL_TESTS_OK: {len(checks)}")
