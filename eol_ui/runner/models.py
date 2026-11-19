from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .events import LogEvent, SdkEvent, StepCompleteEvent, freeze

STAGE_NAMES = ("setup", "force_test", "teardown")

_MEASUREMENT_NAME = re.compile(r"^force_(-?\d+(?:\.\d+)?)C_(-?\d+(?:\.\d+)?)um$")
_RESULTS_SAVED = re.compile(r"Test results saved to: (.+?)\s*$")


class Verdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ABORTED = "ABORTED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RunRequest:
    serial_number: str
    wip_id: Optional[str] = None
    parameters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MeasurementRecord:
    name: str
    temperature: Optional[float]
    position: Optional[float]
    force: float
    min_value: Optional[float]
    max_value: Optional[float]
    passed: bool


@dataclass(frozen=True)
class StageResult:
    name: str
    passed: bool
    duration: float
    error: Optional[str]


@dataclass(frozen=True)
class RunOutcome:
    verdict: Verdict
    result: Mapping[str, Any]
    error: Optional[str]
    measurements: Tuple[MeasurementRecord, ...]
    stages: Mapping[str, StageResult]
    results_dir: Optional[Path]
    result_files: Tuple[Path, ...]
    started_at: datetime
    finished_at: datetime
    serial_number: str
    wip_id: Optional[str]
    abort_requested: bool


def judge(abort_requested: bool, passed: bool, error: Optional[str]) -> Verdict:
    if abort_requested and not passed:
        return Verdict.ABORTED
    if error:
        return Verdict.ERROR
    if passed:
        return Verdict.PASS
    return Verdict.FAIL


def _step_completions(events: Sequence[SdkEvent]) -> Dict[str, StepCompleteEvent]:
    return {
        event.step_name: event for event in events if isinstance(event, StepCompleteEvent)
    }


def _measurement_records(step: Optional[StepCompleteEvent]) -> Tuple[MeasurementRecord, ...]:
    if step is None:
        return ()
    records = []
    for name, data in step.measurements.items():
        match = _MEASUREMENT_NAME.match(name)
        records.append(
            MeasurementRecord(
                name=name,
                temperature=float(match.group(1)) if match else None,
                position=float(match.group(2)) if match else None,
                force=float(data["value"]),
                min_value=data.get("min"),
                max_value=data.get("max"),
                passed=bool(data.get("passed")),
            )
        )
    return tuple(records)


def _results_dir(events: Sequence[SdkEvent]) -> Optional[Path]:
    found: Optional[Path] = None
    for event in events:
        if isinstance(event, LogEvent):
            match = _RESULTS_SAVED.search(event.message)
            if match:
                found = Path(match.group(1))
    return found


def _files_modified_since(directory: Optional[Path], started_at: datetime) -> Tuple[Path, ...]:
    if directory is None or not directory.is_dir():
        return ()
    threshold = started_at.timestamp()
    files = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.stat().st_mtime >= threshold
    ]
    return tuple(sorted(files))


def build_outcome(
    request: RunRequest,
    result: Optional[Mapping[str, Any]],
    failure: Optional[BaseException],
    events: Sequence[SdkEvent],
    abort_requested: bool,
    started_at: datetime,
    finished_at: datetime,
) -> RunOutcome:
    completions = _step_completions(events)
    force_test = completions.get("force_test")
    result = result or {}
    error: Optional[str] = result.get("error")
    if not error and force_test is not None:
        error = force_test.error
    if not error and failure is not None:
        error = f"{type(failure).__name__}: {failure}"

    stages = {
        name: StageResult(name, step.passed, step.duration, step.error)
        for name, step in completions.items()
        if name in STAGE_NAMES
    }
    results_dir = _results_dir(events)
    return RunOutcome(
        verdict=judge(abort_requested, bool(result.get("passed", False)), error),
        result=freeze(result),
        error=error,
        measurements=_measurement_records(force_test),
        stages=MappingProxyType(stages),
        results_dir=results_dir,
        result_files=_files_modified_since(results_dir, started_at),
        started_at=started_at,
        finished_at=finished_at,
        serial_number=request.serial_number,
        wip_id=request.wip_id,
        abort_requested=abort_requested,
    )
