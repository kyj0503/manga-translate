# 창에서 모든 구성 요소 설치·취소 설계

- 작성일: 2026-09-25
- 상태: 사용자 승인 (채팅)
- 관계: `2026-09-25-bt-wrapper-design.md`를 확장한다. 번역 흐름과 엔진 구동 방식은 그대로이며, 설치와 저장 위치, 취소가 바뀐다.

## 1. 목표

사용자가 창 하나에서 번역에 필요한 모든 것을 설치하고, 어떤 작업이든 중단할 수 있게 한다.

- 설치 대상: 번역 엔진(BallonsTranslator와 그 Python 의존성·모델), llama.cpp(llama-server), 번역 모델(GGUF)
- 각 설치와 번역 자체에 "중단"
- 앱이 만드는 모든 파일은 **프로그램 폴더 안**에 둔다. `%LOCALAPPDATA%` 등 다른 곳에 폴더를 만들지 않는다.
- 소스 저장소와 실행 위치를 나눈다. 빌드 스크립트가 프로그램 폴더(개발 PC에서는 `C:\Users\serial\Downloads\manga-translate`)를 만들고, 실행·테스트는 그곳에서 한다.

## 2. 프로그램 폴더

```
<프로그램 폴더>\
  .venv\                         앱 전용 Python 환경 (빌드 스크립트가 만듦)
  tools\uv.exe                   빌드 스크립트가 복사한 uv
  manga-translate.lnk            실행 바로가기
  settings.json                  마지막 입출력 폴더, 직접 고른 모델
  engine\BallonsTranslator\      엔진 코드, 엔진 venv, 검출·OCR·인페인팅 모델
  runtime\llama\                 llama-server.exe와 CUDA DLL
  models\                        번역 모델 GGUF
  downloads\                     받는 중인 파일(.part)과 압축 파일
```

- 프로그램 폴더 = 앱 venv의 상위 폴더(`sys.prefix`의 부모). 환경 변수 `MANGA_TRANSLATE_HOME`으로 덮어쓸 수 있다(테스트용).
- 소스 저장소에서 `uv run`으로 실행하면 저장소 루트가 프로그램 폴더가 된다. 그래서 위 폴더들을 `.gitignore`에 둔다.
- uv 찾는 순서: `UV` 환경 변수(`uv run`이 설정) → `<프로그램 폴더>\tools\uv.exe` → PATH의 `uv`. 못 찾으면 안내한다.

## 3. 구성 요소와 고정 값

| 구성 요소 | 받는 것 | 검증 | 설치됨 판정 |
|---|---|---|---|
| 번역 엔진 | `https://github.com/dmMaze/BallonsTranslator/archive/3e401b29f72bc0b3cdad5a4d1c7fa9c6033cdcd8.zip`을 풀고, 엔진 venv(Python 3.12)와 패키지(uv), 모델 10개 | 모델은 기존 SHA-256 | 표시 파일 `.manga-translate-setup` = 커밋 해시, venv Python 존재 |
| llama.cpp | b11177 `llama-b11177-bin-win-cuda-12.4-x64.zip`(254,724,695B, sha256 `14e756ba453e29db57578c1e5791245fe05c893671d3b334e08482ba1a0946bb`), `cudart-llama-bin-win-cuda-12.4-x64.zip`(391,443,627B, sha256 `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6`)를 `runtime\llama`에 풂 | SHA-256 | 표시 파일 `.manga-translate-llama` = `b11177`, `llama-server.exe` 존재 |
| 번역 모델 | `unsloth/gemma-4-E4B-it-GGUF` 리비전 `bfc15c382204943c3a8fff0c750b94ae2364d7a3`의 `gemma-4-E4B-it-Q4_K_M.gguf`(4,977,171,584B, sha256 `85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87`) | SHA-256 | 파일 존재 + 크기 일치 |

- git이 더는 필요 없다(엔진은 소스 zip으로 받는다). 엔진 zip은 GitHub가 체크섬을 보장하지 않으므로 검증하지 않고, 커밋 고정으로 대신한다.
- 사용자는 "변경..."으로 다른 GGUF를 직접 고를 수 있다. 고른 모델이 있으면 그것을 쓰고, 없으면 설치한 기본 모델을 쓴다.

## 4. 다운로드와 압축 풀기

- `downloads\` 또는 최종 위치 옆의 `<이름>.part`로 받는다. `.part`가 있으면 `Range` 요청으로 이어받는다. 서버가 `Range`를 무시하면 처음부터 받는다.
- 1MB 조각마다 중단 여부를 확인한다. 중단하거나 네트워크가 끊기면 `.part`를 남긴다(다음에 이어받음).
- 다 받으면 SHA-256을 확인하고, 틀리면 `.part`를 지우고 오류로 알린다. 맞으면 최종 이름으로 바꾼다.
- 진행은 로그에 50MB마다 표시한다. 연결 제한 시간은 60초.
- zip을 풀 때 파일마다 중단 여부를 확인하고, 폴더 밖을 가리키는 경로(`..`, 절대 경로, 드라이브 문자)는 거부한다.

## 5. 취소

- 창에 "중단" 버튼 하나. 작업(설치 셋 중 하나, 또는 번역)은 한 번에 하나만 실행되고, 작업 중에는 다른 버튼이 잠긴다.
- 설치 중단: 공유 중단 신호를 켜고 작업의 Job Object를 닫아 uv 같은 하위 프로세스를 즉시 끝낸다. 다운로드와 압축 풀기는 다음 조각·파일에서 멈춘다. 설치 완료 표시는 쓰지 않는다. 다시 "설치"를 누르면 이어서 진행한다.
- 번역 중단: 중단 신호를 켜면 번역 작업의 Job Object를 닫아 llama-server와 엔진을 끝낸다. 그때까지 완성된 페이지는 출력 폴더에 복사하고, 요약에 "n / 전체장 저장 후 중단했습니다"를 보여준다. 작업 폴더는 지운다.
- 중단은 오류가 아니다. 오류 창 대신 로그와 안내로 알린다.

## 6. 창

```
입력 폴더  [          ] [찾아보기...]
출력 폴더  [          ] [찾아보기...]
언어       일본어 → 한국어
── 구성 요소 ──
번역 엔진   설치됨 / 설치 필요 (약 6GB)        [설치]
llama.cpp   설치됨 / 설치 필요 (약 0.6GB)      [설치]
번역 모델   gemma-4-E4B-it-Q4_K_M (설치됨)     [설치] [변경...]
[진행 막대................] n / 전체장
[번역 시작] [중단]
[로그]
```

- "설치" 버튼은 설치가 필요한 구성 요소에만 켜진다. "번역 시작"은 엔진·llama.cpp가 설치되어 있고 쓸 모델이 있을 때만 켜진다.

## 7. 빌드

`scripts/build.ps1 [-Dest <폴더>]`(기본 `%USERPROFILE%\Downloads\manga-translate`):
1. `uv build --wheel`로 앱 휠을 만든다.
2. `<Dest>\.venv`를 만들고(없을 때) 휠을 설치한다(`--reinstall`).
3. 실행 중인 uv를 `<Dest>\tools\uv.exe`로 복사한다.
4. `<Dest>\manga-translate.lnk` 바로가기를 만든다.

다시 실행하면 앱만 새로 설치하고 엔진·llama·모델·설정은 그대로 둔다.

## 8. 테스트

- 다운로드: 이어받기(206), `Range` 무시(200), 완료된 `.part`(416), 체크섬 실패, 중단 시 `.part` 유지, 진행 로그
- 압축 풀기: 최상위 폴더 제거, 경로 조작 거부, 중단
- 엔진·llama·모델 설치: 가짜 다운로드와 실행기로 단계 순서, 중단 시 표시 파일 없음, 이미 설치된 경우 건너뜀
- 번역 중단: 가짜 엔진으로 부분 결과 저장과 `cancelled`, Job 종료
- 창: 상태 문구, 버튼 활성화 규칙, 쓸 모델 결정, 요청 만들기, 요약(중단 포함), uv 찾기
- 실제 확인: `Downloads\manga-translate`에 빌드 → llama.cpp 설치(중간 중단 후 이어받기) → 모델·엔진 설치(이미 받은 파일 재사용) → 번역 중단 → 전체 번역 → 창 캡처
