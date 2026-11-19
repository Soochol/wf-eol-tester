"""LMAMCU 냉각 대기 시간 시험. 직렬 포트를 열지 않고 대기 함수를 가짜로 바꾼다."""

import asyncio

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
    assert cooling[0][0] == 120.0
    assert cooling[0][0] == lma_mcu.COOLING_COMPLETE_TIMEOUT_S
    assert mcu.get_all_timing_data()["total_cooling_count"] == 1


async def test_set_cooling_temperature_waits_cooling_timeout():
    mcu, calls = _make_mcu()

    await mcu.set_cooling_temperature(38.0)

    cooling = [c for c in calls if c[1] == 0x0D]
    assert len(cooling) == 1
    assert cooling[0][0] == 120.0


async def test_standby_cooling_timeout_retries_with_cooling_timeout():
    mcu, calls = _make_mcu(timeout_cmds={0x0C})

    with pytest.raises(RuntimeError) as exc:
        await mcu.start_standby_cooling()

    msg = str(exc.value)
    assert "Standby cooling start failed after 3 attempts" in msg
    assert "Cooling complete signal not received within timeout" in msg
    cooling = [c for c in calls if c[1] == 0x0C]
    assert len(cooling) == 3
    assert all(c[0] == 120.0 for c in cooling)


async def test_heating_waits_stay_10_seconds():
    mcu, calls = _make_mcu()
    await mcu.start_standby_heating(50.0, 38.0)
    await mcu.set_operating_temperature(50.0)

    heating = [c for c in calls if c[1] == 0x0B]
    assert len(heating) == 2
    assert all(c[0] == 10.0 for c in heating)


class ReadSerial:
    """read 호출마다 chunks를 하나씩 돌려주는 가짜 시리얼."""

    is_open = True

    def __init__(self, chunks=()):
        self.chunks = list(chunks)
        self.written = []

    @property
    def in_waiting(self):
        return len(self.chunks[0]) if self.chunks else 0

    def read(self, n):
        return self.chunks.pop(0)

    def write(self, data):
        self.written.append(data)
        if self.on_write:
            self.chunks.extend(self.on_write)
            self.on_write = None

    on_write = None

    def close(self):
        self.is_open = False


def _real_mcu(chunks=()):
    mcu = LMAMCU("FAKE")
    mcu._is_connected = True
    mcu.serial_conn = ReadSerial(chunks)
    return mcu


async def test_ack_and_completion_in_one_read():
    mcu = _real_mcu([_packet(0x08) + _packet(0x0C)])

    ack = await mcu._wait_for_additional_response(timeout=0.2, expected_cmd=0x08)
    done = await mcu._wait_for_additional_response(timeout=0.2, expected_cmd=0x0C)

    assert ack == _packet(0x08)
    assert done == _packet(0x0C)


async def test_start_standby_cooling_with_combined_read():
    mcu = _real_mcu()
    mcu.serial_conn.on_write = [_packet(0x08) + _packet(0x0C)]

    await asyncio.wait_for(mcu.start_standby_cooling(), timeout=2.0)

    data = mcu.get_all_timing_data()
    assert data["total_cooling_count"] == 1
    assert mcu._cooling_timing_history[0]["attempt_number"] == 1


async def test_unexpected_frame_is_kept():
    mcu = _real_mcu([_packet(0x0B) + _packet(0x0C)])

    first = await mcu._wait_for_additional_response(timeout=0.2, expected_cmd=0x0C)
    second = await mcu._wait_for_additional_response(timeout=0.2, expected_cmd=0x0B)

    assert first == _packet(0x0C)
    assert second == _packet(0x0B)


async def test_frame_split_across_reads():
    frame = _packet(0x0C)
    mcu = _real_mcu([frame[:3], frame[3:]])

    got = await mcu._wait_for_additional_response(timeout=0.5, expected_cmd=0x0C)

    assert got == frame


async def test_wait_times_out_without_frame():
    mcu = _real_mcu([_packet(0x08)])

    got = await mcu._wait_for_additional_response(timeout=0.1, expected_cmd=0x0C)

    assert got is None


def _stale_mcu():
    mcu = _real_mcu()
    mcu._packet_buffer.append(_packet(0x0C))
    mcu._response_data = b"\xff\xff\x0c"
    return mcu


async def test_disconnect_clears_buffers():
    mcu = _stale_mcu()

    await mcu.disconnect()

    assert mcu._packet_buffer == []
    assert mcu._response_data == b""


async def test_send_packet_sync_clears_buffers():
    mcu = _stale_mcu()

    mcu._send_packet_sync("FFFF0800FEFE", timeout=0.05)

    assert mcu._packet_buffer == []
    assert mcu._response_data == b""
    got = await mcu._wait_for_additional_response(timeout=0.05, expected_cmd=0x0C)
    assert got is None


async def test_connect_clears_buffers(monkeypatch):
    mcu = _stale_mcu()
    monkeypatch.setattr(lma_mcu.serial, "Serial", lambda **kw: ReadSerial())

    await mcu.connect()

    assert mcu._packet_buffer == []
    assert mcu._response_data == b""
