"""Structured progress reporting for the ingestion pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from pkmrag.models import IngestProgress, IngestStage


class IngestProgressReporter:
    """Turns pipeline milestones into structured stage updates.

    Consumers switch on :class:`~pkmrag.models.IngestStage` instead of parsing
    the human-readable ``phase`` text.
    """

    def __init__(
        self,
        callback: Optional[Callable[[IngestProgress], None]],
        model_name: str,
    ) -> None:
        self._callback = callback
        self._model_name = model_name

    def _emit(self, progress: IngestProgress) -> None:
        if self._callback is not None:
            self._callback(progress)

    def scan(self) -> None:
        """Announce the start of the vault scan."""
        self._emit(
            IngestProgress(
                stage=IngestStage.SCAN,
                phase="Scanning vault files",
                cur=0,
                total=1,
            )
        )

    def graph(self, cur: int, total: int) -> None:
        """Report progress of the property graph build."""
        self._emit(
            IngestProgress(
                stage=IngestStage.GRAPH,
                phase="Ingesting graph notes",
                cur=cur,
                total=total,
            )
        )

    def vector(self, cur: int, total: int) -> None:
        """Report progress of the chunk embedding pass."""
        self._emit(
            IngestProgress(
                stage=IngestStage.VECTOR,
                phase="Vectorizing chunks",
                cur=cur,
                total=total,
            )
        )

    def model_download(self, downloaded: int, total: int) -> None:
        """Report byte progress of the embedding model download."""
        self._emit(
            IngestProgress(
                stage=IngestStage.MODEL_DOWNLOAD,
                phase=f"Downloading embedding model ({self._model_name})",
                cur=downloaded,
                total=total,
                unit="bytes",
            )
        )

    def byte_reporter(self) -> Callable[[int, int], None]:
        """Return a callback reporting model download progress in bytes."""

        def report(downloaded: int, total: int) -> None:
            self.model_download(downloaded, total)

        return report
