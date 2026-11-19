from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from station_service_sdk import ExecutionContext

import eol_tester.config as eol_config
from eol_tester import EOLForceTestSequence
from eol_tester.services import ConfigurationValidator
from eol_ui.settings import HardwareStore

SHIPPED_HARDWARE = Path(eol_config.CONFIG_DIR) / "hardware_config.yaml"


def test_shipped_hardware_config_loads() -> None:
    config = eol_config.load_hardware_config()

    assert config.digital_io.input_module_no == 0
    assert config.digital_io.output_module_no == 1
    assert config.robot.motion_param_file is None
    assert config.power.model == "mock"
    assert not config.is_mock_mode()


def test_default_motion_file_is_found_by_robot_fallback() -> None:
    assert (eol_config.CONFIG_DIR / "robot_motion_settings.mot").is_file()


def _shipped_test_configuration():
    sequence = EOLForceTestSequence(ExecutionContext(serial_number="SN1", wip_id="W1"))
    return sequence._create_test_config_from_profile(eol_config.load_test_profile("default"))


def test_shipped_profile_temperature_tolerance() -> None:
    assert _shipped_test_configuration().temperature_tolerance == 30


async def test_shipped_configs_pass_validation() -> None:
    await ConfigurationValidator().validate_all_configurations(
        _shipped_test_configuration(), eol_config.load_hardware_config()
    )


def test_store_reads_original_loader_defaults_for_missing_keys() -> None:
    store = HardwareStore()

    assert store.get("digital_io", "input_module_no") == 0
    assert store.get("digital_io", "output_module_no") == 1


def test_store_rejects_unknown_key() -> None:
    store = HardwareStore()

    with pytest.raises(KeyError):
        store.get("digital_io", "no_such_key")


def test_saving_other_field_does_not_add_module_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "hardware_config.yaml"
    shutil.copy(SHIPPED_HARDWARE, path)
    monkeypatch.setattr(eol_config, "HARDWARE_CONFIG_FILE", path)

    store = HardwareStore()
    store.set_value("loadcell", "port", "COM3")
    store.save()

    digital_io = yaml.safe_load(path.read_text(encoding="utf-8"))["digital_io"]
    assert "input_module_no" not in digital_io
    assert "output_module_no" not in digital_io
