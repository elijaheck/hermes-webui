"""Fail-closed same-origin proxy for the loopback-only EckOS Calls API."""

from __future__ import annotations

import json
import os
import re
from urllib import error, request


INTERNAL_ORIGIN = "http://127.0.0.1:8792"
PUBLIC_PREFIX = "/api/cockpit/calls"
INTERNAL_PREFIX = "/internal/v1/calls"
MAX_REQUEST_BYTES = 128 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
CALL_ID = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"

_ROUTES = {
    "GET": (
        re.compile(r"^$"),
        re.compile(rf"^/(?P<call_id>{CALL_ID})$"),
    ),
    "POST": (
        re.compile(r"^/browser-sessions$"),
        re.compile(r"^/outbound/prepare$"),
        re.compile(r"^/outbound/confirm$"),
        re.compile(rf"^/(?P<call_id>{CALL_ID})/stop$"),
        re.compile(r"^/policy$"),
    ),
    "PUT": (re.compile(r"^/policy$"),),
}


def _json(handler, payload: dict, status: int) -> bool:
    body = json.dumps(payload, separators=(",", ":")).encode()
    handler.send_response(status)
    for name, value in (
        ("Content-Type", "application/json; charset=utf-8"),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Content-Length", str(len(body))),
    ):
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body)
    return True


def _allowed_suffix(path: str, method: str) -> str | None:
    if not path.startswith(PUBLIC_PREFIX):
        return None
    suffix = path[len(PUBLIC_PREFIX) :]
    if suffix == "/events":
        return None
    for pattern in _ROUTES.get(method, ()):
        if pattern.fullmatch(suffix):
            return suffix
    return None


def _read_body(handler, method: str) -> bytes | None:
    if method == "GET":
        return None
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except (TypeError, ValueError):
        raise ValueError("Invalid request body") from None
    if length < 0 or length > MAX_REQUEST_BYTES:
        raise ValueError("Request body too large")
    return handler.rfile.read(length) if length else b"{}"


def proxy_call_request(handler, path: str, method: str) -> bool:
    """Proxy one allowlisted call operation without exposing token or target."""
    method = method.upper()
    suffix = _allowed_suffix(path, method)
    if suffix is None:
        return _json(handler, {"error": "Call route not found"}, 404)

    token = os.environ.get("ECKOS_INTERNAL_API_TOKEN", "").strip()
    if not token:
        return _json(handler, {"error": "EckOS Calls is not configured"}, 503)
    try:
        body = _read_body(handler, method)
    except ValueError as exc:
        return _json(handler, {"error": str(exc)}, 413)

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    upstream = request.Request(
        INTERNAL_ORIGIN + INTERNAL_PREFIX + suffix,
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with request.urlopen(upstream, timeout=20) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                return _json(handler, {"error": "EckOS Calls response was too large"}, 502)
            status = int(getattr(response, "status", 200) or 200)
            content_type = str(response.headers.get("Content-Type", "application/json"))
    except error.HTTPError as exc:
        status = exc.code if 400 <= exc.code < 500 else 502
        return _json(handler, {"error": "EckOS Calls rejected the request"}, status)
    except (error.URLError, TimeoutError):
        return _json(handler, {"error": "EckOS Calls is unavailable"}, 503)
    except Exception:
        return _json(handler, {"error": "EckOS Calls request failed"}, 502)

    # Only JSON is accepted on this bounded request/response surface. The call
    # service owns an internal event stream, but this proxy does not expose it
    # until WebUI has a bounded replay/cursor contract; the UI polls status.
    if "json" not in content_type.lower():
        return _json(handler, {"error": "EckOS Calls returned an invalid response"}, 502)
    handler.send_response(status)
    for name, value in (
        ("Content-Type", "application/json; charset=utf-8"),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Content-Length", str(len(payload))),
    ):
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(payload)
    return True
