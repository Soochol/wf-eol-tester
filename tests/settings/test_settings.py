from __future__ import annotations

import asyncio
import copy
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from station_service_sdk import ExecutionContext

import eol_tester.config as eol_config
from eol_tester import EOLForceTestSequence
from eol_ui.settings import HardwareStore, ProfileExistsError, SettingsModel

from ..conftest import RecordingOutput

ORIGINAL_CONFIG_DIR = Path(eol_config.CONFIG_DIR)
ORIGINAL_HARDWARE = ORIGINAL_CONFIG_DIR / "hardware_config.yaml"


@pytest.fixture
def model() -> SettingsModel:
    settings = SettingsModel()
    settings.load("default")
    return settings


@pytest.fixture
def real_hardware(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "hardware_config.yaml"
    shutil.copy(ORIGINAL_HARDWARE, path)
    monkeypatch.setattr(eol_config, "HARDWARE_CONFIG_FILE", path)
    return path


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_schema_from_manifest(model: SettingsModel) -> None:
    schema = model.schema
    assert len(schema) == 15
    assert (schema["voltage"].unit, schema["voltage"].min, schema["voltage"].max) == ("V", 0.0, 50.0)
    assert (schema["repeat_count"].kind, schema["repeat_count"].min, schema["repeat_count"].max) == (
        "int",
        1,
        100,
    )
    assert schema["temperature_list"].kind == "float_list"
    assert schema["stroke_positions"].kind == "float_list"
    assert schema["stop_on_failure"].kind == "bool"


def test_baseline_from_profile(model: SettingsModel) -> None:
    assert model.baseline("voltage") == 40.0
    assert model.baseline("current") == 42.0
    assert len(model.baseline("temperature_list")) == 4
    assert model.baseline("operating_position") == 175000
    assert model.baseline("stop_on_failure") is True
    assert model.changed_count() == 0


def test_only_changed_parameters(model: SettingsModel) -> None:
    model.set_value("voltage", "45")
    model.set_value("repeat_count", "2")
    model.set_value("current", "42")
    parameters = model.to_parameters()

    assert parameters == {"test_profile": "default", "voltage": 45.0, "repeat_count": 2}
    assert type(parameters["voltage"]) is float
    assert type(parameters["repeat_count"]) is int
    assert model.changed_count() == 2

    model.set_value("voltage", "40")
    model.set_value("repeat_count", 1)
    assert model.to_parameters() == {"test_profile": "default"}


def test_list_parameters_typed(model: SettingsModel) -> None:
    model.set_value("temperature_list", [38, 52])
    parameters = model.to_parameters()
    assert parameters["temperature_list"] == [38.0, 52.0]
    assert all(type(item) is float for item in parameters["temperature_list"])

    model.set_value("temperature_list", [])
    assert model.error("temperature_list")
    model.set_value("temperature_list", [38, "abc"])
    assert model.error("temperature_list")
    with pytest.raises(ValueError):
        model.to_parameters()


def test_range_validation(model: SettingsModel) -> None:
    model.set_value("velocity", 150000)
    model.set_value("force_limit_min", 50)
    model.set_value("force_limit_max", 10)
    model.set_value("stroke_positions", [200000])
    assert set(model.errors()) == {"velocity", "force_limit_max", "stroke_positions"}
    assert model.error_count() == 3

    model.set_value("velocity", 100000)
    model.set_value("force_limit_max", 60)
    model.set_value("stroke_positions", [170000])
    assert model.error_count() == 0


def test_revert(model: SettingsModel) -> None:
    model.set_value("voltage", 45)
    model.set_value("repeat_count", 5)
    model.set_value("temperature_list", [30])
    model.set_value("stop_on_failure", False)
    assert model.changed_count() == 4

    model.revert()
    assert model.changed_count() == 0
    assert model.to_parameters() == {"test_profile": "default"}


def test_save_as_roundtrip(fast_profiles: Path) -> None:
    model = SettingsModel()
    model.load("default")
    original = eol_config.load_test_profile("default")
    model.set_value("voltage", "30")
    model.save_as("line2")

    saved = eol_config.load_test_profile("line2")
    assert saved["hardware"]["voltage"] == 30.0
    for section in ("timing", "safety", "tolerances"):
        assert saved[section] == original[section]
    assert saved["metadata"]["profile_name"] == "line2"
    assert "line2" in eol_config.list_test_profiles()
    assert model.profile_name == "line2"
    assert model.changed_count() == 0

    model.set_value("voltage", 31)
    with pytest.raises(ProfileExistsError):
        model.save_as("line2")
    model.save_as("line2", overwrite=True)
    assert eol_config.load_test_profile("line2")["hardware"]["voltage"] == 31.0


async def test_parameters_drive_sequence(
    fast_profiles: Path, mock_hardware: Path, tmp_results: Path, recording_output: RecordingOutput
) -> None:
    model = SettingsModel()
    model.load("default")
    model.set_value("temperature_list", [38])
    model.set_value("force_limit_max", 1.0)

    context = ExecutionContext(serial_number="SN1", wip_id="W1")
    sequence = EOLForceTestSequence(
        context, output_strategy=recording_output, parameters=model.to_parameters()
    )
    result = await sequence._execute()

    assert len(recording_output.named("measurement")) == 1
    assert result["passed"] is False


def test_hardware_store_preserves_keys(real_hardware: Path) -> None:
    before = _yaml(real_hardware)
    store = HardwareStore()
    store.set_value("loadcell", "port", "COM3")
    store.save()

    after = _yaml(real_hardware)
    assert after["loadcell"]["port"] == "COM3"
    expected = copy.deepcopy(before)
    expected["loadcell"]["port"] = "COM3"
    assert after == expected
    for key in ("digital_io", "metadata"):
        assert after[key] == before[key]
    assert after["power"]["delimiter"] == before["power"]["delimiter"]
    assert after["robot"]["motion_param_file"] == before["robot"]["motion_param_file"]


def test_hardware_store_rejects_bad_values(real_hardware: Path) -> None:
    store = HardwareStore()
    with pytest.raises(ValueError):
        store.set_value("mcu", "baudrate", "fast")
    with pytest.raises(ValueError):
        store.set_value("loadcell", "port", " ")
    with pytest.raises(KeyError):
        store.set_value("loadcell", "model", "mock")


def test_hardware_store_mock_roundtrip(real_hardware: Path) -> None:
    store = HardwareStore()
    assert not store.is_mock()
    store.set_mock(True)
    store.save()
    assert eol_config.load_hardware_config().is_mock_mode()
    assert _yaml(real_hardware)["ui_real_models"]["loadcell"] == "bs205"

    reopened = HardwareStore()
    reopened.set_mock(False)
    reopened.save()
    loaded = eol_config.load_hardware_config()
    assert (
        loaded.robot.model,
        loaded.loadcell.model,
        loaded.mcu.model,
        loaded.power.model,
        loaded.digital_io.model,
    ) == ("ajinextek", "bs205", "lma", "oda", "ajinextek")


def test_hardware_store_unmock_without_backup_uses_manifest_models(mock_hardware: Path) -> None:
    store = HardwareStore()
    assert store.is_mock()
    store.set_mock(False)
    assert [store.model(d) for d in ("robot", "loadcell", "mcu", "power", "digital_io")] == [
        "ajinextek",
        "bs205",
        "lma",
        "oda",
        "ajinextek",
    ]


async def test_connection_test_mock(mock_hardware: Path) -> None:
    result = await HardwareStore().connection_test()
    assert set(result) == {"robot", "loadcell", "mcu", "power", "digital_io"}
    assert all(ok for ok, _ in result.values())


async def test_connection_test_reports_adapter_failure(
    mock_hardware: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(**_: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("eol_ui.settings.hardware_store.create_standalone_hardware_adapter", broken)
    result = await HardwareStore().connection_test()
    assert all(value == (False, "boom") for value in result.values())


async def test_connection_test_isolates_failing_device(
    mock_hardware: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eol_tester.hardware.mock import MockLoadCellService, MockPowerService

    async def failing_connect(self: Any) -> None:
        raise ConnectionError("COM8 not found")

    real_power_connect = MockPowerService.connect

    async def slow_power_connect(self: Any) -> None:
        await asyncio.sleep(0.05)
        await real_power_connect(self)

    connected: list[Any] = []
    real_disconnect = MockPowerService.disconnect

    async def tracking_disconnect(self: Any) -> None:
        await real_disconnect(self)
        connected.append(await self.is_connected())

    monkeypatch.setattr(MockLoadCellService, "connect", failing_connect)
    monkeypatch.setattr(MockPowerService, "connect", slow_power_connect)
    monkeypatch.setattr(MockPowerService, "disconnect", tracking_disconnect)

    result = await HardwareStore().connection_test()

    assert result["loadcell"] == (False, "COM8 not found")
    for device in ("robot", "mcu", "power", "digital_io"):
        assert result[device] == (True, None)
    assert connected == [False]


@pytest.mark.parametrize("content", ["robot: [unclosed", "", "- just\n- a list\n"])
async def test_connection_test_unreadable_config_fails_all(
    mock_hardware: Path, content: str
) -> None:
    store = HardwareStore()
    mock_hardware.write_text(content, encoding="utf-8")
    result = await store.connection_test()
    assert set(result) == {"robot", "loadcell", "mcu", "power", "digital_io"}
    assert all(not ok and error for ok, error in result.values())


def test_non_finite_and_huge_inputs_are_value_errors(
    real_hardware: Path, model: SettingsModel
) -> None:
    store = HardwareStore()
    for raw in ("inf", "nan", "1e999", 10**400, None):
        with pytest.raises(ValueError):
            store.set_value("robot", "axis_id", raw)
    for raw in (None, True):
        with pytest.raises(ValueError):
            store.set_value("loadcell", "port", raw)
    model.set_value("repeat_count", 10**400)
    assert model.error("repeat_count")


def test_null_profile_values_use_defaults_and_save(fast_profiles: Path) -> None:
    path = fast_profiles / "default.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["hardware"]["voltage"] = None
    data["execution"] = None
    data["metadata"] = None
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    model = SettingsModel()
    model.load("default")
    assert model.baseline("voltage") == 18.0
    model.set_value("repeat_count", 3)
    model.save_as("nulls")
    assert eol_config.load_test_profile("nulls")["execution"]["repeat_count"] == 3


def test_stop_on_failure_is_stored_in_profile_and_read_back(fast_profiles: Path) -> None:
    model = SettingsModel()
    model.load("default")
    model.set_value("stop_on_failure", False)
    model.save_as("nostop")

    assert eol_config.load_test_profile("nostop")["execution"]["stop_on_failure"] is False
    assert model.baseline("stop_on_failure") is False
    assert model.changed_count() == 0
    assert model.carried_parameters() == {"stop_on_failure": False}
    assert model.to_parameters() == {"test_profile": "nostop", "stop_on_failure": False}

    model.set_value("stop_on_failure", True)
    assert model.to_parameters() == {"test_profile": "nostop", "stop_on_failure": True}
    model.load("default")
    assert model.carried_parameters() == {}


async def test_profile_with_stop_on_failure_runs(
    fast_profiles: Path, mock_hardware: Path, tmp_results: Path, recording_output: RecordingOutput
) -> None:
    model = SettingsModel()
    model.load("default")
    model.set_value("stop_on_failure", False)
    model.save_as("nostop")
    assert eol_config.load_test_profile("nostop")["execution"]["stop_on_failure"] is False

    context = ExecutionContext(serial_number="SN1", wip_id="W1")
    sequence = EOLForceTestSequence(
        context, output_strategy=recording_output, parameters=model.to_parameters()
    )
    result = await sequence._execute()

    assert sequence.stop_on_failure is False
    assert not any(
        "Configuration validation failed" in str(args) for _, args in recording_output.events
    )
    assert "passed" in result


@pytest.mark.parametrize(
    "name, value",
    [
        ("standby_temperature", 60),
        ("temperature_list", [90]),
        ("stroke_positions", [500]),
        ("temperature_list", [38, 1e300]),
    ],
)
def test_validator_rules_are_reported_by_model(model: SettingsModel, name: str, value: Any) -> None:
    if name == "standby_temperature":
        model.set_value("activation_temperature", 50)
    model.set_value(name, value)

    assert model.rule_errors()
    assert model.error_count() >= 1
    with pytest.raises(ValueError):
        model.to_parameters()
    with pytest.raises(ValueError):
        model.save_as("blocked")


def test_equal_force_limits_are_reported_by_model(model: SettingsModel) -> None:
    model.set_value("force_limit_min", 10)
    model.set_value("force_limit_max", 10)

    assert any("Force limit" in message for message in model.rule_errors())


def test_default_profile_has_no_rule_errors(model: SettingsModel) -> None:
    assert model.rule_errors() == []
    assert model.error_count() == 0
