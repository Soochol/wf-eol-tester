from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton

import eol_tester.config as eol_config
from eol_ui.main_window import MainWindow
from eol_ui.pages.settings.fields import ListField
from eol_ui.pages.settings.parameters import DISCARD_NOTICE, GROUPS
from eol_ui.runner import RunOutcome, SequenceRunner
from eol_ui.settings import load_schema
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


@pytest.mark.parametrize("name", ["", "   ", "line2.yaml", "a.b", "../x", "a/b", "a\\b", "bad:name"])
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
