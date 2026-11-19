from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable, List, Optional, cast
from unittest.mock import AsyncMock

import pytest
from loguru import logger
from station_service_sdk import ExecutionContext
from station_service_sdk.core.exceptions import AbortError

from eol_tester import EOLForceTestSequence
from eol_tester.config import load_hardware_config
from eol_tester.domain.value_objects import DUTCommandInfo, HardwareConfig, TestConfiguration
from eol_tester.hardware_adapter import create_standalone_hardware_adapter
from eol_tester.interfaces import MCUService, TestMode
from eol_tester.services.hardware_facade import HardwareServiceFacade

from ..conftest import RecordingOutput

pytestmark = pytest.mark.usefixtures("mock_hardware", "fast_profiles", "tmp_results")


def _sequence(output: RecordingOutput) -> EOLForceTestSequence:
    context = ExecutionContext(serial_number="SN1", wip_id="W1")
    return EOLForceTestSequence(context, output_strategy=output)


class _AbortOnLog:
    def __init__(self, seq: EOLForceTestSequence, marker: str) -> None:
        self.lines: List[str] = []
        self.scheduled_at: Optional[float] = None
        self._seq = seq
        self._marker = marker
        self._loop = asyncio.get_running_loop()
        self._sink_id = logger.add(self._sink, level="DEBUG")

    def _request_abort(self) -> None:
        try:
            self._seq.abort()
        except AbortError:
            pass

    def _sink(self, message: Any) -> None:
        text = message.record["message"]
        self.lines.append(text)
        if self._marker in text and self.scheduled_at is None:
            self.scheduled_at = time.monotonic()
            self._loop.call_soon(self._request_abort)

    def close(self) -> None:
        logger.remove(self._sink_id)


@pytest.fixture
def abort_on_log():
    watchers: List[_AbortOnLog] = []

    def install(seq: EOLForceTestSequence, marker: str) -> _AbortOnLog:
        watcher = _AbortOnLog(seq, marker)
        watchers.append(watcher)
        return watcher

    yield install
    for watcher in watchers:
        watcher.close()


def _step_complete(output: RecordingOutput, name: str) -> dict:
    (event,) = [e for e in output.named("step_complete") if e["step_name"] == name]
    return event


def _assert_teardown_recorded(output: RecordingOutput) -> None:
    assert _step_complete(output, "teardown")
    assert output.named("sequence_complete")


def _result_jsons(tmp_results: Path) -> List[Path]:
    return sorted(tmp_results.rglob("SN1_*.json"))


async def test_mock_run_completes(recording_output: RecordingOutput, tmp_results: Path) -> None:
    result = await _sequence(recording_output)._execute()

    assert result["passed"] is True
    assert len(recording_output.named("measurement")) == 2
    _assert_teardown_recorded(recording_output)
    assert _result_jsons(tmp_results)


async def test_abort_stops_in_force_loop(
    recording_output: RecordingOutput, tmp_results: Path, abort_on_log
) -> None:
    seq = _sequence(recording_output)
    lines = abort_on_log(seq, "Measuring at position").lines

    await seq._execute()

    assert any("Measuring at position" in line for line in lines)
    assert not any("Setting temperature to 52.0C" in line for line in lines)
    assert recording_output.named("measurement") == []
    force_test = _step_complete(recording_output, "force_test")
    assert force_test["passed"] is False
    assert "Abort" in force_test["error"]
    _assert_teardown_recorded(recording_output)
    assert _result_jsons(tmp_results) == []


async def test_abort_during_setup_boot_wait(
    recording_output: RecordingOutput, abort_on_log
) -> None:
    seq = _sequence(recording_output)
    watcher = abort_on_log(seq, "Waiting for MCU boot complete signal")
    lines = watcher.lines

    result = await seq._execute()
    assert watcher.scheduled_at is not None
    elapsed = time.monotonic() - watcher.scheduled_at

    assert not any("Starting LMA standby sequence" in line for line in lines)
    assert not any("Setting temperature to" in line for line in lines)
    assert not any("Boot complete signal received" in line for line in lines)
    assert [e for e in recording_output.named("step_start") if e["step_name"] == "force_test"] == []
    assert result["passed"] is False
    assert "Abort" in str(result["error"])
    _assert_teardown_recorded(recording_output)
    assert elapsed < 3


# verify_mcu_temperature skips verification when the MCU class name contains "Mock".
class _FakeMCU:
    def __init__(
        self,
        temperature_offset: float = 0.0,
        boot_hangs: bool = False,
        boot_delay: float = 0.0,
    ) -> None:
        self.temperature_offset = temperature_offset
        self.boot_hangs = boot_hangs
        self.boot_delay = boot_delay
        self.boot_wait_calls = 0
        self.test_mode_calls = 0
        self.call_hook: Callable[[str], None] = lambda name: None
        self.operating_temperatures: List[float] = []
        self.expected = 0.0
        self.standby = 0.0
        self.get_temperature_calls = 0
        self.boot_wait_cancelled = False

    async def get_temperature(self) -> float:
        self.get_temperature_calls += 1
        return self.expected + self.temperature_offset

    async def wait_boot_complete(self) -> None:
        self.boot_wait_calls += 1
        self.call_hook("wait_boot_complete")
        if self.boot_delay:
            await asyncio.sleep(self.boot_delay)
        if not self.boot_hangs:
            return
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.boot_wait_cancelled = True
            raise

    async def set_test_mode(self, mode: TestMode) -> None:
        self.test_mode_calls += 1
        self.call_hook("set_test_mode")

    async def set_upper_temperature(self, temperature: float) -> None: ...
    async def set_fan_speed(self, speed: int) -> None: ...

    async def start_standby_heating(self, operating_temp: float, standby_temp: float) -> None:
        self.expected = operating_temp
        self.standby = standby_temp

    async def start_standby_cooling(self) -> None:
        self.expected = self.standby

    async def set_operating_temperature(self, temperature: float) -> None:
        self.expected = temperature
        self.operating_temperatures.append(temperature)


def _facade(mcu: _FakeMCU) -> HardwareServiceFacade:
    loadcell = AsyncMock()
    loadcell.read_peak_force.return_value = 1.5
    return HardwareServiceFacade(
        robot_service=AsyncMock(),
        mcu_service=cast(MCUService, mcu),
        loadcell_service=loadcell,
        power_service=AsyncMock(),
        digital_io_service=AsyncMock(),
    )


@pytest.fixture
def instant_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    real_sleep = asyncio.sleep

    async def sleep(delay: float, result: Any = None) -> Any:
        return await real_sleep(0, result)

    monkeypatch.setattr(asyncio, "sleep", sleep)


@pytest.mark.parametrize("abort_on_call", [2, 3, 5])
async def test_verify_temperature_retry_aborts(abort_on_call: int, instant_sleep: None) -> None:
    mcu = _FakeMCU(temperature_offset=10.0)
    mcu.expected = 50.0
    facade = _facade(mcu)
    calls = 0

    def abort_check() -> None:
        nonlocal calls
        calls += 1
        if calls >= abort_on_call:
            raise AbortError("Abort requested")

    with pytest.raises(AbortError):
        await facade.verify_mcu_temperature(
            50.0, TestConfiguration(), abort_check=abort_check
        )

    assert mcu.get_temperature_calls == abort_on_call - 2
    assert mcu.get_temperature_calls < 11


async def test_boot_wait_timeout_unchanged() -> None:
    mcu = _FakeMCU(boot_hangs=True)
    facade = _facade(mcu)
    config = TestConfiguration(
        timeout_seconds=0.3,
        poweron_stabilization=0,
        mcu_boot_complete_stabilization=0,
        mcu_command_stabilization=0,
    )

    for abort_check in (None, lambda: None):
        mcu.boot_wait_cancelled = False
        with pytest.raises(asyncio.TimeoutError):
            await facade.setup_test(config, HardwareConfig(), abort_check=abort_check)
        assert mcu.boot_wait_cancelled


async def test_abort_flag_unused_without_request(instant_sleep: None) -> None:
    mcu = _FakeMCU()
    facade = _facade(mcu)
    config = TestConfiguration(
        temperature_list=[38.0],
        stroke_positions=[20000.0],
        poweron_stabilization=0,
        mcu_boot_complete_stabilization=0,
        mcu_command_stabilization=0,
        robot_move_stabilization=0,
        robot_standby_stabilization=0,
    )
    hardware_config = HardwareConfig()
    dut = DUTCommandInfo(dut_id="W1", model_number="M", serial_number="SN1")

    await facade.verify_mcu_temperature(0.0, config)

    await facade.set_lma_standby(config, hardware_config)

    await facade.setup_test(config, hardware_config)
    measurements, cycles = await facade.perform_force_test_sequence(config, hardware_config, dut)
    assert len(cycles) == config.repeat_count

    adapter = create_standalone_hardware_adapter(
        test_config=config, hardware_config=load_hardware_config()
    )
    await adapter.setup_test()
    await adapter.execute_force_test(dut)


class _AbortSwitch:
    def __init__(self) -> None:
        self.armed = False
        self.lines: List[str] = []
        self._sink_id = logger.add(self._sink, level="DEBUG")
        self._marker: Optional[str] = None

    def _sink(self, message: Any) -> None:
        text = message.record["message"]
        self.lines.append(text)
        if self._marker is not None and self._marker in text:
            self.armed = True

    def arm_on_log(self, marker: str) -> None:
        self._marker = marker

    def arm_on_call(self, mcu: _FakeMCU, method: str) -> None:
        def hook(name: str) -> None:
            if name == method:
                self.armed = True

        mcu.call_hook = hook

    def __call__(self) -> None:
        if self.armed:
            raise AbortError("Abort requested")

    def logged(self, marker: str) -> bool:
        return any(marker in line for line in self.lines)

    def close(self) -> None:
        logger.remove(self._sink_id)


@pytest.fixture
def abort_switch():
    switch = _AbortSwitch()
    yield switch
    switch.close()


def _fast_config(**overrides: Any) -> TestConfiguration:
    values: dict = dict(
        temperature_list=[38.0, 52.0],
        stroke_positions=[20000.0],
        poweron_stabilization=0,
        mcu_boot_complete_stabilization=0,
        mcu_command_stabilization=0,
        robot_move_stabilization=0,
        robot_standby_stabilization=0,
    )
    values.update(overrides)
    return TestConfiguration(**values)


async def test_boot_wait_without_timeout_completes() -> None:
    mcu = _FakeMCU(boot_delay=0.3)
    facade = _facade(mcu)
    config = _fast_config(timeout_seconds=None)

    for abort_check in (None, lambda: None):
        mcu.boot_wait_calls = 0
        await facade.setup_test(config, HardwareConfig(), abort_check=abort_check)
        assert mcu.boot_wait_calls == 1


async def test_boot_wait_without_timeout_aborts() -> None:
    mcu = _FakeMCU(boot_hangs=True)
    facade = _facade(mcu)
    config = _fast_config(timeout_seconds=None)
    calls = 0

    def abort_check() -> None:
        nonlocal calls
        calls += 1
        if calls >= 4:
            raise AbortError("Abort requested")

    with pytest.raises(AbortError):
        await facade.setup_test(config, HardwareConfig(), abort_check=abort_check)

    assert mcu.boot_wait_cancelled


_SETUP_CHECKS = {
    "after_power_on": ("Waiting for MCU boot complete signal", lambda mcu: mcu.boot_wait_calls),
    "after_boot_wait": ("Starting LMA standby sequence", lambda mcu: mcu.test_mode_calls),
    "after_test_mode": ("Starting LMA standby sequence", lambda mcu: 0),
}


@pytest.mark.parametrize("point", list(_SETUP_CHECKS))
async def test_setup_test_check_between_steps(point: str, abort_switch: _AbortSwitch) -> None:
    mcu = _FakeMCU()
    facade = _facade(mcu)
    if point == "after_power_on":
        abort_switch.arm_on_log("Power enabled")
    elif point == "after_boot_wait":
        abort_switch.arm_on_call(mcu, "wait_boot_complete")
    else:
        abort_switch.arm_on_call(mcu, "set_test_mode")

    with pytest.raises(AbortError):
        await facade.setup_test(_fast_config(), HardwareConfig(), abort_check=abort_switch)

    skipped_log, skipped_calls = _SETUP_CHECKS[point]
    assert not abort_switch.logged(skipped_log)
    assert skipped_calls(mcu) == 0


_FORCE_CHECKS = {
    "repetition_start": ("Cycle 1 completed", "Force Test Repetition 2/2"),
    "temperature_start": ("Force Test Repetition 1/2", "Setting temperature to"),
    "position_start": ("Temperature verified", "Measuring at position"),
}


@pytest.mark.parametrize("point", list(_FORCE_CHECKS))
async def test_force_sequence_check_between_steps(point: str, abort_switch: _AbortSwitch) -> None:
    mcu = _FakeMCU()
    config = _fast_config(repeat_count=2)
    mcu.standby = config.standby_temperature
    facade = _facade(mcu)
    armed_on, skipped = _FORCE_CHECKS[point]
    abort_switch.arm_on_log(armed_on)
    dut = DUTCommandInfo(dut_id="W1", model_number="M", serial_number="SN1")

    with pytest.raises(AbortError):
        await facade.perform_force_test_sequence(
            config, HardwareConfig(), dut, abort_check=abort_switch
        )

    assert abort_switch.logged(armed_on)
    assert not abort_switch.logged(skipped)
    if point == "temperature_start":
        assert mcu.operating_temperatures == []
