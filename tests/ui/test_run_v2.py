from __future__ import annotations

from typing import List

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

from eol_tester import config as eol_config
from eol_ui.pages.run.plan import MeasurementPlan
from eol_ui.progress import Phase
from eol_ui.runner import LogRecord
from eol_ui.widgets import LogPanel
from tests.ui.test_screen_fit import (
    WORK_AREA,
    finish_run,
    open_window,
    reach_running,
    start_run,
)

pytestmark = pytest.mark.usefixtures("mock_hardware", "fast_profiles", "tmp_results")

PHASES = (Phase.SETUP, Phase.FORCE_TEST, Phase.TEARDOWN)


def record(level: str, message: str = "msg") -> LogRecord:
    import datetime

    return LogRecord(timestamp=datetime.datetime(2026, 1, 1, 12, 0, 0), level=level, message=message, source="test")


def clipped_labels(window) -> List[str]:
    window.resize(*WORK_AREA)
    QApplication.processEvents()
    clipped = []
    for text in window.run_page.findChildren(QLabel):
        if not text.isVisible() or not text.text() or text.wordWrap() or not text.pixmap().isNull():
            continue
        if text.sizeHint().width() > text.width():
            clipped.append((text.objectName(), text.text(), text.sizeHint().width(), text.width()))
    return clipped


def test_idle_screen(qtbot):
    window = open_window(qtbot)
    page = window.run_page
    assert page.progress.status_text() == "대기"
    assert [page.progress.stage_status(p) for p in PHASES] == ["pending"] * 3
    assert [page.progress.stage_mark(p) for p in PHASES] == ["1", "2", "3"]
    assert not page.progress.spinner_visible()
    assert page.progress.activity_text() == "시리얼 번호를 입력하고 시작을 누르세요"
    assert {page.tiles.detail(name) for name in page.tiles.texts()} == {"실행 전"}
    assert set(page.tiles.texts().values()) == {"—"}
    assert page.measurements.empty_visible()
    assert page.measurements.plan_text() == "온도 2개 × 위치 1개 = 측정 2회 예정"
    assert page.measurements.counts_text() == "0 / 2"
    assert page.measurements.limits_text() == ""
    assert page.log_panel.empty_text() == "시작하면 시퀀스 로그가 여기에 표시됩니다"
    assert page.findChild(object, "run-hint").text() == "프로파일 default(으)로 실행합니다."
    assert clipped_labels(window) == []


def test_pending_parameters_change_plan(qtbot):
    window = open_window(qtbot)
    page = window.run_page
    page.set_pending_parameters({"temperature_list": "38, 52, 66"})
    assert page.measurements.plan_text() == "온도 3개 × 위치 1개 = 측정 3회 예정"
    page.set_pending_parameters({"temperature_list": [38.0, 52.0, 66.0], "repeat_count": 2})
    assert page.measurements.plan_text() == "온도 3개 × 위치 1개 × 반복 2회 = 측정 6회 예정"
    page.set_pending_parameters({"temperature_list": "bad"})
    assert page.measurements.plan_text() == ""


def test_missing_profile_file_hides_plan(qtbot):
    window = open_window(qtbot)
    (eol_config.TEST_PROFILES_DIR / "default.yaml").unlink()
    window.run_page.set_pending_parameters({})
    assert window.run_page.measurements.plan_text() == ""
    assert not (eol_config.TEST_PROFILES_DIR / "default.yaml").exists()


def test_running_screen(qtbot):
    window = open_window(qtbot)
    page = window.run_page
    reach_running(qtbot, window)
    assert page.progress.status_text() == "테스트 진행 중"
    assert page.progress.stage_status(Phase.SETUP) == "done"
    assert page.progress.stage_mark(Phase.SETUP) == "✓"
    assert page.progress.stage_status(Phase.FORCE_TEST) == "running"
    assert page.progress.spinner_visible()
    assert page.progress.spinner_active()
    assert page.findChild(object, "run-hint").text().startswith("중단하면 현재 동작 뒤 Teardown")
    assert clipped_labels(window) == []
    finish_run(qtbot, window)
    qtbot.waitUntil(lambda: not page.is_running, timeout=60_000)
    assert not page.progress.spinner_visible()
    assert not page.progress.spinner_active()
    assert page.progress.status_text() in ("완료", "중단 요청됨")


def test_abort_shows_requested_badge(qtbot):
    window = open_window(qtbot)
    reach_running(qtbot, window)
    window.findChild(QPushButton, "abort-button").click()
    assert window.run_page.progress.status_text() == "중단 요청됨"
    finish_run(qtbot, window)
    qtbot.waitUntil(lambda: not window.run_page.is_running, timeout=60_000)
    assert window.run_page.progress.status_text() == "완료"


def test_log_badges_and_filter_empty(qtbot):
    panel = LogPanel()
    qtbot.addWidget(panel)
    panel.append(record("WARNING", "hot"))
    panel.append(record("SUCCESS", "ok"))
    assert panel.badge_texts() == ["WARN", "OK"]
    assert panel.visible_lines()[0] == "12:00:00  WARNING hot"
    assert panel.item_is_warn(0)
    assert panel.empty_text() == ""
    panel.filter_button("ERROR").click()
    assert panel.visible_lines() == []
    assert panel.empty_text() == "이 레벨의 로그가 없습니다"
    panel.clear()
    assert panel.empty_text() == "시작하면 시퀀스 로그가 여기에 표시됩니다"
