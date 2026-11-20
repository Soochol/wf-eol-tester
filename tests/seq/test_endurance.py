from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List

import pytest
import yaml
from station_service_sdk import ExecutionContext
from station_service_sdk.core.exceptions import AbortError

import eol_tester.config as eol_config
from eol_tester import EOLForceTestSequence
from eol_tester.services import hardware_facade
from eol_tester.services.hardware_facade import _fill_phase

from ..conftest import RecordingOutput

pytestmark = pytest.mark.usefixtures("mock_hardware", "fast_profiles", "tmp_results")


async def test_fill_phase_waits_for_the_rest_of_the_phase() -> None:
    loop = asyncio.get_running_loop()
    started = loop.time()
    await asyncio.sleep(0.1)
    await _fill_phase(started, 0.4, "Heating", None)
    assert loop.time() - started == pytest.approx(0.4, abs=0.05)


async def test_fill_phase_does_not_wait_when_phase_already_passed() -> None:
    loop = asyncio.get_running_loop()
    started = loop.time() - 1.0
    before = loop.time()
    await _fill_phase(started, 0.5, "Cooling", None)
    assert loop.time() - before < 0.05


async def test_fill_phase_zero_means_no_wait() -> None:
    loop = asyncio.get_running_loop()
    before = loop.time()
    await _fill_phase(loop.time(), 0.0, "Heating", None)
    assert loop.time() - before < 0.05


async def test_fill_phase_honours_abort() -> None:
    def abort() -> None:
        raise AbortError("stop")

    with pytest.raises(AbortError):
        await _fill_phase(asyncio.get_running_loop().time(), 5.0, "Cooling", abort)


def _write_profile(fast_profiles: Path, **timing: float) -> None:
    path = fast_profiles / "default.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["timing"].update(timing)
    data["execution"]["repeat_count"] = 3
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


async def test_phases_stretch_each_temperature(
    fast_profiles: Path, recording_output: RecordingOutput
) -> None:
    _write_profile(fast_profiles, heating_phase_seconds=0.3, cooling_phase_seconds=0.5)
    seq = EOLForceTestSequence(
        ExecutionContext(serial_number="SN1", wip_id="W1"),
        parameters={"repeat_count": 1},
        output_strategy=recording_output,
    )
    loop = asyncio.get_running_loop()
    started = loop.time()
    result = await seq._execute()
    assert result["passed"] is True
    temps = len(seq.hardware.test_config.temperature_list)
    assert loop.time() - started >= temps * 0.8


async def test_hold_time_is_sent_with_standby_heating(fast_profiles: Path, recording_output: RecordingOutput, monkeypatch) -> None:
    _write_profile(fast_profiles, mcu_hold_time_ms=40000)
    calls: List[dict] = []
    original = hardware_facade.HardwareServiceFacade.set_lma_standby

    async def spy(self, test_config, hardware_config, abort_check=None):
        mcu = self._mcu
        real = mcu.start_standby_heating

        async def record(**kwargs):
            calls.append(kwargs)
            await real(**kwargs)

        monkeypatch.setattr(mcu, "start_standby_heating", record)
        await original(self, test_config, hardware_config, abort_check)

    monkeypatch.setattr(hardware_facade.HardwareServiceFacade, "set_lma_standby", spy)
    seq = EOLForceTestSequence(
        ExecutionContext(serial_number="SN1", wip_id="W1"),
        parameters={"repeat_count": 1},
        output_strategy=recording_output,
    )
    await seq._execute()
    assert calls and calls[0]["hold_time_ms"] == 40000


async def test_cycles_are_saved_even_if_the_run_errors_later(
    fast_profiles: Path, tmp_results: Path, recording_output: RecordingOutput, monkeypatch
) -> None:
    _write_profile(fast_profiles)
    seq = EOLForceTestSequence(
        ExecutionContext(serial_number="SN1", wip_id="W1"),
        output_strategy=recording_output,
    )
    calls = {"n": 0}
    original = hardware_facade.HardwareServiceFacade.verify_mcu_temperature

    async def failing(self, temperature, test_config, abort_check=None):
        calls["n"] += 1
        temps = len(test_config.temperature_list)
        if calls["n"] > temps * 2 * 2:
            raise RuntimeError("battery empty")
        await original(self, temperature, test_config, abort_check)

    monkeypatch.setattr(hardware_facade.HardwareServiceFacade, "verify_mcu_temperature", failing)
    result = await seq._execute()
    assert result["passed"] is False
    assert seq._saved_cycles == {1}


async def test_full_run_saves_every_cycle_once(
    fast_profiles: Path, tmp_results: Path, recording_output: RecordingOutput, monkeypatch
) -> None:
    _write_profile(fast_profiles)
    seq = EOLForceTestSequence(
        ExecutionContext(serial_number="SN1", wip_id="W1"),
        output_strategy=recording_output,
    )
    saved: List[int] = []
    original = seq._save_one_cycle

    def counting(test_id, total, wip_id, cycle_result):
        saved.append(cycle_result.cycle_number)
        original(test_id, total, wip_id, cycle_result)

    monkeypatch.setattr(seq, "_save_one_cycle", counting)
    result = await seq._execute()
    assert result["passed"] is True
    assert saved == [1, 2, 3]


def test_endurance_profile_matches_request() -> None:
    data = yaml.safe_load(
        (Path(eol_config.CONFIG_DIR) / "test_profiles" / "endurance.yaml").read_text(encoding="utf-8")
    )
    assert data["test_parameters"]["temperature_list"] == [66.0, 58.0, 52.0]
    assert data["timing"]["heating_phase_seconds"] == 20.0
    assert data["timing"]["cooling_phase_seconds"] == 40.0
    assert data["timing"]["mcu_hold_time_ms"] == 40000
    assert data["execution"]["repeat_count"] >= 185
    assert data["execution"].get("stop_on_failure", True) is True
