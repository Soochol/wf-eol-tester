from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, List

import pytest
import shiboken6
from loguru import logger
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QLineEdit, QPushButton

import eol_ui.runner.runner as runner_module
from eol_ui.main_window import MainWindow
from eol_ui.settings import HardwareStore

pytestmark = pytest.mark.usefixtures("mock_hardware", "fast_profiles", "tmp_results")

JOIN_TIMEOUT = 30


class HeldSequence:
    entered = threading.Event()
    release = threading.Event()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def abort(self) -> None:
        pass

    async def _execute(self) -> dict:
        logger.info("held: before release")
        type(self).entered.set()
        await asyncio.get_running_loop().run_in_executor(None, type(self).release.wait)
        logger.info("held: after release")
        return {"passed": True, "steps": [], "measurements": {}}


@pytest.fixture
def held_sequence(monkeypatch: pytest.MonkeyPatch):
    held = type("Held", (HeldSequence,), {"entered": threading.Event(), "release": threading.Event()})
    monkeypatch.setattr(runner_module, "EOLForceTestSequence", held)
    yield held
    held.release.set()


@pytest.fixture
def worker_errors(monkeypatch: pytest.MonkeyPatch) -> List[BaseException]:
    errors: List[BaseException] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: errors.append(args.exc_value))
    return errors


def delete_now(widget: Any) -> None:
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def start_run(win: MainWindow) -> None:
    win.findChild(QLineEdit, "serial-input").setText("SN1")
    win.findChild(QLineEdit, "wip-input").setText("W1")
    win.findChild(QPushButton, "start-button").click()


def test_window_deleted_while_running_does_not_crash(qtbot, held_sequence, worker_errors, capfd):
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    start_run(win)
    assert held_sequence.entered.wait(JOIN_TIMEOUT)
    worker = win.runner._thread
    runner = win.runner

    win.close()
    delete_now(win)
    assert not shiboken6.isValid(runner)

    held_sequence.release.set()
    worker.join(JOIN_TIMEOUT)
    qtbot.wait(100)

    assert not worker.is_alive()
    assert worker_errors == []
    assert "Logging error" not in capfd.readouterr().err


def test_windows_deleted_while_running_in_sequence(qtbot, held_sequence, worker_errors, capfd):
    workers: List[threading.Thread] = []
    for _ in range(3):
        held_sequence.entered.clear()
        win = MainWindow()
        qtbot.addWidget(win)
        win.show()
        start_run(win)
        assert held_sequence.entered.wait(JOIN_TIMEOUT)
        workers.append(win.runner._thread)
        win.close()
        delete_now(win)

    held_sequence.release.set()
    for worker in workers:
        worker.join(JOIN_TIMEOUT)
    qtbot.wait(100)

    assert not any(worker.is_alive() for worker in workers)
    assert worker_errors == []
    assert "Logging error" not in capfd.readouterr().err


def test_connection_thread_outlives_deleted_page(qtbot, monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    async def held(self: HardwareStore):
        entered.set()
        await asyncio.get_running_loop().run_in_executor(None, release.wait)
        return {}

    monkeypatch.setattr(HardwareStore, "connection_test", held)
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    hardware = win.settings_page.hardware
    hardware.test_button.click()
    assert entered.wait(JOIN_TIMEOUT)
    thread = hardware.connection_thread()
    finished: List[bool] = []
    thread.finished.connect(lambda: finished.append(True))

    win.close()
    delete_now(win)

    assert shiboken6.isValid(thread)
    assert thread.isRunning()
    release.set()
    qtbot.waitUntil(lambda: bool(finished), timeout=JOIN_TIMEOUT * 1000)
