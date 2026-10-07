"""Obsidian plugin installation and vault integration."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pkmrag.models import PluginInstallResult


def find_plugin_dir() -> Path:
    """Locate the Obsidian plugin source directory."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "plugins" / "obsidian",
        Path.cwd() / "plugins" / "obsidian",
    ]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "manifest.json").is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not locate 'plugins/obsidian' directory containing manifest.json."
    )


def build_plugin(plugin_dir: Path) -> None:
    """Build the Obsidian plugin using npm."""
    npm_path = shutil.which("npm")
    if not npm_path:
        raise RuntimeError("npm is not installed or not found in PATH. Cannot build plugin.")
    result = subprocess.run(
        [npm_path, "run", "build"],
        cwd=plugin_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Failed to build Obsidian plugin:\n{error_msg}")


def install_obsidian_plugin(
    vault_path: Path | str,
    symlink: bool = False,
    build: bool = False,
    enable: bool = True,
    plugin_dir: Optional[Path] = None,
) -> PluginInstallResult:
    """Install the Obsidian desktop plugin into the specified vault."""
    vault = Path(vault_path).expanduser().resolve()
    if not vault.exists() or not vault.is_dir():
        raise ValueError(f"Vault path does not exist or is not a directory: {vault}")

    source_dir = plugin_dir.resolve() if plugin_dir else find_plugin_dir()
    manifest_path = source_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json not found in {source_dir}")

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    plugin_id: str = manifest_data.get("id", "pkmrag")

    did_build = False
    main_js = source_dir / "main.js"
    if build or not main_js.is_file():
        build_plugin(source_dir)
        did_build = True

    if not main_js.is_file():
        raise FileNotFoundError(f"main.js not found in {source_dir} after build.")

    target_dir = vault / ".obsidian" / "plugins" / plugin_id
    target_dir.mkdir(parents=True, exist_ok=True)

    files_to_install = ["manifest.json", "main.js"]
    if (source_dir / "styles.css").is_file():
        files_to_install.append("styles.css")
    if (source_dir / "icon.svg").is_file():
        files_to_install.append("icon.svg")

    installed_files: list[str] = []
    for fname in files_to_install:
        src = source_dir / fname
        dst = target_dir / fname
        if dst.is_symlink() or dst.exists():
            dst.unlink()

        if symlink:
            dst.symlink_to(src.resolve())
        else:
            shutil.copy2(src, dst)
        installed_files.append(fname)

    is_enabled = False
    if enable:
        obsidian_dir = vault / ".obsidian"
        obsidian_dir.mkdir(parents=True, exist_ok=True)
        comm_file = obsidian_dir / "community-plugins.json"
        try:
            if comm_file.is_file():
                content = comm_file.read_text(encoding="utf-8").strip()
                data = json.loads(content) if content else []
                if isinstance(data, list):
                    if plugin_id not in data:
                        data.append(plugin_id)
                        comm_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                    is_enabled = True
            else:
                comm_file.write_text(json.dumps([plugin_id], indent=2), encoding="utf-8")
                is_enabled = True
        except Exception:
            is_enabled = False

    return PluginInstallResult(
        vault_path=str(vault),
        target_dir=str(target_dir),
        plugin_id=plugin_id,
        installed_files=installed_files,
        symlinked=symlink,
        enabled=is_enabled,
        built=did_build,
    )


def render_plugin_install_result(result: PluginInstallResult, console: Console) -> None:
    """Render plugin installation summary table and instructions."""
    title = (
        f"[bold green]✓ PKMRAG Obsidian Plugin Installed[/bold green] "
        f"([cyan]{result.plugin_id}[/cyan])"
    )
    console.print(Panel.fit(title, border_style="green"))

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold dim")
    table.add_column("Value", style="cyan")

    table.add_row("Vault", result.vault_path)
    table.add_row("Plugin Path", result.target_dir)
    mode_str = "[yellow]Symlinked[/yellow]" if result.symlinked else "[green]Copied[/green]"
    table.add_row("Install Mode", mode_str)
    table.add_row("Files", ", ".join(result.installed_files))
    if result.built:
        table.add_row("Build", "[green]Compiled with npm[/green]")
    status_str = (
        "[green]Enabled in community-plugins.json[/green]"
        if result.enabled
        else "[yellow]Manual enable needed[/yellow]"
    )
    table.add_row("Status", status_str)

    console.print(table)
    console.print()
    console.print("[bold]Next Steps:[/bold]")
    console.print("  1. In Obsidian: Reload plugins (or restart Obsidian).")
    console.print(
        "  2. Open [bold]Settings → Community Plugins[/bold] to verify Orbit Insights is active."
    )
    console.print("  3. Start the PKMRAG background daemon:")
    console.print(
        f'     [bold green]uv run pkmrag serve "{result.vault_path}" '
        f"-t http --port 3747[/bold green]"
    )


def register_plugin_command(app: typer.Typer) -> None:
    """Register install-plugin command with the Typer CLI app."""

    @app.command(name="install-plugin")
    def install_plugin(
        vault_path: Optional[Path] = typer.Argument(
            None,
            help="Path to Obsidian vault (defaults to PKMRAG_VAULT_PATH in .env).",
        ),
        symlink: bool = typer.Option(
            False,
            "--symlink",
            "-s",
            help="Symlink files instead of copying (recommended for live development).",
        ),
        build: bool = typer.Option(
            False,
            "--build",
            "-b",
            help="Rebuild plugin with npm before installing.",
        ),
        enable: bool = typer.Option(
            True,
            "--enable/--no-enable",
            help="Auto-enable plugin in .obsidian/community-plugins.json.",
        ),
        json_output: bool = typer.Option(
            False,
            "--json",
            help="Output installation result in raw JSON format.",
        ),
    ) -> None:
        """Install the PKMRAG Obsidian desktop plugin into your vault."""
        from pkmrag.config import load_vault_env

        console = Console()
        cfg = load_vault_env()
        target_vault = vault_path or cfg.vault_path

        if not target_vault:
            console.print("[bold red]Error:[/bold red] Vault path not specified.")
            console.print(
                "Set [bold cyan]PKMRAG_VAULT_PATH[/bold cyan] in your [green].env[/green] file, "
                "or pass the vault path as an argument:"
            )
            console.print("  [dim]uv run pkmrag install-plugin /path/to/your/vault[/dim]")
            sys.exit(1)

        try:
            result = install_obsidian_plugin(
                vault_path=target_vault,
                symlink=symlink,
                build=build,
                enable=enable,
            )
        except Exception as e:
            console.print(f"[bold red]Installation failed:[/bold red] {e}")
            sys.exit(1)

        if json_output:
            console.print_json(result.model_dump_json())
        else:
            render_plugin_install_result(result, console)
