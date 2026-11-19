# PySide6 UI 후속 정리 플랜

- 작성일: 2026-11-19
- 이 문서는 승인 시점의 기록이며 구현 중 바뀐 것은 반영하지 않는다.
- 앞선 플랜: `docs/plans/pyside-ui.md`

## 풀려는 문제

pyside-ui 플랜의 다섯 작업이 모두 병합됐다. 작업 중 "나중에 할 것"으로 미룬 항목이 세 갈래로 남았다.

1. 시험 중 간헐 segfault: 여러 `MainWindow`를 이어 만드는 시험에서 가끔 났고 원인은 확정되지 않았다(ui-run-screen 보고서). chute가 병합마다 `uv sync --frozen && QT_QPA_PLATFORM=offscreen uv run pytest -q`를 돌리므로 이 흔들림은 반송으로 이어진다. 실제 앱의 창·스레드 정리 결함일 수도 있다.
2. 작은 정리 네 건: `build_outcome`의 KeyError, 부팅 대기의 `timeout_seconds=None` TypeError, 중단 검사 지점을 하나씩 구분하지 못하는 시험, 프로파일이 없을 때 시작 버튼.
3. 설정 모델·화면 결함 네 건(ui-settings-screen 보고서 "미해결 사항, 위험" 1~4): 프로파일 저장 때 `stop_on_failure` 손실, 시퀀스 검증기보다 느슨한 범위 검증, 손상된 YAML에서 Mock 스위치 예외, 연결 테스트 중 창 닫기 때 GUI 멈춤.

## 확정된 결정 (사용자)

1. 오케스트레이터가 제안한 후속 항목을 그대로 진행한다.
2. 원본 `eol_tester` 수정은 `services/hardware_facade.py`의 부팅 대기 하나만 한다. `timeout_seconds=None`이면 원본(`wait_for(timeout=None)`)처럼 무제한으로 기다리고, 중단 확인은 유지한다. 앞서 승인한 `check_abort` 연결의 후속 수정이다.
3. 하지 않는 것: 부팅 대기 timeout 때 취소 중 예외가 `TimeoutError`로 바뀌는 문제(실제 MCU 서비스에는 영향 없음), 그 밖의 원본 동작 변경.
4. 권한은 기본 권한이다. 저장소는 chute로 병합한다.

## 확인한 사실 (main 764760f)

- **runner 구조.** `SequenceRunner.start()`는 실행마다 `logger.add`로 loguru sink를 달고 데몬 `threading.Thread`에서 asyncio 루프를 돌린다. 이벤트는 부모 없는 `QtOutputStrategy`와 `_inbox` 시그널을 거쳐 QueuedConnection으로 GUI 스레드에 온다. sink는 워커가 끝날 때 뗀다.
- **창 닫기.** `MainWindow.closeEvent`는 실행 중이면 `event.ignore()`하고 teardown 뒤에 닫는다. 실행 중이 아니면 `HardwarePage.shutdown()`이 `ConnectionTestThread`(부모가 `HardwarePage`인 `QThread`)를 `wait()`로 기다린다.
- **시험 시간.** `QT_QPA_PLATFORM=offscreen uv run pytest -q tests/ui tests/runner`는 60개 통과, 약 2분이 걸렸다(플래너가 이 worktree에서 실행).
- **프로파일이 없을 때.** 원본 `load_test_profile(name)`은 파일이 없으면 `TestConfiguration()` 기본값으로 그 이름의 파일을 만든다. 그래서 프로파일 폴더가 비어 있어도 설정 화면이 시작할 때 `default.yaml`이 생기고, 실행 화면 목록은 `['default']`, 요청은 `{'test_profile': 'default'}`가 된다. 플래너가 빈 tmp 폴더로 `MainWindow`를 띄워 확인했다. ui-run-screen 보고서의 `test_profile: ""` 상황은 설정 화면이 붙기 전의 것이다. 남은 구멍은 시작 뒤에 선택한 프로파일 파일이 사라진 경우다. 이때 시작하면 시퀀스가 그 이름의 파일을 기본값으로 조용히 다시 만든다.
- **`stop_on_failure`.** 시퀀스는 `get_parameter("stop_on_failure", True)`로만 읽고(`sequence.py:79`) 프로파일에서는 읽지 않는다. `_create_test_config_from_profile`은 절마다 아는 키만 `.get`으로 읽으므로 프로파일의 모르는 키는 무시된다.
- **시퀀스 검증기.** `ConfigurationValidator.validate_test_configuration`(async)은 대기 온도 < 활성화 온도, 온도 목록이 0~`upper_temperature`(프로파일 `hardware.upper_temperature`, 기본 80), 스트로크 ≥ `initial_position`, `force_limit_min < force_limit_max`(엄격 부등호) 등을 검사한다. 설정 모델은 manifest 범위와 `force_limit_min ≤ force_limit_max`만 본다.
- **중단 검사 지점.** `setup_test`는 전원 ON 뒤, 부팅 대기 뒤, 테스트 모드 설정 뒤에 검사한다. 부팅 대기 루프와 `set_lma_standby`도 시작할 때 검사하므로, 단계 사이 검사 하나를 지워도 바로 다음 검사가 중단을 잡는다. 차이는 그 사이의 동작(부팅 대기 시작 로그, `set_test_mode` 호출, `Starting LMA standby sequence` 로그)이 일어나느냐뿐이다. force 루프(반복, 온도, 위치 시작)도 같다.

## 스스로 정한 결정과 이유

1. **작업은 셋이다.** 요청의 세 갈래를 각각 한 PR로 나눈다. 작업 2의 4번(프로파일 없을 때 시작 막기)은 실행 화면을 고치고, 작업 3은 설정·하드웨어 화면을 고친다. 같은 화면이 아니므로 합치지 않는다.
2. **segfault 조사를 마지막에 둔다.** 정리 두 작업(`ui-cleanups`, `ui-settings-fixes`)을 먼저 병렬로 하고, `ui-segfault`는 둘 다 병합된 뒤에 한다. 이유는 다음과 같다.
   - segfault의 원인 위치를 모른다. 고칠 범위가 `eol_ui/runner/`, `main_window.py`, `tests/conftest.py`, `tests/ui/`에 걸칠 수 있어 두 작업의 파일과 겹친다.
   - `ui-settings-fixes`가 연결 테스트 스레드의 종료 방식을 바꾼다. 이것은 창·스레드 정리 경로라 segfault 조사가 그 결과 위에서 하는 편이 맞다.
   - 재현이 안 되면 `ui-segfault`는 PR 없이 보고로 끝난다. 이것을 앞에 두면 뒤 작업의 순서가 묶인다.
   - 위험: 두 정리 작업의 병합 때 segfault가 나면 chute가 반송한다. 지금까지 PR #6, #7은 병합됐고 빈도는 낮다(임시 시험 5회 중 2회, tests/ui 10회 이상 통과).
3. **`ui-cleanups`와 `ui-settings-fixes`는 병렬이다.** 고치는 파일이 겹치지 않는다. 실행 화면(`eol_ui/pages/run/**`)과 `tests/ui/test_run_screen.py`는 `ui-cleanups`가, 메인 창·설정·하드웨어 화면과 `tests/ui/test_settings_screen.py`는 `ui-settings-fixes`가 맡는다.
4. **프로파일이 없을 때.** 시작할 때 자동으로 `default.yaml`을 만드는 동작은 원본 로더의 동작이고 목록과 폼에 보이므로 유지한다. 실행 화면은 프로파일 목록이 비었거나, 시작을 누른 때 선택한 프로파일 파일이 없으면 시작하지 않고 이유를 보여 준다. 시작 뒤에 파일이 사라지면 원본이 기본값으로 다시 만들어 실행하는데, 이것을 막는 것이 이 항목의 실제 효과다.
5. **`stop_on_failure` 저장 방식(권장).** 프로파일 `execution.stop_on_failure`에 저장하고 설정 모델은 그 값을 비교 기준으로 읽는다. 시퀀스는 이 키를 프로파일에서 읽지 않으므로, 기준값이 manifest 기본값(true)과 다르면 UI가 실행 `parameters`에 늘 넣는다. 원본은 모르는 키를 무시하므로 원본 변경이 필요 없다. 요청이 방법을 작업자에게 맡겼으므로 지시서에는 권장으로 적고, 다른 방법은 성공 조건을 지키면 허용한다.
6. **검증은 원본 검증기를 재사용한다.** 원본을 고치지 않고 `ConfigurationValidator.validate_test_configuration`을 부른다. 시퀀스가 만드는 것과 같은 `TestConfiguration`(프로파일 + 바꾼 값)을 넘겨야 화면 판정과 실행 판정이 어긋나지 않는다.
7. **연결 테스트 중 창 닫기.** GUI를 막지 않아야 하고, 돌고 있는 `QThread`가 파괴되거나 앱이 먼저 끝나서도 안 된다. 실행 중 닫기(앞 플랜 결정 12)처럼 "끝난 뒤 닫기"를 권장한다. 실장비 연결을 중간에 끊으면 장치가 연결된 채로 남을 수 있기 때문이다.
8. **segfault 재현 방법.** PC 전체 부하는 쓰지 않는다. 먼저 결정적 방법(실행이 도는 동안 창을 지우도록 워커를 `threading.Event`로 붙잡아 두기 등)으로 가설을 하나씩 확인한다. 그다음 시험 묶음을 순서대로 반복 실행해 빈도를 잰다. 재현이 안 되면 반복 횟수와 조건을 보고하고 PR 없이 끝낸다.

## 작업

| 순서 | 작업 ID | 내용 | 방식 | 방식 이유 |
|---|---|---|---|---|
| 1 | `ui-cleanups` | `build_outcome` 방어, 부팅 대기 `timeout_seconds=None`, 중단 검사 지점 구분 시험, 프로파일 없을 때 시작 막기 | poteto | 원본의 중단·asyncio 대기 코드(동시성)를 고친다 |
| 1 | `ui-settings-fixes` | `stop_on_failure` 저장, 원본 검증기로 미리 검증, 손상된 YAML의 Mock 스위치, 연결 테스트 중 창 닫기 | poteto | 설정 파일 저장(데이터)과 스레드 종료(동시성) |
| 2 | `ui-segfault` | 시험 중 간헐 segfault 재현·원인·수정 | poteto | 스레드·Qt 객체 수명(동시성) 조사 |

- `ui-cleanups`와 `ui-settings-fixes`는 겹치는 파일이 없어 병렬로 돈다.
- `ui-segfault`가 두 작업 뒤인 이유는 결정 2에 있다.

## 범위 밖

- 부팅 대기 timeout 때 취소 중 예외가 `TimeoutError`로 바뀌는 문제.
- 원본 `eol_tester`의 다른 동작 변경. 예: `load_test_profile`의 자동 생성, `HardwareConfig.to_dict()` 손실, `run()`의 중단 예외 처리.
- 손상된 hardware YAML로 앱을 시작하는 경우(이번 결함은 Mock 스위치를 누르는 경우다).
- CI 추가, 실장비(Windows) 확인.

## 사용자가 정해야 하는 결정

1. **`tests/conftest.py` 수정 가능성.** `ui-segfault`가 원인을 시험 정리(fixture)에서 찾으면 이 파일을 고친다. orch는 이 파일을 검증 설정 파일로 분류하므로 병합 전에 확인을 물을 수 있다. 지시서는 검증을 약하게 하는 변경(시험 삭제, skip/xfail, 재시도, 시간 제한 증가, faulthandler 끄기, `pyproject.toml`·`chute.toml`의 시험 설정 변경)을 금지한다. 정리 단계를 더하는 변경만 허용한다.
2. **segfault가 재현되지 않으면.** `ui-segfault`는 반복 횟수·조건·로그를 보고하고 PR 없이 끝난다. 더 돌릴지, 닫을지 정해 주어야 한다.
3. **프로파일 YAML의 `execution.stop_on_failure`(결정 5를 택한 경우).** UI로 저장한 프로파일에 이 키가 생긴다. station-service CLI로 같은 프로파일을 돌리면 원본이 이 키를 읽지 않으므로 적용되지 않는다. 받아들일지 정해 주어야 한다.
4. **프로파일이 없을 때 `default.yaml` 자동 생성(결정 4).** 원본 기본값으로 만든 `default.yaml`로 바로 시작할 수 있다. 이것도 막아야 한다면(예: 자동 생성된 프로파일은 저장 전까지 시작 금지) 따로 알려 주어야 한다.

이 플랜에 검증을 약하게 하는 작업(검증 단계 삭제, 시간 제한 증가, `paths` 축소)은 없다.
