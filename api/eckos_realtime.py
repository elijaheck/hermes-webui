"""Raw WebRTC SDP bridge from Hermes WebUI to the EckOS call service."""

from __future__ import annotations

import json
import logging
import os
from urllib import error, request


logger = logging.getLogger(__name__)
ECKOS_BROWSER_SESSION_URL = "http://127.0.0.1:8792/internal/v1/calls/browser-sessions"
MAX_OFFER_BYTES = 64 * 1024
MAX_ANSWER_BYTES = 128 * 1024


def _json_error(handler, message: str, status: int) -> bool:
    body = json.dumps({"error": message}, separators=(",", ":")).encode()
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


def handle_realtime_call(handler) -> bool:
    token = os.environ.get("ECKOS_INTERNAL_API_TOKEN", "").strip()
    if not token:
        return _json_error(handler, "EckOS Calls is not configured", 503)
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except (TypeError, ValueError):
        return _json_error(handler, "Invalid SDP offer", 400)
    if length <= 0 or length > MAX_OFFER_BYTES:
        return _json_error(handler, "Invalid SDP offer", 413 if length > MAX_OFFER_BYTES else 400)
    if "application/sdp" not in str(handler.headers.get("Content-Type", "")):
        return _json_error(handler, "Expected application/sdp", 415)

    offer = handler.rfile.read(length)
    upstream = request.Request(
        ECKOS_BROWSER_SESSION_URL,
        data=offer,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/sdp",
            "Accept": "application/sdp",
        },
    )
    try:
        with request.urlopen(upstream, timeout=20) as response:
            answer = response.read(MAX_ANSWER_BYTES + 1)
            if len(answer) > MAX_ANSWER_BYTES:
                return _json_error(handler, "EckOS Calls response was too large", 502)
            if "application/sdp" not in str(response.headers.get("Content-Type", "")):
                return _json_error(handler, "EckOS Calls returned an invalid response", 502)
    except error.HTTPError as exc:
        logger.warning("EckOS browser session failed with status %s", exc.code)
        return _json_error(handler, "EckOS Calls rejected the browser session", 502)
    except (error.URLError, TimeoutError):
        logger.warning("EckOS call service timed out or was unreachable")
        return _json_error(handler, "EckOS Calls is unavailable", 503)
    except Exception:
        logger.exception("Unexpected EckOS browser-session failure")
        return _json_error(handler, "EckOS Calls request failed", 502)

    handler.send_response(200)
    for name, value in (
        ("Content-Type", "application/sdp"),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Content-Length", str(len(answer))),
    ):
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(answer)
    return True
