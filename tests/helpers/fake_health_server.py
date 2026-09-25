"""Minimal stand-in for llama-server: /health returns 503 until ready_after seconds pass."""
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

port = int(sys.argv[1])
ready_after = float(sys.argv[2])
started = time.monotonic()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            ready = time.monotonic() - started >= ready_after
            self.send_response(200 if ready else 503)
            self.end_headers()
            self.wfile.write(b"{}")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", port), Handler).serve_forever()
