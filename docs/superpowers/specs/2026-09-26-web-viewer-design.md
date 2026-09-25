# 실시간 오버레이 번역 뷰어 설계

- 작성일: 2026-09-26
- 상태: 사용자 승인 (채팅). 워커(검출·OCR)와 엔진 설치 부분은 2026-09-26에 `2026-09-26-onnx-vision-release-design.md`로 대체됨
- 관계: `2026-09-25-gui-installer-design.md`의 tkinter 배치 번역 앱을 **대체**한다. 설치(엔진, llama.cpp, 모델, 다운로드, 취소)와
  저장 위치 원칙은 그대로 유지한다. `2026-09-25-manga-viewer-design.md`(보류)의 뷰어 아이디어를 현재 구조 위에서 다시 설계한 것이다.

## 1. 목표

만화 이미지 폴더를 앱 창에서 한 장씩 읽으면, 로컬 GPU가 현재 페이지부터 말풍선을 검출·OCR·번역하고,
원본 이미지 위에 한국어 번역을 HTML 오버레이로 겹쳐 보여준다.

- 대상 사용자: 개발자가 아닌 일반인. 바로가기로 창 하나를 열고 그 안에서 설치부터 읽기까지 모두 한다.
- 대상 환경: Windows 10/11, NVIDIA RTX 30 시리즈 이상. WebView2 런타임(Windows 11 기본 포함).
- 언어: 일본어 → 한국어 고정.

### 범위에서 제외 (YAGNI)

- 폴더 → 폴더 배치 번역, 식자 이미지 저장(인페인팅). 기존 배치 기능은 제거한다.
- 세로 스크롤(웹툰) 보기, 두 쪽 펼침 보기
- OCR·번역 결과 수동 편집, 용어집
- 외부 브라우저 접속, 원격 접속

## 2. 결정 사항 요약

| 항목 | 결정 |
|---|---|
| 기존 앱과의 관계 | 뷰어로 교체 (배치 번역 제거) |
| 화면 | pywebview(WebView2) 창 안의 로컬 웹 UI |
| 번역 표시 | HTML 오버레이 (원본 이미지 + 말풍선 위치에 반투명 칸과 한글) |
| 읽기 방식 | 한 장씩 넘기기, 넘기는 방향 설정 가능 |
| 캐시 | 프로그램 폴더 `cache\`에 저장, 만화 폴더에는 쓰지 않음 |
| 엔진 구동 | 상주 워커 프로세스(검출 + OCR) + 앱이 llama-server에 직접 번역 요청 |

### 실현 가능성 확인 (2026-09-26 프로브)

엔진 venv에서 `TEXTDETECTORS.get("ctd").resolve()`, `OCR.get("manga_ocr").resolve()`로 클래스를 얻어
한 번 로드한 뒤 `detect(img)` → `run_ocr(img, blocks)`를 호출했다.

- 모델 로드: 약 9초 (워커 시작 시 한 번)
- 페이지당 검출 + OCR: 964×1200 기준 1.3~2.5초
- 블록별 `xyxy`, `vertical`, 원문 텍스트를 얻을 수 있다.
- PyTorch 최대 할당 약 1.1GB, 예약 약 1.4GB (인페인팅 모델을 올리지 않으므로 배치 방식보다 가볍다)

## 3. 구조

```
앱 프로세스 (pythonw -m manga_translate)
 ├ pywebview 창 ─ http://127.0.0.1:<port>/?token=<t> 를 띄움
 ├ 웹 서버 (ThreadingHTTPServer, 127.0.0.1, 빈 포트)
 │   ├ 정적 파일: index.html, app.js, style.css
 │   └ API: 설치 상태·진행률, 책장, 페이지 이미지, 번역 결과
 ├ 번역 스케줄러 (스레드 1개, 한 번에 한 페이지)
 ├ 캐시 (<프로그램 폴더>\cache\*.json)
 │
 ├─ 워커 (엔진 venv의 python, 상주) ─ 검출 + OCR, stdin/stdout JSON 줄 단위
 └─ llama-server ─ 앱이 /v1/chat/completions 로 직접 번역 요청

워커와 llama-server는 KillOnCloseJob에 넣어 앱과 수명을 묶는다.
```

### 모듈 구성

| 모듈 | 책임 | 상태 |
|---|---|---|
| `paths.py` | 프로그램 폴더 구성. `cache_dir`, `logs_dir` 추가 | 수정 |
| `download.py`, `components.py`, `engine.py` | 설치(엔진, llama.cpp, 모델), 다운로드, 취소 | 유지 |
| `winjob.py`, `llm/process.py`, `llm/llama.py` | Job Object, llama-server 구동 | 유지 |
| `source.py` | `find_images` (책 안의 페이지 목록) | 유지 |
| `settings.py` | 모델, 최근 폴더, 권별 마지막 페이지, 넘기는 방향 | 수정 |
| `library.py` | 폴더를 스캔해 책 목록(이미지가 있는 폴더) 생성 | 신규 |
| `worker_client.py` | 워커 프로세스 시작·요청·응답·재시작 | 신규 |
| `scripts/bt_worker.py` | 엔진 venv 안에서 실행. ctd + manga_ocr 상주, JSON 줄 프로토콜 | 신규 |
| `translate.py` | llama-server 번역 요청 (스키마, 문맥, 재시도) | 신규 |
| `cache.py` | 페이지 결과 저장·조회·무효화 | 신규 |
| `scheduler.py` | 우선순위 대기열, 페이지 처리(워커 → 번역 → 캐시) | 신규 |
| `server.py` | HTTP 서버, 토큰 검사, API 라우팅, 경로 검사 | 신규 |
| `app.py` | 앱 상태(설치 작업, 워커·llama 시작/종료), 서버와 창 연결 | 신규 |
| `web/` (`index.html`, `app.js`, `style.css`) | 설치·책장·뷰어 화면 | 신규 |
| `gui.py`, `pipeline.py`, `engine_run.py`, `scripts/bt_write_config.py` | tkinter 창과 배치 번역 | 삭제 |

`gui.py`의 순수 함수 중 계속 필요한 것(구성 요소 상태 문구, `effective_model` 등)은 `app.py`로 옮긴다.

## 4. 번역 흐름

### 4.1 페이지 요청

1. 뷰어가 페이지를 열면 원본 이미지(`/api/image`)를 바로 표시하고 `/api/translation`을 요청한다.
2. 캐시가 유효하면 결과를 즉시 반환한다.
3. 없으면 스케줄러에 "현재 페이지"를 알리고 `{"status": "pending"}`을 반환한다. 뷰어는 0.5초 간격으로 다시 요청한다(폴링).
4. 완료되면 `{"status": "done", "size": [w, h], "blocks": [...]}`, 실패하면 `{"status": "failed", "error": "..."}`.

### 4.2 스케줄러

- 사용자가 페이지를 열 때마다 `focus(book, index)`를 호출한다.
- 대기열 우선순위: 현재 페이지 → 다음 3장 → 이전 1장. 캐시가 유효한 페이지는 넣지 않는다.
- `focus`가 바뀌면 대기열을 새로 만든다. 처리 중인 페이지는 끝까지 처리해 캐시에 넣는다(중간 취소 없음).
- 한 페이지 처리: 워커(검출 + OCR) → 번역 → 캐시 저장. 블록이 0개면 번역 없이 빈 결과를 저장한다.
- 실패한 페이지는 실패 상태로 기억하고 자동 재시도하지 않는다. `/api/retry`로 다시 대기열 맨 앞에 넣는다.

### 4.3 워커 프로토콜 (stdin/stdout, UTF-8, JSON 한 줄)

- 시작하면 모델을 로드하고 `{"ready": true}`를 보낸다.
- 요청: `{"id": 7, "image": "C:/.../012.webp"}`
- 응답: `{"id": 7, "size": [w, h], "blocks": [{"xyxy": [x1, y1, x2, y2], "vertical": true, "text": "..."}]}`
- 오류: `{"id": 7, "error": "..."}`. 워커는 계속 동작한다.
- 엔진 로그는 stderr로 보내고, 앱은 이를 `logs\worker.log`에 쓴다.
- 워커가 죽으면 다음 요청 때 한 번 다시 시작한다. 다시 시작해도 실패하면 오류 상태를 보고한다.
- 블록 순서는 엔진이 돌려준 순서를 그대로 쓴다.

### 4.4 번역 요청

- `POST {base_url}/v1/chat/completions`, `temperature=0.1`, `max_tokens=2048`, thinking 비활성(`chat_template_kwargs: {"enable_thinking": false}`), llama-server는 `--reasoning-budget 0`으로 실행.
- `response_format`: `{"type": "json_schema", "json_schema": {"name": "translations", "schema": S}}`.
  `S`는 `"1"`~`"N"` 키가 모두 필수인 문자열 객체이고 추가 키는 금지한다(N = 블록 수).
- 프롬프트: 일본 만화 대사를 자연스러운 한국어 구어체로 옮기라는 지시, 입력은 `{"1": 원문, ...}` JSON.
- 문맥: 같은 책의 직전 페이지 최대 3장의 캐시에서 (원문, 번역) 쌍을 이전 대화로 넣는다.
- 타임아웃 60초. 네트워크 오류나 스키마 위반이면 한 번 재시도하고, 그래도 실패하면 페이지를 실패 처리한다.
- 요청은 `trust_env=False`로 보낸다(프록시 무시).

### 4.5 캐시

- 파일: `<프로그램 폴더>\cache\<sha256(원본 이미지의 절대 경로)>.json`
- 내용: `{"version": 1, "source": 경로, "source_size": 바이트, "source_mtime_ns": ..., "model": 모델 파일 이름, "size": [w, h], "blocks": [{"xyxy", "vertical", "text", "translation"}]}`
- 원본 파일 크기, 수정 시각, 모델 이름 중 하나라도 다르면 무효로 본다.
- 임시 파일에 쓴 뒤 `os.replace`로 교체한다.

## 5. 화면

한 페이지짜리 웹 앱이다. 해시 라우팅(`#/setup`, `#/library`, `#/read/<book>/<index>`)을 쓰고, 빌드 도구 없이 순수 HTML·CSS·JS로 만든다.
정적 파일은 패키지(`manga_translate/web/`)에 포함한다.

### 5.1 설치 화면

- 번역 엔진, llama.cpp, 번역 모델 세 줄: 상태, 설치 버튼, 진행 막대. 공용 "중단" 버튼과 로그 영역. 동작은 기존 tkinter 창과 같다.
- 모델 "변경...": pywebview 파일 선택 창으로 GGUF를 고른다.
- 셋이 모두 설치되면 "시작"이 켜진다. 누르면 llama-server와 워커를 띄우고(진행 표시) 준비되면 책장으로 이동한다.
- 앱을 시작했을 때 모두 설치되어 있으면 자동으로 "시작"을 진행한다.

### 5.2 책장

- "폴더 열기" → pywebview 폴더 선택 창.
- 고른 폴더와 그 하위 폴더 가운데 이미지가 직접 들어 있는 폴더 하나를 책 한 권으로 본다. 첫 이미지를 썸네일로, 폴더의 상대 경로를 제목으로 보여준다.
- 최근 폴더 1개와 권별 마지막 페이지를 `settings.json`에 저장한다.

### 5.3 뷰어

- 한 장을 창에 맞춰 표시한다. 방향키, 화면 좌우 클릭, 휠로 넘긴다. 넘기는 방향(일본식/서양식)은 설정으로 고른다.
- 오버레이: 블록 `xyxy`를 이미지 표시 크기 비율로 변환한 위치에 반투명 흰 칸 + 한글(가로쓰기).
  칸 안에 들어가도록 글자 크기를 자동으로 맞춘다(이진 탐색으로 최대 크기).
- `T` 키: 오버레이 켜기/끄기. 칸에 마우스를 올리면 원문을 툴팁으로 보여준다.
- 상단 바: 책 이름, `페이지 / 전체`, 번역 상태(대기, 번역 중, 완료, 실패), 모델 이름, `일본어 → 한국어`, 책장 버튼.
- 실패 페이지에는 "다시 번역" 버튼.

## 6. HTTP API

모든 요청은 `token` 쿼리 파라미터(또는 `X-Token` 헤더)가 실행 시 생성한 값과 같아야 한다. 다르면 403.

| 메서드·경로 | 설명 |
|---|---|
| `GET /` | `index.html` (토큰이 맞을 때만) |
| `GET /static/<file>` | `app.js`, `style.css` |
| `GET /api/state` | 구성 요소 상태, 진행 중 작업, 진행률, 로그 꼬리, 번역 준비 여부, 모델 이름 |
| `POST /api/install/{engine,llama,model}` | 설치 시작 |
| `POST /api/cancel` | 진행 중 작업 중단 |
| `POST /api/model` | 모델 변경 (pywebview 파일 선택) |
| `POST /api/start` | llama-server + 워커 시작 |
| `POST /api/library/open` | 폴더 선택 후 책 목록 반환 |
| `GET /api/library` | 현재 책 목록 |
| `GET /api/image?book=&index=` | 원본 이미지 바이트 |
| `GET /api/translation?book=&index=` | 캐시 결과 또는 pending/failed (스케줄러 focus 갱신) |
| `POST /api/retry?book=&index=` | 실패 페이지 다시 번역 |
| `POST /api/progress?book=&index=` | 마지막 읽은 페이지 저장 |

- 책은 목록 안의 번호로 가리키고, 서버는 그 번호의 폴더 안 이미지만 제공한다.
- 모든 이미지 경로는 `resolve()` 후 현재 열린 루트 폴더에 대해 `is_relative_to`로 검사한다.

## 7. 수명과 오류 처리

- 앱 시작: 서버 → pywebview 창. 창을 닫으면 진행 중 작업을 취소하고 Job을 닫아 워커와 llama-server를 종료한다.
- 워커·llama-server 기동 실패: 설치 화면에 오류와 로그 경로를 표시하고 "시작"을 다시 누를 수 있게 한다.
- 워커 비정상 종료: 한 번 자동 재시작, 반복 실패 시 상단 바에 "번역 엔진 오류".
- 이미지 디코딩 실패: 그 페이지만 실패 처리.
- 로그: `<프로그램 폴더>\logs\app.log`, `worker.log`, `llama-server.log`. 실행할 때마다 새로 쓴다.
- 설치 작업 취소, 다운로드 이어받기, 무결성 검사는 기존 동작을 유지한다.

## 8. 의존성과 빌드

- 추가: `pywebview` (WebView2 백엔드). 웹 서버는 표준 라이브러리 `http.server.ThreadingHTTPServer`.
- 패키지 데이터: `manga_translate/web/*`, `manga_translate/scripts/bt_worker.py`.
- `scripts/build.ps1`, 바로가기(`manga-translate.lnk` → `.venv\Scripts\manga-translate.exe`)는 그대로 쓴다. gui-script 진입점을 `manga_translate.app:main`으로 바꾼다.

## 9. 테스트

pytest, GPU 불필요. 기존 테스트 중 삭제되는 모듈의 테스트는 함께 삭제한다.

- `cache`: 저장·조회, 원본 크기·수정 시각·모델 변경 시 무효화, 원자적 쓰기
- `scheduler`: 우선순위(현재 → 다음 3 → 이전 1), focus 변경 시 재구성, 처리 중 페이지 유지, 실패와 재시도. 가짜 워커·번역기 사용
- `worker_client` + `bt_worker.py`: 가짜 엔진 모듈(`tests/helpers/fake_bt` 확장)로 ready, 정상 응답, 오류 응답, 워커 종료 후 재시작
- `translate`: 스키마 생성, 문맥 구성, 스키마 위반 시 재시도, 타임아웃. 가짜 HTTP 서버 사용
- `server`: 토큰 불일치 403, 경로 이탈 차단, 각 API 응답 형식
- `library`: 하위 폴더 스캔, 이미지 없는 폴더 제외, 정렬

### 수동 확인 (실제 GPU)

- 샘플은 `C:\Users\serial\Downloads\(페그오` 폴더만 사용한다.
- 앱 실행 → 시작 → 폴더 열기 → 첫 페이지 오버레이 표시 시간, 다음 페이지 미리 번역 여부, 창 닫을 때 프로세스 종료, VRAM 최대치를 기록한다.

## 10. 문서

- README: 사용법을 뷰어 기준으로 다시 쓴다.
- AGENTS.md: "GUI 프로그램만 유지한다"를 "뷰어 앱만 유지한다. CLI를 추가하지 않는다"로 바꾼다.
