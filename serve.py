"""
Локальный HTTP-сервер для проекта ai-toir.

Раздаёт статику (index.html, defects_cache.json, Описания_дефектов.csv) и
предоставляет POST /embed — считает эмбеддинг запроса той же моделью, что и
build_cache.py, чтобы фронтенд мог сравнивать запрос с кэшем.

Запуск:  python serve.py
Открыть:  http://localhost:8000/index.html
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).parent
MODEL_NAME = "BAAI/bge-m3"

_model = None  # загружается лениво при первом /embed


def get_model():
    global _model
    if _model is None:
        from FlagEmbedding import FlagModel
        _model = FlagModel(
            MODEL_NAME,
            query_instruction_for_retrieval="",
            use_fp16=False,  # CPU → fp32
        )
    return _model


class Handler(BaseHTTPRequestHandler):
    # Отключаем access-log в stderr, чтобы не мешал
    def log_message(self, fmt, *args):
        pass

    def _send(self, status: int, body: bytes, content_type: str = "application/octet-stream",
              extra_headers: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # Убираем query-параметры и приводим путь к файлу
        path = self.path.split("?", 1)[0]
        if path in ("", "/"):
            path = "/index.html"
        rel = path.lstrip("/")
        # Защита от выхода за пределы каталога
        try:
            target = (BASE / rel).resolve()
            if BASE.resolve() not in target.parents and target != BASE.resolve():
                raise ValueError("escape")
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
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js":   "application/javascript; charset=utf-8",
            ".css":  "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".csv":  "text/csv; charset=cp1251",
        }.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, data, ctype)

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
            self._send(400, json.dumps({"error": f"bad json: {e}"}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        if not text:
            self._send(400, json.dumps({"error": "empty text"}).encode("utf-8"),
                       "application/json; charset=utf-8")
            return
        try:
            import numpy as np
            model = get_model()
            vec = model.encode([text], batch_size=1, max_length=512, convert_to_numpy=False)[0]
            arr = np.asarray(vec, dtype=np.float32)
            n = float(np.linalg.norm(arr))
            if n > 0:
                arr = arr / n
            body = json.dumps({"embedding": [float(x) for x in arr]}).encode("utf-8")
            self._send(200, body, "application/json; charset=utf-8")
        except Exception as e:  # noqa: BLE001
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode("utf-8"),
                       "application/json; charset=utf-8")


def main():
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Сервер запущен: http://localhost:{port}/index.html")
    print(f"  в локальной сети: http://<твой-ip>:{port}/index.html")
    print(f"  статика из: {BASE}")
    print(f"  модель:      {MODEL_NAME}")
    print("  Ctrl+C для остановки")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")


if __name__ == "__main__":
    main()
