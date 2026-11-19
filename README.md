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

메인 창에는 실행 화면과 판정 완료 화면이 있습니다. 설정 탭은 빈 페이지이고 다음 작업이 채웁니다.

- 시리얼 번호(필수), WIP ID, 프로파일을 정하고 "시작"을 누르면 시퀀스가 돕니다. 프로파일 목록은 `eol_tester/config/test_profiles/*.yaml`입니다.
- 실행 중에는 진행 상태, 로그, 실시간 값, 측정 결과가 갱신됩니다. "중단"을 누르면 현재 측정이 끝난 뒤 Teardown(전원 OFF, 로봇 원점 복귀)을 실행하고 "중단됨"으로 끝납니다.
- 끝나면 판정 완료 화면(PASS, FAIL, 중단됨, 오류)으로 바뀝니다. 같은 WIP와 프로파일로 다음 DUT를 이어서 시험하거나 실행 화면으로 돌아갈 수 있습니다.
- 실행 중에 창을 닫으면 닫기를 미루고 중단을 요청합니다. Teardown이 끝나면 창이 닫힙니다.
- 헤더의 MOCK 배지는 `hardware_config.yaml`의 장치 5개가 모두 `mock`일 때 나옵니다. 장치 연결 점은 실행 중 `Hardware status` 로그로 갱신되고 그 전에는 회색입니다.

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
