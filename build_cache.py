"""
Скрипт читает все строки с непустым описанием из Описания_дефектов.csv
(CP1251, разделитель ';'), считает эмбеддинги поля «Описание дефекта»
моделью BAAI/bge-m3 через FlagEmbedding и сохраняет кэш в defects_cache.json.

Структура JSON:
[
  {
    "id": "357609",
    "description": "...",
    "cause": "...",
    "equipment": "...",
    "plant": "YXW",
    "date": "2024-12-16 16:24:00.000",
    "embedding": [0.0123, -0.0456, ...]   // 1024 floats
  },
  ...
]

Запуск:  python build_cache.py
"""

import csv
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent
CSV_PATH = BASE / "Описания_дефектов.csv"
OUT_PATH = BASE / "defects_cache.json"

MODEL_NAME = "BAAI/bge-m3"


def normalize(text: str) -> str:
    if text is None:
        return ""
    text = text.replace(" ", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_csv(path: Path):
    rows = []
    with open(path, "r", encoding="cp1251", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(
                {
                    "id": (row.get("Номер") or "").strip(),
                    "description": normalize(row.get("Описание дефекта") or ""),
                    "cause": normalize(row.get("Причина") or ""),
                    "equipment": normalize(row.get("Оборудование") or ""),
                    "plant": (row.get("Завод") or "").strip(),
                    "date": (row.get("Дата") or "").strip(),
                }
            )
    return rows


def main():
    if not CSV_PATH.exists():
        print(f"Файл не найден: {CSV_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Читаю CSV: {CSV_PATH.name} (CP1251)...")
    rows = load_csv(CSV_PATH)
    print(f"  прочитано: {len(rows)}")

    rows = [r for r in rows if r["description"]]
    print(f"  с непустым описанием: {len(rows)}")

    print(f"\nЗагружаю модель: {MODEL_NAME}")
    print("(при первом запуске будет скачана ~2.2 ГБ)")
    from FlagEmbedding import FlagModel  # noqa: E402

    model = FlagModel(
        MODEL_NAME,
        query_instruction_for_retrieval="",
        use_fp16=False,  # CPU → fp32
    )

    texts = [r["description"] for r in rows]
    print(f"\nСчитаю эмбеддинги для {len(texts)} описаний (batch 16)...")
    embeddings = model.encode(
        texts,
        batch_size=16,
        max_length=512,
        convert_to_numpy=False,
    )
    # FlagModel.encode не нормализует по умолчанию — нормализуем явно
    import numpy as np
    arr = np.asarray(embeddings, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    arr = arr / norms
    print(f"  dim={arr.shape[1]}, normalized")

    print("\nФормирую JSON...")
    out = []
    for r, vec in zip(rows, arr):
        out.append(
            {
                "id": r["id"],
                "description": r["description"],
                "cause": r["cause"],
                "equipment": r["equipment"],
                "plant": r["plant"],
                "date": r["date"],
                "embedding": [float(x) for x in vec],
            }
        )

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = OUT_PATH.stat().st_size / (1024 * 1024)
    print(f"\nГотово: {OUT_PATH.name} — {len(out)} записей, {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
