# EOL Force Test 시퀀스용 PySide6 UI 플랜

- 작성일: 2026-11-19
- 이 문서는 승인 시점의 기록이며 구현 중 바뀐 것은 반영하지 않는다.

## 풀려는 문제

`F2X_NeuroHub_Station/sequences/eol_force_test`의 파이썬 시퀀스(패키지 이름 `eol_tester`)를 그대로 쓰면서, 진행 상태를 보여 주고 설정값을 바꿀 수 있는 데스크톱 UI를 붙인다. 지금 이 시퀀스는 station-service가 띄우는 CLI(JSON Lines 출력)로만 돌아서, 현장에서 바로 돌리고 진행을 볼 화면이 없다.

## 확정된 결정 (사용자)

1. UI 기술은 PySide6 데스크톱 앱이다.
2. 원본 패키지는 이 저장소에 복사한다. submodule이나 pip 의존성으로 두지 않는다.
3. 즉시 중단을 위해 원본에 `check_abort`를 넣어도 된다. 넣을 수 있는 곳은 두 군데다.
   - force test 반복 루프
   - setup 경로: `setup_test`와 그 안의 LMA standby, MCU 부팅 대기, `verify_mcu_temperature`의 온도 확인 재시도 루프. 플랜 리뷰 뒤 사용자가 허용했다.

   원본 변경은 이것과 그 연결에 필요한 최소 변경뿐이다.
4. 화면은 사용자가 승인한 미리보기(https://claude.ai/artifact/XGs6b1XLmSogFjqoazuRak)를 따른다. 실행 화면, 설정 화면(테스트 파라미터 / 하드웨어 연결), 판정 완료 화면의 3개다. 스타일은 밝은 회색 바탕 #F3F4F6, 흰 카드, 강조 #2B59C3, PASS #0F7B5F, FAIL #C2410C, 글꼴 IBM Plex Sans KR / IBM Plex Mono(없으면 시스템 글꼴)이고 QSS로 구현한다.

## 확인한 사실 (원본 커밋 2b22b622cbba09e18b2f0c7588773c6ce083930d, station-service-sdk 2.1.0)

플래너가 원본을 스크래치패드에 복사해 mock 하드웨어로 직접 돌려 확인했다.

- **같은 프로세스 연결이 된다.** `EOLForceTestSequence(context, parameters=..., output_strategy=...)`에 커스텀 `OutputStrategy`를 넘기고 `await seq._execute()`를 돌리면 mock으로 끝까지 돈다. 온도 2개, 위치 1개일 때 약 14초 걸렸고, 그중 setup이 10.7초였다. 이벤트는 `status(setup) → status(running) → step_start/complete(setup) → step_start(force_test) → measurement×N → step_complete(force_test) → status(teardown) → step_start/complete(teardown) → sequence_complete` 순서로 나온다. **setup의 step 이벤트는 setup이 끝난 뒤에야 나온다.** 그래서 진행 단계는 `status` 이벤트로 판단해야 한다.
- **`seq.abort()`는 플래그를 세우고, 부른 쪽에서 `AbortError`를 던진다.** UI는 이 예외를 잡아야 한다.
- **지금은 force test 중에 중단해도 멈추지 않는다.** 11.5초에 abort를 걸어도 끝까지 측정하고 `passed: True`가 나왔다. 루프에 `check_abort`가 없기 때문이다.
- **원본은 중단을 FAIL이나 오류로 보고한다.** `run()`의 `except Exception`이 `AbortError`를 삼키기 때문이다. `stop_on_failure=True`(기본값)이면 `passed: False, error: None`이 나오고, `False`이면 `StepError`가 된다. setup 안의 중단은 `SetupError`로 바뀐다. setup 도중(3초)에 건 중단은 setup의 남은 `check_abort` 지점을 지난 뒤라서, `run()` 첫 `check_abort`에서야 멈췄다.
- **진행 세부 정보는 loguru 로그에만 있다.** `Test matrix: T temps x P positions x R repeats = N measurements`(emit_log), `Setting temperature to 38.0C (1/2)`, `Measuring at position 20000.0um (1/1)`, `Force: 6.146kgf`(DEBUG 레벨), `Power enabled: 40.0V, 42.0A`, `Hardware status: {...}`(emit_log), `===== Force Test Repetition r/R =====`(R>1일 때만)이 그 예다. `eol_tester/__init__.py`는 import할 때 `logger.remove()`를 부르므로, UI의 sink는 import한 뒤에 달아야 한다.
- **`HardwareConfig.to_dict()`가 값을 잃는다.** 저장하면 robot의 irq_no와 motion_param_file, mcu의 baudrate, power의 port와 delimiter, digital_io의 핀 배치 전부가 빠진다. 그래서 `save_hardware_config()`는 UI 저장에 쓸 수 없다.
- **설정 초기값이 두 군데서 다르다.** manifest의 기본값(전압 18 / 전류 20 / 온도 3개 / operating_position 170000)과 `config/test_profiles/default.yaml`(40 / 42 / 온도 4개 / 175000)이 다르다. 시퀀스는 프로파일을 읽은 뒤 `parameters`로 덮어쓴다. `force_limit_min/max`는 `get_parameter`로 따로 읽고, `stop_on_failure`는 프로파일에 없다.
- **결과 저장 위치는 `eol_tester/results/`(`ResultRepository` 기본값)다.** 저장소의 `.gitignore`에 `results/`가 있어 커밋되지 않는다. 중단되면 저장하지 않는다.
- **Linux에서 Qt를 띄울 수 있다.** Linux에서 Ajinextek robot/DIO는 경고를 내고 mock으로 대체된다. PySide6 6.12, Python 3.12, `QT_QPA_PLATFORM=offscreen` 조합으로 위젯을 띄우는 것을 확인했다. SDK는 Python 3.11 이상이 필요하다.

## 스스로 정한 결정과 이유

1. **배치.** 원본을 저장소 루트의 `eol_tester/`에 복사해 import 이름을 그대로 둔다. UI는 `eol_ui/`, 시험은 `tests/`에 둔다. 의존성과 실행은 루트 `pyproject.toml`과 uv로 관리하고, Python은 3.12로 고정한다. 원본 안의 `pyproject.toml`, `main.py` 등도 원본 그대로 둔다.
2. **복사 커밋과 수정 커밋을 나눈다.** 첫 커밋은 원본 복사(결과 샘플, `__pycache__`, DLL 제외)다. 둘째 커밋은 `check_abort` 추가이고 `sequence.py`, `hardware_adapter.py`, `services/hardware_facade.py` 세 파일만 바꾼다.

   연결은 시퀀스의 `self.check_abort`를 `abort_check` 콜백으로 adapter를 거쳐 facade에 넘기는 방식을 권한다. 콜백을 받는 facade 메서드는 `perform_force_test_sequence`, `setup_test`, `set_lma_standby`, `verify_mcu_temperature`이고, 모두 기본값이 None인 키워드 인자로 받는다. 기본값을 None으로 두면 다른 호출자는 영향을 받지 않는다. 시퀀스 쪽에서는 `run()`이 `execute_force_test(..., abort_check=self.check_abort)`를, `setup()`이 `setup_test(abort_check=self.check_abort)`를 부른다.

   검사 지점은 다음과 같다.
   - force test: 반복 시작, 온도 시작, 위치 시작. 각 온도의 `verify_mcu_temperature` 호출에도 콜백을 넘긴다.
   - `setup_test`: 각 단계 사이(전원 ON 뒤, 부팅 대기 뒤, 테스트 모드 설정 뒤)
   - MCU 부팅 대기: `wait_boot_complete()`를 한 번에 await하는 대신 task로 돌리고, 짧은 주기(0.2초 이하)로 콜백을 확인한다. 중단되면 task를 취소한다. 기존 timeout은 그대로 지킨다.
   - `set_lma_standby`: 각 MCU 명령과 로봇 이동 사이
   - `verify_mcu_temperature`: 시작할 때(mock 생략 분기보다 앞)와 재시도마다

   setup 안의 중단은 원본대로 `SetupError`로 바뀌어 보고된다. 이 예외 처리는 고치지 않고, 판정은 UI가 한다(결정 3).
3. **중단 판정은 UI가 한다.** 원본이 중단을 FAIL이나 오류로 보고하므로, UI가 "중단을 요청했고 PASS가 아니다"이면 `ABORTED`로 판정한다. 원본의 `run()` 예외 처리는 고치지 않는다. 원본 변경을 최소로 하기 위해서다.
4. **판정은 네 가지다.** `ABORTED`(위 조건), `ERROR`(setup 실패, `result.error`, 또는 force_test `step_complete`에 error가 있음), `PASS`(`passed`), `FAIL`(force_test가 오류 없이 끝났고 `passed`가 False)이다. 미리보기에는 PASS/FAIL만 있으므로 ABORTED/ERROR 배너는 같은 틀에 중립색과 FAIL색으로 만든다.
5. **진행률은 로그 파서로 계산한다.** 원본에 progress 이벤트를 넣지 않는다(원본 변경 최소). 파서는 `eol_ui/progress.py` 한 모듈에 모으고, Qt 없이 시험한다. 전체 % 는 setup 구간 0→10, force test 구간 10→95(완료 측정 수 / 전체 측정 수), teardown 95, 끝 100으로 계산한다. 측정 완료는 `Force:` 줄로 센다.
6. **실시간 값 타일은 로그에서 마지막으로 알려진 값이다.** 하드웨어를 따로 폴링하지 않는다. 시퀀스가 쓰는 장치에 두 번째 접근을 만들지 않기 위해서다. 값별 출처는 다음과 같고, 모르는 값은 "—"로 둔다.
   - MCU 온도: 목표는 `Setting temperature`, 실측은 `Temperature verified`(실장비에서만 나옴)
   - Force: `Force:`
   - 전원: `Power enabled`가 오면 ON, teardown이 끝나면 OFF
   - 로봇 위치: `Measuring at position`, `Moving robot to initial position`, mock의 `Moved to`
7. **장치 연결 점.** 실행 중에는 `Hardware status: {...}` 로그로 갱신하고, 설정 화면의 연결 테스트 결과로도 갱신한다. 그 전에는 회색(모름)이다.
8. **설정 폼.** 항목, 단위, min/max는 manifest `parameters` 15개에서 만들고, 초기값(비교 기준)은 선택한 프로파일에서 읽는다. 프로파일에 없는 `stop_on_failure`는 manifest 기본값을 기준으로 한다. 시퀀스에는 `{"test_profile": <선택 프로파일>}`에 사용자가 바꾼 항목만 더해 타입을 변환해 넘긴다(float, `repeat_count`는 int, `stop_on_failure`는 bool, 두 목록은 `list[float]`). 검증은 manifest 범위, 숫자 형식, 빈 목록 금지, 스트로크 각 값 0~180000(manifest의 위치 max), `force_limit_min ≤ force_limit_max`다.
9. **프로파일 저장.** 원래 프로파일 YAML을 읽어 바꾼 항목만 해당 절(`hardware`, `motion_control`, `test_parameters`, `execution`, `pass_criteria`)에 덮어쓴다. 다른 절(timing, safety, tolerances)은 보존한다. 저장 위치는 `eol_tester.config.TEST_PROFILES_DIR`이고, 원본 `load_test_profile()`이 읽는 곳과 같다. 같은 이름이 있으면 덮어쓰기를 확인한다. 이름 입력은 모달 대화상자 대신 프로파일 바 안의 입력칸으로 만든다. offscreen 시험에서 다루기 쉽기 때문이다.
10. **하드웨어 설정 저장.** `save_hardware_config()`가 값을 잃기 때문에, UI는 YAML dict를 그대로 읽어 편집한 키만 바꿔 쓴다. Mock 스위치를 켜면 5개 장치의 `model`을 `mock`으로 바꾸고, 원래 모델을 같은 파일의 최상위 키 `ui_real_models`에 남긴다. 끄면 그 값으로 되돌린다. 원본 `HardwareConfig.from_dict`는 모르는 최상위 키를 무시한다(`metadata`와 같다). 연결 테스트는 저장된 설정을 원본 `load_hardware_config()`로 읽어 `create_standalone_hardware_adapter()`의 공개 API(`connect` → `get_hardware_status` → `disconnect`)로 수행한다. 실행 중에는 하드웨어 편집, 저장, 연결 테스트를 막는다.
11. **결과 파일 표시.** 시퀀스 로그 `Test results saved to: <dir>`에서 폴더를 얻는다. 그 폴더에서 실행 시작 이후 수정된 파일을 보여 주고, "결과 폴더 열기"는 `QDesktopServices`로 연다.
12. **실행 중 창 닫기.** 닫으면 중단을 요청하고, teardown(전원 OFF, 로봇 복귀)이 끝난 뒤 닫는다. 장비 안전을 위해서다.
13. **시험 방식.** 시험은 mock 하드웨어와 빠른 프로파일(timing 0, 작은 위치)로 돌린다. `eol_tester.config.HARDWARE_CONFIG_FILE`, `TEST_PROFILES_DIR`, `eol_tester.sequence.ResultRepository`를 tmp 경로로 바꾸는 공용 fixture를 `tests/conftest.py`에 두어 저장소 파일을 건드리지 않는다. 중단 시험은 시간을 기다리는 대신 첫 `Measuring at position` 로그를 보고 중단을 거는 결정적 방식으로 한다.
14. **글꼴은 번들하지 않는다.** QSS의 font-family에 대체 글꼴 목록을 둔다.
15. **CI는 추가하지 않는다.** 저장소에 CI가 없다. 사용자도 추가하지 않기로 했다(아래 "사용자 결정").

## 작업

| 순서 | 작업 ID | 내용 | 방식 | 방식 이유 |
|---|---|---|---|---|
| 1 | `seq-import` | 원본 복사 커밋 + `check_abort` 커밋 + pyproject/uv + 공용 fixture + 시퀀스 시험 | poteto | 원본 코드의 중단(동시성) 동작을 바꾸고 저장소 뼈대를 정함 |
| 2 | `ui-runner` | `eol_ui/runner/`(OutputStrategy→Qt 시그널, 워커 스레드 asyncio, loguru sink, 중단, 판정) + `eol_ui/progress.py`(로그 파서) | poteto | 스레드·asyncio·중단 동시성 |
| 2 | `ui-settings-model` | `eol_ui/settings/`(manifest 스키마, 프로파일 비교·검증·변환, 프로파일 저장, 하드웨어 YAML 편집·Mock 전환·연결 테스트) | poteto | 설정 파일 저장(데이터) |
| 3 | `ui-run-screen` | 앱 진입점, 메인 창(헤더·탭), QSS, 실행 화면, 판정 완료 화면, 실행 중 닫기 | poteto | 여러 모듈에 걸친 새 UI 설계와 워커 연결 |
| 4 | `ui-settings-screen` | 설정 화면(테스트 파라미터 / 하드웨어 연결)과 실행 화면 연결 | poteto | 설정 파일 저장 흐름과 실행 파라미터 흐름을 잇는 설계 |

병렬과 순차는 다음과 같다.

- `ui-runner`와 `ui-settings-model`은 `seq-import` 뒤에 병렬로 돈다. 겹치는 파일이 없다.
- `ui-settings-model`은 `ui-run-screen`과도 순서가 없다. 겹치는 파일이 없다.
- `seq-import`가 먼저인 이유: 나머지 모두가 복사된 `eol_tester`, 의존성, 공용 fixture를 쓴다.
- `ui-run-screen`이 `ui-runner` 뒤인 이유: 실행 화면이 러너의 시그널과 진행 상태 모델을 쓴다.
- `ui-settings-screen`이 `ui-run-screen`과 `ui-settings-model` 뒤인 이유: 메인 창과 실행 화면(`eol_ui/main_window.py`, `eol_ui/pages/run/**`)을 다시 짜서 설정 화면을 끼우고, 설정 모델을 쓴다.
- `tests/conftest.py`는 `seq-import`만 만든다. 다른 작업은 conftest.py를 만들거나 고치지 않는다.

## 범위 밖

- 원본 시퀀스 동작의 다른 수정. 예: `run()`의 중단 예외 처리, setup의 `AbortError`→`SetupError` 변환, `HardwareConfig.to_dict()` 손실 수정. 허용된 `check_abort` 추가와 그 연결만 한다.
- manifest의 manual_commands(수동 조작) UI.
- station-service(MES) 연동과 CLI 실행 방식의 변경.
- 실장비(Windows)에서의 확인. 시험은 Linux mock으로만 한다.
- 설치 프로그램과 패키징(PyInstaller 등), CI 추가.

## 사용자 결정

플랜 리뷰 때 사용자가 답한 내용이다.

1. **Ajinextek DLL(`driver/ajinextek/lib/32Bit|64Bit`, 약 34MB, 독점 바이너리)은 커밋하지 않는다.** `.gitkeep`만 유지한다. 원본 `axl_wrapper`는 lib 폴더에 DLL이 없으면 시스템 PATH의 `AXL.dll`을 찾는다. 그래서 Ajinextek 드라이버를 설치한 Windows 장비에서는 그대로 동작할 수 있다.
2. **setup 단계에도 `check_abort`를 넣는다.** 범위는 `setup_test`와 그 안의 MCU 부팅 대기, LMA standby, `verify_mcu_temperature`의 재시도 루프다. 연결 방식은 "스스로 정한 결정" 2번에 있다. 이 결정으로 `seq-import`의 원본 수정 범위가 setup 경로까지 넓어졌다. 바꾸는 파일은 그대로 세 개다.
3. **추적 설정 파일은 원본이 읽는 위치에 직접 쓴다.** Mock 전환, 하드웨어 설정 편집, 프로파일 저장이 `eol_tester/config/hardware_config.yaml`과 `eol_tester/config/test_profiles/`에 쓴다. 그래서 개발 PC에서 Mock을 켜면 `git status`에 변경이 생기는데, 이것을 받아들인다.
4. **CI는 추가하지 않는다.**
5. **`tests/conftest.py` 병합 보류는 확인했다.** `seq-import`가 새로 만드는 이 파일은 orch가 검증 설정 파일로 분류한다. 신규 파일이고 검증을 약하게 하지 않는 것으로 처리한다. 이 플랜에 검증을 약하게 하는 작업(검증 단계 삭제, 시간 제한 증가, `paths` 축소)은 없다.
6. **병합 방식.** 이 저장소는 direct 방식으로 병합한다. 사용자는 4절 확인을 통과한 작업 PR의 병합을 오케스트레이터에게 위임했다.
