"""
Докачка BAAI/bge-m3 в кэш HF (~2.2 ГБ pytorch_model.bin).
Резюмит: пропускает уже скачанные файлы.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = "BAAI/bge-m3"
CACHE = Path.home() / ".cache" / "huggingface"

# Качаем только то, что нужно FlagEmbedding на CPU:
# - pytorch_model.bin (основные веса, ~2.2 ГБ)
# - config.json / tokenizer.json / tokenizer_config.json / vocab.txt / sentencepiece.model
# - special_tokens_map.json
# Не качаем .bin из подпапок 1_Pooling и т.п. — FlagEmbedding для bge-m3 их не требует
FILES = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "added_tokens.json",
    "pytorch_model.bin",
]


def main() -> int:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub не установлен. Поставь: pip install -U huggingface_hub", file=sys.stderr)
        return 1

    print(f"Downloading {REPO} -> {CACHE}")
    print("Files:")
    for f in FILES:
        print(f"  - {f}")
    print()

    path = snapshot_download(
        repo_id=REPO,
        cache_dir=str(CACHE),
        allow_patterns=FILES,
        max_workers=2,           # не давим канал
        resume_download=True,
        etag_timeout=30,
    )
    print(f"\nDone. Model at: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
