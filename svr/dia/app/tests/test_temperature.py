from app.handler.temperature import (
    ReportTemperature,
    check_short_window_temperature_rise,
    diagnose_temperature,
)


def _reports(*temperatures: float) -> list[ReportTemperature]:
    return [
        ReportTemperature(
            report_id=f"r{index}",
            temperature_c=temperature,
            sort_key=index,
        )
        for index, temperature in enumerate(temperatures)
    ]


def test_short_window_detects_cumulative_minor_rise():
    result = check_short_window_temperature_rise(_reports(21.0, 21.4, 21.8, 22.2))

    assert result.enough_data
    assert result.status == "持续升温"
    assert result.level == "关注"
    assert result.cumulative_delta_c == 1.2
    assert result.latest_delta_c == 0.4


def test_short_window_detects_high_hold_after_rise():
    result = check_short_window_temperature_rise(_reports(20.0, 22.0, 23.0, 23.2, 23.6, 23.8))

    assert result.enough_data
    assert result.status == "高位保持"
    assert result.level == "严重"
    assert result.cumulative_delta_c == 3.8
    assert result.latest_delta_c == 0.2


def test_short_window_skips_when_current_temperature_does_not_rise():
    result = check_short_window_temperature_rise(_reports(20.0, 22.0, 23.0, 23.0))

    assert result.enough_data
    assert result.status is None
    assert result.level is None
    assert result.cumulative_delta_c is None
    assert result.latest_delta_c == 0.0


def test_diagnosis_includes_short_window_result():
    result = diagnose_temperature(
        sn="STL26SH0001",
        report_id="r3",
        reports=_reports(28.0, 30.0, 33.0, 33.4),
    )

    assert result.short_window.status == "高位保持"
    assert result.short_window.level == "严重"
    assert result.conclusion.level == "严重"
    assert result.conclusion.triggered
    assert result.conclusion.items[0].name == "短窗口"
    assert result.conclusion.items[0].level == "严重"
    assert result.conclusion.items[0].triggered
    assert result.conclusion.items[1].name == "长窗口"
    assert result.conclusion.items[1].level == "未检测"
    assert result.conclusion.items[2].name == "单次检测温度抬升"
    assert result.conclusion.items[2].level == "正常"
    assert "温度诊断结论：严重" in result.conclusion.conclusion


def test_diagnosis_conclusion_is_normal_when_no_track_triggers():
    result = diagnose_temperature(
        sn="STL26SH0001",
        report_id="r3",
        reports=_reports(20.0, 20.1, 20.2, 20.2),
    )

    assert result.conclusion.level == "正常"
    assert not result.conclusion.triggered
    assert result.conclusion.conclusion == "温度诊断结论：正常"
    assert [item.name for item in result.conclusion.items] == [
        "短窗口",
        "长窗口",
        "单次检测温度抬升",
    ]
