# BallonsTranslator 래퍼 CLI 설계

- 작성일: 2026-09-25
- 상태: 사용자 승인 (채팅)
- 관계: `2026-09-25-batch-cli-design.md`(자체 파이프라인 배치 CLI)를 **대체**한다. 검출·OCR·인페인팅·식자는
  BallonsTranslator(dmMaze, GPL-3.0)가 맡고, 이 프로젝트는 설치와 실행을 감싼다. 프로젝트 라이선스는 GPL-3.0으로 한다.

## 1. 목표

A 폴더의 일본 만화 이미지를 한국어로 번역·식자한 이미지를 B 폴더에 저장하는 명령줄 도구. 번역은 로컬 llama-server(Gemma 4)가,
나머지는 BallonsTranslator headless 모드가 한다. 이번 단계는 명령어로 실행하는 최소 구현이다.

- 대상 환경: Windows 10/11, NVIDIA RTX 30 시리즈 이상. 네이티브 Windows에서 빌드·실행·테스트(WSL·Docker 미사용).
- 번역은 **텍스트 전용**이다. 페이지 이미지 참고(mmproj)는 쓰지 않는다.

## 2. 사용법

```
manga-viewer setup [--engine-dir <경로>] [--uv <uv.exe>]
manga-viewer translate <A폴더> <B폴더> --llama-server <exe> --model <gguf> [--engine-dir <경로>] [--ctx-size N] [--keep-work]
```

- `--engine-dir` 기본값: `%LOCALAPPDATA%\manga-viewer\BallonsTranslator`
- `--uv` 기본값: PATH의 `uv`

## 3. setup

1. 엔진 저장소를 고정 커밋 `3e401b29f72bc0b3cdad5a4d1c7fa9c6033cdcd8`(https://github.com/dmMaze/BallonsTranslator)로 받는다.
   폴더가 없으면 `git init` + `remote add` 후 해당 커밋을 fetch·checkout한다. 이미 있으면 fetch·checkout만 한다.
2. 엔진 전용 venv(`<engine>\.venv`, Python 3.12)를 uv로 만들고(이미 있으면 건너뜀) 다음을 설치한다.
   - `-r requirements.txt`, `-e . --no-deps`
   - `torch torchvision` (index `https://download.pytorch.org/whl/cu128`)
   - `transformers==4.57.6 jaconv fugashi unidic-lite openai>=2.8.1 httpx[socks,brotli] tiktoken>=0.7.0`
3. 모델 파일(약 785MB)을 Hugging Face에서 받는다. 체크섬이 있는 파일은 SHA-256을 검증하고, 이미 올바른 파일은 건너뛴다.
   `.part`로 받은 뒤 검증이 끝나면 이름을 바꾼다.
   - `data/models/comictextdetector.pt`, `data/models/comictextdetector.pt.onnx`
   - `data/models/lama_large_512px.ckpt`
   - `data/models/manga-ocr-base/`의 7개 파일
4. 끝나면 `<engine>\.manga-viewer-setup`에 커밋 해시를 기록한다. 이 파일과 venv Python이 있으면 "설치됨"으로 본다.
5. 다시 실행해도 안전하다(패키지 설치는 설치됨 상태면 건너뛰고, 모델은 검증 후 건너뜀).

## 4. translate

1. 입력 검증: A 폴더와 이미지 존재, llama-server·모델 파일 존재, 엔진 설치됨, A와 B가 다름. 실패하면 한국어 안내와 종료 코드 2.
2. A의 이미지(`.jpg .jpeg .png .webp .bmp`, 하위 폴더 제외)를 임시 작업 폴더(`%TEMP%\manga-viewer-*\pages`)에 복사한다.
   엔진이 입력 폴더 안에 작업 파일을 만들기 때문에 A는 건드리지 않는다.
3. llama-server를 빈 포트, `127.0.0.1`, `--reasoning-budget 0`(추론 모드 끔)으로 띄운다. Job Object로 수명을 묶는다.
4. 엔진 설정을 쓴다: 엔진 venv의 Python으로 우리 스크립트를 실행하고, 스크립트는 엔진의 설정 모듈로 `config/config.json`을 저장한다.
   - 검출 `ctd`, OCR `manga_ocr`, 인페인팅 `lama_large_512px`, 번역 `LLMTranslator`
   - LLM 프로필: `base_url=http://127.0.0.1:<port>/v1`, 모델 이름은 GGUF 파일 이름, 추론 끔, 비전 끔
   - 일본어 → 한국어, 이전 페이지 문맥(`history`), 폰트 맑은 고딕
5. 엔진을 `-m ballontranslator --headless --exec_dirs <작업 폴더>`로 실행한다(작업 디렉터리는 엔진 루트, `PYTHONIOENCODING=utf-8`).
   표준 입력에 미리 `exit`를 넣어 두어 끝나면 스스로 종료하게 한다. 출력은 터미널에 그대로 보여준다. 엔진 프로세스도 같은 Job에 넣는다.
6. `<작업 폴더>\result\`의 파일을 B로 복사한다. 입력 이미지마다 같은 이름(확장자 무관)의 결과가 있는지 확인한다.
7. 요약을 출력한다. 모든 페이지 결과가 있으면 종료 코드 0이고 작업 폴더를 지운다. 빠진 페이지가 있으면 목록을 출력하고
   종료 코드 1, 작업 폴더는 원인 확인용으로 남긴다(`--keep-work`면 항상 남긴다).
8. 어떤 경우든 엔진 프로세스와 llama-server를 종료한다.

## 4-1. GUI (간단한 창)

사용자 요청(2026-09-25)으로 명령어 대신 쓸 수 있는 작은 창을 둔다. tkinter(표준 라이브러리)로 만든다.

- 입력 폴더, 출력 폴더: 각각 입력칸 + "찾아보기" 버튼. 입력 폴더를 고르면 출력이 비어 있을 때 `<입력>_번역`을 자동으로 채운다.
- 번역 모델: 선택된 GGUF 파일 이름을 표시하고 "변경..."으로 고른다. llama-server.exe도 같은 방식으로 표시·선택한다.
- 언어: "일본어 → 한국어"를 표시한다(고정).
- "번역 시작" 버튼, 진행 막대와 "n / 전체장" 표시, 엔진 로그를 보여주는 텍스트 영역.
- 진행도는 엔진이 `result\`에 저장한 파일 수로 센다.
- 끝나면 결과 요약 대화상자를 띄운다. 엔진이 설치되지 않았으면 `manga-viewer setup`을 먼저 실행하라고 안내한다.
- 선택한 경로(모델, llama-server, 엔진 폴더, 마지막 입출력 폴더)는 `%LOCALAPPDATA%\manga-viewer\settings.json`에 저장한다.
- 번역 중에 창을 닫으면 확인을 받고, 닫으면 Job Object 덕분에 엔진과 llama-server가 함께 종료된다.
- 실행: `manga-viewer gui` 또는 콘솔 창 없는 `manga-viewer-gui`.

번역 흐름은 CLI와 GUI가 같은 `pipeline.py`를 쓴다.

## 5. 코드 구성

| 모듈 | 책임 |
|---|---|
| `source.py` | 이미지 목록 (기존) |
| `winjob.py` | Job Object (기존) |
| `llm/process.py`, `llm/llama.py` | llama-server 기동 (기존, `--reasoning-budget 0` 추가, mmproj 제거) |
| `engine.py` (신규) | 엔진 위치, 설치 명령, 모델 다운로드·검증, 설치 여부 |
| `engine_run.py` (신규) | 설정 쓰기, 작업 폴더 준비, headless 실행(스트리밍), 결과 수집 |
| `scripts/bt_write_config.py` (신규) | 엔진 venv에서만 실행되는 설정 스크립트 |
| `pipeline.py` (신규) | 번역 작업 하나: 입력 검증, llama-server·엔진 실행, 진행도, 결과 수집 |
| `settings.py` (신규) | GUI 설정 저장·불러오기 |
| `gui.py` (신규) | tkinter 창 |
| `cli.py` | `setup`, `translate`, `gui` |

자체 파이프라인 코드(mokuro 비전, 번역기, bench, 렌더러 등)와 PyTorch `engine` extra는 제거한다(git 기록에 남음).
저장소에 GPL-3.0 `LICENSE`와 짧은 사용법 `README.md`를 둔다.

## 6. 테스트

- 설치 명령 구성, 설치 여부 판정, 모델 다운로드(로컬 HTTP 서버로 체크섬 성공·실패·건너뜀)
- 설정 스크립트: 가짜 `ballontranslator` 패키지로 실행해 저장된 설정값 검증
- 스트리밍 실행: 실제 하위 프로세스로 출력 전달·표준 입력 `exit`·오류 시 종료 확인
- CLI: 가짜 llama-server·엔진으로 정상·일부 실패·입력 오류 흐름
- 실제 확인: 평가 때 설치한 `.dev\BallonsTranslator`에 `setup`을 다시 실행해 멱등성을 확인하고, 샘플 6장을 E4B로 번역

## 7. 보류 (다음 단계)

- 드래그 앤 드롭 실행, 출력 폴더 자동 이름
- llama-server·Gemma 모델 자동 설치와 기본 모델 선택
- 용어집 전달, 여러 폴더 처리, 하위 폴더·ZIP/CBZ
- 엔진을 켜 둔 채 반복 처리하는 모드
