# manga-translate

일본 만화 이미지 폴더를 로컬 LLM으로 한국어로 번역해, 말풍선을 지우고 한국어를 식자한 이미지를 저장하는 Windows 프로그램입니다.
검출·OCR·인페인팅·식자는 [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)가, 번역은
[llama.cpp](https://github.com/ggml-org/llama.cpp)의 llama-server와 Gemma 4 모델이 맡습니다. 필요한 것은 모두 프로그램 창에서 설치합니다.

## 요구 사항

- Windows 10/11, NVIDIA RTX 30 시리즈 이상 그래픽카드
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- 여유 디스크 공간 약 12GB

## 설치

```powershell
git clone https://github.com/kyj0503/manga-translate.git
cd manga-translate
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

`%USERPROFILE%\Downloads\manga-translate`에 프로그램 폴더가 만들어집니다. 다른 곳에 만들려면 `-Dest <폴더>`를 붙입니다.
프로그램이 받는 파일(엔진, llama.cpp, 모델, 설정)은 모두 이 폴더 안에만 저장됩니다. 엔진을 설치할 때 쓰는 uv의
캐시와 관리형 Python, 번역 중 임시 작업 폴더도 모두 이 프로그램 폴더 안에 남으므로, 폴더를 지우면 전부 함께
지워집니다.

## 사용법

1. 프로그램 폴더의 `manga-translate` 바로가기를 실행합니다.
2. "구성 요소"의 세 줄에서 각각 "설치"를 누릅니다.
   - 번역 엔진: 약 6GB, 수십 분 걸릴 수 있습니다.
   - llama.cpp: 약 0.6GB
   - 번역 모델(Gemma 4 E4B): 약 5GB
3. 입력 폴더와 출력 폴더를 고르고 "번역 시작"을 누릅니다. 원본 폴더는 건드리지 않습니다.

설치나 번역 중에 "중단"을 누르면 멈춥니다. 설치는 다시 "설치"를 누르면 받던 곳부터 이어서 진행하고,
번역은 그때까지 완성된 페이지를 출력 폴더에 남깁니다. 다른 GGUF 모델을 쓰려면 "변경..."으로 고릅니다.

## 개발

```powershell
uv sync
uv run pytest
```

## 라이선스

GPL-3.0. BallonsTranslator(GPL-3.0)를 사용합니다.
