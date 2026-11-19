"""Shared fixtures. Only this file defines fixtures common to every test package."""

from __future__ import annotations

import copy
import inspect
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import eol_tester.config as eol_config  # noqa: E402
import eol_tester.sequence as eol_sequence  # noqa: E402
from station_service_sdk.core.interfaces import OutputStrategy  # noqa: E402

_DEVICES = ("robot", "loadcell", "mcu", "power", "digital_io")


@pytest.fixture
def mock_hardware(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """hardware_config.yaml with every device on the mock driver."""
    data = yaml.safe_load(eol_config.HARDWARE_CONFIG_FILE.read_text(encoding="utf-8"))
    for device in _DEVICES:
        data[device]["model"] = "mock"
    path = tmp_path / "hardware_config.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(eol_config, "HARDWARE_CONFIG_FILE", path)
    return path


@pytest.fixture
def fast_profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """test_profiles/ whose default.yaml has zero timing and a 2-temperature, 1-position matrix."""
    original = eol_config.TEST_PROFILES_DIR / "default.yaml"
    profile: Dict[str, Any] = copy.deepcopy(yaml.safe_load(original.read_text(encoding="utf-8")))
    profile["timing"] = {key: 0 for key in profile["timing"]}
    profile["hardware"]["operating_position"] = 20000
    profile["test_parameters"]["stroke_positions"] = [20000.0]
    profile["test_parameters"]["temperature_list"] = [38.0, 52.0]
    profiles_dir = tmp_path / "test_profiles"
    profiles_dir.mkdir()
    (profiles_dir / "default.yaml").write_text(
        yaml.safe_dump(profile, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setattr(eol_config, "TEST_PROFILES_DIR", profiles_dir)
    return profiles_dir


@pytest.fixture
def tmp_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pin the sequence's ResultRepository to a tmp base_dir."""
    base_dir = tmp_path / "results"
    real_repository = eol_sequence.ResultRepository
    monkeypatch.setattr(
        eol_sequence,
        "ResultRepository",
        lambda *args, **kwargs: real_repository(base_dir=base_dir),
    )
    return base_dir


class RecordingOutput:
    """OutputStrategy that records every call as (method name, bound arguments)."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, Dict[str, Any]]] = []

    def named(self, name: str) -> List[Dict[str, Any]]:
        return [args for event, args in self.events if event == name]


def _recorder(name: str, signature: inspect.Signature) -> Callable[..., Any]:
    def record(self: RecordingOutput, *args: Any, **kwargs: Any) -> None:
        bound = signature.bind(self, *args, **kwargs)
        bound.apply_defaults()
        arguments = dict(bound.arguments)
        arguments.pop("self")
        self.events.append((name, arguments))

    record.__name__ = name
    return record


for _name, _method in inspect.getmembers(OutputStrategy, inspect.isfunction):
    if not _name.startswith("_"):
        setattr(RecordingOutput, _name, _recorder(_name, inspect.signature(_method)))


@pytest.fixture
def recording_output() -> RecordingOutput:
    return RecordingOutput()
