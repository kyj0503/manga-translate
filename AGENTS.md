# AGENTS.md

manga-translate는 일본 만화 이미지 폴더를 로컬 LLM으로 한국어로 번역하는 Windows GUI 프로그램입니다.
검출·OCR·인페인팅·식자는 BallonsTranslator, 번역은 llama-server가 맡습니다. 사용법은 README.md를 봅니다.

## 규칙

### 수정하면 항상 새로 빌드한다

소스(`src/`, `scripts/`, `pyproject.toml` 등 프로그램에 들어가는 파일)를 수정했다면, 작업을 끝내기 전에
반드시 프로그램 폴더를 새로 빌드한다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

- 빌드 결과는 `C:\Users\serial\Downloads\manga-translate`에 만들어진다(기본값).
- 빌드는 앱 venv와 앱 wheel, `tools\uv.exe`, 바로가기만 새로 만든다. 설치된 엔진, llama.cpp, 모델, 설정은 그대로 둔다.
- 번역 엔진이 실행 중이면(번역, 실험 등) 끝난 뒤에 빌드한다.
- 빌드한 뒤 설치된 코드가 저장소와 같은지 확인한다.

  ```bash
  diff -rq src/manga_translate "$USERPROFILE/Downloads/manga-translate/.venv/Lib/site-packages/manga_translate" -x __pycache__
  ```

### 그 밖의 규칙

- 테스트: `uv run pytest`가 모두 통과해야 한다.
- 빌드, 실행, 테스트는 이 PC에서 직접 한다. WSL이나 Docker는 쓰지 않는다.
- 프로그램이 받거나 만드는 파일(엔진, llama.cpp, 모델, 설정, uv 캐시, 작업 폴더)은 모두 프로그램 폴더 안에만 둔다. `%LOCALAPPDATA%` 같은 다른 곳에 폴더를 만들지 않는다.
- GUI 프로그램만 유지한다. CLI를 추가하지 않는다.
- 줄바꿈은 LF를 쓴다(`.gitattributes`).
- 커밋 작성자는 `heroria0503@gmail.com`이다(저장소 로컬 설정). 커밋 메시지에 `Co-Authored-By` 트레일러를 붙이지 않는다.
- 주석에는 코드가 하는 일을 쓴다. "X를 제거했다" 같은 변경 이력은 쓰지 않는다.
