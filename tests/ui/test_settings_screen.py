from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest
import shiboken6
import yaml
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton

import eol_tester.config as eol_config
from eol_ui.main_window import MainWindow
from eol_ui.pages.settings.fields import ListField
from eol_ui.pages.settings.parameters import DISCARD_NOTICE, GROUPS
from eol_ui.runner import RunOutcome, SequenceRunner
from eol_ui.settings import HardwareStore, load_schema
from eol_ui.theme import stylesheet

pytestmark = pytest.mark.usefixtures("mock_hardware", "fast_profiles", "tmp_results")

RUN_TIMEOUT_MS = 60_000
DEVICES = ("robot", "loadcell", "mcu", "power", "digital_io")


@pytest.fixture
def window(qtbot):
    QApplication.instance().setStyleSheet(stylesheet())
    win = MainWindow()
    qtbot.addWidget(win)
    win.show()
    return win


@pytest.fixture
def real_hardware(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "real_hardware_config.yaml"
    shutil.copy(eol_config.CONFIG_DIR / "hardware_config.yaml", path)
    monkeypatch.setattr(eol_config, "HARDWARE_CONFIG_FILE", path)
    return path


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> List[Any]:
    requests: List[Any] = []
    real_start = SequenceRunner.start

    def record(self: SequenceRunner, request: Any) -> None:
        requests.append(request)
        real_start(self, request)

    monkeypatch.setattr(SequenceRunner, "start", record)
    return requests


def params(win: MainWindow):
    return win.settings_page.parameters


def hardware(win: MainWindow):
    return win.settings_page.hardware


def edit(win: MainWindow, name: str, text: str) -> None:
    params(win).field(name).edit.setText(text)


def start_run(win: MainWindow, serial: str = "SN1") -> None:
    win.findChild(QLineEdit, "serial-input").setText(serial)
    win.findChild(QPushButton, "start-button").click()


def collect_outcomes(win: MainWindow) -> List[RunOutcome]:
    outcomes: List[RunOutcome] = []
    win.runner.finished.connect(outcomes.append)
    return outcomes


def pick_run_profile(win: MainWindow, name: str) -> None:
    combo = win.findChild(QComboBox, "profile-combo")
    combo.setCurrentIndex(combo.findText(name))
    combo.activated.emit(combo.currentIndex())


def save_profile(win: MainWindow, name: str) -> None:
    bar = params(win).bar
    bar.name_input.setText(name)
    bar.save_button.click()


def read_models(path: Path) -> Dict[str, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {device: data[device]["model"] for device in DEVICES}


def test_apply_sends_only_changed_parameters(qtbot, window, started):
    outcomes = collect_outcomes(window)
    edit(window, "voltage", "45")
    edit(window, "repeat_count", "2")
    params(window).bar.apply_button.click()

    start_run(window)

    assert started[0].parameters == {"test_profile": "default", "voltage": 45.0, "repeat_count": 2}
    assert "적용된 변경 2개" in window.run_page.applied_text()
    qtbot.waitUntil(lambda: bool(outcomes), timeout=RUN_TIMEOUT_MS)


def test_unapplied_edits_not_used(qtbot, window, started):
    outcomes = collect_outcomes(window)
    edit(window, "voltage", "45")

    start_run(window)

    assert started[0].parameters == {"test_profile": "default"}
    assert window.run_page.applied_text() == "적용된 변경 0개"
    qtbot.waitUntil(lambda: bool(outcomes), timeout=RUN_TIMEOUT_MS)


def test_validation_blocks_apply(window):
    bar = params(window).bar
    edit(window, "velocity", "150000")

    field = params(window).field("velocity")
    assert field.error_text() != ""
    assert field.has_error_property()
    assert "오류 1" in bar.counts_text()
    assert not bar.apply_button.isEnabled()

    edit(window, "velocity", "50000")

    assert field.error_text() == ""
    assert not field.has_error_property()
    assert bar.apply_button.isEnabled()


def test_changed_badge_and_revert(window):
    field = params(window).field("voltage")
    assert not field.changed_visible()

    edit(window, "voltage", "45")

    assert field.changed_visible()
    assert "프로파일 40.0" in field.hint_text()
    assert "변경 1" in params(window).bar.counts_text()

    params(window).bar.revert_button.click()

    assert not field.changed_visible()
    assert "프로파일" not in field.hint_text()
    assert field.edit.text() == "40.0"
    assert "변경 0" in params(window).bar.counts_text()


def test_save_profile(window, fast_profiles):
    edit(window, "voltage", "45")

    save_profile(window, "line2")

    assert (fast_profiles / "line2.yaml").exists()
    assert "line2" in window.run_page.profile_names()
    assert "line2" in params(window).bar.profile_names()
    assert "변경 0" in params(window).bar.counts_text()
    assert params(window).field("voltage").edit.text() == "45.0"
    assert window.run_page.profile_name() == "line2"

    save_profile(window, "line2")

    bar = params(window).bar
    assert bar.overwrite_prompt_visible()
    bar.cancel_button.click()
    assert not bar.overwrite_prompt_visible()

    save_profile(window, "line2")
    bar.overwrite_button.click()
    assert not bar.overwrite_prompt_visible()
    assert "저장했습니다" in bar.message_text()


@pytest.mark.parametrize("name", ["", "   ", "line2.yaml", "a.b", "../x", "a/b", "a\\b", "bad:name", "a" * 65])
def test_save_profile_rejects_bad_names(window, fast_profiles, name):
    edit(window, "voltage", "45")
    before = sorted(p.name for p in fast_profiles.iterdir())

    save_profile(window, name)

    assert params(window).bar.message_text() != ""
    assert sorted(p.name for p in fast_profiles.iterdir()) == before
    assert "변경 1" in params(window).bar.counts_text()


def test_profile_choices_come_from_existing_profiles_only(window, fast_profiles):
    params(window).select_profile("ghost")

    assert not (fast_profiles / "ghost.yaml").exists()
    assert params(window).profile_name == "default"
    assert window.run_page.profile_names() == ["default"]
    assert params(window).bar.profile_names() == ["default"]


def test_profile_switch_syncs(window):
    edit(window, "voltage", "45")
    save_profile(window, "line2")
    pick_run_profile(window, "default")

    assert params(window).bar.current_profile() == "default"
    assert params(window).profile_name == "default"

    edit(window, "voltage", "41")
    params(window).bar.apply_button.click()
    assert window.run_page.applied_text() == "적용된 변경 1개"

    params(window).bar.select_profile("line2")

    assert window.run_page.profile_name() == "line2"
    assert window.run_page.applied_text() == "적용된 변경 0개"
    assert params(window).bar.message_text() == DISCARD_NOTICE
    assert "변경 0" in params(window).bar.counts_text()

    edit(window, "voltage", "46")
    params(window).bar.apply_button.click()
    pick_run_profile(window, "default")

    assert params(window).bar.current_profile() == "default"
    assert window.run_page.applied_text() == "적용된 변경 0개"
    assert params(window).field("voltage").edit.text() == "40.0"


def test_list_chips_add_and_remove(window):
    field = params(window).field("temperature_list")
    assert isinstance(field, ListField)
    assert field.chip_texts() == ["38 ℃", "52 ℃"]

    field.edit.setText("66")
    field.add_button.click()
    assert field.chip_texts() == ["38 ℃", "52 ℃", "66 ℃"]
    assert field.changed_visible()

    window.settings_page.parameters.field("temperature_list").edit.setText("abc")
    field.add_button.click()
    assert field.error_text() != ""
    assert field.chip_texts() == ["38 ℃", "52 ℃", "66 ℃"]

    for _ in range(3):
        field.findChild(QPushButton, "chip-remove-temperature_list-0").click()
    assert field.chip_texts() == []
    assert "오류 1" in params(window).bar.counts_text()
    assert not params(window).bar.apply_button.isEnabled()


def test_every_manifest_parameter_has_a_field():
    shown = [name for _, members in GROUPS for name, _ in members]
    assert sorted(shown) == sorted(load_schema())


def test_mock_toggle_updates_badge(real_hardware, window):
    original = read_models(real_hardware)
    assert "mock" not in original.values()
    window.refresh_mock_badge()
    assert window.mock_badge.isHidden()

    hardware(window).mock_switch.click()

    assert not window.mock_badge.isHidden()
    assert set(read_models(real_hardware).values()) == {"mock"}
    assert hardware(window).model_text("robot") == "mock"

    hardware(window).mock_switch.click()

    assert window.mock_badge.isHidden()
    assert read_models(real_hardware) == original
    assert hardware(window).model_text("robot") == original["robot"]


def test_hardware_edit_and_save(real_hardware, window):
    hardware(window).edit("loadcell", "port").setText("COM5")
    hardware(window).edit("mcu", "baudrate").setText("57600")

    hardware(window).save_button.click()

    data = yaml.safe_load(real_hardware.read_text(encoding="utf-8"))
    assert data["loadcell"]["port"] == "COM5"
    assert data["mcu"]["baudrate"] == 57600
    assert data["loadcell"]["parity"] == "even"


def test_hardware_save_rejects_invalid_value(real_hardware, window):
    before = real_hardware.read_text(encoding="utf-8")
    hardware(window).edit("loadcell", "port").setText("COM5")
    hardware(window).edit("mcu", "baudrate").setText("fast")

    hardware(window).save_button.click()

    assert real_hardware.read_text(encoding="utf-8") == before
    assert hardware(window).edit("mcu", "baudrate").property("error") is True
    assert "저장하지 않았습니다" in hardware(window).message_text()


def test_connection_test_mock(qtbot, window):
    assert all(hardware(window).status_text(device) == "미확인" for device in DEVICES)

    hardware(window).test_button.click()

    qtbot.waitUntil(lambda: not hardware(window).is_testing(), timeout=RUN_TIMEOUT_MS)
    assert [hardware(window).status_text(device) for device in DEVICES] == ["연결됨"] * 5
    assert all(window.device_connected(device) is True for device in DEVICES)


def test_hardware_locked_while_running(qtbot, window):
    outcomes = collect_outcomes(window)
    locked_controls = [
        hardware(window).save_button,
        hardware(window).mock_switch,
        hardware(window).test_button,
        *hardware(window).edit_widgets(),
    ]
    assert all(control.isEnabled() for control in locked_controls)
    assert hardware(window).lock_reason() == ""

    start_run(window)

    assert window.runner.is_running
    assert not any(control.isEnabled() for control in locked_controls)
    assert hardware(window).lock_reason() != ""
    edit(window, "voltage", "45")
    assert params(window).bar.apply_button.isEnabled()

    qtbot.waitUntil(lambda: bool(outcomes), timeout=RUN_TIMEOUT_MS)

    assert all(control.isEnabled() for control in locked_controls)
    assert hardware(window).lock_reason() == ""


def test_run_start_blocked_while_connection_test_runs(qtbot, window):
    window.findChild(QLineEdit, "serial-input").setText("SN1")
    start = window.findChild(QPushButton, "start-button")
    assert start.isEnabled()

    hardware(window).test_button.click()

    assert not start.isEnabled()
    qtbot.waitUntil(lambda: not hardware(window).is_testing(), timeout=RUN_TIMEOUT_MS)
    assert start.isEnabled()
    assert window.run_page.notice_text() == ""


def test_device_dots_unknown_after_run_ends(qtbot, window):
    outcomes = collect_outcomes(window)
    seen: List[Any] = []
    window.runner.progress.connect(lambda _: seen.append(window.device_connected("robot")))

    start_run(window)
    qtbot.waitUntil(lambda: bool(outcomes), timeout=RUN_TIMEOUT_MS)

    assert True in seen
    assert all(window.device_connected(device) is None for device in DEVICES)


def test_e2e_changed_params_reach_sequence(qtbot, window):
    outcomes = collect_outcomes(window)
    field = params(window).field("temperature_list")
    assert field.chip_texts() == ["38 ℃", "52 ℃"]
    field.findChild(QPushButton, "chip-remove-temperature_list-1").click()
    assert field.chip_texts() == ["38 ℃"]
    params(window).bar.apply_button.click()

    start_run(window)
    qtbot.waitUntil(lambda: bool(outcomes), timeout=RUN_TIMEOUT_MS)

    assert window.result_page.isVisible()
    assert window.result_page.table_row_count() == 1
    assert "1/1" in window.result_page.banner_summary


def test_hardware_save_writes_only_edited_keys(real_hardware, window):
    data = yaml.safe_load(real_hardware.read_text(encoding="utf-8"))
    data["robot"]["axis_id"] = 7
    real_hardware.write_text(yaml.safe_dump(data), encoding="utf-8")
    hardware(window).edit("mcu", "baudrate").setText("57600")

    hardware(window).save_button.click()

    saved = yaml.safe_load(real_hardware.read_text(encoding="utf-8"))
    assert saved["robot"]["axis_id"] == 7
    assert saved["mcu"]["baudrate"] == 57600


def test_run_profile_follows_profile_added_after_startup(window, fast_profiles):
    source = fast_profiles / "default.yaml"
    (fast_profiles / "late.yaml").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    params(window).refresh_profiles()
    params(window).select_profile("late")

    assert window.run_page.profile_name() == "late"
    edit(window, "voltage", "41")
    params(window).bar.apply_button.click()
    assert window.run_page.build_request().parameters == {"test_profile": "late", "voltage": 41.0}


def set_list(win: MainWindow, name: str, values: List[str]) -> None:
    field = params(win).field(name)
    while field.chip_texts():
        field.findChild(QPushButton, f"chip-remove-{name}-0").click()
    for value in values:
        field.edit.setText(value)
        field.add_button.click()


def error_total(win: MainWindow) -> int:
    return int(re.search(r"오류 (\d+)", params(win).bar.counts_text()).group(1))


def test_stop_on_failure_survives_profile_save(window):
    check = params(window).field("stop_on_failure").check
    check.setChecked(False)
    params(window).bar.apply_button.click()

    save_profile(window, "nostop")

    assert not check.isChecked()
    assert window.run_page.build_request().parameters["stop_on_failure"] is False

    params(window).bar.select_profile("default")

    assert check.isChecked()
    assert "stop_on_failure" not in window.run_page.build_request().parameters

    params(window).bar.select_profile("nostop")

    assert not check.isChecked()
    assert window.run_page.build_request().parameters["stop_on_failure"] is False


def test_stop_on_failure_profile_is_used_at_startup(fast_profiles):
    data = yaml.safe_load((fast_profiles / "default.yaml").read_text(encoding="utf-8"))
    data["execution"]["stop_on_failure"] = False
    (fast_profiles / "default.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

    win = MainWindow()
    try:
        assert not params(win).field("stop_on_failure").check.isChecked()
        assert win.run_page.build_request().parameters["stop_on_failure"] is False
        assert win.run_page.applied_text() == "적용된 변경 0개"
    finally:
        win.close()


def apply_standby_over_activation(win: MainWindow) -> None:
    edit(win, "standby_temperature", "60")
    edit(win, "activation_temperature", "50")


def apply_temperature_over_upper(win: MainWindow) -> None:
    set_list(win, "temperature_list", ["90"])


def apply_stroke_below_initial(win: MainWindow) -> None:
    set_list(win, "stroke_positions", ["500"])


def apply_huge_temperature(win: MainWindow) -> None:
    set_list(win, "temperature_list", ["38", "1e300"])


def apply_equal_force_limits(win: MainWindow) -> None:
    edit(win, "force_limit_min", "10")
    edit(win, "force_limit_max", "10")


@pytest.mark.parametrize(
    "change",
    [
        apply_standby_over_activation,
        apply_temperature_over_upper,
        apply_stroke_below_initial,
        apply_huge_temperature,
        apply_equal_force_limits,
    ],
)
def test_validator_rules_block_apply(window, change):
    bar = params(window).bar
    change(window)

    assert error_total(window) >= 1
    assert not bar.apply_button.isEnabled()
    assert not bar.save_button.isEnabled()
    assert bar.rule_errors_text() != ""
    assert bar.rule_errors_visible()


def test_validator_errors_clear_when_fixed(window):
    bar = params(window).bar
    apply_equal_force_limits(window)
    assert not bar.apply_button.isEnabled()

    bar.revert_button.click()

    assert error_total(window) == 0
    assert bar.apply_button.isEnabled()
    assert bar.save_button.isEnabled()
    assert not bar.rule_errors_visible()


def test_default_profile_has_no_validator_errors(window):
    assert error_total(window) == 0
    assert params(window).bar.apply_button.isEnabled()
    assert not params(window).bar.rule_errors_visible()


def test_mock_toggle_on_corrupt_yaml_shows_error(window, mock_hardware):
    switch = hardware(window).mock_switch
    assert switch.isChecked()
    mock_hardware.write_text(": : [", encoding="utf-8")

    switch.click()

    assert switch.isChecked()
    assert "Mock 전환을 저장하지 못했습니다" in hardware(window).message_text()
    assert hardware(window).model_text("robot") == "mock"
    assert mock_hardware.read_text(encoding="utf-8") == ": : ["


def slow_connection_test(seconds: float):
    async def connection_test(self: HardwareStore):
        await asyncio.sleep(seconds)
        return {device: (True, None) for device in DEVICES}

    return connection_test


def test_close_during_connection_test_does_not_block(qtbot, window, monkeypatch):
    monkeypatch.setattr(HardwareStore, "connection_test", slow_connection_test(1.5))
    hardware(window).test_button.click()
    thread = hardware(window).connection_thread()
    events: List[str] = []
    thread.finished.connect(lambda: events.append("finished"))
    thread.destroyed.connect(lambda: events.append("destroyed"))
    assert thread.isRunning()

    began = time.monotonic()
    window.close()
    elapsed = time.monotonic() - began

    assert elapsed < 0.2
    assert window.isVisible()
    assert shiboken6.isValid(thread) and thread.isRunning()
    assert hardware(window).message_text() != "연결을 시험하는 중입니다..."
    assert "닫" in hardware(window).message_text()
    assert not hardware(window).test_button.isEnabled()

    qtbot.waitUntil(lambda: not window.isVisible(), timeout=10_000)
    qtbot.waitUntil(lambda: events == ["finished", "destroyed"], timeout=10_000)


def test_close_after_connection_test_closes_immediately(qtbot, window):
    hardware(window).test_button.click()
    qtbot.waitUntil(lambda: not hardware(window).is_testing(), timeout=RUN_TIMEOUT_MS)

    window.close()

    assert not window.isVisible()


APP_SCRIPT = textwrap.dedent(
    """
    import asyncio, os, sys
    from pathlib import Path
    import eol_tester.config as eol_config
    eol_config.HARDWARE_CONFIG_FILE = Path(os.environ["EOL_HARDWARE_CONFIG"])
    eol_config.TEST_PROFILES_DIR = Path(os.environ["EOL_TEST_PROFILES"])
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication
    from eol_ui.app import main
    from eol_ui.main_window import MainWindow
    from eol_ui.settings import HardwareStore

    async def slow(self):
        await asyncio.sleep(1.0)
        return {d: (True, None) for d in ("robot", "loadcell", "mcu", "power", "digital_io")}

    HardwareStore.connection_test = slow

    def start_test():
        window = next(w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow))
        window.settings_page.hardware.test_button.click()
        QTimer.singleShot(150, window.close)

    QTimer.singleShot(300, start_test)
    sys.exit(main(["eol-ui"]))
    """
)


def test_app_exits_cleanly_when_closed_during_connection_test(tmp_path, mock_hardware, fast_profiles):
    script = tmp_path / "run_app.py"
    script.write_text(APP_SCRIPT, encoding="utf-8")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    env["EOL_HARDWARE_CONFIG"] = str(mock_hardware)
    env["EOL_TEST_PROFILES"] = str(fast_profiles)

    done = subprocess.run(
        [sys.executable, "-c", f"import runpy; runpy.run_path({str(script)!r}, run_name='__main__')"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert "QThread: Destroyed while thread is still running" not in done.stderr
    assert done.returncode == 0, done.stderr
