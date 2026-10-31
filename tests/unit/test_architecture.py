"""The dependency rule, enforced: domain imports nothing outward; application never imports infrastructure
or interfaces; infrastructure never imports interfaces. A violation fails CI instead of a code review."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "bizops"
LAYERS = ["domain", "application", "infrastructure", "interfaces"]  # inner to outer
FORBIDDEN = {
    "domain": {"application", "infrastructure", "interfaces"},
    "application": {"infrastructure", "interfaces"},
    "infrastructure": {"interfaces"},
    "interfaces": set(),
}


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text())
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            out.extend((node.lineno, a.name) for a in node.names)
    return out


@pytest.mark.parametrize("layer", LAYERS)
def test_dependency_rule(layer: str) -> None:
    violations = []
    for path in sorted((SRC / layer).rglob("*.py")):
        for lineno, module in _imports(path):
            parts = module.split(".")
            if parts[0] == "bizops" and len(parts) > 1 and parts[1] in FORBIDDEN[layer]:
                violations.append(f"{path.relative_to(SRC)}:{lineno} imports {module}")
    assert not violations, "\n".join(violations)


def test_domain_has_no_io_imports() -> None:
    banned = {"sqlite3", "httpx", "anthropic", "mcp", "os", "pathlib"}
    found = [
        f"{p.relative_to(SRC)}:{n} {m}"
        for p in (SRC / "domain").rglob("*.py")
        for n, m in _imports(p)
        if m.split(".")[0] in banned
    ]
    assert not found, "\n".join(found)
