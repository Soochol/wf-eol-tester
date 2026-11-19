from __future__ import annotations

import asyncio
import threading
from datetime import datetime
from functools import partial
from typing import Any, Dict, Optional

from loguru import logger
from PySide6.QtCore import QObject, Qt, Signal
from station_service_sdk import ExecutionContext
from station_service_sdk.core.exceptions import AbortError

from eol_tester import EOLForceTestSequence
from eol_ui.progress import ProgressTracker

from .events import LogEvent, LogRecord, SdkEvent, SequenceCompleteEvent, StatusEvent, StepCompleteEvent
from .models import RunOutcome, RunRequest, build_outcome
from .qt_output import QtOutputStrategy

_SDK_SOURCE = "sdk"


class RunnerBusyError(RuntimeError):
    pass


class SequenceRunner(QObject):
    event = Signal(object)
    log = Signal(object)
    progress = Signal(object)
    finished = Signal(object)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._strategy: Optional[QtOutputStrategy] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sequence: Optional[EOLForceTestSequence] = None
        self._abort_requested = False
        self._tracker = ProgressTracker()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def abort_requested(self) -> bool:
        return self._abort_requested

    def progress_state(self):
        return self._tracker.snapshot()

    def start(self, request: RunRequest) -> None:
        with self._lock:
            if self._running:
                raise RunnerBusyError("a sequence is already running")
            self._running = True
            self._abort_requested = False
            self._loop = None
            self._sequence = None

        self._tracker = ProgressTracker()
        self.progress.emit(self._tracker.snapshot())

        strategy = self._strategy = QtOutputStrategy()
        strategy.inbox.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)
        sink_id = logger.add(partial(self._forward_log, strategy), level="DEBUG")
        self._thread = threading.Thread(
            target=self._work,
            args=(request, strategy, sink_id),
            name="eol-sequence-runner",
            daemon=True,
        )
        self._thread.start()

    def request_abort(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._abort_requested = True
            loop, sequence = self._loop, self._sequence
        if loop is not None and sequence is not None:
            self._schedule_abort(loop, sequence)

    def wait(self, timeout: Optional[float] = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _schedule_abort(
        self, loop: asyncio.AbstractEventLoop, sequence: EOLForceTestSequence
    ) -> None:
        try:
            loop.call_soon_threadsafe(self._abort_sequence, sequence)
        except RuntimeError:
            pass

    @staticmethod
    def _abort_sequence(sequence: EOLForceTestSequence) -> None:
        try:
            sequence.abort()
        except AbortError:
            pass

    @staticmethod
    def _forward_log(strategy: QtOutputStrategy, message: Any) -> None:
        record = message.record
        strategy.post(
            LogRecord(
                timestamp=record["time"].replace(tzinfo=None),
                level=record["level"].name,
                message=record["message"],
                source=record["name"] or "",
            )
        )

    def _work(self, request: RunRequest, strategy: QtOutputStrategy, sink_id: int) -> None:
        started_at = datetime.now()
        loop = asyncio.new_event_loop()
        result: Optional[Dict[str, Any]] = None
        failure: Optional[BaseException] = None
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self._execute(loop, request, strategy))
        except BaseException as exc:
            failure = exc
        finally:
            self._remove_sink(sink_id)
            loop.close()
        with self._lock:
            abort_requested = self._abort_requested
        outcome = build_outcome(
            request,
            result,
            failure,
            strategy.recorded,
            abort_requested,
            started_at,
            datetime.now(),
            strategy.status_times,
        )
        strategy.post(outcome)

    @staticmethod
    def _remove_sink(sink_id: int) -> None:
        try:
            logger.remove(sink_id)
        except ValueError:
            pass

    async def _execute(
        self, loop: asyncio.AbstractEventLoop, request: RunRequest, strategy: QtOutputStrategy
    ) -> Dict[str, Any]:
        sequence = EOLForceTestSequence(
            ExecutionContext(serial_number=request.serial_number, wip_id=request.wip_id),
            parameters=dict(request.parameters),
            output_strategy=strategy,
        )
        with self._lock:
            self._loop, self._sequence = loop, sequence
            abort_pending = self._abort_requested
        if abort_pending:
            self._abort_sequence(sequence)
        return await sequence._execute()

    def _dispatch(self, item: object) -> None:
        if isinstance(item, RunOutcome):
            self._finish(item)
        elif isinstance(item, LogRecord):
            self._publish_log(item)
        else:
            self._publish_event(item)

    def _publish_event(self, event: SdkEvent) -> None:
        self.event.emit(event)
        changed = False
        if isinstance(event, LogEvent):
            record = LogRecord(event.timestamp, event.level.upper(), event.message, _SDK_SOURCE)
            self._publish_log(record)
        elif isinstance(event, StatusEvent):
            changed = self._tracker.on_status(event.status)
        elif isinstance(event, StepCompleteEvent):
            changed = self._tracker.on_step_complete(event.step_name, event.passed, event.duration)
        elif isinstance(event, SequenceCompleteEvent):
            changed = self._tracker.on_sequence_complete()
        if changed:
            self.progress.emit(self._tracker.snapshot())

    def _publish_log(self, record: LogRecord) -> None:
        self.log.emit(record)
        if self._tracker.on_log(record.message):
            self.progress.emit(self._tracker.snapshot())

    def _finish(self, outcome: RunOutcome) -> None:
        thread = self._thread
        if thread is not None:
            thread.join()
        with self._lock:
            self._running = False
            self._loop = None
            self._sequence = None
            self._strategy = None
        self.finished.emit(outcome)
