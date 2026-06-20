from app.handler.temperature import (
    ReportTemperature,
    _format_temperature_conclusion_log,
    check_absolute_temperature,
    check_short_window_temperature_rise,
    check_temperature_trend,
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


def test_short_window_detects_high_hold_when_current_temperature_does_not_rise():
    result = check_short_window_temperature_rise(_reports(20.0, 22.0, 23.0, 23.0))

    assert result.enough_data
    assert result.status == "高位保持"
    assert result.level == "严重"
    assert result.cumulative_delta_c == 3.0
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
    assert result.conclusion.items[0].name == "绝对温度"
    assert result.conclusion.items[0].level == "正常"
    assert result.conclusion.items[1].name == "短窗口"
    assert result.conclusion.items[1].level == "严重"
    assert result.conclusion.items[1].triggered
    assert "cumulative_delta_c=5.4" in result.conclusion.items[1].evidence
    assert "短窗口: cumulative_delta_c=5.4" in result.conclusion.evidence
    assert result.conclusion.items[2].name == "长窗口"
    assert result.conclusion.items[2].level == "未检测"
    assert result.conclusion.items[3].name == "单次检测温度抬升"
    assert result.conclusion.items[3].level == "正常"
    assert "温度诊断结论：严重" in result.conclusion.conclusion


def test_absolute_temperature_warns_at_50_degrees_without_rise():
    absolute = check_absolute_temperature(_reports(50.0)[0])

    assert absolute.enough_data
    assert absolute.current_temperature_c == 50.0
    assert absolute.threshold_c == 50.0
    assert absolute.level == "警告"

    result = diagnose_temperature(
        sn="STL26SH0001",
        report_id="r2",
        reports=_reports(50.0, 50.0, 50.0),
    )

    assert result.absolute.level == "警告"
    assert result.short_window.level is None
    assert result.short_term.level is None
    assert result.conclusion.level == "警告"
    assert result.conclusion.triggered
    assert result.conclusion.items[0].name == "绝对温度"
    assert result.conclusion.items[0].triggered
    assert "current_temperature_c=50" in result.conclusion.items[0].evidence
    assert "threshold_c=50" in result.conclusion.items[0].evidence
    assert "rule=current_temperature_c >= threshold_c" in result.conclusion.items[0].evidence
    assert "绝对温度: current_temperature_c=50" in result.conclusion.evidence
    assert "绝对温度过高" in result.conclusion.conclusion


def test_temperature_conclusion_log_is_multiline_with_evidence():
    result = diagnose_temperature(
        sn="STL26SH0001",
        report_id="r2",
        reports=_reports(50.0, 50.0, 50.0),
    )

    log_message = _format_temperature_conclusion_log(result)

    assert "Temperature diagnosis conclusion" in log_message
    assert "  sn: STL26SH0001" in log_message
    assert "  report_id: r2" in log_message
    assert "  checks:" in log_message
    assert "    - 绝对温度" in log_message
    assert "      evidence:" in log_message
    assert "        - current_temperature_c=50" in log_message
    assert "        - threshold_c=50" in log_message


def test_long_window_detects_chronic_temperature_drift():
    reports = _reports(*([20.0] * 36), *([23.5] * 36))
    result = check_temperature_trend(reports)

    assert result.enough_data
    assert result.status == "慢性漂移"
    assert result.level == "警告"
    assert result.warning
    assert result.baseline_mean_temperature_c == 20.0
    assert result.recent_mean_temperature_c == 23.5
    assert result.drift_delta_c == 3.5

    diagnosis = diagnose_temperature(
        sn="STL26SH0001",
        report_id="r71",
        reports=reports,
    )

    assert diagnosis.conclusion.items[2].name == "长窗口"
    assert diagnosis.conclusion.items[2].level == "警告"
    assert "drift_delta_c=3.5" in diagnosis.conclusion.items[2].evidence


def test_diagnosis_conclusion_is_normal_when_no_track_triggers():
    result = diagnose_temperature(
        sn="STL26SH0001",
        report_id="r3",
        reports=_reports(20.0, 20.1, 20.2, 20.2),
    )

    assert result.conclusion.level == "正常"
    assert not result.conclusion.triggered
    assert result.conclusion.conclusion == "温度诊断结论：正常"
    assert result.conclusion.evidence
    assert "绝对温度: level=正常, status=not_triggered" in result.conclusion.evidence
    assert [item.name for item in result.conclusion.items] == [
        "绝对温度",
        "短窗口",
        "长窗口",
        "单次检测温度抬升",
        "同组温度横向比较",
    ]
