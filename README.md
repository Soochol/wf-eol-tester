# EOL Tester

EOL Force Test 시퀀스(`F2X_NeuroHub_Station/sequences/eol_force_test`)를 그대로 사용하고, 진행 상태 표시와 설정값 변경을 위한 PySide6 UI를 덧붙이는 프로젝트입니다. 전체 결정과 이유는 [`docs/plans/pyside-ui.md`](docs/plans/pyside-ui.md)에 있습니다.

## 설치

Python 3.11 이상이 필요하고 `.python-version`은 3.12입니다. [uv](https://docs.astral.sh/uv/)로 의존성을 설치합니다.

```
uv sync
```

패키지로 설치하지 않습니다(`[tool.uv] package = false`). 저장소 루트에서 `eol_tester`, `eol_ui`를 바로 import합니다.

```
uv run python -c "import eol_tester, eol_ui; print(eol_tester.EOLForceTestSequence.name)"
```

## 앱 실행

```
uv run python -m eol_ui
```

메인 창에는 실행 화면, 판정 완료 화면, 설정 화면이 있습니다.

- 시리얼 번호(필수), WIP ID, 프로파일을 정하고 "시작"을 누르면 시퀀스가 돕니다. 프로파일 목록은 `eol_tester/config/test_profiles/*.yaml`입니다.
- 실행 중에는 진행 상태, 로그, 실시간 값, 측정 결과가 갱신됩니다. "중단"을 누르면 현재 측정이 끝난 뒤 Teardown(전원 OFF, 로봇 원점 복귀)을 실행하고 "중단됨"으로 끝납니다.
- 끝나면 판정 완료 화면(PASS, FAIL, 중단됨, 오류)으로 바뀝니다. 같은 WIP와 프로파일로 다음 DUT를 이어서 시험하거나 실행 화면으로 돌아갈 수 있습니다.
- 실행 중에 창을 닫으면 닫기를 미루고 중단을 요청합니다. Teardown이 끝나면 창이 닫힙니다.
- 헤더의 MOCK 배지는 `hardware_config.yaml`의 장치 5개가 모두 `mock`일 때 나옵니다. 장치 연결 점은 실행 중 `Hardware status` 로그로 갱신되고, 설정 화면의 연결 테스트 결과로도 갱신됩니다. 그 전과 실행이 끝나 장치 연결을 끊은 뒤에는 회색(모름)입니다.

## 설정 화면

헤더의 "설정" 탭에 왼쪽 메뉴 두 개가 있습니다.

**테스트 파라미터**

- 폼의 초기값은 선택한 프로파일(`eol_tester/config/test_profiles/<이름>.yaml`)에서 읽습니다. 항목, 단위, 범위는 `manifest.yaml`의 `parameters`에서 옵니다.
- 바꾼 항목에는 "변경" 배지와 "프로파일 <원래 값>"이 붙고, 범위를 넘으면 빨간 테두리와 메시지가 나옵니다. 오류가 하나라도 있으면 "다음 실행에 적용"과 "프로파일로 저장"이 비활성입니다.
- "다음 실행에 적용"을 누르면 바꾼 항목만 `{"test_profile": <이름>, ...}`로 실행 화면에 넘어가고 실행 화면에 "적용된 변경 n개"가 보입니다. 적용하지 않은 편집은 실행에 쓰이지 않습니다. 적용한 값은 프로파일을 바꾸거나 다시 적용하기 전까지 다음 실행에도 계속 쓰입니다.
- "프로파일로 저장"은 바 안의 이름 입력칸에 이름을 쓰고 누릅니다. 이름에는 글자, 숫자, `_`, `-`만 쓸 수 있고 `.yaml`은 붙이지 않습니다. 같은 이름이 있으면 바 안에서 덮어쓰기를 한 번 더 묻습니다.
- 프로파일 선택은 실행 화면과 설정 화면이 같은 상태입니다. 목록에 있는 프로파일만 고를 수 있고, 바꾸면 편집 중인 변경과 적용한 변경을 버립니다.

**하드웨어 연결**

- `eol_tester/config/hardware_config.yaml`의 장치 5개의 모델과 연결 설정(포트, 속도, 호스트 등)을 보고 고칩니다. "저장"은 고친 키만 파일에 씁니다.
- Mock 스위치는 바로 저장합니다. 켜면 5개 장치 `model`이 `mock`이 되고 원래 모델은 같은 파일의 `ui_real_models`에 남습니다. 끄면 되돌아옵니다. 헤더 MOCK 배지가 같이 바뀝니다.
- "연결 테스트"는 워커 스레드에서 저장된 설정으로 연결을 시험하고 상태 열과 헤더의 장치 연결 점을 갱신합니다. 시험하는 동안에는 실행을 시작할 수 없습니다.
- 실행 중에는 하드웨어 편집, 저장, Mock 전환, 연결 테스트가 비활성이고 이유가 표시됩니다. 테스트 파라미터는 실행 중에도 편집하고 적용할 수 있고 다음 실행에 쓰입니다.

Mock 전환, 하드웨어 저장, 프로파일 저장은 추적되는 설정 파일을 직접 고치므로 개발 PC에서는 `git status`에 변경이 생깁니다.

글꼴은 번들하지 않습니다. `IBM Plex Sans KR`, `IBM Plex Mono`가 설치돼 있으면 쓰고, 없으면 시스템 대체 글꼴을 씁니다.

## 시험 실행

```
uv run pytest tests/seq -q   # 시퀀스와 check_abort 시험
uv run pytest -q             # 전체
```

Qt 시험은 `QT_QPA_PLATFORM=offscreen`으로 돕니다(`tests/conftest.py`가 기본값으로 설정합니다). 시험은 mock 하드웨어와 tmp 폴더만 쓰고 저장소 안의 파일을 바꾸지 않습니다.

공용 fixture는 `tests/conftest.py`에 있습니다.

| fixture | 하는 일 |
|---|---|
| `mock_hardware` | 5개 장치가 모두 `model: mock`인 tmp `hardware_config.yaml`을 가리키게 한다 |
| `fast_profiles` | 대기 시간 0, 온도 `[38, 52]`, 위치 1개인 tmp `test_profiles/`를 가리키게 한다 |
| `tmp_results` | 시퀀스의 `ResultRepository`를 tmp 폴더로 고정한다 |
| `recording_output` | 모든 `OutputStrategy` 호출을 `(이름, 인자)`로 기록하는 가짜 출력 |

## 디렉터리 구조

| 경로 | 내용 |
|---|---|
| `eol_tester/` | 원본 시퀀스 패키지. 원본 커밋 `2b22b622cbba09e18b2f0c7588773c6ce083930d`의 `sequences/eol_force_test/`를 복사했다. 원본과 다른 곳은 즉시 중단을 위한 `check_abort`뿐이다(`sequence.py`, `hardware_adapter.py`, `services/hardware_facade.py`) |
| `eol_ui/` | PySide6 UI 패키지 |
| `tests/` | 시험. `tests/seq/`는 시퀀스 시험 |
| `docs/plans/` | 플랜 문서 |

## DLL을 커밋하지 않은 이유

`eol_tester/driver/ajinextek/lib/32Bit/`, `lib/64Bit/`의 Ajinextek 라이브러리(`AXL.dll`, `AXL.lib`, `EzBasicAxl.dll`, `EzBasicAxl.lib`)는 독점 파일이고 재배포 라이선스가 정해지지 않아 이 저장소에 넣지 않았습니다. `lib/.gitkeep`만 있습니다. Linux에서는 Ajinextek robot과 DIO가 경고를 내고 mock으로 대체되므로 시험에는 필요 없습니다.

실장비(Windows)에서는 원본 저장소 또는 Ajinextek 설치본에서 받은 파일을 같은 이름으로 다음 위치에 둡니다.

```
eol_tester/driver/ajinextek/lib/32Bit/
eol_tester/driver/ajinextek/lib/64Bit/
```
