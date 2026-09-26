"""Turning text into vectors, with no hosted API in the loop.

One interface, two backends:

- `local` runs ONNX inference in-process through fastembed. No network hop
  and no extra container, which is what makes this viable on a small VM.
- `tei` posts to a Hugging Face Text Embedding Inference sidecar.

The single most important detail in this file is that **all local
inference is dispatched to a worker thread**. Embedding is CPU-bound
synchronous work; calling it directly from a coroutine would block the
event loop, which means one student triggering a reindex would stall the
streaming response of every other student on the box. `asyncio.to_thread`
keeps the loop free.

Failures raise `EmbeddingUnavailable` and are always catchable by the
caller: retrieval is an enhancement, and a missing model must degrade the
product to "answered without past-paper quotes" rather than into a 500.
"""
from __future__ import annotations

import asyncio
import threading
from collections.abc import Sequence

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

logger = get_logger(component="embedding_service")


class EmbeddingUnavailable(RuntimeError):
    """Raised when embeddings could not be produced."""


class EmbeddingService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._model_name = settings.embedding_model
        self._dimensions = settings.embedding_dimensions
        self._batch_size = max(1, settings.embedding_batch_size)
        self._backend = settings.embedding_backend
        self._local_model = None
        # fastembed's model registry is not documented as thread-safe, and
        # two concurrent first-uses would otherwise both pay the load cost.
        self._local_lock = threading.Lock()

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def model(self) -> str:
        return self._model_name

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts, preserving input order.

        Empty and whitespace-only input yields no vectors at all rather
        than a vector of zeros — a zero vector has no meaningful cosine
        direction, so it would match everything or nothing depending on
        how the database treats it.
        """
        cleaned = [t for t in texts if t and t.strip()]
        if not cleaned:
            return []
        if self._backend == "tei":
            return await self._embed_tei(cleaned)
        return await self._embed_local(cleaned)

    async def embed_one(self, text: str) -> list[float]:
        vectors = await self.embed([text])
        if not vectors:
            raise EmbeddingUnavailable("Cannot embed empty text")
        return vectors[0]

    # --- local (ONNX in-process) ---

    def _load_local_model(self):
        if self._local_model is not None:
            return self._local_model
        with self._local_lock:
            if self._local_model is not None:
                return self._local_model
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - dependency is declared
                raise EmbeddingUnavailable(
                    "fastembed is not installed; install requirements.txt or set EMBEDDING_BACKEND=tei"
                ) from exc
            logger.info("loading_embedding_model", model=self._model_name, backend="local")
            try:
                self._local_model = TextEmbedding(model_name=self._model_name)
            except Exception as exc:
                raise EmbeddingUnavailable(
                    f"Could not load embedding model {self._model_name!r}: {exc}"
                ) from exc
        return self._local_model

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        # Loading and inference both run off-loop: the first call after a
        # deploy would otherwise block every concurrent request while the
        # model is read off disk.
        try:
            return await asyncio.to_thread(self._embed_local_sync, texts)
        except EmbeddingUnavailable:
            raise
        except Exception as exc:
            raise EmbeddingUnavailable(f"Local embedding failed: {exc}") from exc

    def _embed_local_sync(self, texts: list[str]) -> list[list[float]]:
        model = self._load_local_model()
        collected: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            collected.extend([list(map(float, v)) for v in model.embed(batch)])
        self._assert_dimensions(collected)
        return collected

    # --- TEI sidecar ---

    async def _embed_tei(self, texts: list[str]) -> list[list[float]]:
        url = f"{self._settings.embedding_base_url.rstrip('/')}/embed"
        collected: list[list[float]] = []
        timeout = self._settings.embedding_timeout_seconds
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                for start in range(0, len(texts), self._batch_size):
                    batch = texts[start : start + self._batch_size]
                    response = await client.post(url, json={"inputs": batch})
                    response.raise_for_status()
                    payload = response.json()
                    # TEI returns either a bare list of vectors or a list
                    # of {"embedding": [...]} objects depending on version.
                    for item in payload:
                        collected.append([float(x) for x in (item["embedding"] if isinstance(item, dict) else item)])
        except Exception as exc:
            raise EmbeddingUnavailable(
                f"Text Embedding Inference sidecar at {url} is unavailable: {exc}"
            ) from exc
        self._assert_dimensions(collected)
        return collected

    def _assert_dimensions(self, vectors: list[list[float]]) -> None:
        """Refuse to write vectors the database column cannot hold.

        Catching a width mismatch here turns a confusing
        "expected 384 dimensions, not 768" psycopg error — or worse, a
        silently wrong HNSW index — into a clear configuration bug.
        """
        if not vectors:
            return
        width = len(vectors[0])
        if width != self._dimensions:
            raise EmbeddingUnavailable(
                f"Embedding model {self._model_name!r} produced {width}-dimensional vectors but "
                f"EMBEDDING_DIMENSIONS is {self._dimensions}. Either set EMBEDDING_DIMENSIONS={width} "
                f"together with a migration that resizes the column, or pick a model with "
                f"{self._dimensions} dimensions."
            )
