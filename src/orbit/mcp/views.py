"""Terminal display renderers for MCP HTTP/SSE server and client configurations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from orbit import __version__
from orbit.mcp.auth import get_token_file_path


def render_server_startup(
    vault_path: Path,
    host: str,
    port: int,
    token: str = "",
    no_auth: bool = False,
    console: Optional[Console] = None,
) -> None:
    """Render startup banner with server address, endpoints, and token info."""
    c = console or Console()
    header = (
        f"[bold cyan]Project Orbit[/bold cyan] v[green]{__version__}[/green] "
        "— HTTP & SSE Knowledge Server"
    )
    c.print(Panel.fit(header, border_style="cyan"))

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="bold dim")
    table.add_column("Value", style="cyan")

    table.add_row("Vault", str(vault_path))
    table.add_row("Listen Address", f"http://{host}:{port}")
    table.add_row("MCP SSE Endpoint", f"http://{host}:{port}/sse")
    table.add_row("REST API Prefix", f"http://{host}:{port}/api/v1")
    table.add_row("Health Probe", f"http://{host}:{port}/health")

    if no_auth or not token:
        table.add_row("Authentication", "[yellow]Disabled (--no-auth)[/yellow]")
    else:
        token_path = get_token_file_path(vault_path)
        table.add_row("Authentication", "[green]Enabled (Bearer token)[/green]")
        table.add_row("Token File", f"[dim]{token_path}[/dim]")
        masked = token[:6] + "..." + token[-4:] if len(token) > 10 else "***"
        table.add_row("Active Token", f"[bold magenta]{masked}[/bold magenta]")

    c.print(table)
    c.print()


def render_mcp_config(
    vault_path: Path,
    console: Optional[Console] = None,
    transport: str = "stdio",
    port: int = 3747,
) -> None:
    """Render ready-to-use MCP configuration snippets for Claude and Cursor."""
    c = console or Console()
    resolved = vault_path.resolve()

    if transport in ("http", "sse"):
        from orbit.mcp.auth import resolve_server_token

        tok = resolve_server_token(resolved)
        headers = {"Authorization": f"Bearer {tok}"} if tok else {}
        cfg = {
            "mcpServers": {
                "orbit": {
                    "url": f"http://127.0.0.1:{port}/sse",
                    "headers": headers,
                }
            }
        }
        c.print("[bold green]Claude Desktop / Cursor (SSE Configuration):[/bold green]\n")
        c.print_json(json.dumps(cfg, indent=2))
        return

    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    is_dev = (repo_root / "pyproject.toml").is_file()
    cmd = "uv" if is_dev else "orbit"
    args = (
        ["--directory", str(repo_root), "run", "orbit", "serve", str(resolved)]
        if is_dev
        else ["serve", str(resolved)]
    )
    cfg = {"mcpServers": {"orbit": {"command": cmd, "args": args}}}
    c.print("[bold green]Claude Desktop / Cursor Configuration:[/bold green]\n")
    c.print_json(json.dumps(cfg, indent=2))
    cmd_str = (
        f"opencode mcp add orbit -- uv --directory {repo_root} run orbit serve {resolved}"
        if is_dev
        else f"opencode mcp add orbit -- orbit serve {resolved}"
    )
    c.print("\n[bold cyan]OpenCode CLI (One-Line Setup):[/bold cyan]")
    c.print(f"[white]{cmd_str}[/white]\n")
