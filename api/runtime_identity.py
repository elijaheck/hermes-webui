"""Read-only source/runtime identity shown in Hermes Cockpit."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git_revision(root: Path | None) -> str | None:
    if root is None or not root.is_dir():
        return None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else None


def runtime_identity() -> dict:
    from api.config import REPO_ROOT, _AGENT_DIR
    from api.updates import AGENT_VERSION, WEBUI_VERSION

    agent_root = Path(_AGENT_DIR).resolve() if _AGENT_DIR is not None else None
    webui_root = Path(REPO_ROOT).resolve()
    return {
        "webui": {
            "version": WEBUI_VERSION,
            "revision": _git_revision(webui_root),
            "source_root": str(webui_root),
        },
        "hermes_runtime": {
            "version": AGENT_VERSION,
            "revision": _git_revision(agent_root),
            "source_root": str(agent_root) if agent_root else None,
        },
    }
