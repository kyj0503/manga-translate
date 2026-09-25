# manga-viewer

일본 만화 이미지 폴더를 로컬 LLM으로 한국어로 번역해, 말풍선을 지우고 한국어를 식자한 이미지를 저장하는 Windows 프로그램입니다.
검출·OCR·인페인팅·식자는 [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)가, 번역은 로컬
[llama.cpp](https://github.com/ggml-org/llama.cpp) 서버(Gemma 4 등 GGUF 모델)가 맡습니다.

## 요구 사항

- Windows 10/11, NVIDIA RTX 30 시리즈 이상
- [uv](https://docs.astral.sh/uv/), [Git for Windows](https://git-scm.com/download/win)
- llama.cpp Windows CUDA 빌드(`llama-server.exe`)와 번역용 GGUF 모델

## 실행

```powershell
uv sync
uv run manga-viewer
```

1. 처음 한 번 "엔진 설치"를 누릅니다. BallonsTranslator(고정 커밋), 전용 Python 환경, 검출·OCR·인페인팅 모델(약 1GB)을
   `%LOCALAPPDATA%\manga-viewer\BallonsTranslator`에 설치합니다.
2. 번역 모델(GGUF)과 `llama-server.exe`를 고릅니다.
3. 입력 폴더와 출력 폴더를 고르고 "번역 시작"을 누릅니다. 원본 폴더는 건드리지 않습니다.

## 라이선스

GPL-3.0. BallonsTranslator(GPL-3.0)를 사용합니다.
