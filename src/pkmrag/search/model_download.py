"""Byte-accurate pre-fetch of the local embedding model weights.

FastEmbed pulls the ONNX weights through HuggingFace Hub without exposing byte
progress. Pre-fetching the same snapshot files with ``hf_hub_download`` lets the
ingest pipeline report real download progress; FastEmbed then loads the
already cached weights.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils.tqdm import tqdm as hf_tqdm

logger = logging.getLogger(__name__)

# Files FastEmbed expects in the HuggingFace snapshot of an ONNX text model.
CONFIG_FILES = (
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "preprocessor_config.json",
)

# Reporter for the transfer currently in flight; read by the tqdm subclass.
_active_reporter: Optional[Callable[[int, int], None]] = None


class _ProgressTqdm(hf_tqdm):
    """tqdm subclass mirroring HuggingFace byte progress into the active reporter."""

    def update(self, n: float = 1) -> Optional[bool]:
        result: Optional[bool] = super().update(n)
        reporter = _active_reporter
        if reporter is not None:
            reporter(int(self.n), int(self.total or 0))
        return result


class _TransferTracker:
    """Accumulates per-file byte progress into a single transfer total.

    Updates are throttled to whole percentage points so a fast transfer does
    not flood the event stream with thousands of progress messages.
    """

    def __init__(self, total_bytes: int, on_progress: Callable[[int, int], None]) -> None:
        self.total_bytes = total_bytes
        self.on_progress = on_progress
        self.completed = 0
        self._last_percent = -1

    def file_cached(self, size: int) -> None:
        """Record a file that was already present in the cache."""
        self.completed += size

    def file_reporter(self) -> Callable[[int, int], None]:
        """Return a reporter bound to the file currently being transferred."""

        def report(done: int, _file_total: int) -> None:
            self.report(self.completed + done)

        return report

    def file_finished(self, size: int) -> None:
        """Record a file that finished downloading."""
        self.completed += size
        self.report(self.completed)

    def report(self, downloaded: int) -> None:
        percent = int(downloaded * 100 / self.total_bytes) if self.total_bytes else 0
        if percent == self._last_percent:
            return
        self._last_percent = percent
        self.on_progress(downloaded, self.total_bytes)


def _cache_dir() -> Path:
    """Resolve the cache directory FastEmbed uses for model weights."""
    try:
        from fastembed.common.utils import define_cache_dir

        return define_cache_dir(None)
    except Exception:  # pragma: no cover - depends on the installed fastembed
        default = Path(tempfile.gettempdir()) / "fastembed_cache"
        return Path(os.environ.get("FASTEMBED_CACHE_PATH", str(default)))


def _model_spec(model_name: str) -> Optional[tuple[str, str, list[str]]]:
    """Return the HuggingFace repo, the ONNX file and the snapshot files of a model."""
    from fastembed import TextEmbedding

    for model in TextEmbedding.list_supported_models():
        if str(model.get("model", "")).lower() != model_name.lower():
            continue
        repo = model.get("sources", {}).get("hf")
        model_file = model.get("model_file")
        if not repo or not model_file:
            return None
        extra = [str(f) for f in model.get("additional_files", [])]
        return str(repo), str(model_file), [*CONFIG_FILES, str(model_file), *extra]
    return None


def _is_cached(repo_id: str, filename: str, cache_dir: Path) -> bool:
    """Report whether a snapshot file is already present in the local cache."""
    try:
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            cache_dir=cache_dir,
            local_files_only=True,
        )
        return True
    except Exception:
        return False


def model_is_cached(model_name: str) -> bool:
    """Report whether the embedding model weights are already available locally."""
    spec = _model_spec(model_name)
    if spec is None:
        return False
    repo_id, model_file, _ = spec
    return _is_cached(repo_id, model_file, _cache_dir())


def prefetch_model(model_name: str, on_progress: Callable[[int, int], None]) -> bool:
    """Download the embedding model weights into the shared HuggingFace cache.

    ``on_progress`` receives ``(downloaded_bytes, total_bytes)`` as the transfer
    advances. Returns True when every required file is available afterwards.
    """
    global _active_reporter

    spec = _model_spec(model_name)
    if spec is None:
        return False
    repo_id, _, desired = spec
    cache_dir = _cache_dir()

    try:
        info = HfApi().model_info(repo_id, files_metadata=True)
    except Exception as exc:
        logger.debug("Could not read the model manifest for %s: %s", repo_id, exc)
        return False

    available = {sibling.rfilename: int(sibling.size or 0) for sibling in info.siblings or []}
    files = [name for name in desired if name in available]
    if not files:
        return False
    total_bytes = sum(available[name] for name in files)

    tracker = _TransferTracker(total_bytes, on_progress)
    try:
        for name in files:
            size = available[name]
            if _is_cached(repo_id, name, cache_dir):
                tracker.file_cached(size)
                continue
            _active_reporter = tracker.file_reporter()
            try:
                hf_hub_download(
                    repo_id=repo_id,
                    filename=name,
                    cache_dir=cache_dir,
                    tqdm_class=_ProgressTqdm,
                )
            except Exception as exc:
                logger.debug("Could not pre-fetch %s from %s: %s", name, repo_id, exc)
                return False
            finally:
                _active_reporter = None
            tracker.file_finished(size)
    finally:
        _active_reporter = None
    return True
