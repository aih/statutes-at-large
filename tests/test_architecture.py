"""The boundaries, enforced instead of remembered: no SQL outside storage/ and
ingest/, no `db.models` in the API, no template engine anywhere."""

import ast
from pathlib import Path

from tests.conftest import REPO_ROOT

API = REPO_ROOT / "api"
SHARED = [REPO_ROOT / "main.py", REPO_ROOT / "citation.py", REPO_ROOT / "params.py", REPO_ROOT / "uslmtext.py"]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _modules(*roots: Path) -> list[Path]:
    return [p for root in roots for p in ([root] if root.is_file() else list(root.rglob("*.py")))]


def test_the_api_never_imports_the_models():
    offenders = {
        str(path.relative_to(REPO_ROOT)): sorted(n for n in _imports(path) if n.startswith("db"))
        for path in _modules(API, *SHARED)
    }
    assert {k: v for k, v in offenders.items() if v} == {}


def test_only_storage_and_ingest_write_sql():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _modules(API, *SHARED)
        if any(n.startswith("sqlalchemy") for n in _imports(path))
    ]
    assert offenders == []


def test_no_python_module_renders_html():
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _modules(API, REPO_ROOT / "storage", REPO_ROOT / "ingest", *SHARED)
        if any(n.startswith(("jinja2", "mako")) for n in _imports(path))
    ]
    assert offenders == []


def test_the_govinfo_key_is_not_in_source():
    """The key comes from the environment (`GOVINFO_API_KEY`), never from a file."""
    import re

    suspicious = []
    for path in REPO_ROOT.rglob("*"):
        if path.is_dir() or ".venv" in path.parts or ".git" in path.parts or "data" in path.parts:
            continue
        if path.suffix not in {".py", ".md", ".yml", ".yaml", ".toml", ".json", ".xml", ".ini", ".example", ""} and path.name != "Makefile":
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for match in re.finditer(r"api_key=([A-Za-z0-9]{20,})", text):
            suspicious.append((str(path.relative_to(REPO_ROOT)), match.group(1)[:6]))
    assert suspicious == []


def test_the_citation_parser_is_pure():
    """`citeparse.py` knows what string names an identifier and nothing about
    what exists: no storage, db, fastapi or sqlalchemy (the US Code site's
    ADR-0023), so its accepted-forms table runs with no database."""
    names = _imports(REPO_ROOT / "citeparse.py")
    offenders = sorted(n for n in names if n.split(".")[0] in {"storage", "db", "fastapi", "sqlalchemy", "httpx", "api", "params"})
    assert offenders == []
