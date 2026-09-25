"""The app window: install the engine, llama.cpp and the model; translate a folder; stop any of it."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Sequence

from . import components
from .download import Cancelled, InstallError
from .engine import EngineError, EngineLayout, setup_engine
from .engine_run import run_streaming
from .paths import AppLayout, app_dir, find_uv, uv_environment
from .pipeline import (
    SOURCE_LANGUAGE,
    TARGET_LANGUAGE,
    PipelineError,
    TranslationRequest,
    TranslationResult,
    run_translation,
)
from .settings import Settings, load_settings, save_settings
from .winjob import KillOnCloseJob

TITLE = "manga-translate 번역"
POLL_MS = 100
ENGINE_SIZE = "약 6GB"
LLAMA_SIZE = "약 0.6GB"
MODEL_SIZE = "약 5GB"


def default_output_dir(input_dir: Path) -> Path:
    if not input_dir.name:
        return input_dir / "번역"
    return input_dir.with_name(f"{input_dir.name}_번역")


def format_progress(done: int, total: int) -> str:
    return f"{done} / {total}장" if total else "대기 중"


def component_status_text(ready: bool, size: str) -> str:
    return "설치됨" if ready else f"설치 필요 ({size})"


def effective_model(layout: AppLayout, settings: Settings) -> Path | None:
    """The GGUF to translate with: the user's pick if it exists, else the installed default."""
    default = components.model_path(layout) if components.model_ready(layout) else None
    if settings.model:
        chosen = Path(settings.model)
        return chosen if chosen.is_file() else default
    return default


def model_status_text(layout: AppLayout, settings: Settings) -> str:
    if settings.model:
        chosen = Path(settings.model)
        if chosen.is_file():
            return f"{chosen.stem} (직접 선택)"
        if components.model_ready(layout):
            return f"{chosen.stem} (파일 없음, 기본 모델 사용)"
        return f"{chosen.stem} (파일 없음)"
    if components.model_ready(layout):
        return f"{Path(components.MODEL.name).stem} (설치됨)"
    return f"설치 필요 ({MODEL_SIZE})"


def can_translate(layout: AppLayout, settings: Settings) -> bool:
    return (
        EngineLayout(layout.engine_dir).is_ready()
        and components.llama_ready(layout)
        and effective_model(layout, settings) is not None
    )


def make_runner(on_line: Callable[[str], None], job: KillOnCloseJob | None = None) -> Callable[[Sequence[str]], None]:
    """Engine setup commands for the window: no console, output goes to the log."""

    def run(argv: Sequence[str]) -> None:
        code = run_streaming(argv, Path.home(), job=job, on_line=on_line, stdin_text="")
        if code != 0:
            raise EngineError(f"명령이 실패했습니다 (코드 {code}): {' '.join(map(str, argv))}")

    return run


def build_request(layout: AppLayout, settings: Settings, input_dir: str, output_dir: str) -> TranslationRequest:
    if not input_dir:
        raise PipelineError("입력 폴더를 선택하세요.")
    if not output_dir:
        raise PipelineError("출력 폴더를 선택하세요.")
    model = effective_model(layout, settings)
    if model is None:
        raise PipelineError("번역 모델을 먼저 설치하거나 선택하세요.")
    return TranslationRequest(
        input_dir=Path(input_dir),
        output_dir=Path(output_dir),
        llama_server=layout.llama_server,
        model=model,
        engine=EngineLayout(layout.engine_dir),
        work_root=layout.work_dir,
    )


def summary_text(result: TranslationResult, output_dir: Path) -> str:
    done = result.total - len(result.missing)
    if result.cancelled:
        return f"{done} / {result.total}장 저장 후 중단했습니다.\n저장 위치: {output_dir}"
    lines = [f"{done} / {result.total}장을 번역했습니다.", f"저장 위치: {output_dir}"]
    if result.missing:
        lines.append("결과가 없는 페이지: " + ", ".join(p.name for p in result.missing))
    if result.work_dir is not None:
        lines.append(f"작업 폴더: {result.work_dir}")
    if result.engine_exit_code != 0:
        lines.append(f"엔진이 오류로 끝났습니다 (코드 {result.engine_exit_code}). 로그를 확인하세요.")
    return "\n".join(lines)


def _set_enabled(widget: ttk.Button, enabled: bool) -> None:
    widget.configure(state="normal" if enabled else "disabled")


class App:
    def __init__(self, root: tk.Tk, layout: AppLayout) -> None:
        self.root = root
        self.layout = layout
        self.settings = load_settings(layout.settings_path)
        self.events: queue.Queue = queue.Queue()
        self.running = False
        self.cancel = threading.Event()
        self.task_job: KillOnCloseJob | None = None
        self.output_dir: Path | None = None

        root.title(TITLE)
        root.minsize(680, 580)
        self.input_var = tk.StringVar(value=self.settings.last_input)
        self.output_var = tk.StringVar(value=self.settings.last_output)
        self.engine_var = tk.StringVar()
        self.llama_var = tk.StringVar()
        self.model_var = tk.StringVar()
        self.progress_var = tk.StringVar(value=format_progress(0, 0))

        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="입력 폴더").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.input_var).grid(row=0, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Button(frame, text="찾아보기...", command=self._pick_input).grid(row=0, column=3, sticky="ew")

        ttk.Label(frame, text="출력 폴더").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.output_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Button(frame, text="찾아보기...", command=self._pick_output).grid(row=1, column=3, sticky="ew")

        ttk.Label(frame, text="언어").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Label(frame, text=f"{SOURCE_LANGUAGE} → {TARGET_LANGUAGE}").grid(row=2, column=1, sticky="w", padx=6)

        ttk.Label(frame, text="구성 요소").grid(row=3, column=0, sticky="w", pady=(12, 2))

        ttk.Label(frame, text="번역 엔진").grid(row=4, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.engine_var).grid(row=4, column=1, sticky="w", padx=6)
        self.engine_button = ttk.Button(frame, text="설치", command=self._install_engine)
        self.engine_button.grid(row=4, column=2, sticky="ew")

        ttk.Label(frame, text="llama.cpp").grid(row=5, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.llama_var).grid(row=5, column=1, sticky="w", padx=6)
        self.llama_button = ttk.Button(frame, text="설치", command=self._install_llama)
        self.llama_button.grid(row=5, column=2, sticky="ew")

        ttk.Label(frame, text="번역 모델").grid(row=6, column=0, sticky="w", pady=4)
        ttk.Label(frame, textvariable=self.model_var).grid(row=6, column=1, sticky="w", padx=6)
        self.model_button = ttk.Button(frame, text="설치", command=self._install_model)
        self.model_button.grid(row=6, column=2, sticky="ew")
        self.pick_model_button = ttk.Button(frame, text="변경...", command=self._pick_model)
        self.pick_model_button.grid(row=6, column=3, sticky="ew")

        self.bar = ttk.Progressbar(frame, mode="determinate", maximum=1)
        self.bar.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(12, 4))
        ttk.Label(frame, textvariable=self.progress_var).grid(row=7, column=3)

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=4, pady=8)
        self.start_button = ttk.Button(buttons, text="번역 시작", command=self._start)
        self.start_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(buttons, text="중단", command=self._stop)
        self.stop_button.pack(side="left", padx=4)

        self.log = tk.Text(frame, height=12, state="disabled", wrap="word")
        self.log.grid(row=9, column=0, columnspan=4, sticky="nsew")
        frame.rowconfigure(9, weight=1)

        self._refresh()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.after(POLL_MS, self._drain)

    # --- state ---

    def _save(self) -> None:
        save_settings(self.settings, self.layout.settings_path)

    def _refresh(self) -> None:
        engine_ok = EngineLayout(self.layout.engine_dir).is_ready()
        llama_ok = components.llama_ready(self.layout)
        model_ok = components.model_ready(self.layout)
        self.engine_var.set(component_status_text(engine_ok, ENGINE_SIZE))
        self.llama_var.set(component_status_text(llama_ok, LLAMA_SIZE))
        self.model_var.set(model_status_text(self.layout, self.settings))
        idle = not self.running
        _set_enabled(self.engine_button, idle and not engine_ok)
        _set_enabled(self.llama_button, idle and not llama_ok)
        _set_enabled(self.model_button, idle and not model_ok)
        _set_enabled(self.pick_model_button, idle)
        _set_enabled(self.start_button, idle and can_translate(self.layout, self.settings))
        _set_enabled(self.stop_button, self.running)

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
            self._save()
            self._refresh()

    # --- one background task at a time ---

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _log(self, line: str) -> None:
        # Safe from any thread: Tk is only touched in _drain.
        self.events.put(("log", line))

    def _launch(self, work: Callable[[], object], kind: str) -> None:
        self.running = True
        self.cancel = threading.Event()
        self.task_job = None
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._refresh()
        threading.Thread(target=self._run, args=(work, kind), daemon=True).start()

    def _run(self, work: Callable[[], object], kind: str) -> None:
        try:
            self.events.put((kind, work()))
        except Cancelled:
            self.events.put(("cancelled",))
        except Exception as e:
            if self.cancel.is_set():
                self.events.put(("cancelled",))  # a killed process failing is part of stopping
            elif isinstance(e, (InstallError, PipelineError)):
                self.events.put(("error", str(e)))
            else:
                self.events.put(("error", f"예상하지 못한 오류: {e!r}"))

    def _install_engine(self) -> None:
        uv = find_uv(self.layout)
        if uv is None:
            messagebox.showerror(TITLE, "uv를 찾을 수 없습니다. 빌드 스크립트로 프로그램을 다시 만들어 주세요.")
            return

        def work() -> str:
            job = KillOnCloseJob()
            self.task_job = job
            try:
                self._log(f"엔진 설치 위치: {self.layout.engine_dir}")
                setup_engine(
                    EngineLayout(self.layout.engine_dir),
                    uv=uv,
                    downloads_dir=self.layout.downloads_dir,
                    run=make_runner(self._log, job),
                    log=self._log,
                    cancel=self.cancel,
                )
                return "번역 엔진 설치가 끝났습니다."
            finally:
                job.close()

        self._launch(work, "installed")

    def _install_llama(self) -> None:
        def work() -> str:
            components.install_llama(self.layout, log=self._log, cancel=self.cancel)
            return "llama.cpp 설치가 끝났습니다."

        self._launch(work, "installed")

    def _install_model(self) -> None:
        def work() -> str:
            components.install_model(self.layout, log=self._log, cancel=self.cancel)
            return "번역 모델 설치가 끝났습니다."

        self._launch(work, "installed")

    def _start(self) -> None:
        try:
            req = build_request(self.layout, self.settings, self.input_var.get().strip(), self.output_var.get().strip())
        except PipelineError as e:
            messagebox.showwarning(TITLE, str(e))
            return
        self.settings.last_input = str(req.input_dir)
        self.settings.last_output = str(req.output_dir)
        self._save()
        self.output_dir = req.output_dir
        self.bar.configure(maximum=1, value=0)
        self.progress_var.set(format_progress(0, 0))

        def work() -> TranslationResult:
            return run_translation(
                req,
                on_log=self._log,
                on_progress=lambda done, total: self.events.put(("progress", done, total)),
                cancel=self.cancel,
            )

        self._launch(work, "translated")

    def _stop(self) -> None:
        if not self.running:
            return
        self.cancel.set()
        job = self.task_job
        if job is not None:
            job.close()  # ends uv and friends right away
        self._append_log("중단하는 중...")
        _set_enabled(self.stop_button, False)

    def _finish(self) -> None:
        self.running = False
        self.task_job = None
        self._refresh()

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
                    messagebox.showinfo(TITLE, event[1])
                elif kind == "translated":
                    self._finish()
                    result = event[1]
                    show = messagebox.showinfo if result.ok or result.cancelled else messagebox.showwarning
                    show(TITLE, summary_text(result, self.output_dir))
                elif kind == "cancelled":
                    self._finish()
                    self._append_log("중단했습니다. 다시 누르면 이어서 진행합니다.")
                elif kind == "error":
                    self._finish()
                    messagebox.showerror(TITLE, event[1])
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._drain)

    def _on_close(self) -> None:
        if self.running and not messagebox.askokcancel(TITLE, "작업 중입니다. 창을 닫으면 작업이 중단됩니다. 닫을까요?"):
            return
        self.cancel.set()
        # Exiting closes our Job Object handles, which ends llama-server, the engine and uv too.
        self.root.destroy()


def main() -> int:
    layout = AppLayout(app_dir())
    os.environ.update(uv_environment(layout))  # keep uv's cache and Python inside the program folder
    root = tk.Tk()
    App(root, layout)
    root.mainloop()
    return 0
