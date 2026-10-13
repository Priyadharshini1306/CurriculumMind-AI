"""Sentence-transformers embeddings (all-MiniLM-L6-v2, 384 dims), stored in Neo4j vector indexes."""
import asyncio
import logging
import threading
import time

log = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None
_load_lock = threading.Lock()  # concurrent first loads from worker threads corrupt model initialisation


class EmbeddingError(Exception):
    pass


def _get_model():
    global _model
    with _load_lock:
        if _model is None:
            try:
                from sentence_transformers import SentenceTransformer  # heavy import, load lazily
                _model = SentenceTransformer(MODEL_NAME)
            except Exception as e:
                raise EmbeddingError(f"Could not load embedding model: {e}") from e
        return _model


def embed_sync(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    vecs = _get_model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [[float(x) for x in v] for v in vecs]


async def embed(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(embed_sync, texts)


async def warmup() -> None:
    """Load the model (import torch, read/download the weights, run one encode) at server start instead of on the first
    user's "save concept map" click, where it can take minutes on a fresh deploy. Best effort: a failure here just means
    the first real call loads it as before."""
    t0 = time.perf_counter()
    try:
        await asyncio.to_thread(embed_sync, ["warm up"])
        log.info("embedding model ready in %.1fs", time.perf_counter() - t0)
    except Exception as e:
        log.warning("embedding warm-up failed (will retry on first use): %s", e)
