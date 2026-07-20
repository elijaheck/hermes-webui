from __future__ import annotations

import json


def write_registry(path, projects):
    path.write_text(json.dumps({"schemaVersion": 2, "projects": projects}), encoding="utf-8")


def row(project_id, root):
    return {
        "projectId": project_id,
        "displayName": project_id,
        "canonicalRoot": str(root),
        "kind": "product",
        "lifecycle": "active",
        "eligibleBrainRoots": [],
        "agentPolicy": {},
    }


def test_workspace_resolves_to_most_specific_canonical_project(tmp_path, monkeypatch):
    from api import canonical_projects

    outer = tmp_path / "projects"
    inner = outer / "app"
    inner.mkdir(parents=True)
    registry = tmp_path / "registry.json"
    write_registry(registry, [row("outer", outer), row("inner", inner)])
    monkeypatch.setenv("HERMES_PROJECT_REGISTRY_PATH", str(registry))
    assert canonical_projects.resolve_project_id(str(inner / "src")) == "inner"


def test_duplicate_canonical_ids_fail_closed(tmp_path, monkeypatch):
    from api import canonical_projects

    registry = tmp_path / "registry.json"
    write_registry(registry, [row("same", tmp_path / "one"), row("same", tmp_path / "two")])
    monkeypatch.setenv("HERMES_PROJECT_REGISTRY_PATH", str(registry))
    try:
        canonical_projects.load_canonical_projects()
    except ValueError as exc:
        assert "invalid identity" in str(exc)
    else:
        raise AssertionError("duplicate project IDs must fail closed")


def test_new_session_persists_canonical_project_id(tmp_path, monkeypatch):
    from api import canonical_projects, models

    root = tmp_path / "project"
    root.mkdir()
    registry = tmp_path / "registry.json"
    write_registry(registry, [row("stable-id", root)])
    monkeypatch.setenv("HERMES_PROJECT_REGISTRY_PATH", str(registry))
    canonical_projects._load_cached.cache_clear()
    session = models.new_session(workspace=str(root))
    assert session.canonical_project_id == "stable-id"
    assert session.compact()["canonical_project_id"] == "stable-id"
