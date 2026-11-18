"""Embeddings (§5.3): local model (fastembed, default) or external service (Voyage AI)."""
import time

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.ai import EmbeddingConfiguration

OPTIONS = {
    "local": {"model_name": "BAAI/bge-small-en-v1.5", "dimension": 384},
    "external": {"model_name": "voyage-3", "dimension": 1024},
}
QUERY_PREFIX_LOCAL = "Represent this sentence for searching relevant passages: "

_local_models: dict = {}


def active_config(db: Session) -> EmbeddingConfiguration | None:
    return db.scalar(select(EmbeddingConfiguration).where(EmbeddingConfiguration.is_active.is_(True)))


def _local(model_name: str):
    if model_name not in _local_models:
        from fastembed import TextEmbedding  # imported lazily: loading the model takes a few seconds
        _local_models[model_name] = TextEmbedding(model_name=model_name, cache_dir=str(get_settings().model_cache_path))
    return _local_models[model_name]


def _external(texts: list[str], model_name: str, input_type: str) -> list[list[float]]:
    from app.core.secrets import get_secret
    from app.db import SessionLocal

    with SessionLocal() as s:
        key = get_secret(s, "voyage")
    if not key:
        raise RuntimeError("No Voyage AI key is configured. Add one in Administration > API keys.")
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):
        batch = texts[i:i + 64]
        for attempt in range(3):
            r = httpx.post("https://api.voyageai.com/v1/embeddings", timeout=60,
                           headers={"Authorization": f"Bearer {key}"},
                           json={"input": batch, "model": model_name, "input_type": input_type})
            if r.status_code == 429 and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            break
        out.extend(d["embedding"] for d in sorted(r.json()["data"], key=lambda d: d["index"]))
    return out


def embed(cfg: EmbeddingConfiguration, texts: list[str], *, query: bool = False) -> list[list[float]]:
    if not texts:
        return []
    if cfg.provider == "local":
        if query:
            texts = [QUERY_PREFIX_LOCAL + t for t in texts]
        return [v.tolist() for v in _local(cfg.model_name).embed(texts, batch_size=32)]
    return _external(texts, cfg.model_name, "query" if query else "document")


def embed_one(cfg: EmbeddingConfiguration, text: str, *, query: bool = True) -> list[float]:
    return embed(cfg, [text], query=query)[0]
