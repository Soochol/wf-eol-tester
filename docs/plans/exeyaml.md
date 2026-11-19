# 운영 실행파일 YAML 설정 교체 + LMA 냉각 대기 120초 + 응답 프레임 유실 수정 플랜

- 작성일: 2026-11-19
- 이 문서는 승인 시점의 기록이며 구현 중 바뀐 것은 반영하지 않는다.

## 풀려는 문제

하드웨어 PC의 운영 배포본(`C:\StationService_v1.0.0_Windows_x64\sequences\eol_force_test\`)이 최신 설정을 담고 있다. 사용자는 이 YAML로 저장소 설정을 바꿔 달라고 했다. 또 실장비 시험에서 문제가 둘 나왔다.

1. 냉각 완료 신호(0x0C)가 60.003초에 왔다. 지금 대기 한도 60초와 거의 같다.
2. 가열 1회차에서 0x0B가 120초 동안 오지 않았다. 재시도하자 0.7초 만에 왔다(`full_run4.log`).

사용자 요청은 다음과 같다.

- "실행파일 폴더 … 에 있는 yaml 셋업을 가져와서 대체해줘. 그게 최신 셋업 yaml이야."
- "냉각 120초로 변경하고, 가열은 10초 유지"
- 오케스트레이터를 거쳐 추가 승인: 운영본 `lma_mcu.py`의 응답 프레임 유실 수정을 옮긴다("개선해줘"). 같은 수정에 섞인 가열 대기 연장은 옮기지 않는다.

## 확인한 사실 (main 96ad39a)

- **YAML 차이.** 운영본과 저장소의 차이는 두 파일뿐이다(CRLF 무시).
  - `hardware_config.yaml`: `power.model`이 `oda`에서 `mock`으로 바뀌었다. `robot.motion_param_file`, `power_analyzer` 절, `digital_io.input_module_no`/`output_module_no`가 빠졌다.
  - `test_profiles/default.yaml`: `tolerances.temperature_tolerance: 3.0`이 `30 # 3.0`으로 바뀌었다.
  - 줄끝을 LF로 바꾼 운영본의 sha256은 `hardware_config.yaml` `cfdcdafa…16195`, `default.yaml` `23ae5dec…13c3`이다(지시서에 전체 값).
- **교체 뒤 시험 결과.** 임시 worktree에서 두 파일만 바꾸고 전체 시험을 돌렸다. 6개가 실패하고 59개가 setup 오류를 냈다. 원인은 두 가지다.
  1. `HardwarePage._build_editors`(`eol_ui/pages/hardware/page.py`)가 `HardwareStore.get("digital_io", "input_module_no")`를 부른다. `get`은 `self._data[device][key]`를 바로 읽으므로 키가 없으면 `KeyError`가 난다. 그래서 `MainWindow`를 만드는 UI 시험과 앱 종료 시험이 모두 깨진다.
  2. `tests/settings/test_settings.py::test_hardware_store_preserves_keys`가 `after["robot"]["motion_param_file"]`를 읽는다.
- **원본 로더는 그대로 돈다.** `DigitalIOConfig.from_dict`는 모듈 번호가 없으면 0/1을 쓴다. factory도 `config.get("input_module_no", 0)`/`1`이다. `_resolve_motion_param_file_path`는 키가 없으면 건너뛴다. `AjinextekRobot.connect`는 `motion_param_file`이 없으면 `_load_robot_parameters`로 `eol_tester/config/robot_motion_settings.mot`를 찾는다. 이 파일은 저장소에 있다. `power_analyzer`를 읽는 코드는 없다. `ConfigurationValidator`는 `temperature_tolerance`를 검사하지 않고, manifest에도 이 값이 없다.
- **Mock 전환이 운영 설정을 바꾼다.** `HardwareStore.set_mock(True)`는 이미 `mock`인 장치를 백업하지 않는다. `set_mock(False)`는 백업이 없는 장치에 `REAL_MODELS`(`power: oda`)를 넣는다. 그래서 운영본(`power: mock`)에서 Mock을 켰다 끄면 power가 `oda`로 바뀌어 저장된다. 지금은 시험이 KeyError로 먼저 깨져서 드러나지 않는다. `tests/ui/test_settings_screen.py::test_mock_toggle_updates_badge`는 원본 YAML에 `mock`이 없다고 가정한다(`assert "mock" not in original.values()`). `test_hardware_store_mock_roundtrip`은 되돌린 power가 `oda`라고 기대한다.
- **프레임 유실.** `LMAMCU`의 명령은 `serial_conn.write` 뒤 `_wait_for_additional_response`로 ACK를 기다리고, 같은 함수를 한 번 더 불러 완료 신호를 기다린다. 이 함수는 호출할 때마다 지역 `response_data`로 읽는다. 맞는 프레임을 찾으면 그 프레임만 돌려주고 같은 read에 든 나머지 바이트는 버린다. 그래서 ACK와 완료 신호가 한 read에 같이 오면 완료 신호를 잃는다. 다음 대기는 시간 초과까지 기다린 뒤 재시도한다. `full_run4.log`의 "120초 무응답 → 재시도 0.7초" 흐름과 맞다. `_packet_buffer`는 선언되어 있지만 아무 곳에서도 채우지 않는다. 버퍼에서 꺼낸 프레임이 원하는 것이 아니면 그 프레임을 버린다.
- **운영본 수정**(`lma_mcu_exe.diff`): 인스턴스 `_response_data`(남은 바이트)와 `_packet_buffer`(완성 프레임)를 둔다. 대기마다 먼저 남은 바이트에서 프레임을 모두 뽑아 버퍼에 쌓는다. 그다음 버퍼에서 원하는 cmd의 첫 프레임을 꺼내고, 맞지 않는 프레임은 남긴다. 새로 읽은 바이트는 `_response_data`에 이어 붙인다. connect, disconnect, `_send_packet_sync` 때 둘 다 비운다. 같은 diff가 0x0B 대기를 `max(10.0, hold_time_ms/1000 + 30.0)`으로 늘렸지만 이번에는 옮기지 않는다. 운영본은 coolwait 이전 코드라 냉각 대기가 40초다. 우리 코드에는 이미 `COOLING_COMPLETE_TIMEOUT_S`(0x0C와 0x0D가 함께 씀)가 있다.
- **실장비 냉각 후 온도.** `full_run4.log`에서 0x0C를 받은 뒤 42.3℃(목표 38℃)라 ±3℃ 검증에 실패했다. 운영본의 `temperature_tolerance: 30`이면 이 검증은 통과한다.

## 확정된 결정 (사용자)

1. `hardware_config.yaml`과 `test_profiles/default.yaml`을 운영본 내용으로 바꾼다. 줄끝은 LF로 한다.
2. `COOLING_COMPLETE_TIMEOUT_S`를 120.0초로 바꾼다. 가열 도달 대기(0x0B, 10초)는 바꾸지 않는다.
3. 운영본의 응답 프레임 유실 수정을 옮긴다. 같은 수정에 섞인 가열 대기 연장은 옮기지 않는다.
4. 교체 뒤 깨지는 곳은 최소로 고친다. 원본 YAML 값에 기대는 시험 fixture는 고치되 약화하지 않는다. 권한은 기본 권한이고 저장소는 chute로 병합한다.

## 스스로 정한 결정과 이유

1. **작업 둘, 병렬.** `exeyaml-config`(YAML 교체와 UI·시험 보정)와 `lma-frames`(lma_mcu.py)는 고치는 파일이 겹치지 않는다. 한쪽이 다른 쪽의 결과를 쓰지도 않는다. 냉각 120초는 `lma_mcu.py` 안의 상수라 `lma-frames`에 넣는다. 오케스트레이터가 같은 파일이니 한 작업이나 순차를 권했고, 그래서 120초와 프레임 수정을 한 작업으로 묶었다.
2. **`HardwareStore.get`은 키가 없으면 로더가 쓰는 값을 돌려준다.** 기본값은 `HardwareConfig.from_dict(self._data)`의 같은 필드에서 읽는다(DIO 0/1). 값을 따로 적지 않으니 로더와 화면이 어긋나지 않는다. 저장은 지금처럼 고친 키만 쓴다. 그래서 손대지 않은 키는 파일에 다시 생기지 않는다. YAML에 키를 다시 넣는 길은 택하지 않았다. 사용자가 운영본 그대로 쓰라고 했기 때문이다.
3. **Mock을 켰다 끄면 켜기 전 모델로 돌아간다.** 켤 때 Mock이 아닌 장치가 하나라도 있으면 모든 장치의 지금 모델(`mock` 포함)을 백업한다. 끌 때는 백업을 쓰고, 백업이 없는 장치만 `REAL_MODELS`를 쓴다. 이미 전부 `mock`일 때 켜면 백업을 바꾸지 않는다. 그래야 전부 mock이고 백업이 없는 설정에서 끄면 지금처럼 `REAL_MODELS`로 간다. 그대로 두면 운영 PC에서 화면의 Mock 스위치를 한 번 켰다 끄기만 해도 power가 `oda`로 저장된다. 그러면 없는 ODA 장치에 연결하다 실패한다. 이 문제는 이번 교체로 생긴다.
4. **시험 보정.** `test_hardware_store_preserves_keys`는 `motion_param_file` 줄을 빼고, 대신 `robot` 절 전체가 그대로인지 본다(지금 `expected` 전체 비교가 이미 이를 덮는다). Mock 왕복 시험 두 개는 교체한 설정에서 "켜기 전과 같은 모델로 돌아온다(power는 mock)"를 본다. 모든 장치가 실제 모델인 설정에서 되돌린 power가 `oda`라는 기존 기대는 tmp 사본의 power를 `oda`로 바꿔 유지한다. 기존 기대를 지우지 않으니 약화가 아니다.
5. **프레임 수정은 운영본 동작을 그대로 옮긴다.** 버퍼를 비우는 곳은 운영본과 같이 connect, disconnect, `_send_packet_sync` 세 곳이다. `serial_conn.write`를 직접 부르는 명령에서도 비우는 것은 운영본에 없는 새 동작이라 넣지 않는다. 0x0D(`set_cooling_temperature`)도 `COOLING_COMPLETE_TIMEOUT_S`를 쓰므로 함께 120초가 된다. coolwait 플랜이 두 대기를 한 상수로 묶었다.
6. **mock 시퀀스 확인은 기존 시험을 쓴다.** `mock_hardware`·`fast_profiles` fixture는 저장소의 `hardware_config.yaml`·`default.yaml`을 읽어 만든다. 그래서 교체 뒤 `tests/ui/test_run_screen.py::test_run_to_result_pass`와 `tests/settings/test_settings.py`의 시퀀스 실행 시험이 교체한 설정으로 끝까지 돈다. 교체한 설정을 원본 로더와 검증기로 읽는 시험 하나만 새로 쓴다.

## 작업

| 작업 | 내용 | 순서 | 방식 | 방식 이유 |
|---|---|---|---|---|
| `exeyaml-config` | 두 YAML을 운영본으로 바꾸고, `HardwareStore.get` 기본값과 Mock 왕복을 고치고, 시험을 맞춘다 | 바로 시작(병렬) | poteto | 설정 파일에 저장되는 상태(Mock 백업)를 바꾼다 |
| `lma-frames` | 냉각 대기 120초, 응답 프레임 보관 수정, 가짜 시리얼 시험 | 바로 시작(병렬) | basic | 한 파일의 작은 버그 수정과 시험. 저장·동시성·머지 판정 코드가 아니다 |

두 작업은 고치는 파일이 겹치지 않아 순차로 둔 작업이 없다.

## 범위 밖

- 운영본 0x0B 가열 대기 연장(`completion_timeout = max(10.0, hold_time_ms/1000 + 30.0)`).
- ACK 대기, 재시도 횟수, 부팅 대기, 실패 문구 변경. 버퍼를 비우는 곳을 운영본보다 늘리는 일.
- `hardware_facade.py`, `sequence.py`, factory, value_objects 등 다른 원본 코드.
- `power_analyzer`나 DIO 모듈 번호를 화면에서 고치게 하는 기능.
- 실장비에서 120초와 프레임 수정이 충분한지 확인하는 일. 이 플랜의 시험은 가짜 시리얼로만 본다.

## 사용자가 정해야 하는 결정

1. **`temperature_tolerance: 30`은 온도 검증을 사실상 끈다.** 요청대로 운영본 값 30을 그대로 쓴다. 이 값이면 MCU 온도 검증 허용차가 ±3℃에서 ±30℃가 된다. 38℃ 목표에서 8~68℃를 모두 통과시키니 검증을 약하게 하는 변경이다. 주석 `# 3.0`을 보면 원래 값을 알고 임시로 올린 것으로 보인다. 3.0이나 다른 값으로 바꾸려면 알려 달라. 알려 주지 않으면 30으로 진행한다.
2. **`power.model: mock`은 실행 중 전원 공급기를 쓰지 않는다는 뜻이다.** 요청대로 따른다. 운영에서 실제 ODA 전원을 다시 쓰게 되면 설정 화면에서 바꾸거나 YAML을 고쳐야 한다.
