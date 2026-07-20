"""Read-only adapter for the owner-controlled canonical project registry."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path


DEFAULT_REGISTRY = Path("/Users/elijaheck/Projects/.project-registry.generated.json")


def registry_path() -> Path:
    configured = os.environ.get("HERMES_PROJECT_REGISTRY_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_REGISTRY


@lru_cache(maxsize=4)
def _load_cached(path_text: str, size: int, mtime_ns: int) -> tuple[dict, ...]:
    del size, mtime_ns
    payload = json.loads(Path(path_text).read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 2 or not isinstance(payload.get("projects"), list):
        raise ValueError("canonical project registry must use schema v2")
    rows = []
    seen = set()
    for source in payload["projects"]:
        project_id = str(source.get("projectId") or "").strip()
        root = str(source.get("canonicalRoot") or "").strip()
        if not project_id or project_id in seen or not Path(root).is_absolute():
            raise ValueError("canonical project registry contains invalid identity")
        seen.add(project_id)
        rows.append({
            "project_id": project_id,
            "name": str(source.get("displayName") or project_id),
            "canonical_root": root,
            "kind": str(source.get("kind") or "project"),
            "lifecycle": str(source.get("lifecycle") or "active"),
            "collection_id": source.get("collectionId"),
            "eligible_brain_roots": list(source.get("eligibleBrainRoots") or []),
            "agent_policy": dict(source.get("agentPolicy") or {}),
            "read_only": True,
        })
    return tuple(rows)


def load_canonical_projects() -> list[dict]:
    path = registry_path()
    stat = path.stat()
    return [dict(row) for row in _load_cached(str(path.resolve()), stat.st_size, stat.st_mtime_ns)]


def canonical_project(project_id: str | None) -> dict | None:
    if not project_id:
        return None
    return next((row for row in load_canonical_projects() if row["project_id"] == project_id), None)


def resolve_project_id(workspace: str | None) -> str | None:
    if not workspace:
        return None
    candidate = Path(workspace).expanduser().resolve(strict=False)
    matches = []
    for row in load_canonical_projects():
        root = Path(row["canonical_root"]).expanduser().resolve(strict=False)
        if candidate == root or root in candidate.parents:
            matches.append((len(root.parts), row["project_id"]))
    return max(matches)[1] if matches else None
