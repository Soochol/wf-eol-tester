from __future__ import annotations

import os
from pathlib import Path
from typing import List

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton

from eol_ui.main_window import MainWindow
from eol_ui.runner import RunOutcome
from eol_ui.theme import register_fonts, stylesheet

pytestmark = pytest.mark.usefixtures("mock_hardware", "fast_profiles", "tmp_results")

WORK_AREA = (1280, 940)
SHOT_SIZE = (1280, 1024)
RUN_TIMEOUT_MS = 60_000


def open_window(qtbot) -> MainWindow:
    register_fonts()
    QApplication.instance().setStyleSheet(stylesheet())
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window


def start_run(window: MainWindow, serial: str = "SN1", wip: str = "W1") -> None:
    window.findChild(QLineEdit, "serial-input").setText(serial)
    window.findChild(QLineEdit, "wip-input").setText(wip)
    window.findChild(QPushButton, "start-button").click()


def reach_running(qtbot, window: MainWindow) -> None:
    seen: List[bool] = []
    window.runner.progress.connect(
        lambda _: seen.append(True) if window.run_page.measurements.row_count() >= 1 else None
    )
    start_run(window)
    qtbot.waitUntil(lambda: bool(seen), timeout=RUN_TIMEOUT_MS)


def run_to_result(qtbot, window: MainWindow, force_limits=None) -> None:
    if force_limits is not None:
        low, high = force_limits
        window.run_page.set_pending_parameters({"force_limit_min": low, "force_limit_max": high})
    outcomes: List[RunOutcome] = []
    window.runner.finished.connect(outcomes.append)
    start_run(window)
    qtbot.waitUntil(lambda: bool(outcomes), timeout=RUN_TIMEOUT_MS)
    assert window._run_stack.currentWidget() is window.result_page


def finish_run(qtbot, window: MainWindow) -> None:
    if window.runner.is_running:
        outcomes: List[RunOutcome] = []
        window.runner.finished.connect(outcomes.append)
        window.run_page.request_abort("test")
        qtbot.waitUntil(lambda: bool(outcomes), timeout=RUN_TIMEOUT_MS)


def check_fit(window: MainWindow) -> None:
    window.resize(*WORK_AREA)
    QApplication.processEvents()
    hint = window.centralWidget().minimumSizeHint()
    assert hint.width() <= WORK_AREA[0], hint
    assert hint.height() <= WORK_AREA[1], hint
    header = window.findChild(object, "header")
    for text in header.findChildren(QLabel):
        if text.text() and not text.wordWrap() and text.pixmap().isNull():
            assert text.sizeHint().width() <= text.width(), (text.text(), text.width())


def snapshot(window: MainWindow, name: str) -> None:
    shot_dir = os.environ.get("EOL_UI_SHOT_DIR")
    if not shot_dir:
        return
    Path(shot_dir).mkdir(parents=True, exist_ok=True)
    window.resize(*SHOT_SIZE)
    QApplication.processEvents()
    window.grab().save(str(Path(shot_dir) / f"{name}.png"))


def test_idle_fits(qtbot):
    window = open_window(qtbot)
    check_fit(window)
    snapshot(window, "idle")


def test_running_fits(qtbot):
    window = open_window(qtbot)
    reach_running(qtbot, window)
    check_fit(window)
    snapshot(window, "running")
    finish_run(qtbot, window)


def test_pass_fits(qtbot):
    window = open_window(qtbot)
    run_to_result(qtbot, window)
    check_fit(window)
    snapshot(window, "pass")


def test_fail_fits(qtbot):
    window = open_window(qtbot)
    run_to_result(qtbot, window, force_limits=(0.0, 1.0))
    check_fit(window)
    snapshot(window, "fail")
