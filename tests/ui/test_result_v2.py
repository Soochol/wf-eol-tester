from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton

from eol_ui.pages.result import ResultPage
from eol_ui.pages.result.page import NO_RESULTS_TEXT
from eol_ui.runner import MeasurementRecord, RunOutcome, StageResult, Verdict
from eol_ui.theme import register_fonts, stylesheet

START = datetime(2026, 11, 19, 10, 0, 0)


def record(temp: float, force: Optional[float], low=0.0, high=100.0, passed=True) -> MeasurementRecord:
    return MeasurementRecord(f"force_{temp}C_170000um", temp, 170000.0, force, low, high, passed)


def outcome(
    verdict: Verdict = Verdict.PASS,
    measurements=(),
    stages=None,
    error: Optional[str] = None,
    files=(),
    results_dir: Optional[Path] = None,
) -> RunOutcome:
    return RunOutcome(
        verdict=verdict,
        result={},
        error=error,
        measurements=tuple(measurements),
        stages={} if stages is None else stages,
        results_dir=results_dir,
        result_files=tuple(files),
        started_at=START,
        finished_at=START + timedelta(seconds=252),
        serial_number="WF24-110873",
        wip_id="WIP-0419",
        abort_requested=verdict is Verdict.ABORTED,
    )


@pytest.fixture
def page(qtbot):
    register_fonts()
    QApplication.instance().setStyleSheet(stylesheet())
    widget = ResultPage()
    qtbot.addWidget(widget)
    widget.resize(1280, 940)
    widget.show()
    return widget


def test_pass(page):
    page.show_outcome(outcome(measurements=[record(38.0, 50.0), record(52.0, 60.0)]))
    assert page.banner_kind == "PASS"
    assert page.banner_title == "PASS"
    assert page.banner_detail == "모든 측정값이 판정 기준 안에 있습니다."
    assert page.banner_values() == ["WF24-110873", "WIP-0419", "04:12", "2/2"]
    assert page.banner_summary == "SN WF24-110873 · WIP WIP-0419 · 소요 04:12 · 2/2 PASS"
    assert page.table_row_count() == 2


def test_fail_upper_limit(page):
    rows = [record(38.0, 50.0), record(52.0, 120.5, passed=False)]
    page.show_outcome(outcome(Verdict.FAIL, rows))
    assert page.banner_kind == "FAIL"
    assert page.banner_detail == "52 ℃에서 Force 상한 100 kgf를 넘었습니다."
    assert page.row_background(1).red() > 240 and page.row_background(1).green() < 250
    force = page.row_force_color(1)
    assert force.red() > 150 and force.green() < 60 and force.blue() < 60
    assert page.row_force_color(0).red() < 60


def test_fail_lower_limit(page):
    page.show_outcome(outcome(Verdict.FAIL, [record(38.0, 0.5, low=1.0, high=100.0, passed=False)]))
    assert "하한" in page.banner_detail
    assert "38 ℃" in page.banner_detail
    assert "1 kgf" in page.banner_detail


def test_fail_without_limits(page):
    page.show_outcome(outcome(Verdict.FAIL, [record(38.0, 5.0, low=None, high=None, passed=False)]))
    assert page.banner_detail == "판정 기준을 벗어난 측정이 있습니다."


@pytest.mark.parametrize(
    "verdict, title, error, detail",
    [
        (Verdict.ABORTED, "중단됨", None, "사용자 요청으로 중단되었습니다. Teardown을 실행했습니다."),
        (Verdict.ERROR, "오류", "MCU boot complete 신호 없음", "MCU boot complete 신호 없음"),
    ],
)
def test_aborted_and_error(page, verdict, title, error, detail):
    page.show_outcome(outcome(verdict, error=error))
    assert page.banner_kind == verdict.value
    assert page.banner_title == title
    assert page.banner_detail == detail


def test_teardown_card(page):
    ok = StageResult("teardown", True, 0.4, None)
    bad = StageResult("teardown", False, 1.2, "power off failed")
    for stages, title in (({"teardown": ok}, "Teardown 완료"), ({"teardown": bad}, "Teardown 실패"), ({}, "Teardown 기록 없음")):
        page.show_outcome(outcome(stages=stages))
        assert page.teardown_title() == title
        assert page.findChild(QLabel, "teardown-result").text() == page.teardown_text()
    page.show_outcome(outcome(stages={"teardown": bad}))
    assert "power off failed" in page.teardown_text()


def test_no_saved_results(page):
    page.show_outcome(outcome())
    assert page.no_results_visible()
    assert page.findChild(QLabel, "no-results").text() == NO_RESULTS_TEXT
    assert page.file_names() == []
    assert not page.findChild(QPushButton, "open-folder-button").isEnabled()


def test_saved_results(page, tmp_path):
    files = [tmp_path / "LOG_a.json", tmp_path / "raw.csv"]
    for path in files:
        path.write_text("x")
    page.show_outcome(outcome(files=files, results_dir=tmp_path))
    assert page.file_names() == ["LOG_a.json", "raw.csv"]
    assert not page.no_results_visible()
    assert page.findChild(QPushButton, "open-folder-button").isEnabled()


def test_next_dut(page, qtbot):
    page.show_outcome(outcome())
    button = page.findChild(QPushButton, "next-button")
    field = page.findChild(QLineEdit, "next-serial-input")
    assert not button.isEnabled()
    seen: List[str] = []
    page.next_requested.connect(seen.append)
    field.setText("SN2")
    assert button.isEnabled()
    qtbot.keyClick(field, Qt.Key.Key_Return)
    assert seen == ["SN2"]


@pytest.mark.parametrize("verdict", [Verdict.PASS, Verdict.FAIL])
def test_no_clipped_labels(page, tmp_path, verdict):
    rows = [record(38.0, 50.0), record(52.0, 120.5, passed=verdict is Verdict.PASS)]
    long_name = tmp_path / "LOG_WF24-110873_20261119_171400_extra_long_name.json"
    long_name.write_text("x")
    stage = StageResult("teardown", True, 0.4, None)
    page.show_outcome(outcome(verdict, rows, {"teardown": stage}, files=[long_name], results_dir=tmp_path))
    QApplication.processEvents()
    for text in page.findChildren(QLabel):
        if text.isVisibleTo(page) and text.text() and not text.wordWrap() and text.pixmap().isNull():
            assert text.sizeHint().width() <= text.width(), (text.text(), text.width())
    hint = page.minimumSizeHint()
    assert hint.width() <= 1280 and hint.height() <= 940
