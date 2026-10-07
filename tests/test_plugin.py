"""Tests for Obsidian plugin installer and CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from pkmrag.cli import app
from pkmrag.models import PluginInstallResult
from pkmrag.plugin import find_plugin_dir, install_obsidian_plugin

runner = CliRunner()


def _extract_json(text: str) -> Any:
    """Robustly extract and parse JSON payload from CLI output."""
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue

    return json.loads(text)


def test_find_plugin_dir() -> None:
    """Verify find_plugin_dir successfully locates plugins/obsidian."""
    plugin_dir = find_plugin_dir()
    assert plugin_dir.is_dir()
    assert (plugin_dir / "manifest.json").is_file()
    assert (plugin_dir / "main.js").is_file()


def test_install_obsidian_plugin_copy(tmp_path: Path) -> None:
    """Verify install_obsidian_plugin copies files into vault."""
    vault = tmp_path / "test_vault"
    vault.mkdir()

    result = install_obsidian_plugin(vault_path=vault, symlink=False, enable=True)

    assert isinstance(result, PluginInstallResult)
    assert result.plugin_id == "pkmrag"
    assert result.symlinked is False
    assert result.enabled is True

    target_dir = vault / ".obsidian" / "plugins" / "pkmrag"
    assert target_dir.is_dir()

    manifest_file = target_dir / "manifest.json"
    main_file = target_dir / "main.js"
    styles_file = target_dir / "styles.css"

    assert manifest_file.is_file() and not manifest_file.is_symlink()
    assert main_file.is_file() and not main_file.is_symlink()
    assert styles_file.is_file() and not styles_file.is_symlink()

    # Verify community-plugins.json was created
    comm_file = vault / ".obsidian" / "community-plugins.json"
    assert comm_file.is_file()
    enabled_list = json.loads(comm_file.read_text(encoding="utf-8"))
    assert "pkmrag" in enabled_list


def test_install_obsidian_plugin_symlink(tmp_path: Path) -> None:
    """Verify install_obsidian_plugin creates symlinks when requested."""
    vault = tmp_path / "test_vault"
    vault.mkdir()

    result = install_obsidian_plugin(vault_path=vault, symlink=True, enable=False)

    assert result.symlinked is True
    assert result.enabled is False

    target_dir = vault / ".obsidian" / "plugins" / "pkmrag"
    assert target_dir.is_dir()

    manifest_file = target_dir / "manifest.json"
    main_file = target_dir / "main.js"

    assert manifest_file.is_symlink()
    assert main_file.is_symlink()


def test_install_obsidian_plugin_existing_community_plugins(tmp_path: Path) -> None:
    """Verify auto-enable preserves existing community plugins without duplicates."""
    vault = tmp_path / "test_vault"
    obsidian_dir = vault / ".obsidian"
    obsidian_dir.mkdir(parents=True)
    comm_file = obsidian_dir / "community-plugins.json"
    comm_file.write_text(json.dumps(["dataview", "templater"]), encoding="utf-8")

    install_obsidian_plugin(vault_path=vault, enable=True)

    enabled_list = json.loads(comm_file.read_text(encoding="utf-8"))
    assert enabled_list == ["dataview", "templater", "pkmrag"]

    # Re-installing should not duplicate
    install_obsidian_plugin(vault_path=vault, enable=True)
    re_list = json.loads(comm_file.read_text(encoding="utf-8"))
    assert re_list == ["dataview", "templater", "pkmrag"]


def test_install_obsidian_plugin_invalid_vault() -> None:
    """Verify error when vault directory does not exist."""
    with pytest.raises(ValueError, match="does not exist or is not a directory"):
        install_obsidian_plugin(vault_path="/nonexistent/vault/path/pkmrag")


def test_cli_install_plugin_with_argument(tmp_path: Path) -> None:
    """Verify CLI install-plugin command with explicit vault argument."""
    vault = tmp_path / "test_vault"
    vault.mkdir()

    res = runner.invoke(app, ["install-plugin", str(vault), "--json"])
    assert res.exit_code == 0
    data = _extract_json(res.output)
    assert data["plugin_id"] == "pkmrag"
    assert data["vault_path"] == str(vault.resolve())
    assert (vault / ".obsidian" / "plugins" / "pkmrag" / "main.js").is_file()


def test_cli_install_plugin_with_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI install-plugin uses PKMRAG_VAULT_PATH from environment."""
    vault = tmp_path / "env_vault"
    vault.mkdir()

    monkeypatch.setenv("PKMRAG_VAULT_PATH", str(vault))

    res = runner.invoke(app, ["install-plugin", "--json"])
    assert res.exit_code == 0
    data = _extract_json(res.output)
    assert data["vault_path"] == str(vault.resolve())
    assert (vault / ".obsidian" / "plugins" / "pkmrag" / "manifest.json").is_file()


def test_cli_install_plugin_missing_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify CLI exits with code 1 when no vault path is provided or configured."""
    monkeypatch.delenv("PKMRAG_VAULT_PATH", raising=False)
    monkeypatch.delenv("VAULT_PATH", raising=False)
    monkeypatch.delenv("OBSIDIAN_VAULT_PATH", raising=False)

    res = runner.invoke(app, ["install-plugin"])
    assert res.exit_code == 1
    assert "Vault path not specified" in res.output
