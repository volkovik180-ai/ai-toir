"""
HTTP-handler для ai-toir.

GET   /          — index.html (редирект)
GET   /<file>    — статика из BASE
GET   /config    — JSON с дефолтами для UI (без серверных секретов)
POST  /embed     — JSON {"text": "..."} → {"embedding": [float, ...]}

Embedder singleton берётся через get_embedder() — модель грузится
один раз при первом запросе, потом используется повторно.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from config import load
from embedder import get_embedder

BASE = Path(__file__).parent

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".csv":  "text/csv; charset=cp1251",
}


def public_config() -> dict:
    """То, что отдаём фронту. Серверные детали (host/port/use_fp16) — не светим."""
    cfg = load()
    return {
        "ui": {
            "default_threshold": cfg.ui.default_threshold,
            "default_topk":      cfg.ui.default_topk,
            "truncate_at":       cfg.ui.truncate_at,
        },
        "model": {
            "name": cfg.model.name,
        },
    }


class EmbedHandler(BaseHTTPRequestHandler):
    # Убираем access-логи в stderr
    def log_message(self, fmt, *args):
        pass

    # ----- helpers -----

    def _send(self, status: int, body: bytes,
              content_type: str = "application/octet-stream") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _serve_static(self, rel: str) -> None:
        try:
            target = (BASE / rel).resolve()
            if BASE.resolve() not in target.parents and target != BASE.resolve():
                self._send(403, b"forbidden", "text/plain; charset=utf-8")
                return
        except (ValueError, OSError):
            self._send(403, b"forbidden", "text/plain; charset=utf-8")
            return

        if not target.is_file():
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return

        try:
            data = target.read_bytes()
        except OSError:
            self._send(500, b"read error", "text/plain; charset=utf-8")
            return

        ctype = STATIC_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, data, ctype)

    # ----- GET -----

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("", "/"):
            path = "/index.html"

        if path == "/config":
            self._send_json(200, public_config())
            return

        rel = path.lstrip("/")
        self._serve_static(rel)

    # ----- POST -----

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/embed":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            text = (payload.get("text") or "").strip()
        except (ValueError, UnicodeDecodeError) as e:
            self._send_json(400, {"error": f"bad json: {e}"})
            return

        if not text:
            self._send_json(400, {"error": "empty text"})
            return

        try:
            embedding = get_embedder().encode(text)
            self._send_json(200, {"embedding": embedding})
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": f"{type(e).__name__}: {e}"})
