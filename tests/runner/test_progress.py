from __future__ import annotations

import json
from pathlib import Path
from typing import List

from eol_ui.progress import Phase, ProgressState, ProgressTracker, StageStatus

DATA = Path(__file__).parent / "data"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def replay(name: str) -> List[ProgressState]:
    clock = FakeClock()
    tracker = ProgressTracker(clock)
    states = [tracker.snapshot()]
    for line in (DATA / name).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        clock.now = row["t"]
        kind = row["kind"]
        if kind == "log":
            tracker.on_log(row["message"])
        elif kind == "status":
            tracker.on_status(row["status"])
        elif kind == "step_complete":
            tracker.on_step_complete(row["step_name"], row["passed"], row["duration"])
        elif kind == "sequence_complete":
            tracker.on_sequence_complete()
        states.append(tracker.snapshot())
    return states


def distinct(values):
    seen = []
    for value in values:
        if not seen or seen[-1] != value:
            seen.append(value)
    return seen


def test_progress_parser_recorded_log():
    states = replay("mock_run_1rep.jsonl")
    final = states[-1]

    assert distinct(s.phase for s in states) == [
        Phase.SETUP,
        Phase.FORCE_TEST,
        Phase.TEARDOWN,
        Phase.DONE,
    ]
    assert any(
        s.phase is Phase.FORCE_TEST
        and s.stages[Phase.SETUP].status is StageStatus.DONE
        and s.stages[Phase.FORCE_TEST].status is StageStatus.RUNNING
        and s.stages[Phase.TEARDOWN].status is StageStatus.PENDING
        for s in states
    )
    assert all(final.stages[stage].status is StageStatus.DONE for stage in final.stages)
    assert final.stages[Phase.SETUP].duration == 2.511
    assert final.stages[Phase.FORCE_TEST].duration is not None

    assert distinct((s.measurements_done, s.measurements_total) for s in states if s.measurements_total) == [
        (0, 2),
        (1, 2),
        (2, 2),
    ]
    percents = [s.percent for s in states]
    assert percents == sorted(percents)
    assert percents[0] == 0.0
    assert percents[-1] == 100.0
    assert {s.percent for s in states if s.phase is Phase.SETUP} == {0.0}
    assert {s.percent for s in states if s.phase is Phase.TEARDOWN} == {95.0}
    assert {s.percent for s in states if s.phase is Phase.FORCE_TEST} == {10.0, 52.5, 95.0}

    assert final.temperature == (2, 2)
    assert final.position == (1, 1)
    assert final.repetition == (1, 1)
    assert final.last_force == 6.870
    assert final.robot_position == 1000.0
    assert final.mcu_target_temperature == 52.0
    assert final.mcu_actual_temperature is None

    power = [(s.power_voltage, s.power_current, s.power_on) for s in states]
    assert (40.0, 42.0, True) in power
    assert power[-1] == (40.0, 42.0, False)
    assert distinct(s.power_on for s in states) == [None, True, False]

    all_connected = {
        "robot": True,
        "mcu": True,
        "power": True,
        "loadcell": True,
        "digital_io": True,
    }
    assert any(dict(s.devices) == all_connected for s in states)
    assert dict(final.devices) == {}
    assert final.elapsed == 5.39
    assert final.activity == "완료"


def test_progress_parser_remaining_time():
    states = replay("mock_run_1rep.jsonl")
    force_phase = [s for s in states if s.phase is Phase.FORCE_TEST]

    assert all(s.remaining is None for s in force_phase if s.measurements_done == 0)
    first_done = next(s for s in force_phase if s.measurements_done == 1)
    expected = (first_done.elapsed - 2.514) / 1 * 1
    assert abs(first_done.remaining - expected) < 0.05
    assert states[-1].remaining is None


def test_progress_parser_repetitions():
    states = replay("mock_run_2rep.jsonl")
    final = states[-1]

    assert max(s.measurements_total for s in states) == 4
    assert final.measurements_done == 4
    assert distinct(s.repetition for s in states if s.repetition != (0, 0)) == [(1, 2), (2, 2)]
    assert final.repetition == (2, 2)
    assert final.percent == 100.0


def test_progress_parser_ignores_unknown_lines():
    tracker = ProgressTracker(FakeClock())
    before = tracker.snapshot()

    for line in ("MockPower: Output enabled", "Hardware status: not a dict", ""):
        assert tracker.on_log(line) is False
    assert tracker.on_status("paused") is False
    assert tracker.on_step_complete("unknown_step", True, 1.0) is False
    assert tracker.snapshot() == before


def test_progress_parser_reads_verified_temperature():
    tracker = ProgressTracker(FakeClock())

    tracker.on_log("✅ Temperature verified: 51.7C (target 52.0C)")

    assert tracker.snapshot().mcu_actual_temperature == 51.7


def test_progress_parser_setup_failure():
    tracker = ProgressTracker(FakeClock())

    tracker.on_status("setup")
    tracker.on_step_complete("setup", False, 1.5)
    tracker.on_status("teardown")
    tracker.on_step_complete("teardown", True, 0.2)
    tracker.on_sequence_complete()
    final = tracker.snapshot()

    assert final.stages[Phase.SETUP].status is StageStatus.FAILED
    assert final.stages[Phase.FORCE_TEST].status is StageStatus.PENDING
    assert final.stages[Phase.TEARDOWN].status is StageStatus.DONE
    assert final.percent == 100.0


def test_progress_parser_closes_running_stages_when_sequence_completes():
    tracker = ProgressTracker(FakeClock())

    tracker.on_status("setup")
    tracker.on_status("running")
    tracker.on_status("teardown")
    tracker.on_step_complete("teardown", True, 0.2)
    tracker.on_sequence_complete()
    final = tracker.snapshot()

    assert final.stages[Phase.FORCE_TEST].status is StageStatus.FAILED
    assert StageStatus.RUNNING not in {stage.status for stage in final.stages.values()}


def test_progress_parser_failed_teardown_does_not_claim_power_off():
    tracker = ProgressTracker(FakeClock())
    tracker.on_log("Power enabled: 40.0V, 42.0A")

    tracker.on_step_complete("teardown", False, 0.2)

    assert tracker.snapshot().power_on is None


def test_progress_parser_failed_teardown_keeps_confirmed_power_off():
    tracker = ProgressTracker(FakeClock())
    tracker.on_log("Power enabled: 40.0V, 42.0A")
    tracker.on_log("Test teardown complete")

    tracker.on_step_complete("teardown", False, 0.2)

    assert tracker.snapshot().power_on is False


def test_progress_devices_unknown_after_hardware_disconnected():
    tracker = ProgressTracker(FakeClock())

    tracker.on_log("Hardware status: {'robot': True, 'mcu': False}")
    assert dict(tracker.snapshot().devices) == {"robot": True, "mcu": False}

    assert tracker.on_log("Hardware disconnected") is True
    assert dict(tracker.snapshot().devices) == {}
    assert tracker.on_log("Hardware disconnected") is False
