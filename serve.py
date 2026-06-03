"""
Точка входа ai-toir.

Запуск:    python serve.py [port]
Открыть:   http://localhost:8000/index.html

Порт берётся из config.json (server.port). Аргумент CLI перекрывает.
"""
from __future__ import annotations

import sys
from http.server import ThreadingHTTPServer

from config import load
from handlers import EmbedHandler


def main() -> int:
    cfg = load()
    host = cfg.server.host
    port = cfg.server.port
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    server = ThreadingHTTPServer((host, port), EmbedHandler)
    print(f"ai-toir запущен: http://localhost:{port}/index.html")
    if host == "0.0.0.0":
        print(f"  в локальной сети:   http://<ваш-IP>:{port}/index.html")
    print(f"  модель:             {cfg.model.name}")
    print("  Ctrl+C для остановки")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
