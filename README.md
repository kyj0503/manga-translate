# manga-viewer

일본 만화 이미지 폴더를 로컬 LLM으로 한국어로 번역해, 말풍선을 지우고 한국어를 식자한 이미지를 저장하는 Windows 프로그램입니다.
검출·OCR·인페인팅·식자는 [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)가, 번역은 로컬
[llama.cpp](https://github.com/ggml-org/llama.cpp) 서버(Gemma 4 등 GGUF 모델)가 맡습니다.

## 1. 요구 사항

- Windows 10/11
- NVIDIA RTX 30 시리즈 이상 그래픽카드
- [uv](https://docs.astral.sh/uv/)
- [Git for Windows](https://git-scm.com/download/win)

## 2. 코드 받기

저장소 이름은 manga-translate로 바뀔 예정이지만, 프로그램 이름(manga-viewer)은 그대로입니다.

```powershell
git clone https://github.com/kyj0503/manga-translate.git
cd manga-translate
```

## 3. llama.cpp 받기

[llama.cpp 릴리스 페이지](https://github.com/ggml-org/llama.cpp/releases)에서 아래 두 파일을 받아 **같은 폴더**에
압축을 풉니다.

- `llama-<태그>-bin-win-cuda-12.4-x64.zip`
- `cudart-llama-bin-win-cuda-12.4-x64.zip`

`--reasoning-budget` 옵션이 필요하므로, 태그가 **b11177 이상**인 빌드를 받아야 합니다.

## 4. 번역 모델 받기

[unsloth/gemma-4-E4B-it-GGUF](https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF)에서
`gemma-4-E4B-it-Q4_K_M.gguf` 파일(약 5GB)을 받습니다. 이 GGUF 파일 하나면 충분하고, mmproj 파일은 필요 없습니다.

## 5. 실행

```powershell
uv sync
uv run manga-viewer
```

처음 켰을 때 "엔진 설치"를 누르면 BallonsTranslator 전용 Python 환경(CUDA용 PyTorch 포함)과 검출·OCR·인페인팅 모델
(약 785MB)을 합쳐 약 6GB를 받습니다. 수십 분 걸릴 수 있으니, 설치가 끝날 때까지 창을 닫지 마세요.

## 6. 사용법

1. 위에서 받은 번역 모델(GGUF)과 `llama-server.exe`를 고릅니다.
2. 입력 폴더(번역할 만화 이미지가 있는 폴더)와 출력 폴더를 고릅니다. 입력 폴더는 건드리지 않습니다.
3. "번역 시작"을 누릅니다.

## 라이선스

GPL-3.0. BallonsTranslator(GPL-3.0)를 사용합니다.
