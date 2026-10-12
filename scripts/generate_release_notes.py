"""Generate concise, standardized release notes for GitHub Releases."""

from __future__ import annotations

import os
import subprocess
import sys


def get_prev_tag(tag: str) -> str:
    """Find the tag immediately preceding the given tag."""
    cmd = ["git", "describe", "--tags", "--abbrev=0", f"{tag}^"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.stdout.strip() if res.returncode == 0 else ""


def get_commits(prev_tag: str, tag: str) -> list[tuple[str, str]]:
    """Return list of (sha, commit_message) between prev_tag and tag."""
    if prev_tag:
        cmd = ["git", "log", f"{prev_tag}..{tag}", "--oneline", "--no-merges"]
    else:
        cmd = ["git", "log", "-n", "10", "--oneline", "--no-merges"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    commits: list[tuple[str, str]] = []
    for line in res.stdout.strip().splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            commits.append((parts[0], parts[1]))
    return commits


def generate_notes(tag: str, repo: str) -> str:
    """Format compact release notes with installation instructions and changelog."""
    prev_tag = get_prev_tag(tag)
    commits = get_commits(prev_tag, tag)

    lines: list[str] = [
        f"### 🛰️ PKMRAG `{tag}`",
        "Local-first Hybrid GraphRAG Context Engine & Model Context Protocol (MCP) Server.",
        "",
        "#### 📦 Quick Install / Upgrade",
        "```bash",
        "pipx install pkmrag",
        "pipx upgrade pkmrag",
        "```",
        "",
        "#### 💎 Obsidian Companion Plugin",
        "```bash",
        "pkmrag install-plugin /path/to/vault",
        "```",
        "*(Or manually download `main.js`, `manifest.json`, and `styles.css` from assets below)*",
        "",
        "#### 📋 What's Changed",
    ]

    if commits:
        for sha, msg in commits:
            lines.append(f"- {msg} ([`{sha}`](https://github.com/{repo}/commit/{sha}))")
    else:
        lines.append("- Performance improvements and minor maintenance.")

    lines.append("")
    if prev_tag:
        lines.append(
            f"**Full Diff:** [{prev_tag}...{tag}](https://github.com/{repo}/compare/{prev_tag}...{tag})"
        )
    else:
        lines.append(f"**Source Code:** [{tag}](https://github.com/{repo}/tree/{tag})")

    return "\n".join(lines) + "\n"


def main() -> None:
    tag = os.environ.get("GITHUB_REF_NAME") or (sys.argv[1] if len(sys.argv) > 1 else "v0.9.1")
    repo = os.environ.get("GITHUB_REPOSITORY") or "dev-hashemi/pkmrag"
    print(generate_notes(tag, repo), end="")


if __name__ == "__main__":
    main()
