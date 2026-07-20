"""Security contracts for the WebUI-to-EckOS browser-call SDP bridge."""

import io
from pathlib import Path
from unittest.mock import patch

from api import eckos_realtime


class Handler:
    def __init__(self, body=b"v=0\r\n", content_type="application/sdp"):
        self.headers = {"Content-Length": str(len(body)), "Content-Type": content_type}
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
    headers = {"Content-Type": "application/sdp"}

    def __init__(self, body=b"v=0\r\nanswer"):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        return self.body


def test_missing_internal_token_fails_closed(monkeypatch):
    monkeypatch.delenv("ECKOS_INTERNAL_API_TOKEN", raising=False)
    handler = Handler()
    assert eckos_realtime.handle_realtime_call(handler)
    assert handler.status == 503


def test_offer_goes_only_to_fixed_eckos_loopback_with_server_token(monkeypatch):
    monkeypatch.setenv("ECKOS_INTERNAL_API_TOKEN", "test-secret")
    handler = Handler(b"real-browser-sdp")
    captured = {}

    def fake_open(req, timeout):
        captured.update(url=req.full_url, headers=dict(req.header_items()), body=req.data, timeout=timeout)
        return Response()

    with patch("api.eckos_realtime.request.urlopen", fake_open):
        eckos_realtime.handle_realtime_call(handler)
    assert handler.status == 200
    assert dict(handler.response_headers)["Content-Type"] == "application/sdp"
    assert captured["url"] == eckos_realtime.ECKOS_BROWSER_SESSION_URL
    assert captured["headers"]["Authorization"] == "Bearer test-secret"
    assert captured["body"] == b"real-browser-sdp"
    assert b"test-secret" not in handler.wfile.getvalue()
    assert "OPENAI_API_KEY" not in Path(eckos_realtime.__file__).read_text()


def test_invalid_content_type_and_oversize(monkeypatch):
    monkeypatch.setenv("ECKOS_INTERNAL_API_TOKEN", "test-secret")
    wrong = Handler(content_type="application/json")
    eckos_realtime.handle_realtime_call(wrong)
    assert wrong.status == 415
    large = Handler()
    large.headers["Content-Length"] = str(eckos_realtime.MAX_OFFER_BYTES + 1)
    eckos_realtime.handle_realtime_call(large)
    assert large.status == 413


def test_upstream_errors_are_redacted(monkeypatch):
    monkeypatch.setenv("ECKOS_INTERNAL_API_TOKEN", "test-secret")
    handler = Handler()

    def fail(*_args, **_kwargs):
        raise eckos_realtime.error.HTTPError("url", 400, "secret upstream detail", {}, None)

    with patch("api.eckos_realtime.request.urlopen", fail):
        eckos_realtime.handle_realtime_call(handler)
    body = handler.wfile.getvalue().decode()
    assert handler.status == 502
    assert "secret upstream detail" not in body
    assert "test-secret" not in body


def test_raw_sdp_route_precedes_json_parser():
    source = (Path(eckos_realtime.__file__).parent / "routes.py").read_text()
    route = source.index('parsed.path == "/api/cockpit/realtime/calls"')
    parser = source.index("body = read_body(handler)", route)
    assert route < parser
