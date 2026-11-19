# setup 실패 에러 메시지 보강 플랜

- 작성일: 2026-11-19
- 이 문서는 승인 시점의 기록이며 구현 중 바뀐 것은 반영하지 않는다.
- 앞선 플랜: `docs/plans/followup.md`

## 풀려는 문제

실장비(Windows 하드웨어 PC)에서 DUT 없이 시퀀스를 돌려 MCU 부팅 대기 시간 초과를 확인했다. 결과 에러가 `Setup failed: Setup failed: `로 나왔고, UI ERROR 화면에도 이유가 보이지 않았다.

실행 로그(`timeout_seconds=10`)의 흐름은 다음과 같다.

1. `Waiting for MCU boot complete signal...`
2. 10초 뒤 `error {"code": "SETUP_ERROR", "message": ""}`
3. setup 단계 `error: "Setup failed: "`
4. `sequence_complete` `error: "Setup failed: Setup failed: "`

## 확인한 사실 (main 19430e0)

- **원인.** `eol_tester/services/hardware_facade.py`의 `_wait_boot_complete`는 시간 초과 때 메시지 없는 `asyncio.TimeoutError()`를 올린다. 이 함수는 seq-import 작업이 `check_abort`를 연결하며 만들었다. `EOLForceTestSequence.setup()`(`eol_tester/sequence.py:172-175`)은 이 예외를 `emit_error("SETUP_ERROR", str(e))`로 내보내고 `SetupError(f"Setup failed: {e}")`로 감싼다. `str(e)`가 빈 문자열이라 이유가 사라진다. SDK가 한 번 더 `Setup failed: `를 붙인다.
- **실제 MCU 드라이버.** `LMAMCU.wait_boot_complete`는 자체 60초 제한이 있고, 넘으면 `RuntimeError("MCU boot complete signal timeout")`를 올린다. 프로파일 `timeout_seconds`(기본 60)가 그보다 짧으면 facade의 시간 초과가 먼저 난다. 실행 로그가 이 경우다.
- **UI가 받는 정보.** `build_outcome`(`eol_ui/runner/models.py`)은 `result["error"]`, `force_test` 단계 error, 워커 예외(`type(failure).__name__: failure`) 순으로 에러 문자열을 고른다. 시퀀스가 setup 예외를 잡아 결과로 돌려주므로 이 경우 워커 예외는 없다. 예외 종류 이름은 UI까지 오지 않는다. UI가 받는 것은 `ErrorEvent(code="SETUP_ERROR", message="")`, setup 단계 error 문자열, 로그다. 결과 화면 `ResultPage._detail_text`는 ERROR일 때 `outcome.error`를 그대로 보인다.
- **기존 시험.** `tests/seq/test_sequence.py::test_boot_wait_timeout_unchanged`는 시간 초과 때 `asyncio.TimeoutError`와 부팅 대기 취소만 확인한다. `tests/runner/test_runner.py::test_runner_setup_error`는 연결 실패 메시지가 `outcome.error`에 들어가는지 본다. 결과 화면의 ERROR 표시 시험은 없다.
- **진행 중인 작업.** 같은 탭 계획의 `ui-segfault`가 `eol_ui/**`, `tests/conftest.py`, `tests/ui/**`, `tests/runner/**`, `tests/settings/**`를 고칠 수 있다.

## 확정된 결정 (사용자)

1. 수정을 승인했다.
2. `_wait_boot_complete`의 시간 초과 예외에 이유를 담는다. 앞서 승인한 `check_abort` 연결로 바꾼 부팅 대기 함수의 후속 수정이다. 다른 원본 동작은 바꾸지 않는다.
3. UI는 에러 문자열이 비었거나 `Setup failed: `처럼 이유가 없으면, 받을 수 있는 정보를 대신 보인다. 방법은 작업자가 정한다.
4. 시험: 부팅 대기 시간 초과 때 에러 문구에 이유가 들어가는지(시퀀스 시험), UI ERROR 화면에 이유가 보이는지.
5. 권한은 기본 권한이다. 저장소는 chute로 병합한다.

## 스스로 정한 결정과 이유

1. **두 작업으로 나눈다.** 실제 증상은 시퀀스 쪽 한 줄 수정으로 풀린다. 이 수정은 `ui-segfault`와 겹치는 파일이 없어 바로 병렬로 진행한다. UI 보강은 `eol_ui/**`를 건드리므로 `ui-segfault` 뒤로 둔다.
2. **시간 초과 예외 종류는 `asyncio.TimeoutError` 그대로 둔다.** 메시지만 더한다. 예외 종류를 바꾸면 원본 동작이 바뀐다. 기존 시험도 이 종류를 확인한다.
3. **문구는 제한 시간을 담는다.** 예: `MCU boot complete signal not received within 10.0s`. 작업자가 다듬어도 되지만 "MCU boot complete"와 제한 시간 숫자는 들어가야 한다.
4. **UI 보강은 "이유 없음"을 판정해 대체 정보를 붙이는 방식으로 한다.** 예외 종류 이름은 UI까지 오지 않으므로, 대체 정보는 `ErrorEvent`의 코드(`SETUP_ERROR` 등)와 "이유가 전달되지 않았다"는 안내가 중심이 된다. 워커 예외가 있으면 그 종류 이름을 쓴다. 원본 `sequence.py`의 `emit_error` 문구는 고치지 않는다(결정 2의 범위 밖).
5. **`errmsg-ui`는 `errmsg-seq` 뒤에도 둔다.** UI 시험에서 부팅 대기 시간 초과를 끝까지 돌려 화면에 이유가 보이는지 확인하려면 시퀀스 수정이 먼저 들어가야 한다.

## 작업

| 작업 | 내용 | 순서 | 방식 | 방식 이유 |
|---|---|---|---|---|
| `errmsg-seq` | `_wait_boot_complete` 시간 초과 예외에 이유를 담고 시퀀스 시험을 더한다 | 바로 시작(병렬) | basic | 원본 함수 한 곳의 작은 버그 수정과 시험 |
| `errmsg-ui` | 이유 없는 에러일 때 runner/결과 화면이 대체 정보를 보이게 하고 시험을 더한다 | `ui-segfault`, `errmsg-seq` 뒤 | basic | 결과 표시 문구와 판정의 작은 수정 |

순차로 둔 이유:

- `errmsg-ui` → `ui-segfault` 뒤: `ui-segfault`의 범위가 `eol_ui/**`와 `tests/ui/**`, `tests/runner/**` 전체라서 runner와 결과 화면 파일이 겹칠 수 있다.
- `errmsg-ui` → `errmsg-seq` 뒤: UI 시험이 시퀀스 수정의 결과(이유가 담긴 시간 초과 문구)를 쓴다.

## 범위 밖

- 원본 `sequence.py`의 `emit_error`/`SetupError` 문구와 감싸기 방식(`Setup failed: Setup failed: ` 중복 접두어 포함).
- 실제 MCU 드라이버(`lma_mcu.py`)의 자체 60초 제한.
- 부팅 대기 timeout 때 취소 중 예외가 `TimeoutError`로 바뀌는 문제(followup 플랜에서 하지 않기로 한 것).
- 그 밖의 원본 동작 변경, ERROR 화면 배치 변경.

## 사용자가 정해야 하는 결정

- 검증을 약하게 하는 작업은 없다.
- `ui-segfault`가 성공 조건 4(코드 변경 없이 PR 없이 막힘)로 끝나면 `errmsg-ui`의 선행 작업이 병합되지 않는다. 그때 `errmsg-ui`를 순서에서 풀어 시작할지 정해야 한다.
