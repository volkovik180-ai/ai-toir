"""
Загрузка и валидация config.json (единый источник правды для ai-toir).

Использование:
    from config import load
    cfg = load()              # Config (dataclass), кэшируется
    print(cfg.server.port)    # 8000
    print(cfg.model.name)     # "BAAI/bge-m3"

Если config.json отсутствует — печатает понятную ошибку и завершает.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BASE = Path(__file__).parent
CONFIG_PATH = BASE / "config.json"


@dataclass(frozen=True)
class ServerCfg:
    host: str
    port: int


@dataclass(frozen=True)
class ModelCfg:
    name: str
    query_instruction: str
    use_fp16: bool
    max_length: int
    batch_size: int


@dataclass(frozen=True)
class UiCfg:
    default_threshold: float
    default_topk: int
    truncate_at: int


@dataclass(frozen=True)
class Config:
    server: ServerCfg
    model: ModelCfg
    ui: UiCfg


def _die(msg: str) -> None:
    print(f"config.json: {msg}", file=sys.stderr)
    sys.exit(1)


@lru_cache(maxsize=1)
def load() -> Config:
    if not CONFIG_PATH.exists():
        _die(f"не найден ({CONFIG_PATH})")
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _die(f"ошибка JSON: {e}")

    if not isinstance(raw, dict):
        _die("ожидается объект в корне")

    try:
        s = raw["server"]; m = raw["model"]; u = raw["ui"]
        server = ServerCfg(host=str(s["host"]), port=int(s["port"]))
        model = ModelCfg(
            name=str(m["name"]),
            query_instruction=str(m.get("query_instruction", "")),
            use_fp16=bool(m.get("use_fp16", False)),
            max_length=int(m.get("max_length", 512)),
            batch_size=int(m.get("batch_size", 1)),
        )
        ui = UiCfg(
            default_threshold=float(u["default_threshold"]),
            default_topk=int(u["default_topk"]),
            truncate_at=int(u.get("truncate_at", 16)),
        )
    except KeyError as e:
        _die(f"отсутствует обязательное поле: {e}")
    except (TypeError, ValueError) as e:
        _die(f"неверный тип поля: {e}")

    return Config(server=server, model=model, ui=ui)
