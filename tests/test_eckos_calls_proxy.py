from __future__ import annotations

import io
import json
from unittest.mock import patch


class Handler:
    def __init__(self, body=b""):
        self.command = "GET"
        self.headers = {"Content-Length": str(len(body))}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = None
        self.response_headers = []

    def send_response(self, status):
        self.status = status

    def send_header(self, name, value):
        self.response_headers.append((name, value))

    def end_headers(self):
        pass


class Response:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, body=b'{"calls":[]}'):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size=-1):
        return self.body


def test_proxy_uses_fixed_loopback_target_and_server_token(monkeypatch):
    from api import eckos_calls

    monkeypatch.setenv("ECKOS_INTERNAL_API_TOKEN", "server-secret")
    handler = Handler()
    captured = {}

    def fake_open(request, timeout):
        captured.update(
            url=request.full_url,
            headers=dict(request.header_items()),
            method=request.method,
            timeout=timeout,
        )
        return Response()

    with patch("api.eckos_calls.request.urlopen", fake_open):
        assert eckos_calls.proxy_call_request(handler, "/api/cockpit/calls", "GET")

    assert captured["url"] == "http://127.0.0.1:8792/internal/v1/calls"
    assert captured["headers"]["Authorization"] == "Bearer server-secret"
    assert b"127.0.0.1" not in handler.wfile.getvalue()
    assert b"server-secret" not in handler.wfile.getvalue()


def test_proxy_rejects_unknown_paths_without_upstream_request(monkeypatch):
    from api import eckos_calls

    monkeypatch.setenv("ECKOS_INTERNAL_API_TOKEN", "server-secret")
    handler = Handler()
    with patch("api.eckos_calls.request.urlopen") as upstream:
        assert eckos_calls.proxy_call_request(handler, "/api/cockpit/calls/../../brain", "GET")
    assert handler.status == 404
    upstream.assert_not_called()


def test_proxy_fails_closed_when_token_is_missing(monkeypatch):
    from api import eckos_calls

    monkeypatch.delenv("ECKOS_INTERNAL_API_TOKEN", raising=False)
    handler = Handler()
    assert eckos_calls.proxy_call_request(handler, "/api/cockpit/calls", "GET")
    assert handler.status == 503
    assert json.loads(handler.wfile.getvalue())["error"] == "EckOS Calls is not configured"


def test_mutation_allowlist_is_method_specific(monkeypatch):
    from api import eckos_calls

    monkeypatch.setenv("ECKOS_INTERNAL_API_TOKEN", "server-secret")
    handler = Handler(b"{}")
    with patch("api.eckos_calls.request.urlopen") as upstream:
        assert eckos_calls.proxy_call_request(handler, "/api/cockpit/calls/outbound/confirm", "DELETE")
    assert handler.status == 404
    upstream.assert_not_called()


def test_internal_event_stream_is_not_exposed_as_a_buffered_json_route(monkeypatch):
    from api import eckos_calls

    monkeypatch.setenv("ECKOS_INTERNAL_API_TOKEN", "server-secret")
    handler = Handler()
    with patch("api.eckos_calls.request.urlopen") as upstream:
        assert eckos_calls.proxy_call_request(handler, "/api/cockpit/calls/events", "GET")
    assert handler.status == 404
    upstream.assert_not_called()
