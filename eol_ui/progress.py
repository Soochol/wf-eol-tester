from __future__ import annotations

import ast
import re
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from types import MappingProxyType
from typing import Callable, Mapping, Optional, Tuple


class Phase(str, Enum):
    SETUP = "setup"
    FORCE_TEST = "force_test"
    TEARDOWN = "teardown"
    DONE = "done"


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class StageProgress:
    status: StageStatus = StageStatus.PENDING
    duration: Optional[float] = None


Fraction = Tuple[int, int]

_STAGES = (Phase.SETUP, Phase.FORCE_TEST, Phase.TEARDOWN)

_SETUP_END_PERCENT = 10.0
_FORCE_SPAN_PERCENT = 85.0
_TEARDOWN_START_PERCENT = 95.0


def _initial_stages() -> Mapping[Phase, StageProgress]:
    return MappingProxyType({stage: StageProgress() for stage in _STAGES})


@dataclass(frozen=True)
class ProgressState:
    phase: Phase = Phase.SETUP
    stages: Mapping[Phase, StageProgress] = field(default_factory=_initial_stages)
    measurements_done: int = 0
    measurements_total: int = 0
    temperature: Fraction = (0, 0)
    position: Fraction = (0, 0)
    repetition: Fraction = (0, 0)
    percent: float = 0.0
    activity: str = "대기 중"
    elapsed: float = 0.0
    remaining: Optional[float] = None
    mcu_target_temperature: Optional[float] = None
    mcu_actual_temperature: Optional[float] = None
    last_force: Optional[float] = None
    power_voltage: Optional[float] = None
    power_current: Optional[float] = None
    power_on: Optional[bool] = None
    robot_position: Optional[float] = None
    devices: Mapping[str, bool] = field(default_factory=lambda: MappingProxyType({}))


_NUMBER = r"(-?\d+(?:\.\d+)?)"
_TEST_MATRIX = re.compile(
    r"Test matrix: (\d+) temps x (\d+) positions x (\d+) repeats = (\d+) measurements"
)
_SET_TEMPERATURE = re.compile(rf"Setting temperature to {_NUMBER}C \((\d+)/(\d+)\)")
_MEASURE_POSITION = re.compile(rf"Measuring at position {_NUMBER}um \((\d+)/(\d+)\)")
_REPETITION = re.compile(r"===== Force Test Repetition (\d+)/(\d+) =====")
_FORCE = re.compile(rf"Force: {_NUMBER}kgf")
_POWER_ENABLED = re.compile(rf"Power enabled: {_NUMBER}V, {_NUMBER}A")
_TEMPERATURE_VERIFIED = re.compile(rf"Temperature verified: {_NUMBER}C")
_ROBOT_INITIAL = re.compile(rf"Moving robot to initial position: {_NUMBER}um")
_ROBOT_MOVED = re.compile(rf"Moved to {_NUMBER}um")
_HARDWARE_STATUS = re.compile(r"Hardware status: (\{.*\})\s*$")
_TEARDOWN_COMPLETE = re.compile(r"Test teardown complete")


def _stage_for(name: str) -> Optional[Phase]:
    for stage in _STAGES:
        if stage.value == name:
            return stage
    return None


class ProgressTracker:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._started_at = clock()
        self._force_started_at: Optional[float] = None
        self._finished_at: Optional[float] = None
        self._state = ProgressState()

    def snapshot(self) -> ProgressState:
        now = self._finished_at if self._finished_at is not None else self._clock()
        return replace(
            self._state,
            elapsed=now - self._started_at,
            remaining=self._remaining(now),
        )

    def on_status(self, status: str) -> bool:
        if status == "setup":
            return self._enter_setup()
        if status == "running":
            return self._enter_force_test()
        if status == "teardown":
            return self._enter_teardown()
        return False

    def on_step_complete(self, step_name: str, passed: bool, duration: float) -> bool:
        stage = _stage_for(step_name)
        if stage is None:
            return False
        outcome = StageProgress(StageStatus.DONE if passed else StageStatus.FAILED, duration)
        stages = self._with_stage(stage, outcome)
        if stage is Phase.TEARDOWN:
            return self._apply(stages=stages, power_on=False)
        return self._apply(stages=stages)

    def on_sequence_complete(self) -> bool:
        if self._finished_at is None:
            self._finished_at = self._clock()
        return self._apply(phase=Phase.DONE, activity="완료")

    def on_log(self, message: str) -> bool:
        for pattern, handler in self._log_handlers():
            match = pattern.search(message)
            if match:
                return handler(match)
        return False

    def _log_handlers(self):
        return (
            (_TEST_MATRIX, self._on_matrix),
            (_SET_TEMPERATURE, self._on_set_temperature),
            (_MEASURE_POSITION, self._on_measure_position),
            (_REPETITION, self._on_repetition),
            (_FORCE, self._on_force),
            (_POWER_ENABLED, self._on_power_enabled),
            (_TEMPERATURE_VERIFIED, self._on_temperature_verified),
            (_ROBOT_INITIAL, self._on_robot_position),
            (_ROBOT_MOVED, self._on_robot_position),
            (_HARDWARE_STATUS, self._on_hardware_status),
            (_TEARDOWN_COMPLETE, self._on_teardown_complete),
        )

    def _apply(self, **changes: object) -> bool:
        updated = replace(self._state, **changes)
        updated = replace(updated, percent=max(self._state.percent, self._percent(updated)))
        if updated == self._state:
            return False
        self._state = updated
        return True

    def _with_stage(self, stage: Phase, progress: StageProgress) -> Mapping[Phase, StageProgress]:
        stages = dict(self._state.stages)
        stages[stage] = progress
        return MappingProxyType(stages)

    def _enter_setup(self) -> bool:
        return self._apply(
            phase=Phase.SETUP,
            stages=self._with_stage(Phase.SETUP, StageProgress(StageStatus.RUNNING)),
            activity="장비 초기화 중",
        )

    def _enter_force_test(self) -> bool:
        self._force_started_at = self._clock()
        stages = dict(self._state.stages)
        setup = stages[Phase.SETUP]
        if setup.status is not StageStatus.DONE:
            stages[Phase.SETUP] = StageProgress(
                StageStatus.DONE, self._clock() - self._started_at
            )
        stages[Phase.FORCE_TEST] = StageProgress(StageStatus.RUNNING)
        return self._apply(
            phase=Phase.FORCE_TEST,
            stages=MappingProxyType(stages),
            activity="Force 시험 준비 중",
        )

    def _enter_teardown(self) -> bool:
        stages = dict(self._state.stages)
        if stages[Phase.SETUP].status is StageStatus.RUNNING:
            stages[Phase.SETUP] = StageProgress(StageStatus.FAILED)
        stages[Phase.TEARDOWN] = StageProgress(StageStatus.RUNNING)
        return self._apply(
            phase=Phase.TEARDOWN,
            stages=MappingProxyType(stages),
            activity="장비 정리 중",
        )

    def _on_matrix(self, match: "re.Match[str]") -> bool:
        repeats = int(match.group(3))
        return self._apply(
            measurements_total=int(match.group(4)),
            repetition=(1, repeats),
        )

    def _on_set_temperature(self, match: "re.Match[str]") -> bool:
        temperature, index, total = float(match.group(1)), int(match.group(2)), int(match.group(3))
        return self._apply(
            mcu_target_temperature=temperature,
            temperature=(index, total),
            activity=f"온도 {temperature:g}°C 설정 중 ({index}/{total})",
        )

    def _on_measure_position(self, match: "re.Match[str]") -> bool:
        position, index, total = float(match.group(1)), int(match.group(2)), int(match.group(3))
        return self._apply(
            robot_position=position,
            position=(index, total),
            activity=f"위치 {position:g}µm에서 측정 중 ({index}/{total})",
        )

    def _on_repetition(self, match: "re.Match[str]") -> bool:
        return self._apply(repetition=(int(match.group(1)), int(match.group(2))))

    def _on_force(self, match: "re.Match[str]") -> bool:
        force = float(match.group(1))
        return self._apply(
            last_force=force,
            measurements_done=self._state.measurements_done + 1,
            activity=f"Force {force:g} kgf 측정 완료",
        )

    def _on_power_enabled(self, match: "re.Match[str]") -> bool:
        return self._apply(
            power_voltage=float(match.group(1)),
            power_current=float(match.group(2)),
            power_on=True,
        )

    def _on_temperature_verified(self, match: "re.Match[str]") -> bool:
        return self._apply(mcu_actual_temperature=float(match.group(1)))

    def _on_robot_position(self, match: "re.Match[str]") -> bool:
        return self._apply(robot_position=float(match.group(1)))

    def _on_hardware_status(self, match: "re.Match[str]") -> bool:
        try:
            raw = ast.literal_eval(match.group(1))
        except (ValueError, SyntaxError):
            return False
        if not isinstance(raw, dict):
            return False
        devices = {str(name): value for name, value in raw.items() if isinstance(value, bool)}
        return self._apply(devices=MappingProxyType(devices))

    def _on_teardown_complete(self, _: "re.Match[str]") -> bool:
        return self._apply(power_on=False)

    def _percent(self, state: ProgressState) -> float:
        if state.phase is Phase.DONE:
            return 100.0
        if state.phase is Phase.TEARDOWN:
            return _TEARDOWN_START_PERCENT
        if state.phase is Phase.FORCE_TEST:
            if state.measurements_total <= 0:
                return _SETUP_END_PERCENT
            done = min(state.measurements_done, state.measurements_total)
            return _SETUP_END_PERCENT + _FORCE_SPAN_PERCENT * done / state.measurements_total
        return 0.0

    def _remaining(self, now: float) -> Optional[float]:
        state = self._state
        if (
            state.phase is not Phase.FORCE_TEST
            or self._force_started_at is None
            or state.measurements_done < 1
        ):
            return None
        left = max(state.measurements_total - state.measurements_done, 0)
        return (now - self._force_started_at) / state.measurements_done * left
