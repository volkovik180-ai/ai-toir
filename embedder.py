"""
Embedder — обёртка над FlagModel с ленивой загрузкой.

Модель грузится один раз при первом вызове encode() (≈10-20 сек, потом
всё в памяти). Берёт параметры из config.json (config.model.*).
"""
from __future__ import annotations

import numpy as np

from config import load


class Embedder:
    def __init__(self):
        self._cfg = load().model
        self._model = None  # загружается лениво

    def _ensure(self):
        if self._model is None:
            from FlagEmbedding import FlagModel
            self._model = FlagModel(
                self._cfg.name,
                query_instruction_for_retrieval=self._cfg.query_instruction,
                use_fp16=self._cfg.use_fp16,
            )
        return self._model

    def encode(self, text: str) -> list[float]:
        m = self._ensure()
        mcfg = self._cfg
        vec = m.encode(
            [text],
            batch_size=mcfg.batch_size,
            max_length=mcfg.max_length,
            convert_to_numpy=False,
        )[0]
        arr = np.asarray(vec, dtype=np.float32)
        n = float(np.linalg.norm(arr))
        if n > 0:
            arr = arr / n
        return [float(x) for x in arr]


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Возвращает singleton-экземпляр Embedder (модель грузится один раз)."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder
