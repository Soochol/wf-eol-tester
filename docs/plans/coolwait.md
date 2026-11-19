# LMA 냉각 완료 신호 대기 시간 40초 → 60초 플랜

- 작성일: 2026-11-19
- 이 문서는 승인 시점의 기록이며 구현 중 바뀐 것은 반영하지 않는다.

## 풀려는 문제

실장비(DUT + 배터리 전원)에서 짧은 full test를 돌렸다. setup의 LMA 대기 냉각(52℃ → 38℃)에서 냉각 완료 신호(CMD 0x0C)가 40초 안에 오지 않았다. 3회 재시도 뒤 `SETUP_ERROR`로 끝났다.

실행 로그 `/tmp/claude-1000/-home-dev-code-eol-tester/c2f57296-a9f7-485f-9cbf-a53e02778de7/scratchpad/hw/full_run1.log`의 흐름은 다음과 같다.

1. 16:05:37 `PC -> MCU: FFFF0800FEFE (Cooling: 52.0°C → 38.0°C)`
2. 16:06:17, 16:06:58, 16:07:39 `Cooling complete signal not received within timeout` (40초 간격으로 세 번)
3. `SETUP_ERROR`: `Standby cooling start failed after 3 attempts: Cooling complete signal not received within timeout`

사용자는 이 장비가 40초 안에 38℃까지 식지 못한다고 보고, 대기 시간을 60초로 늘려 달라고 했다.

## 확인한 사실 (main 720732c)

- **0x0C 대기.** `LMAMCU.start_standby_cooling`(`eol_tester/hardware/real/lma_mcu.py`)은 ACK(0x08)를 받은 뒤 `_wait_for_additional_response(timeout=40.0, expected_cmd=0x0C)`로 냉각 완료를 기다린다. 실패하면 test mode 1을 보내고 최대 3회 다시 시도한다. facade는 `setup_test`의 대기 냉각과 teardown 쪽 대기 냉각, 두 곳에서 이 함수를 부른다(`eol_tester/services/hardware_facade.py`).
- **0x0D 대기.** `LMAMCU.set_cooling_temperature`는 ACK(0x06)를 받은 뒤 `_wait_for_additional_response(timeout=40.0, expected_cmd=0x0D)`로 "냉각 목표 온도 도달" 신호를 기다린다. 실패 문구는 `Cooling temperature reached signal not received within timeout`이다. `MCUService` 인터페이스에 없는 메서드이고, 저장소 안에 호출하는 곳이 없다.
- **다른 온도 대기.** 가열 쪽 도달 신호(0x0B, `set_operating_temperature`·`start_standby_heating`)는 10초 제한이다. 이번 증상과 무관하다.
- **바깥 제한.** facade는 `start_standby_cooling`을 시간 제한 없이 `await`한다. 프로파일 `timeout_seconds`는 부팅 대기에만 걸린다. 그래서 MCU 쪽 값만 바꾸면 된다.
- **기존 시험.** `lma_mcu.py`를 직접 시험하는 파일이 없다. `tests/seq/test_sequence.py`의 가짜 MCU는 `start_standby_cooling`을 흉내 낼 뿐 `LMAMCU`를 쓰지 않는다.
- **진행 중인 작업.** 같은 탭 계획의 `ui-segfault`가 `eol_ui/**`, `tests/conftest.py`, `tests/ui/**`, `tests/runner/**`, `tests/settings/**`를 고친다. `errmsg-ui`는 `ui-segfault` 뒤에서 대기 중이다. 이 플랜의 파일과 겹치지 않는다.

## 확정된 결정 (사용자)

1. 냉각 완료(0x0C) 대기 시간을 60초로 늘린다. 원본 eol_tester 코드 수정을 승인했다.
2. 값은 모듈 상수 하나로 둔다. 설정 파일로 빼지 않는다.
3. 가짜 MCU로 대기 시간이 60초로 전달되는지 확인하는 시험을 더한다. 시험은 실제로 60초를 기다리지 않는다.
4. 범위는 `lma_mcu.py`와 그 시험이다. 다른 원본 동작은 바꾸지 않는다. 권한은 기본 권한이고 저장소는 chute로 병합한다.

## 스스로 정한 결정과 이유

1. **0x0D 대기도 같은 상수로 60초로 맞춘다.** 두 대기 모두 MCU가 냉각해 목표 온도에 닿았다는 신호를 기다리고, 지금 같은 40초를 쓴다. 냉각 속도라는 같은 물리 조건에 묶인 값이다. 하나만 바꾸면 같은 장비에서 `set_cooling_temperature`를 쓰는 순간 같은 실패가 난다. 지금 호출하는 곳이 없어 실제 동작은 바뀌지 않는다. 작업자는 코드를 다시 읽어 이 판단을 확인하고 보고서에 이유를 적는다. 확인해 보니 성격이 다르면 0x0D는 40초로 두고 그 이유를 보고서에 적는다.
2. **상수 이름은 `COOLING_COMPLETE_TIMEOUT_S = 60.0`이다.** 파일 위쪽 `TEMP_SCALE_FACTOR`, `DEFAULT_TIMEOUT` 옆에 둔다. 두 호출은 이 상수를 쓴다. 가열 대기(10초), ACK 대기(`self._timeout`), test mode 재시도 대기(2초)는 바꾸지 않는다.
3. **재시도 횟수(3회)와 실패 문구는 그대로 둔다.** 최악의 setup 냉각 대기는 약 3분(60초 × 3회 + 재시도 사이 대기)으로 늘어난다. 바깥 제한이 없어 다른 곳을 고칠 필요는 없다.
4. **시험은 새 파일 `tests/hardware/test_lma_mcu.py`에 둔다.** 진행 중인 `ui-segfault`의 경로와 겹치지 않는다. 직렬 포트를 열지 않는다. 대신 `serial_conn`을 가짜 객체로 넣고, `_wait_for_additional_response`를 호출 인자를 기록하는 가짜로 바꾼다.
5. **작업 하나로 끝낸다.** 상수 하나와 시험 파일 하나라서 나눌 이유가 없다.

## 작업

| 작업 | 내용 | 순서 | 방식 | 방식 이유 |
|---|---|---|---|---|
| `coolwait` | 냉각 도달 대기(0x0C, 0x0D)를 모듈 상수 60초로 바꾸고 가짜 MCU 시험을 더한다 | 바로 시작(병렬) | basic | 상수 하나 바꾸는 작은 수정과 시험. 상태 저장·동시성·머지 판정 코드가 아니다 |

순차로 둔 작업이 없다. 진행 중인 `ui-segfault`, `errmsg-ui`와 고치는 파일이 겹치지 않는다.

## 범위 밖

- 대기 시간의 설정 파일화(프로파일·하드웨어 설정에 값 추가).
- 가열 도달 대기(0x0B, 10초), ACK 대기, 재시도 횟수, 실패 문구 변경.
- `hardware_facade.py`, `sequence.py`, `MockMCU` 등 다른 원본 코드.
- 실장비에서 60초면 충분한지 확인하는 일. 이 플랜의 시험은 값이 전달되는지만 본다.

## 사용자가 정해야 하는 결정

없다. 다만 실장비에서 60초로도 실패하면 냉각 성능 문제인지 신호 문제인지 따로 봐야 한다. 이 플랜은 그 확인을 하지 않는다.
