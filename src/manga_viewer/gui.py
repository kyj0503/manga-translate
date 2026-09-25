"""The app window: pick folders, see model and languages, install the engine, translate and watch progress."""
from __future__ import annotations

import queue
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Sequence

from .engine import EngineError, EngineLayout, default_engine_dir, setup_engine
from .engine_run import run_streaming
from .pipeline import (
    SOURCE_LANGUAGE,
    TARGET_LANGUAGE,
    PipelineError,
    TranslationRequest,
    TranslationResult,
    run_translation,
)
from .settings import Settings, default_settings_path, load_settings, save_settings

TITLE = "manga-viewer 번역"
POLL_MS = 100
NOT_SELECTED = "(선택되지 않음)"


def default_output_dir(input_dir: Path) -> Path:
    return input_dir.with_name(f"{input_dir.name}_번역")


def format_progress(done: int, total: int) -> str:
    return f"{done} / {total}장" if total else "대기 중"


def model_label(path: str) -> str:
    return Path(path).stem if path else NOT_SELECTED


def engine_layout(settings: Settings) -> EngineLayout:
    return EngineLayout(Path(settings.engine_dir) if settings.engine_dir else default_engine_dir())


def engine_status_text(layout: EngineLayout) -> str:
    return "설치됨" if layout.is_ready() else "설치 필요 (약 1GB 다운로드, 몇 분 걸림)"


def find_uv(settings: Settings) -> Path | None:
    if settings.uv:
        chosen = Path(settings.uv)
        return chosen if chosen.is_file() else None
    found = shutil.which("uv")
    return Path(found) if found else None


def make_runner(on_line: Callable[[str], None]) -> Callable[[Sequence[str]], None]:
    """Engine setup commands for the window: no console, output goes to the log."""

    def run(argv: Sequence[str]) -> None:
        code = run_streaming(argv, Path.home(), on_line=on_line, stdin_text="")
        if code != 0:
            raise EngineError(f"명령이 실패했습니다 (코드 {code}): {' '.join(map(str, argv))}")

    return run


def build_request(settings: Settings, input_dir: str, output_dir: str) -> TranslationRequest:
    if not input_dir:
        raise PipelineError("입력 폴더를 선택하세요.")
    if not output_dir:
        raise PipelineError("출력 폴더를 선택하세요.")
    if not settings.model:
        raise PipelineError("번역 모델(GGUF 파일)을 선택하세요.")
    if not settings.llama_server:
        raise PipelineError("llama-server.exe를 선택하세요.")
    return TranslationRequest(
        input_dir=Path(input_dir),
        output_dir=Path(output_dir),
        llama_server=Path(settings.llama_server),
        model=Path(settings.model),
        engine=engine_layout(settings),
    )


def summary_text(result: TranslationResult, output_dir: Path) -> str:
    lines = [f"{result.total - len(result.missing)} / {result.total}장을 번역했습니다.", f"저장 위치: {output_dir}"]
    if result.missing:
        lines.append("결과가 없는 페이지: " + ", ".join(p.name for p in result.missing))
    if result.work_dir is not None:
        lines.append(f"작업 폴더: {result.work_dir}")
    return "\n".join(lines)


class App:
    def __init__(self, root: tk.Tk, settings_path: Path) -> None:
        self.root = root
        self.settings_path = settings_path
        self.settings = load_settings(settings_path)
        self.events: queue.Queue = queue.Queue()
        self.running = False

        root.title(TITLE)
        root.minsize(620, 500)
        self.input_var = tk.StringVar(value=self.settings.last_input)
        self.output_var = tk.StringVar(value=self.settings.last_output)
        self.model_var = tk.StringVar(value=model_label(self.settings.model))
        self.llama_var = tk.StringVar(value=self.settings.llama_server or NOT_SELECTED)
        self.engine_var = tk.StringVar()
        self.progress_var = tk.StringVar(value=format_progress(0, 0))

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="입력 폴더").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="찾아보기...", command=self._pick_input).grid(row=0, column=2, sticky="ew")

        ttk.Label(frame, text="출력 폴더").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="찾아보기...", command=self._pick_output).grid(row=1, column=2, sticky="ew")

        ttk.Label(frame, text="번역 모델").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.model_var).grid(row=2, column=1, sticky="w", padx=6)
        ttk.Button(frame, text="변경...", command=self._pick_model).grid(row=2, column=2, sticky="ew")

        ttk.Label(frame, text="llama-server").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.llama_var).grid(row=3, column=1, sticky="w", padx=6)
        ttk.Button(frame, text="변경...", command=self._pick_llama).grid(row=3, column=2, sticky="ew")

        ttk.Label(frame, text="언어").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Label(frame, text=f"{SOURCE_LANGUAGE} → {TARGET_LANGUAGE}").grid(row=4, column=1, sticky="w", padx=6)

        ttk.Label(frame, text="번역 엔진").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.engine_var).grid(row=5, column=1, sticky="w", padx=6)
        self.install_button = ttk.Button(frame, text="엔진 설치", command=self._install)
        self.install_button.grid(row=5, column=2, sticky="ew")

        self.bar = ttk.Progressbar(frame, mode="determinate", maximum=1)
        self.bar.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(12, 4))
        ttk.Label(frame, textvariable=self.progress_var).grid(row=6, column=2)

        self.start_button = ttk.Button(frame, text="번역 시작", command=self._start)
        self.start_button.grid(row=7, column=0, columnspan=3, pady=8)

        self.log = tk.Text(frame, height=12, state="disabled", wrap="word")
        self.log.grid(row=8, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(8, weight=1)

        self._refresh_engine()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(POLL_MS, self._drain)

    # --- settings and pickers ---

    def _save(self) -> None:
        save_settings(self.settings, self.settings_path)

    def _refresh_engine(self) -> None:
        self.engine_var.set(engine_status_text(engine_layout(self.settings)))

    def _pick_input(self) -> None:
        path = filedialog.askdirectory(title="입력 폴더 선택")
        if path:
            self.input_var.set(path)
            if not self.output_var.get().strip():
                self.output_var.set(str(default_output_dir(Path(path))))

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="출력 폴더 선택")
        if path:
            self.output_var.set(path)

    def _pick_model(self) -> None:
        path = filedialog.askopenfilename(title="번역 모델 선택", filetypes=[("GGUF 모델", "*.gguf")])
        if path:
            self.settings.model = path
            self.model_var.set(model_label(path))
            self._save()

    def _pick_llama(self) -> None:
        path = filedialog.askopenfilename(title="llama-server.exe 선택", filetypes=[("실행 파일", "*.exe")])
        if path:
            self.settings.llama_server = path
            self.llama_var.set(path)
            self._save()

    # --- running work on a background thread ---

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _begin(self) -> None:
        self.running = True
        self.start_button.configure(state="disabled")
        self.install_button.configure(state="disabled")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _finish(self) -> None:
        self.running = False
        self.start_button.configure(state="normal")
        self.install_button.configure(state="normal")
        self._refresh_engine()

    def _install(self) -> None:
        uv = find_uv(self.settings)
        if uv is None:
            path = filedialog.askopenfilename(title="uv.exe 선택", filetypes=[("실행 파일", "*.exe")])
            if not path:
                return
            self.settings.uv = path
            self._save()
            uv = Path(path)
        git = shutil.which("git")
        if git is None:
            messagebox.showerror(TITLE, "git을 찾을 수 없습니다. Git for Windows를 설치한 뒤 다시 시도하세요.")
            return
        self._begin()
        threading.Thread(target=self._install_work, args=(engine_layout(self.settings), uv, Path(git)), daemon=True).start()

    def _install_work(self, layout: EngineLayout, uv: Path, git: Path) -> None:
        # Worker thread: only talk to Tk through the event queue.
        def log(line: str) -> None:
            self.events.put(("log", line))

        try:
            log(f"엔진 설치 위치: {layout.root}")
            setup_engine(layout, uv=uv, git=git, run=make_runner(log), log=log)
            self.events.put(("installed",))
        except EngineError as e:
            self.events.put(("error", str(e)))
        except Exception as e:  # keep the window usable and show what went wrong
            self.events.put(("error", f"예상하지 못한 오류: {e!r}"))

    def _start(self) -> None:
        try:
            req = build_request(self.settings, self.input_var.get().strip(), self.output_var.get().strip())
        except PipelineError as e:
            messagebox.showwarning(TITLE, str(e))
            return
        self.settings.last_input = str(req.input_dir)
        self.settings.last_output = str(req.output_dir)
        self._save()
        self._begin()
        self.bar.configure(maximum=1, value=0)
        self.progress_var.set(format_progress(0, 0))
        threading.Thread(target=self._translate_work, args=(req,), daemon=True).start()

    def _translate_work(self, req: TranslationRequest) -> None:
        # Worker thread: only talk to Tk through the event queue.
        try:
            result = run_translation(
                req,
                on_log=lambda line: self.events.put(("log", line)),
                on_progress=lambda done, total: self.events.put(("progress", done, total)),
            )
            self.events.put(("done", result, req.output_dir))
        except (PipelineError, EngineError) as e:
            self.events.put(("error", str(e)))
        except Exception as e:  # keep the window usable and show what went wrong
            self.events.put(("error", f"예상하지 못한 오류: {e!r}"))

    def _drain(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "log":
                    self._append_log(event[1])
                elif kind == "progress":
                    _, done, total = event
                    self.bar.configure(maximum=max(total, 1), value=done)
                    self.progress_var.set(format_progress(done, total))
                elif kind == "installed":
                    self._finish()
                    messagebox.showinfo(TITLE, "엔진 설치가 끝났습니다.")
                elif kind == "done":
                    self._finish()
                    _, result, output_dir = event
                    show = messagebox.showinfo if result.ok else messagebox.showwarning
                    show(TITLE, summary_text(result, output_dir))
                elif kind == "error":
                    self._finish()
                    messagebox.showerror(TITLE, event[1])
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain)

    def _on_close(self) -> None:
        if self.running and not messagebox.askokcancel(TITLE, "작업 중입니다. 창을 닫으면 작업이 중단됩니다. 닫을까요?"):
            return
        # Exiting closes our Job Object handles, which ends llama-server and the engine too.
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    App(root, default_settings_path())
    root.mainloop()
    return 0
