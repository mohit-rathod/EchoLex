import ast
from pathlib import Path


CANONICAL_ROOTS = [
    Path("src/echolex/core"),
    Path("src/echolex/domain"),
    Path("src/echolex/ingestion"),
    Path("src/echolex/retrieval"),
    Path("src/echolex/voice"),
    Path("src/echolex/integrations"),
    Path("src/echolex/cli"),
]
LEGACY_PREFIXES = (
    "echolex.config",
    "echolex.chunking",
    "echolex.rag",
    "echolex.processors",
    "echolex.services",
)


def test_canonical_modules_do_not_depend_on_compatibility_paths() -> None:
    violations: list[str] = []

    for root in CANONICAL_ROOTS:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module.startswith(LEGACY_PREFIXES):
                        violations.append(f"{path}:{node.lineno} imports {node.module}")
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith(LEGACY_PREFIXES):
                            violations.append(f"{path}:{node.lineno} imports {alias.name}")

    assert violations == []
