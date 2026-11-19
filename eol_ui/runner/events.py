from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, List, Mapping, Optional, Tuple, Union


def freeze(mapping: Optional[Mapping[str, Any]]) -> Mapping[str, Any]:
    return MappingProxyType(copy.deepcopy(dict(mapping or {})))


@dataclass(frozen=True)
class LogEvent:
    level: str
    message: str
    extra: Mapping[str, Any] = field(default_factory=lambda: freeze(None))
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class StepStartEvent:
    step_name: str
    index: int
    total: int
    description: str = ""


@dataclass(frozen=True)
class StepCompleteEvent:
    step_name: str
    index: int
    passed: bool
    duration: float
    measurements: Mapping[str, Any] = field(default_factory=lambda: freeze(None))
    error: Optional[str] = None
    data: Mapping[str, Any] = field(default_factory=lambda: freeze(None))


@dataclass(frozen=True)
class SequenceCompleteEvent:
    overall_pass: bool
    duration: float
    steps: Tuple[Mapping[str, Any], ...]
    measurements: Mapping[str, Any]
    error: Optional[str] = None


@dataclass(frozen=True)
class MeasurementEvent:
    name: str
    value: Any
    unit: str = ""
    passed: Optional[bool] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step_name: Optional[str] = None


@dataclass(frozen=True)
class ErrorEvent:
    code: str
    message: str
    step: Optional[str] = None
    recoverable: bool = False


@dataclass(frozen=True)
class StatusEvent:
    status: str
    progress: float
    current_step: Optional[str] = None
    message: str = ""


@dataclass(frozen=True)
class InputRequestEvent:
    request_id: str
    prompt: str
    input_type: str = "confirm"
    options: Tuple[str, ...] = ()
    default: Any = None
    timeout: Optional[float] = None


SdkEvent = Union[
    LogEvent,
    StepStartEvent,
    StepCompleteEvent,
    SequenceCompleteEvent,
    MeasurementEvent,
    ErrorEvent,
    StatusEvent,
    InputRequestEvent,
]


@dataclass(frozen=True)
class LogRecord:
    timestamp: datetime
    level: str
    message: str
    source: str


def freeze_steps(steps: List[Mapping[str, Any]]) -> Tuple[Mapping[str, Any], ...]:
    return tuple(freeze(step) for step in steps)
