"""Resumable, checksum-verified, cancellable downloads and safe zip extraction."""
from __future__ import annotations

import hashlib
import http.client
import shutil
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable

CHUNK = 1024 * 1024
PROGRESS_EVERY = 50 * 1024 * 1024
TIMEOUT = 60


class InstallError(RuntimeError):
    """An install problem; the message is shown to the user."""


class Cancelled(Exception):
    """The user pressed 중단."""


def check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled()


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _size_text(n: int) -> str:
    return f"{n // (1024 * 1024)}MB" if n >= 1024 * 1024 else f"{n // 1024}KB"


def download(
    url: str,
    dest: Path,
    sha256: str | None = None,
    *,
    log: Callable[[str], None] = print,
    cancel: threading.Event | None = None,
) -> None:
    """Download to <dest>.part (resuming it if present), verify, then rename.

    The .part file is kept when stopped or when the network fails, so the next call resumes.
    """
    if dest.is_file() and (sha256 is None or sha256_of(dest) == sha256):
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    start = part.stat().st_size if part.is_file() else 0
    headers = {"Range": f"bytes={start}-"} if start else {}
    log(f"다운로드: {dest.name}" + (f" ({_size_text(start)}부터 이어받기)" if start else ""))
    expected: int | None = None
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as response:
            if start and response.status == 206:
                content_range = response.headers.get("Content-Range", "")
                range_start = None
                if content_range.startswith("bytes "):
                    try:
                        range_start = int(content_range[len("bytes "):].split("-")[0])
                    except ValueError:
                        range_start = None
                if range_start == 0:
                    start = 0  # the server sent the whole file despite the Range request
                elif range_start != start:
                    raise InstallError(f"다운로드 서버가 잘못된 범위를 보냈습니다: {dest.name}")
            elif start and response.status != 206:
                start = 0  # the server ignored Range: start over

            content_length = response.headers.get("Content-Length")
            if start and response.status == 206:
                content_range = response.headers.get("Content-Range", "")
                total = content_range.rsplit("/", 1)[-1] if "/" in content_range else None
                if total and total != "*":
                    expected = int(total)
                elif content_length is not None:
                    expected = start + int(content_length)
            elif content_length is not None:
                expected = int(content_length)

            with part.open("ab" if start else "wb") as out:
                done = start
                next_log = (done // PROGRESS_EVERY + 1) * PROGRESS_EVERY
                while True:
                    check_cancel(cancel)
                    block = response.read(CHUNK)
                    if not block:
                        break
                    out.write(block)
                    done += len(block)
                    if done >= next_log:
                        log(f"  {dest.name}: {_size_text(done)}")
                        next_log += PROGRESS_EVERY
    except urllib.error.HTTPError as e:
        if not (e.code == 416 and start):  # 416 with a .part means it is already complete
            raise InstallError(f"다운로드에 실패했습니다: {url} ({e})") from e
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        raise InstallError(f"다운로드에 실패했습니다: {url} ({e})") from e
    if expected is not None and done != expected:
        raise InstallError(f"다운로드가 중간에 끊겼습니다: {dest.name} (다시 설치하면 이어받습니다)")
    if sha256 is not None and sha256_of(part) != sha256:
        part.unlink()
        raise InstallError(f"다운로드한 파일 검증에 실패했습니다: {dest.name}")
    try:
        part.replace(dest)
    except OSError as e:
        raise InstallError(f"파일을 저장하지 못했습니다: {dest} ({e})") from e


def extract_zip(
    archive: Path,
    dest: Path,
    *,
    strip_top: bool = False,
    cancel: threading.Event | None = None,
) -> None:
    """Extract into dest (optionally dropping the archive's top folder); refuse paths that escape dest."""
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            check_cancel(cancel)
            name = PurePosixPath(info.filename)
            parts = name.parts[1:] if strip_top else name.parts
            if not parts:
                continue
            target = dest.joinpath(*parts)
            if name.is_absolute() or not target.resolve().is_relative_to(root):
                raise InstallError(f"압축 파일에 잘못된 경로가 있습니다: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)
