# manga-translate

일본 만화 이미지 폴더를 한 장씩 보여주면서, 로컬 LLM으로 말풍선을 한국어로 번역해 그림 위에 겹쳐 보여주는 Windows 뷰어입니다.
검출·OCR은 [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)가, 번역은
[llama.cpp](https://github.com/ggml-org/llama.cpp)의 llama-server와 Gemma 4 모델이 맡습니다. 필요한 것은 모두 프로그램 창에서 설치합니다.

## 요구 사항

- Windows 10/11, NVIDIA RTX 30 시리즈 이상 그래픽카드
- Microsoft Edge WebView2 런타임 (Windows 11에는 기본 포함)
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- 여유 디스크 공간 약 12GB

## 설치

```powershell
git clone https://github.com/kyj0503/manga-translate.git
cd manga-translate
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

`%USERPROFILE%\Downloads\manga-translate`에 프로그램 폴더가 만들어집니다. 다른 곳에 만들려면 `-Dest <폴더>`를 붙입니다.
프로그램이 받거나 만드는 파일(엔진, llama.cpp, 모델, 설정, 번역 캐시, 로그)은 모두 이 폴더 안에만 저장됩니다.
폴더를 지우면 전부 함께 지워집니다. 만화 폴더에는 아무것도 쓰지 않습니다.

## 사용법

1. 프로그램 폴더의 `manga-translate` 바로가기를 실행합니다.
2. 처음에는 구성 요소 화면이 나옵니다. 세 줄에서 각각 "설치"를 누릅니다.
   - 번역 엔진: 약 6GB, 수십 분 걸릴 수 있습니다.
   - llama.cpp: 약 0.6GB
   - 번역 모델(Gemma 4 E4B): 약 5GB
3. "시작"을 누르면 번역 엔진과 LLM 서버가 켜지고 책장으로 넘어갑니다. 다음부터는 자동으로 시작합니다.
4. "폴더 열기"로 만화 폴더를 고릅니다. 이미지가 들어 있는 폴더(하위 폴더 포함)마다 한 권으로 보여줍니다.
5. 책을 고르면 페이지가 열리고, 몇 초 뒤 번역이 말풍선 위에 겹쳐 보입니다. 다음 몇 장은 미리 번역해 둡니다.

| 조작 | 동작 |
|---|---|
| ← / → , 화면 왼쪽·오른쪽 클릭, 마우스 휠 | 페이지 넘기기 (방향은 상단 바에서 일본식/서양식 선택) |
| T | 번역 표시 켜기/끄기 (원문 보기) |
| 번역 칸에 마우스 올리기 | 원문 보기 |

한 번 번역한 페이지는 저장해 두었다가 다시 열면 바로 보여줍니다. 설치 중에 "중단"을 누르면 멈추고, 다시 "설치"를 누르면
받던 곳부터 이어서 진행합니다. 다른 GGUF 모델을 쓰려면 구성 요소 화면에서 "변경..."으로 고릅니다.
문제가 생기면 프로그램 폴더의 `logs\`를 확인합니다.

## 개발

```powershell
uv sync
uv run pytest
```

## 라이선스

GPL-3.0. BallonsTranslator(GPL-3.0)를 사용합니다.
