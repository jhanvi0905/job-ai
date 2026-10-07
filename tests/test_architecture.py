"""Layering contract: core <- engine <- {product, assistant}. The product never
depends on the single-user assistant, and the engine stays tenant-agnostic."""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "jobai"
FORBIDDEN = {
    "core": ("jobai.engine", "jobai.product", "jobai.assistant"),
    "engine": ("jobai.product", "jobai.assistant"),
    "product": ("jobai.assistant",),
    "assistant": ("jobai.product",),
}


def _imports(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    return names


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_layer_does_not_import_forbidden_layers(layer):
    violations = [
        f"{path.relative_to(SRC)} imports {name}"
        for path in (SRC / layer).rglob("*.py")
        for name in _imports(path)
        if name.startswith(FORBIDDEN[layer])
    ]
    assert not violations, "\n".join(violations)
