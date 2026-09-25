"""Local HTTP server for the viewer window: its web files and a JSON API, guarded by a per-run token."""
from __future__ import annotations

import hmac
import json
import logging
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import parse_qs, urlsplit

logger = logging.getLogger(__name__)

TOKEN_PLACEHOLDER = "{{TOKEN}}"
JSON_TYPE = "application/json; charset=utf-8"
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}


@dataclass(frozen=True)
class Response:
    body: bytes
    content_type: str
    status: int = 200


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


Route = Callable[[dict[str, str]], object]


def _json(value: object, status: int = 200) -> Response:
    return Response(json.dumps(value, ensure_ascii=False).encode("utf-8"), JSON_TYPE, status)


def _index(web_dir: Path, token: str) -> Response:
    html = (web_dir / "index.html").read_text(encoding="utf-8").replace(TOKEN_PLACEHOLDER, token)
    return Response(html.encode("utf-8"), STATIC_TYPES[".html"])


def _static(web_dir: Path, name: str) -> Response:
    if not name or "/" in name or "\\" in name or "%" in name or name.startswith("."):
        raise ApiError(404, "not found")
    path = web_dir / name
    content_type = STATIC_TYPES.get(path.suffix)
    if content_type is None or not path.is_file():
        raise ApiError(404, "not found")
    return Response(path.read_bytes(), content_type)


def make_server(
    routes: Mapping[tuple[str, str], Route], token: str, web_dir: Path, port: int = 0
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def log_message(self, format: str, *args: object) -> None:
            logger.debug(format, *args)

        def _handle(self, method: str) -> None:
            url = urlsplit(self.path)
            query = {key: values[-1] for key, values in parse_qs(url.query).items()}
            given = query.pop("token", None) or self.headers.get("X-Token") or ""
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)  # the API takes no bodies
            if not hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8")):
                self._send(_json({"error": "forbidden"}, 403))
                return
            try:
                if method == "GET" and url.path == "/":
                    response = _index(web_dir, token)
                elif method == "GET" and url.path.startswith("/static/"):
                    response = _static(web_dir, url.path[len("/static/"):])
                else:
                    route = routes.get((method, url.path))
                    if route is None:
                        raise ApiError(404, "not found")
                    result = route(query)
                    response = result if isinstance(result, Response) else _json(result)
            except ApiError as e:
                response = _json({"error": e.message}, e.status)
            except Exception as e:
                logger.exception("request failed: %s %s", method, url.path)
                response = _json({"error": f"내부 오류: {e}"}, 500)
            self._send(response)

        def _send(self, response: Response) -> None:
            try:
                self.send_response(response.status)
                self.send_header("Content-Type", response.content_type)
                self.send_header("Content-Length", str(len(response.body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(response.body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # the window navigated away mid-response

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
