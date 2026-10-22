"""
Sentence embeddings for the dense metrics.

The thesis computed them with sentence-transformers (PyTorch). This service runs the same
all-MiniLM-L6-v2 weights through ONNX Runtime (fastembed), which keeps the image small. If the model
cannot be loaded, the dense metrics are reported as unavailable: lexical scores are never substituted.
"""
import logging
import threading
from typing import Optional, Protocol, Sequence

import numpy as np

from .framework import EMBEDDING_MODEL

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    model_name: str

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """One L2-normalised row per text."""


def normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


class FastEmbedEmbedder:
    model_name = EMBEDDING_MODEL

    def __init__(self, cache_dir: Optional[str] = None):
        from fastembed import TextEmbedding  # imported here so tests never load ONNX Runtime

        self._model = TextEmbedding(model_name=self.model_name, cache_dir=cache_dir)
        self._lock = threading.Lock()

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        with self._lock:
            vectors = np.asarray(list(self._model.embed(list(texts))), dtype=np.float32)
        return normalize(vectors)


def load_embedder(kind: str, cache_dir: Optional[str] = None) -> Optional[Embedder]:
    if kind == "none":
        return None
    if kind != "fastembed":
        raise ValueError(f"Unknown embedder '{kind}'")
    try:
        embedder = FastEmbedEmbedder(cache_dir)
        embedder.embed(["warm-up"])
        logger.info("Loaded embedding model %s", embedder.model_name)
        return embedder
    except Exception:
        logger.exception("Could not load the embedding model; dense metrics are unavailable")
        return None
