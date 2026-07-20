from __future__ import annotations

import io
from urllib.parse import urlsplit


class Handler:
    def __init__(self):
        self.command = "GET"
        self.headers = {}
        self.status = None
        self.response_headers = []
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.response_headers.append((name, value))

    def end_headers(self):
        pass


def render(routes, path):
    handler = Handler()
    routes.handle_get(handler, urlsplit(path))
    return handler


def test_cockpit_is_the_same_authenticated_hermes_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    monkeypatch.setenv("HERMES_BASE_HOME", str(tmp_path / "hermes-home"))
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(tmp_path / "webui-state"))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(tmp_path / "hermes-home" / "config.yaml"))
    from api import routes

    root = render(routes, "/")
    cockpit = render(routes, "/cockpit?tab=calls")
    assert root.status == cockpit.status == 200
    assert root.wfile.getvalue() == cockpit.wfile.getvalue()
    assert b'id="messages"' in cockpit.wfile.getvalue()
    assert b'id="approvalCard"' in cockpit.wfile.getvalue()


def test_legacy_eckos_route_redirects_to_calls_tab(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    monkeypatch.setenv("HERMES_BASE_HOME", str(tmp_path / "hermes-home"))
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(tmp_path / "webui-state"))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(tmp_path / "hermes-home" / "config.yaml"))
    from api import routes

    response = render(routes, "/eckos?session=abc&profile=ops")
    headers = dict(response.response_headers)
    assert response.status == 307
    assert headers["Location"] == "/cockpit?tab=calls&session=abc&profile=ops"
    assert headers["Sunset"] == "Wed, 19 Aug 2026 23:59:59 GMT"


def test_cockpit_markup_declares_calls_as_native_tab():
    source = open("static/index.html", encoding="utf-8").read()
    assert "dataset.mode='cockpit'" in source
    assert 'data-cockpit-tab="calls"' in source
    assert 'id="cockpitCallsPanel"' in source
    assert 'src="static/cockpit.js?v=__WEBUI_VERSION__"' in source
    assert 'id="cockpitRuntimeIdentity"' in source


def test_cockpit_runtime_identity_keeps_source_and_deployed_runtime_distinct(monkeypatch):
    from api import runtime_identity

    monkeypatch.setattr(runtime_identity, "_git_revision", lambda root: "abc123" if root else None)
    identity = runtime_identity.runtime_identity()
    assert identity["webui"]["source_root"] != identity["hermes_runtime"]["source_root"]
    assert identity["webui"]["revision"] == "abc123"
    assert identity["hermes_runtime"]["revision"] == "abc123"
