"""Tests for the byte-accurate embedding model download progress."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional

import pytest

from pkmrag.search import model_download


class _FakeSibling:
    """Stand-in for a HuggingFace repository file entry."""

    def __init__(self, rfilename: str, size: int) -> None:
        self.rfilename = rfilename
        self.size = size


class _FakeModelInfo:
    """Stand-in for the HuggingFace model info response."""

    def __init__(self, siblings: list[_FakeSibling]) -> None:
        self.siblings = siblings


def _patch_hub(
    monkeypatch: pytest.MonkeyPatch,
    sizes: dict[str, int],
    cached: set[str],
) -> None:
    """Replace the HuggingFace calls with deterministic local fakes."""

    class _FakeApi:
        def model_info(self, repo_id: str, files_metadata: bool = False) -> _FakeModelInfo:
            return _FakeModelInfo([_FakeSibling(name, size) for name, size in sizes.items()])

    def fake_download(
        repo_id: str,
        filename: str,
        cache_dir: Optional[Path] = None,
        tqdm_class: Optional[Any] = None,
        local_files_only: bool = False,
        **kwargs: Any,
    ) -> str:
        if local_files_only:
            raise FileNotFoundError(filename)
        size = sizes[filename]
        if tqdm_class is not None:
            bar = tqdm_class(total=size, file=io.StringIO())
            step = max(size // 10, 1)
            while bar.n < size:
                bar.update(min(step, size - bar.n))
            bar.close()
        return str(Path(cache_dir or Path(".")) / filename)

    monkeypatch.setattr(model_download, "HfApi", _FakeApi)
    monkeypatch.setattr(model_download, "hf_hub_download", fake_download)
    monkeypatch.setattr(
        model_download,
        "_model_spec",
        lambda name: ("Qdrant/test-model", "model.onnx", ["model.onnx"]),
    )
    monkeypatch.setattr(
        model_download,
        "_is_cached",
        lambda repo_id, filename, cache_dir: filename in cached,
    )
    monkeypatch.setattr(model_download, "_cache_dir", lambda: Path("/tmp/pkmrag-test-cache"))


def test_prefetch_model_reports_throttled_byte_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify byte progress is reported once per whole percentage point."""
    sizes = {"model.onnx": 64 * 1024 * 1024}
    _patch_hub(monkeypatch, sizes, cached=set())

    reported: list[tuple[int, int]] = []
    ok = model_download.prefetch_model(
        "BAAI/bge-small-en-v1.5", lambda done, total: reported.append((done, total))
    )

    assert ok is True
    assert reported, "no download progress was reported"
    assert reported[-1] == (64 * 1024 * 1024, 64 * 1024 * 1024)
    percents = [int(done * 100 / total) for done, total in reported]
    assert percents == sorted(percents)
    assert len(percents) == len(set(percents)), "progress updates were not throttled"


def test_prefetch_model_skips_cached_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify an already cached model reports no download progress."""
    sizes = {"model.onnx": 1024}
    _patch_hub(monkeypatch, sizes, cached={"model.onnx"})

    reported: list[tuple[int, int]] = []
    ok = model_download.prefetch_model(
        "BAAI/bge-small-en-v1.5", lambda done, total: reported.append((done, total))
    )

    assert ok is True
    assert reported == []


def test_model_is_cached_reports_the_local_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify the cache probe reflects the presence of the model file."""
    _patch_hub(monkeypatch, {"model.onnx": 10}, cached={"model.onnx"})
    assert model_download.model_is_cached("BAAI/bge-small-en-v1.5") is True

    _patch_hub(monkeypatch, {"model.onnx": 10}, cached=set())
    assert model_download.model_is_cached("BAAI/bge-small-en-v1.5") is False
