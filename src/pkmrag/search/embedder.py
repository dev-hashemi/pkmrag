"""Embedding provider protocol and local FastEmbed implementation."""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from pkmrag.config import settings


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for pluggable vector embedding models."""

    @property
    def model_name(self) -> str:
        """Name or identifier of the underlying model."""
        ...

    @property
    def dimension(self) -> int:
        """Dimensionality of produced vector embeddings."""
        ...

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for a list of document chunks."""
        ...

    def embed_query(self, query: str) -> list[float]:
        """Compute an embedding for a single search query."""
        ...


class FastEmbedProvider:
    """In-process embedding provider powered by FastEmbed and ONNX runtime."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        dimension: Optional[int] = None,
        batch_size: int = 64,
    ) -> None:
        self._model_name = model_name or settings.embedding_model
        self._dimension = dimension or settings.embedding_dim
        self.batch_size = batch_size
        self._model: Optional[Any] = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_model(self) -> Any:
        """Lazy-load the FastEmbed TextEmbedding instance."""
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self._model_name)
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for a collection of chunk texts."""
        if not texts:
            return []

        model = self._get_model()
        # Ensure non-empty strings so tokenizers do not raise
        cleaned = [t if t.strip() else " " for t in texts]
        raw_embeddings = model.embed(cleaned, batch_size=self.batch_size)
        return [list(map(float, vec)) for vec in raw_embeddings]

    def embed_query(self, query: str) -> list[float]:
        """Compute embedding for a single user query."""
        cleaned = query.strip() or " "
        model = self._get_model()
        # FastEmbed model.query_embed handles BGE query prefixes if applicable
        raw = list(model.query_embed(cleaned))
        return list(map(float, raw[0]))
