from __future__ import annotations

from datetime import datetime
from typing import Any, List, Tuple

import pytest
import yaml
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton

from eol_ui.main_window import MainWindow
from eol_ui.pages.run import ABORT_NOTICE, NO_PROFILES_NOTICE
from eol_ui.runner import LogRecord, RunOutcome, Verdict
from eol_ui.theme import stylesheet
from eol_ui.widgets import LogPanel

pytestmark = pytest.mark.usefixtures("mock_hardware", "fast_profiles", "tmp_results")

RUN_TIMEOUT_MS = 60_000


@pytest.fixture
def window(qtbot):
    QApplication.instance().setStyleSheet(stylesheet())
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    return win


def child(win: MainWindow, kind: type, name: str):
    found = win.findChild(kind, name)
    assert found is not None, name
    return found


def begin_run(win: MainWindow, serial: str = "SN1", wip: str = "W1") -> None:
    child(win, QLineEdit, "serial-input").setText(serial)
    child(win, QLineEdit, "wip-input").setText(wip)
    child(win, QPushButton, "start-button").click()


def collect_outcomes(win: MainWindow) -> List[RunOutcome]:
    outcomes: List[RunOutcome] = []
    win.runner.finished.connect(outcomes.append)
    return outcomes


def on_first_measuring(win: MainWindow, action) -> None:
    fired: List[bool] = []

    def watch(record: LogRecord) -> None:
        if "Measuring at position" in record.message and not fired:
            fired.append(True)
            action()

    win.runner.log.connect(watch)


def wait_for_outcomes(qtbot, outcomes: List[RunOutcome], count: int = 1) -> None:
    qtbot.waitUntil(lambda: len(outcomes) >= count, timeout=RUN_TIMEOUT_MS)


def test_run_to_result_pass(qtbot, window):
    outcomes = collect_outcomes(window)
    seen: List[Tuple[float, int, int]] = []

    def sample(_: Any) -> None:
        if window.runner.is_running:
            run = window.run_page
            seen.append(
                (run.progress.percent_value(), run.log_panel.line_count(), run.measurements.row_count())
            )

    window.runner.progress.connect(sample)

    begin_run(window)
    wait_for_outcomes(qtbot, outcomes)

    assert max(percent for percent, _, _ in seen) > 0
    assert max(lines for _, lines, _ in seen) > 0
    assert max(rows for _, _, rows in seen) == 2
    assert window.result_page.isVisible()
    assert window.result_page.banner_kind == "PASS"
    assert window.result_page.banner_title == "PASS"
    assert "2/2" in window.result_page.banner_summary
    assert any(name.endswith(".json") for name in window.result_page.file_names())
    assert not window.result_page.no_results_visible()
    assert window.device_connected("robot") is None
    assert window.run_page.measurements.badge_texts() == ["PASS", "PASS"]


def test_abort_shows_aborted_and_teardown(qtbot, window):
    outcomes = collect_outcomes(window)
    on_first_measuring(window, child(window, QPushButton, "abort-button").click)

    begin_run(window)
    wait_for_outcomes(qtbot, outcomes)

    assert window.run_page.notice_text() == ABORT_NOTICE
    assert outcomes[0].verdict is Verdict.ABORTED
    assert window.result_page.isVisible()
    assert window.result_page.banner_kind == "ABORTED"
    assert window.result_page.banner_title == "중단됨"
    assert "passed: 예" in window.result_page.teardown_text()
    assert window.result_page.no_results_visible()
    assert window.result_page.file_names() == []


def test_abort_leaves_no_pending_rows(qtbot, window):
    outcomes = collect_outcomes(window)
    during_run: List[List[str]] = []

    def sample(_: Any) -> None:
        if window.runner.is_running:
            during_run.append(window.run_page.measurements.badge_texts())

    window.runner.progress.connect(sample)
    on_first_measuring(window, child(window, QPushButton, "abort-button").click)

    begin_run(window)
    wait_for_outcomes(qtbot, outcomes)

    assert outcomes[0].verdict is Verdict.ABORTED
    assert any(texts == ["판정 대기"] for texts in during_run)
    assert window.run_page.measurements.row_count() >= 1
    assert set(window.run_page.measurements.badge_texts()) == {"미완료"}


def test_fail_verdict_screen(qtbot, window):
    outcomes = collect_outcomes(window)
    window.run_page.set_pending_parameters({"force_limit_min": 0.0, "force_limit_max": 1.0})

    begin_run(window)
    wait_for_outcomes(qtbot, outcomes)

    assert outcomes[0].verdict is Verdict.FAIL
    assert window.result_page.banner_kind == "FAIL"
    assert window.result_page.banner_title == "FAIL"
    assert "0/2" in window.result_page.banner_summary
    assert window.run_page.measurements.badge_texts() == ["FAIL", "FAIL"]


def test_log_filter_and_counts(qtbot):
    panel = LogPanel()
    qtbot.addWidget(panel)
    for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        panel.append(LogRecord(datetime.now(), level, f"{level.lower()} line", "test"))

    assert panel.count_text() == "4줄 · 경고 2"
    expected = {"전체": 4, "INFO": 3, "WARN": 2, "ERROR": 1}
    for text, visible in expected.items():
        panel.filter_button(text).click()
        assert len(panel.visible_lines()) == visible, text

    panel.filter_button("전체").click()
    assert [panel.item_is_warn(row) for row in range(4)] == [False, False, True, True]


def test_log_panel_drops_oldest_lines(qtbot):
    panel = LogPanel(max_lines=3)
    qtbot.addWidget(panel)
    for level in ("WARNING", "INFO", "INFO", "ERROR", "INFO"):
        panel.append(LogRecord(datetime.now(), level, f"{level} line", "test"))

    assert panel.count_text() == "3줄 · 경고 1"
    assert [line.split()[1] for line in panel.visible_lines()] == ["INFO", "ERROR", "INFO"]


def test_start_disabled_without_serial(qtbot, window):
    start = child(window, QPushButton, "start-button")
    abort = child(window, QPushButton, "abort-button")
    serial = child(window, QLineEdit, "serial-input")
    outcomes = collect_outcomes(window)

    assert not start.isEnabled()
    assert not abort.isEnabled()
    serial.setText("SN1")
    assert start.isEnabled()

    start.click()
    assert window.runner.is_running
    assert not start.isEnabled()
    assert abort.isEnabled()

    abort.click()
    wait_for_outcomes(qtbot, outcomes)
    assert start.isEnabled()
    assert not abort.isEnabled()


def test_next_test_from_result(qtbot, window):
    outcomes = collect_outcomes(window)
    begin_run(window, "SN1", "W1")
    wait_for_outcomes(qtbot, outcomes)
    assert window.result_page.banner_kind == "PASS"

    child(window, QLineEdit, "next-serial-input").setText("SN2")
    child(window, QPushButton, "next-button").click()

    assert window.runner.is_running
    assert window.run_page.isVisible()
    assert child(window, QLineEdit, "serial-input").text() == "SN2"
    wait_for_outcomes(qtbot, outcomes, 2)
    assert [o.serial_number for o in outcomes] == ["SN1", "SN2"]
    assert [o.wip_id for o in outcomes] == ["W1", "W1"]
    assert outcomes[1].verdict is Verdict.PASS


def test_back_button_returns_to_run_page(qtbot, window):
    outcomes = collect_outcomes(window)
    begin_run(window)
    wait_for_outcomes(qtbot, outcomes)

    child(window, QPushButton, "back-button").click()

    assert window.run_page.isVisible()
    assert not window.result_page.isVisible()


def test_close_during_run_waits_for_teardown(qtbot, window):
    outcomes = collect_outcomes(window)
    closed_immediately: List[bool] = []
    on_first_measuring(window, lambda: closed_immediately.append(window.close()))

    begin_run(window)
    qtbot.waitUntil(lambda: bool(closed_immediately), timeout=RUN_TIMEOUT_MS)

    assert closed_immediately == [False]
    assert window.runner.abort_requested
    assert window.run_page.notice_text() == "Teardown 후 종료합니다"
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=RUN_TIMEOUT_MS)
    assert len(outcomes) == 1
    assert outcomes[0].abort_requested
    assert "teardown" in outcomes[0].stages
    assert outcomes[0].stages["teardown"].passed


def test_close_when_idle_closes_at_once(window):
    assert window.close()
    assert not window.isVisible()


def test_mock_badge(window, mock_hardware):
    assert not window.mock_badge.isHidden()

    data = yaml.safe_load(mock_hardware.read_text(encoding="utf-8"))
    data["robot"]["model"] = "ajinextek"
    mock_hardware.write_text(yaml.safe_dump(data), encoding="utf-8")
    window.refresh_mock_badge()

    assert window.mock_badge.isHidden()


def test_header_shows_sequence_identity_and_unknown_devices_grey(window):
    identity = child(window, QLabel, "sequence-identity")
    assert identity.text() == "eol_force_test 1.0.3"
    for key in ("robot", "loadcell", "mcu", "power", "digital_io"):
        assert window.device_connected(key) is None


def test_pending_parameters_and_profile_go_into_request(window):
    child(window, QLineEdit, "serial-input").setText("SN9")
    window.run_page.set_pending_parameters({"voltage": 18.0, "test_profile": "ignored"})

    request = window.run_page.build_request()

    assert request.serial_number == "SN9"
    assert request.wip_id is None
    assert request.parameters == {"voltage": 18.0, "test_profile": "default"}


def test_start_blocked_when_profile_file_missing(qtbot, window, fast_profiles):
    outcomes = collect_outcomes(window)
    child(window, QLineEdit, "serial-input").setText("SN1")
    profile_file = fast_profiles / f"{window.run_page.profile_name()}.yaml"
    profile_file.unlink()

    child(window, QPushButton, "start-button").click()

    assert not window.runner.is_running
    assert outcomes == []
    assert "default" in window.run_page.notice_text()
    assert "없" in window.run_page.notice_text()
    assert not profile_file.exists()
    assert window.run_page.profile_names() == []
    assert not child(window, QPushButton, "start-button").isEnabled()


def test_start_disabled_without_profiles(window, fast_profiles):
    child(window, QLineEdit, "serial-input").setText("SN1")
    start = child(window, QPushButton, "start-button")
    assert start.isEnabled()

    (fast_profiles / "default.yaml").unlink()
    window.run_page.refresh_profiles()

    assert not start.isEnabled()
    assert window.run_page.notice_text() == NO_PROFILES_NOTICE
