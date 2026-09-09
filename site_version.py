"""The version and commit this process was built from.

Read by `main.py` (the FastAPI `version`, `/health`) and by `api/routes.py`
(`GET /api/v1/status`'s `site` block). `SITE_VERSION` tries the installed
package's own metadata first and falls back to the `pyproject.toml` literal:
the API image is built with `uv sync --no-install-project`, which never
installs this package under its own name, so the installed lookup always
misses there and the literal is what ships. `GIT_COMMIT` comes from the
`GIT_COMMIT` environment variable, set by `Dockerfile` and
`frontend/Dockerfile`'s matching `ARG`/`ENV` pair from the sha
`.github/workflows/deploy.yml` builds; a process started without it (a dev
server, a build outside CI) reports `"unknown"`.
"""

from __future__ import annotations

import importlib.metadata
import os

_PYPROJECT_VERSION = "0.1.0"


def _site_version() -> str:
    try:
        return importlib.metadata.version("statutes-linkedlegislation")
    except importlib.metadata.PackageNotFoundError:
        return _PYPROJECT_VERSION


SITE_VERSION = _site_version()
GIT_COMMIT = os.environ.get("GIT_COMMIT") or "unknown"
