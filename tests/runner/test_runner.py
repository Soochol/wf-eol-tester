from __future__ import annotations

from typing import Any, List

import pytest
from loguru import logger
from PySide6.QtCore import QCoreApplication, QThread

import eol_tester.hardware_adapter as hardware_adapter
from eol_ui.progress import Phase, ProgressState, StageStatus
from eol_ui.runner import (
    LogRecord,
    RunnerBusyError,
    RunOutcome,
    RunRequest,
    SequenceRunner,
    StepStartEvent,
    Verdict,
)

pytestmark = pytest.mark.usefixtures("mock_hardware", "fast_profiles", "tmp_results")

REQUEST = RunRequest(serial_number="SN1", wip_id="W1", parameters={"test_profile": "default"})
RUN_TIMEOUT_MS = 60_000


class Capture:
    def __init__(self, runner: SequenceRunner) -> None:
        self.events: List[Any] = []
        self.logs: List[LogRecord] = []
        self.progress: List[ProgressState] = []
        self.slot_threads: List[QThread] = []
        runner.event.connect(lambda e: self._record(self.events, e))
        runner.log.connect(lambda r: self._record(self.logs, r))
        runner.progress.connect(lambda p: self._record(self.progress, p))

    def _record(self, bucket: List[Any], item: Any) -> None:
        self.slot_threads.append(QThread.currentThread())
        bucket.append(item)

    def messages(self) -> List[str]:
        return [record.message for record in self.logs]


def run_to_end(qtbot, runner: SequenceRunner, request: RunRequest = REQUEST) -> RunOutcome:
    with qtbot.waitSignal(runner.finished, timeout=RUN_TIMEOUT_MS) as blocker:
        runner.start(request)
    outcome = blocker.args[0]
    assert isinstance(outcome, RunOutcome)
    assert runner.wait(5)
    return outcome


def abort_on_log(runner: SequenceRunner, marker: str) -> None:
    def watch(record: LogRecord) -> None:
        if marker in record.message and not runner.abort_requested:
            runner.request_abort()

    runner.log.connect(watch)


def test_runner_mock_pass(qtbot):
    runner = SequenceRunner()
    capture = Capture(runner)
    finished_threads: List[QThread] = []
    runner.finished.connect(lambda _: finished_threads.append(QThread.currentThread()))

    outcome = run_to_end(qtbot, runner)

    assert outcome.verdict is Verdict.PASS
    assert len(outcome.measurements) == 2
    assert {(m.temperature, m.position) for m in outcome.measurements} == {
        (38.0, 20000.0),
        (52.0, 20000.0),
    }
    assert all(m.passed for m in outcome.measurements)
    assert capture.logs
    assert capture.progress[-1].percent == 100.0
    assert any(path.suffix == ".json" for path in outcome.result_files)
    assert outcome.results_dir is not None
    assert (outcome.serial_number, outcome.wip_id) == ("SN1", "W1")
    assert all(outcome.stages[name].passed for name in ("setup", "force_test", "teardown"))

    main_thread = QCoreApplication.instance().thread()
    assert capture.slot_threads and finished_threads
    assert all(thread == main_thread for thread in capture.slot_threads + finished_threads)
    assert not runner.is_running


def test_runner_abort_during_force_test(qtbot):
    runner = SequenceRunner()
    capture = Capture(runner)
    abort_on_log(runner, "Measuring at position")

    outcome = run_to_end(qtbot, runner)

    assert outcome.verdict is Verdict.ABORTED
    assert outcome.abort_requested
    assert outcome.stages["teardown"].passed
    assert not any("Setting temperature to 52.0C" in text for text in capture.messages())
    assert outcome.result_files == ()


def test_runner_abort_before_force_test(qtbot):
    runner = SequenceRunner()
    capture = Capture(runner)
    abort_on_log(runner, "Waiting for MCU boot complete signal")

    outcome = run_to_end(qtbot, runner)

    assert outcome.verdict is Verdict.ABORTED
    assert "teardown" in outcome.stages
    assert not any(
        isinstance(e, StepStartEvent) and e.step_name == "force_test" for e in capture.events
    )
    assert "force_test" not in outcome.stages
    assert not any("Setting temperature to" in text for text in capture.messages())
    assert not outcome.stages["setup"].passed


def test_runner_setup_error(qtbot, monkeypatch):
    real_factory = hardware_adapter.create_standalone_hardware_adapter

    def failing_factory(**kwargs: Any):
        adapter = real_factory(**kwargs)

        async def connect() -> None:
            raise ConnectionError("mock device unreachable")

        adapter.connect = connect
        return adapter

    monkeypatch.setattr(hardware_adapter, "create_standalone_hardware_adapter", failing_factory)
    runner = SequenceRunner()

    outcome = run_to_end(qtbot, runner)

    assert outcome.verdict is Verdict.ERROR
    assert outcome.error
    assert "mock device unreachable" in outcome.error
    assert not outcome.stages["setup"].passed
    assert outcome.measurements == ()


def test_runner_rejects_second_start(qtbot):
    runner = SequenceRunner()

    with qtbot.waitSignal(runner.finished, timeout=RUN_TIMEOUT_MS) as blocker:
        runner.start(REQUEST)
        assert runner.is_running
        with pytest.raises(RunnerBusyError):
            runner.start(REQUEST)

    assert blocker.args[0].verdict is Verdict.PASS
    assert not runner.is_running


def test_runner_abort_at_end_of_setup(qtbot):
    runner = SequenceRunner()
    bypassed: List[str] = []

    def watch(record: LogRecord) -> None:
        if "Temperature verification bypassed" in record.message:
            bypassed.append(record.message)
            if len(bypassed) == 2:
                runner.request_abort()

    runner.log.connect(watch)

    outcome = run_to_end(qtbot, runner)

    assert outcome.verdict is Verdict.ABORTED
    assert outcome.stages["setup"].passed
    assert outcome.stages["teardown"].passed
    final = runner.progress_state()
    assert final.phase is Phase.DONE
    assert StageStatus.RUNNING not in {stage.status for stage in final.stages.values()}


def test_runner_teardown_failure_does_not_report_power_off(qtbot, monkeypatch):
    real_factory = hardware_adapter.create_standalone_hardware_adapter

    def factory(**kwargs: Any):
        adapter = real_factory(**kwargs)

        async def teardown_test() -> None:
            raise RuntimeError("power stuck")

        adapter.teardown_test = teardown_test
        return adapter

    monkeypatch.setattr(hardware_adapter, "create_standalone_hardware_adapter", factory)
    runner = SequenceRunner()

    outcome = run_to_end(qtbot, runner)

    assert outcome.verdict is Verdict.ERROR
    final = runner.progress_state()
    assert final.stages[Phase.TEARDOWN].status is StageStatus.FAILED
    assert final.power_on is not False


def test_runner_finishes_when_loguru_handlers_are_removed_mid_run(qtbot):
    runner = SequenceRunner()
    removed: List[bool] = []

    def remove_handlers(record: LogRecord) -> None:
        if "Measuring at position" in record.message and not removed:
            removed.append(True)
            logger.remove()

    runner.log.connect(remove_handlers)

    outcome = run_to_end(qtbot, runner)

    assert removed
    assert outcome.verdict is Verdict.PASS
    assert not runner.is_running
