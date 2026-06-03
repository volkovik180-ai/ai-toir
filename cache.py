"""
DefectsCache — ленивая обёртка над defects_cache.json.

Сейчас UI грузит кэш сам в браузере (см. loadServerCache() в index.html).
Этот модуль — заготовка для будущих серверных эндпоинтов:
- GET /api/cache/stats — размер, число записей
- GET /api/defects/<id> — отдать запись по id (если решим не тащить 335 МБ в браузер)
"""
from __future__ import annotations

import json
from pathlib import Path

from config import load

CACHE_PATH = Path(__file__).parent / "defects_cache.json"


class DefectsCache:
    def __init__(self):
        self._items: list[dict] | None = None
        self._mtime: float | None = None

    def load(self) -> list[dict]:
        if not CACHE_PATH.exists():
            raise FileNotFoundError(f"{CACHE_PATH} не найден")
        mtime = CACHE_PATH.stat().st_mtime
        # Перечитываем, только если файл изменился
        if self._items is None or self._mtime != mtime:
            with CACHE_PATH.open("r", encoding="utf-8") as f:
                self._items = json.load(f)
            self._mtime = mtime
        return self._items

    def stats(self) -> dict:
        items = self.load()
        return {
            "path": str(CACHE_PATH),
            "count": len(items),
            "size_mb": round(CACHE_PATH.stat().st_size / (1024 * 1024), 1),
            "embedding_dim": len(items[0]["embedding"]) if items and items[0].get("embedding") else 0,
        }


_cache: DefectsCache | None = None


def get_cache() -> DefectsCache:
    """Возвращает singleton-экземпляр DefectsCache."""
    global _cache
    if _cache is None:
        _cache = DefectsCache()
    return _cache
