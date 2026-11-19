"""LMAMCU 냉각 대기 시간 시험. 직렬 포트를 열지 않고 대기 함수를 가짜로 바꾼다."""

import pytest

from eol_tester.hardware.real import lma_mcu
from eol_tester.hardware.real.lma_mcu import LMAMCU


class FakeSerial:
    is_open = True

    def __init__(self):
        self.written = []

    def write(self, data):
        self.written.append(data)


def _packet(cmd):
    return bytes([0xFF, 0xFF, cmd, 0x00, 0xFE, 0xFE])


def _make_mcu(timeout_cmds=()):
    """timeout_cmds에 든 cmd는 None(시간 초과)을, 나머지는 맞는 패킷을 돌려준다."""
    mcu = LMAMCU("FAKE")
    mcu._is_connected = True
    mcu.serial_conn = FakeSerial()
    calls = []

    async def fake_wait(timeout, expected_cmd):
        calls.append((timeout, expected_cmd))
        if expected_cmd in timeout_cmds:
            return None
        return _packet(expected_cmd)

    mcu._wait_for_additional_response = fake_wait
    return mcu, calls


async def test_standby_cooling_waits_cooling_timeout():
    mcu, calls = _make_mcu()

    await mcu.start_standby_cooling()

    cooling = [c for c in calls if c[1] == 0x0C]
    assert len(cooling) == 1
    assert cooling[0][0] == 60.0
    assert cooling[0][0] == lma_mcu.COOLING_COMPLETE_TIMEOUT_S
    assert mcu.get_all_timing_data()["total_cooling_count"] == 1


async def test_set_cooling_temperature_waits_cooling_timeout():
    mcu, calls = _make_mcu()

    await mcu.set_cooling_temperature(38.0)

    cooling = [c for c in calls if c[1] == 0x0D]
    assert len(cooling) == 1
    assert cooling[0][0] == 60.0


async def test_standby_cooling_timeout_retries_with_cooling_timeout():
    mcu, calls = _make_mcu(timeout_cmds={0x0C})

    with pytest.raises(RuntimeError) as exc:
        await mcu.start_standby_cooling()

    msg = str(exc.value)
    assert "Standby cooling start failed after 3 attempts" in msg
    assert "Cooling complete signal not received within timeout" in msg
    cooling = [c for c in calls if c[1] == 0x0C]
    assert len(cooling) == 3
    assert all(c[0] == 60.0 for c in cooling)
