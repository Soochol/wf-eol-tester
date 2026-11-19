from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from .events import (
    ErrorEvent,
    InputRequestEvent,
    LogEvent,
    MeasurementEvent,
    SdkEvent,
    SequenceCompleteEvent,
    StatusEvent,
    StepCompleteEvent,
    StepStartEvent,
    freeze,
    freeze_steps,
)


class QtOutputStrategy(QObject):
    sdk_event = Signal(object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._recorded: List[SdkEvent] = []
        self._input_defaults: Dict[str, Any] = {}

    @property
    def recorded(self) -> tuple[SdkEvent, ...]:
        return tuple(self._recorded)

    def _publish(self, event: SdkEvent) -> None:
        self._recorded.append(event)
        self.sdk_event.emit(event)

    def log(self, level: str, message: str, **extra: Any) -> None:
        self._publish(LogEvent(level=level, message=message, extra=freeze(extra)))

    def step_start(self, step_name: str, index: int, total: int, description: str = "") -> None:
        self._publish(StepStartEvent(step_name, index, total, description))

    def step_complete(
        self,
        step_name: str,
        index: int,
        passed: bool,
        duration: float,
        measurements: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._publish(
            StepCompleteEvent(
                step_name=step_name,
                index=index,
                passed=passed,
                duration=duration,
                measurements=freeze(measurements),
                error=error,
                data=freeze(data),
            )
        )

    def sequence_complete(
        self,
        overall_pass: bool,
        duration: float,
        steps: List[Dict[str, Any]],
        measurements: Dict[str, Any],
        error: Optional[str] = None,
    ) -> None:
        self._publish(
            SequenceCompleteEvent(
                overall_pass=overall_pass,
                duration=duration,
                steps=freeze_steps(steps),
                measurements=freeze(measurements),
                error=error,
            )
        )

    def measurement(
        self,
        name: str,
        value: Any,
        unit: str = "",
        passed: Optional[bool] = None,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
        step_name: Optional[str] = None,
    ) -> None:
        self._publish(MeasurementEvent(name, value, unit, passed, min_value, max_value, step_name))

    def error(
        self,
        code: str,
        message: str,
        step: Optional[str] = None,
        recoverable: bool = False,
    ) -> None:
        self._publish(ErrorEvent(code, message, step, recoverable))

    def status(
        self,
        status: str,
        progress: float,
        current_step: Optional[str] = None,
        message: str = "",
    ) -> None:
        self._publish(StatusEvent(status, progress, current_step, message))

    def input_request(
        self,
        request_id: str,
        prompt: str,
        input_type: str = "confirm",
        options: Optional[List[str]] = None,
        default: Any = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._input_defaults[request_id] = default
        self._publish(
            InputRequestEvent(request_id, prompt, input_type, tuple(options or ()), default, timeout)
        )

    def wait_for_input(self, request_id: str, timeout: float = 300) -> Any:
        return self._input_defaults.get(request_id)
