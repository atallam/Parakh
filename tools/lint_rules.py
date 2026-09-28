"""Repo rules that ruff and pyright can't express (plan 14 L0).

- Token lint (AC-F22.1): no hex colour outside config/ui_tokens.yaml.
- Layering lint (plan 14 L0, plan 15 §4.1): `app/` and `src/parakh/mcp/` never import
  analytics, lenses or adapters; they go through services (ADR-006, P2).

Run: `uv run python tools/lint_rules.py` (pre-commit and CI run it; tests call the functions).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEX = re.compile(r"(?<![\w&/])#(?:[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
TOKEN_FILE = ROOT / "config" / "ui_tokens.yaml"
TOKEN_SCAN_SUFFIXES = {
    ".py",
    ".yaml",
    ".yml",
    ".toml",
    ".css",
    ".html",
    ".j2",
    ".jinja",
    ".js",
    ".json",
}
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".ruff_cache",
    ".pytest_cache",
    "state",
    "data",
}

LAYERED = {
    "app": ROOT / "app",
    "src/parakh/mcp": ROOT / "src" / "parakh" / "mcp",
}
FORBIDDEN_IMPORTS = ("parakh.analytics", "parakh.lenses", "parakh.adapters")


def _files(root: Path, suffixes: set[str]) -> list[Path]:
    out = []
    for path in root.rglob("*"):
        if (
            path.is_file()
            and path.suffix in suffixes
            and not (set(path.relative_to(root).parts) & SKIP_DIRS)
        ):
            out.append(path)
    return sorted(out)


def token_lint(root: Path = ROOT) -> list[str]:
    problems = []
    for path in _files(root, TOKEN_SCAN_SUFFIXES):
        if path.resolve() == TOKEN_FILE.resolve():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
        ):
            for match in HEX.finditer(line):
                problems.append(
                    f"{path.relative_to(root)}:{lineno}: hex colour {match.group()} (use ui_tokens.yaml)"
                )
    return problems


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.lineno, node.module))
    return found


def layering_lint(root: Path = ROOT) -> list[str]:
    problems = []
    for label, folder in LAYERED.items():
        base = root / folder.relative_to(ROOT)
        if not base.exists():
            continue
        for path in _files(base, {".py"}):
            for lineno, module in _imports(path):
                if module.startswith(FORBIDDEN_IMPORTS):
                    problems.append(
                        f"{path.relative_to(root)}:{lineno}: {label} imports {module}; go through services"
                    )
    return problems


def main() -> int:
    problems = token_lint() + layering_lint()
    for p in problems:
        print(p, file=sys.stderr)
    if not problems:
        print("token and layering lint OK")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
