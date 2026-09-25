# ONNX 검출·OCR 전환과 포터블 배포 설계

- 작성일: 2026-09-26
- 상태: 사용자 승인 (채팅)
- 관계: `2026-09-26-web-viewer-design.md`의 워커(검출·OCR)와 엔진 설치 부분을 **대체**한다. 뷰어 화면, 서버, 스케줄러, 캐시,
  번역 요청(llama-server + JSON 스키마)은 그대로 유지한다. 배포 방식(포터블 zip + GitHub Release)을 새로 정한다.

## 1. 목표

- 검출(comic-text-detector)과 일본어 OCR(manga-ocr)을 PyTorch와 BallonsTranslator 없이 **ONNX Runtime(CPU)**으로 돌린다.
- 결과는 지금 엔진과 같아야 한다.
- 앱 자체 크기를 약 6GB(엔진) → 1GB 안팎으로 줄인다.
- 검출·OCR은 CPU만 쓰고, GPU(VRAM)는 번역 모델이 모두 쓴다.
- 친구들이 GitHub Release의 zip 하나를 받아 압축을 풀고 실행할 수 있게 한다.
  번역 모델(GGUF)만 앱에서 받거나 직접 고른다.

### 범위에서 제외 (YAGNI)

- 검출·OCR의 GPU 실행(DirectML 등) 선택 기능. 느리다는 요구가 생기면 추가한다.
- 번역을 ONNX로 바꾸는 것. 번역은 llama.cpp + GGUF를 유지한다.
- 멀티모달 LLM으로 OCR 대체
- 단일 exe(onefile) 패키징, 설치 프로그램(setup.exe), 코드 서명, 자동 업데이트
- GitHub Actions 자동 배포(처음에는 개발 PC에서 만들어 올린다)

## 2. 근거 (2026-09-26 실험, `.dev\spike-onnx\REPORT.md`)

### 크기

| | 지금 (BallonsTranslator + PyTorch) | ONNX |
|---|---|---|
| Python 환경 | 엔진 venv 5.2GB (PyTorch 4.1~4.2GB) | 약 0.25~0.3GB |
| 검출·OCR 모델 | 약 0.8GB (쓰지 않는 인페인팅 모델 포함) | 약 0.53GB (fp32) |

### 실제 페이지 비교 (`Downloads\sample` 8장, 말풍선 72개, 기준: 지금 엔진 PyTorch CUDA, detect_size 1280)

| 조합 | 말풍선 일치 | 세로쓰기 | OCR (같은 영역 입력) | 검출+OCR 시간/페이지 | VRAM |
|---|---|---|---|---|---|
| ONNX CPU, ctd 1280 변환본, fp32 OCR + KV 디코더 | 72/72 (IoU 1.000) | 72/72 | 72/72 (CER 0%) | 약 2.0초 (24스레드 CPU) | 0 |
| ONNX DirectML (같은 모델) | 72/72 | 72/72 | 72/72 | 약 0.59초 | 약 1.8GB |
| 지금 엔진 | 기준 | 기준 | 기준 | 약 0.75초 | 약 1.6GB |
| 8비트 양자화 OCR | 72/72 | 72/72 | 65/72 | — | — |
| 공개 1024 ONNX 검출 모델 | 67/72 | 67/67 | 51/67 | — | — |

- 경계가 몇 픽셀 달라져 원문 한 글자가 달라진 말풍선이 1개 있다(자기 검출 영역 기준 71/72).
- 결정: **ctd 1280 변환본 + fp32 OCR 인코더 + KV 캐시 디코더**, 전부 CPU에서 실행한다.
  8비트 양자화와 공개 1024 모델은 쓰지 않는다.

## 3. 배포 구성

### Release zip (`manga-translate-<버전>-win64.zip`, 약 1.2~1.4GB)

```
manga-translate\
├ manga-translate.exe        실행기 (scripts/launcher/Launcher.cs를 빌드: python\pythonw.exe -m manga_translate)
├ python\                    독립형 Python 3.12 (python-build-standalone) + 앱 + 의존성
├ runtime\llama\             llama-server + DLL (b11177, win-cuda-12.4-x64 + cudart)
├ models\
│  ├ ctd\ctd_1280.onnx
│  └ manga-ocr\encoder.onnx, cross_kv.onnx, decoder_step.onnx, vocab.txt
├ LICENSE
├ THIRD_PARTY_NOTICES.txt
└ 사용법.txt
```

앱이 실행되면 `settings.json`, `cache\`, `logs\`가 생기고, 번역 GGUF는 `models\`에 받는다.
프로그램 폴더 밖에는 아무것도 만들지 않는다.

- `app_dir()`는 지금처럼 `sys.prefix`의 부모 폴더다. 포터블 구성에서는 `python\`의 부모, 곧 압축을 푼 폴더가 된다.
- 실행기는 자기 폴더 기준으로 `python\pythonw.exe`를 찾는다. 없으면 오류 메시지 창을 띄운다.

### 사용자 흐름

1. Release에서 zip을 받아 압축을 푼다.
2. `manga-translate.exe`를 실행한다. SmartScreen 경고가 뜨면 "추가 정보 → 실행"을 누른다.
3. 구성 요소 화면에서 "번역 모델 설치"를 누르거나, "변경..."으로 GGUF를 고른다.
4. "시작" → "폴더 열기" → 읽기.

## 4. 검출·OCR 엔진

### 프로세스

- 워커는 별도 프로세스로 둔다. 실행 명령은 `[sys.executable, "-m", "manga_translate.vision.worker", <models 폴더>]`이다.
  앱과 같은 Python을 쓰고 엔진 venv는 없다.
- 프로토콜은 지금과 같다(`{"ready": true}`, `{"id", "image"}` → `{"id", "size", "blocks"}` 또는 `{"id", "error"}`).
- `WorkerClient`, 재시작, Job Object도 그대로다.
- 워커는 모델 파일이 없거나 SHA-256이 맞지 않으면 시작하지 않고, 로그 경로를 담은 오류로 끝낸다.

### 모듈 (`src/manga_translate/vision/`)

| 파일 | 책임 | 출처 |
|---|---|---|
| `ctd.py` | ctd ONNX 실행: 레터박스, 입력 채널 순서(BGR, 엔진 torch 경로와 같게), 가로·세로로 긴 페이지 분할과 복원, DB 후처리(box_thresh 0.6, unclip)로 글줄 추출. YOLO 블록 출력은 쓰지 않는다(엔진도 버린다) | comic-text-detector / BallonsTranslator (GPL-3.0) 이식 |
| `grouping.py` | 글줄 → 말풍선 묶기(`group_output`, `examine_textblk`, `try_merge_textline`, `merge_textlines`, `sort_regions`, `sort_pnts` 등), 세로쓰기 판정, 읽는 순서 정렬, 작은 `TextBlock` 자료형 | BallonsTranslator (GPL-3.0) 이식 |
| `ocr.py` | manga-ocr ONNX: 흑백→RGB, 224 bilinear resize, 0.5/0.5 정규화, 빔 서치(num_beams=4, no_repeat_ngram_size=3, length_penalty=2.0, early_stopping), vocab.txt 복원, 공백 제거와 반각→전각(jaconv) 후처리 | 새로 작성 (manga-ocr/엔진 동작에 맞춤) |
| `models.py` | 모델 파일 목록, 경로, SHA-256, 확인 함수 | 새로 작성 |
| `worker.py` | 모델 로드 → ready → 요청마다 검출 → 말풍선 `xyxy`로 잘라 OCR → 응답 | `scripts/bt_worker.py` 대체 |

- 이식한 파일 머리에는 원본 저장소·커밋·라이선스(GPL-3.0)를 적는다.
- 검출·OCR 모두 onnxruntime `CPUExecutionProvider`로 실행하고, 스레드 수는 기본값을 쓴다.
- 결과를 같게 유지하려고 numpy, opencv-python-headless, shapely, pyclipper, Pillow, onnxruntime, jaconv 버전을 고정한다.

### 모델 에셋

- 변환한 모델 5개 파일은 저장소에 커밋하지 않는다.
  - `ctd_1280.onnx`
  - `encoder.onnx`, `cross_kv.onnx`, `decoder_step.onnx`, `vocab.txt`
- 대신 `vision-models-v1.zip`으로 묶어 GitHub Release `vision-models-v1`에 올리고, 스크립트에 URL과 SHA-256을 고정한다.
- 출처:
  - ctd 원본 가중치(`dreMaz/mit_models`의 `comictextdetector.pt`, 라이선스 미명시)를 1280 고정 입력으로 내보냈다.
  - manga-ocr 인코더는 `onnx-community/manga-ocr-base-ONNX`(Apache-2.0)에서 가져왔다.
  - KV 디코더는 `kha-white/manga-ocr-base`(Apache-2.0)에서 내보냈다.
  - `vocab.txt`는 `kha-white/manga-ocr-base`에서 가져왔다.
- ctd 변환본은 원본 출처와 변환 사실을 `THIRD_PARTY_NOTICES.txt`에 적어 함께 배포한다(사용자 결정).
- 변환 스크립트는 `tools/export/`(`export_ctd.py`, `export_decoder_kv.py`)에 둔다. 다시 변환할 때만 PyTorch가 필요하며, 개발용 선택 의존성 그룹(`export`)으로 둔다.

## 5. 앱 변경

- 구성 요소 화면에는 **llama.cpp**와 **번역 모델** 두 줄만 둔다. "번역 엔진" 줄과 그 설치 코드는 삭제한다.
- "시작" 조건은 llama.cpp 준비, 번역 모델 준비, 검출·OCR 모델 확인 통과다.
  검출·OCR 모델이 없으면 시작 시 오류 메시지를 띄운다(예: "검출·OCR 모델이 없습니다. 프로그램을 다시 받아 주세요.").
- `Runtime`은 llama-server를 시작하고 비전 워커(`python -m manga_translate.vision.worker`)를 시작한다.
- 삭제할 것:
  - `engine.py`의 BallonsTranslator 설치(`setup_engine`, `EngineLayout`, `MODEL_FILES`, `ENGINE_*`)
  - `scripts/bt_worker.py`
  - 엔진용 uv 설정(`find_uv`, `uv_environment`, `bundled_uv`, `uv_cache_dir`, `python_dir`)
  - 쓰지 않는 `work_dir`
  - `run_streaming`(엔진 설치에서만 쓰였으므로)
- `AppLayout`에 `vision_models_dir`(`root/models`)를 둔다.
- 번역 모델 설치(`components.install_model`)와 llama.cpp 설치(`components.install_llama`)는 그대로 둔다.
  소스에서 실행하거나 개발용 빌드일 때 llama.cpp를 버튼으로 받는다.

## 6. 빌드와 배포 스크립트

### 개발용 `scripts/build.ps1`

- 지금처럼 프로그램 폴더에 venv를 만들고, wheel을 설치하고, 바로가기를 만든다.
- 모델 에셋을 받아 SHA-256을 확인하고 `models\`에 푼다. 이미 있고 해시가 맞으면 건너뛴다.
- `tools\uv.exe` 복사는 뺀다.
- 소스 폴더와 겹치는 프로그램 폴더를 거부하는 검사는 유지한다.

### 배포용 `scripts/package.ps1` (신규)

1. `uv python install 3.12`를 임시 설치 폴더에 실행해 깨끗한 독립형 Python을 받고, `<stage>\python\`에 복사한다.
2. 앱 wheel을 만들어 그 Python에 설치한다. 의존성은 `uv.lock`과 같은 버전으로 한다.
3. `csc.exe`(.NET Framework 4.x, `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\`)로 `scripts/launcher/Launcher.cs`를 `/target:winexe`로 빌드한다.
4. llama.cpp 에셋을 받아 SHA-256을 확인하고 `runtime\llama\`에 푼다. `components.LLAMA_ASSETS`와 같은 값을 쓰고, 마커 파일도 쓴다.
5. 모델 에셋을 받아 SHA-256을 확인하고 `models\`에 푼다.
6. `LICENSE`, `THIRD_PARTY_NOTICES.txt`, `사용법.txt`를 넣는다.
7. `dist\manga-translate-<pyproject 버전>-win64.zip`으로 묶는다.

- 스크립트의 콘솔 메시지는 영어로 쓴다. Windows PowerShell 5.1이 BOM 없는 스크립트를 ANSI로 읽기 때문이다.
- 임시 파일은 저장소의 `dist\`(git 무시)와 그 아래에만 둔다.

### Release 절차

1. `vision-models-v1` Release를 한 번 만들고 모델 zip을 올린다.
2. `package.ps1`로 앱 zip을 만든다.
3. 새 폴더에 압축을 풀고, uv·PATH 없이 다음을 확인한다.
   - 창 없이: 서버 응답, 워커 ready, `Downloads\sample` 한 장 검출·OCR, 프로세스 정리
   - 사용자: 실제 창 확인
4. `gh release create v0.1.0 dist\manga-translate-0.1.0-win64.zip`을 실행한다. 게시 전에 사용자 확인을 받는다.
   `gh auth login`은 사용자가 직접 한다.

## 7. 테스트

- 삭제:
  - 엔진 설치 테스트(`test_engine.py`의 BallonsTranslator 부분)
  - `bt_worker` 기반 워커 테스트
  - `tests/helpers/fake_bt`
- 신규:
  - `grouping`: 작은 합성 글줄 입력으로 묶기, 세로쓰기, 순서를 확인한다.
  - `ocr`: vocab 복원, 반각→전각 후처리, 빔 서치(작은 가짜 세션)를 확인한다.
  - `models`: 파일 없음과 해시 불일치를 확인한다.
  - `worker`: 가짜 비전 엔진으로 프로토콜, 오류, 재시작을 확인한다.
  - 회귀 테스트: 합성 페이지(저작권 없는 이미지)와 기대 결과 JSON을 저장소에 두고, 모델이 있을 때만 결과가 같은지 확인한다. 모델이 없으면 건너뛴다.
- 유지: 서버, 스케줄러, 캐시, 번역, 앱 상태 테스트(엔진 줄 삭제에 맞춰 수정).
- 개발 도구: 실제 페이지 비교 스크립트(`tools/parity/`)는 기준 엔진(`.dev\BallonsTranslator`)과 수치만 비교한다.
  샘플은 `Downloads\sample`만 쓴다.

## 8. 문서

- README
  - 사용자용 설치: Release zip 받기 → 압축 풀기 → 실행 → SmartScreen 안내 → 번역 모델 설치
  - 개발자용: 빌드와 소스 실행. 모델 에셋은 빌드 스크립트가 받는다.
  - 요구 사항에서 uv를 개발자용으로 옮긴다.
- AGENTS.md
  - 배포 스크립트와 모델 에셋 규칙: 모델은 저장소에 커밋하지 않고, 에셋 SHA-256을 고정한다.
  - GPL 이식 코드는 출처를 표기한다.
- `THIRD_PARTY_NOTICES.txt`: Python, onnxruntime, OpenCV, numpy, shapely, pyclipper, Pillow, jaconv, httpx, pywebview, pythonnet, llama.cpp, comic-text-detector, BallonsTranslator(이식 코드), manga-ocr, onnx-community export의 라이선스와 출처.
- 정리: 이식이 끝나면 `.dev\spike-slim`, `.dev\spike-onnx`의 venv와 캐시를 지운다. 변환 모델은 에셋 업로드 뒤에 지운다.
