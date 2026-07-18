"""Computer-use and same-origin screen contracts for EckOS mode."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch


class Handler:
    def __init__(self):
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
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return self.body


def test_capture_proxy_is_fixed_loopback_and_returns_same_origin_url():
    from api import eckos_computer

    handler = Handler()
    payload = json.dumps({
        "path": "/tmp/host-controlled-value.png",
        "displayName": "Mac display",
        "width": 1728,
        "height": 1117,
        "capturedAt": "2026-07-18T12:00:00Z",
    }).encode()
    captured = {}

    def fake_open(req, timeout):
        captured.update(url=req.full_url, method=req.method, timeout=timeout)
        return Response(payload)

    with patch("api.eckos_computer.request.urlopen", fake_open):
        assert eckos_computer.handle_capture(handler)

    body = json.loads(handler.wfile.getvalue())
    assert handler.status == 200
    assert captured == {
        "url": "http://127.0.0.1:8731/capture",
        "method": "POST",
        "timeout": eckos_computer.BRIDGE_TIMEOUT_SECONDS,
    }
    assert body["screen_url"] == "api/eckos/screen?v=2026-07-18T12%3A00%3A00Z"
    assert "path" not in body
    assert dict(handler.response_headers)["Cache-Control"] == "no-store"


def test_screen_reader_uses_only_fixed_capture_file(tmp_path, monkeypatch):
    from api import eckos_computer

    capture_dir = tmp_path / "EckOSMac"
    capture_dir.mkdir()
    capture_path = capture_dir / "latest-screen.png"
    capture_path.write_bytes(b"\x89PNG\r\n\x1a\nimage")
    monkeypatch.setattr(eckos_computer, "CAPTURE_DIR", capture_dir)
    monkeypatch.setattr(eckos_computer, "CAPTURE_PATH", capture_path)
    handler = Handler()

    assert eckos_computer.handle_screen(handler)

    assert handler.status == 200
    assert handler.wfile.getvalue().startswith(b"\x89PNG")
    headers = dict(handler.response_headers)
    assert headers["Content-Type"] == "image/png"
    assert headers["Cache-Control"] == "no-store"


def test_computer_use_approval_bridge_fails_closed_and_never_caches_globally():
    from api import eckos_computer

    with patch("tools.approval.request_tool_approval", return_value={"approved": True}) as gate:
        assert eckos_computer.computer_use_approval_callback(
            "click", {"element": 4}, "click element #4"
        ) == "approve_once"
    gate.assert_called_once()
    _, reason = gate.call_args.args
    assert "click element #4" in reason
    assert gate.call_args.kwargs == {}

    with patch("tools.approval.request_tool_approval", return_value={"approved": False}):
        assert eckos_computer.computer_use_approval_callback(
            "type", {"text": "hello"}, "type 'hello'"
        ) == "deny"
    with patch("tools.approval.request_tool_approval", side_effect=RuntimeError("boom")):
        assert eckos_computer.computer_use_approval_callback(
            "scroll", {}, "scroll down"
        ) == "deny"


def test_routes_keep_screen_capture_behind_auth_and_csrf():
    root = Path(__file__).parent.parent
    source = (root / "api" / "routes.py").read_text(encoding="utf-8")
    get_route = source.index('parsed.path == "/api/eckos/screen"')
    post_route = source.index('parsed.path == "/api/eckos/screen/capture"')
    csrf_gate = source.index("if not _csrf_exempt_path(parsed.path)")
    json_parser = source.index("body = read_body(handler)", csrf_gate)
    assert get_route > source.index("def handle_get")
    assert csrf_gate < post_route
    assert json_parser < post_route


def test_streaming_installs_computer_use_approval_bridge():
    root = Path(__file__).parent.parent
    source = (root / "api" / "streaming.py").read_text(encoding="utf-8")
    assert "install_computer_use_approval_bridge" in source
