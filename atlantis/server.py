from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .bootstrap import build
from .contracts import RuleError, RunConfig

WEB_ROOT = Path(__file__).parent / "web"


def serve(database: str, port: int, env_file: str = ".env") -> None:
    city, controller, capabilities = build(database, env_file)
    city.recover()
    if not city.list_runs():
        controller.create_run(RunConfig())
    stop = threading.Event()

    def worker() -> None:
        while not stop.wait(0.5):
            for run in city.list_runs():
                if stop.is_set():
                    return
                if run["status"] == "running":
                    try:
                        controller.advance(run["id"])
                    except Exception:
                        city.set_status(run["id"], "paused")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _send(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _valid_host(self) -> bool:
            return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

        def do_GET(self) -> None:
            if not self._valid_host():
                self._send(403, {"error": "Invalid host."})
                return
            path = urlsplit(self.path).path
            try:
                if path == "/api/capabilities":
                    self._send(200, capabilities)
                elif path == "/api/runs":
                    self._send(200, city.list_runs())
                elif path.startswith("/api/runs/") and len(path.split("/")) == 4:
                    self._send(200, city.snapshot(path.split("/")[-1]))
                elif path in ("/", "/app.js", "/style.css"):
                    filename = "index.html" if path == "/" else path[1:]
                    content = (WEB_ROOT / filename).read_bytes()
                    mime = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}[filename]
                    self.send_response(200)
                    self.send_header("Content-Type", mime + "; charset=utf-8")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
                    self.end_headers()
                    self.wfile.write(content)
                else:
                    self._send(404, {"error": "Not found."})
            except RuleError as error:
                self._send(404, {"code": error.code, "error": str(error)})

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            allowed_origins = (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}")
            if not self._valid_host() or (origin is not None and origin not in allowed_origins):
                self._send(403, {"error": "Invalid origin or host."})
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                self._send(415, {"error": "Use application/json."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 8192:
                    raise ValueError("Invalid request size.")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("Expected a JSON object.")
                path = urlsplit(self.path).path
                if path == "/api/runs":
                    config = RunConfig(**body)
                    if config.execution_mode not in controller.runtimes:
                        raise RuleError("model_not_configured", "No live model is configured.")
                    self._send(201, {"id": controller.create_run(config)})
                else:
                    parts = path.split("/")
                    if len(parts) != 5 or parts[:3] != ["", "api", "runs"] or parts[4] not in ("start", "pause"):
                        self._send(404, {"error": "Not found."})
                        return
                    city.set_status(parts[3], "running" if parts[4] == "start" else "paused")
                    self._send(200, {"status": city.snapshot(parts[3])["status"]})
            except RuleError as error:
                self._send(409, {"code": error.code, "error": str(error)})
            except (ValueError, TypeError):
                self._send(400, {"error": "Invalid request or configuration."})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=worker, name="atlantis-scheduler", daemon=True)
    thread.start()
    print(f"Atlantis: http://127.0.0.1:{server.server_port}", flush=True)
    print("Live model: " + (capabilities["model"] or "not configured"), flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        thread.join(timeout=65)
        city.storage.close()
