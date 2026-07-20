"""EckOS computer-use safety bridge and same-origin screen snapshots.

Hermes remains the computer-use runtime.  This module only:

* installs WebUI's adapter into Hermes' existing per-action approval hook; and
* proxies the loopback-only EckOSMac capture bridge to the authenticated WebUI.

The browser never receives a loopback control URL or a local filesystem path.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from urllib import error, parse, request

logger = logging.getLogger(__name__)

BRIDGE_CAPTURE_URL = "http://127.0.0.1:8731/capture"
BRIDGE_TIMEOUT_SECONDS = 20
MAX_BRIDGE_RESPONSE_BYTES = 64 * 1024
MAX_SCREEN_BYTES = 20 * 1024 * 1024
CAPTURE_DIR = Path.home() / "Library" / "Application Support" / "EckOSMac"
CAPTURE_PATH = CAPTURE_DIR / "latest-screen.png"

_approval_install_lock = threading.Lock()
_approval_installed = False


def _json_response(handler, payload: dict, status: int = 200) -> bool:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
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


def computer_use_approval_callback(action: str, args: dict, summary: str) -> str:
    """Route every state-changing Hermes computer-use action to WebUI approval.

    The callback deliberately returns ``approve_once`` even if the underlying
    approval layer records a session/permanent decision.  That keeps the
    computer-use module from growing a second process-global allowlist; the
    existing Hermes approval system remains the only decision owner.
    """
    del args  # The redacted, bounded summary is the human-facing contract.
    action = str(action or "computer action").strip()[:80]
    summary = str(summary or action).strip()[:500]
    try:
        from tools.approval import request_tool_approval

        decision = request_tool_approval(
            "computer_use",
            f"Allow computer_use to {summary}?",
        )
    except Exception:
        logger.exception("Computer-use approval bridge failed closed")
        return "deny"
    return "approve_once" if decision.get("approved") is True else "deny"


def install_computer_use_approval_bridge() -> bool:
    """Install the generic callback once for this WebUI process."""
    global _approval_installed
    with _approval_install_lock:
        if _approval_installed:
            return True
        try:
            from tools.computer_use.tool import set_approval_callback

            set_approval_callback(computer_use_approval_callback)
        except Exception:
            logger.exception("Could not install the computer-use approval bridge")
            return False
        _approval_installed = True
        return True


def _capture_payload(raw: bytes) -> dict | None:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    captured_at = str(value.get("capturedAt") or "").strip()[:100]
    display_name = str(value.get("displayName") or "Mac display").strip()[:120]
    width = value.get("width")
    height = value.get("height")
    if not captured_at or not isinstance(width, int) or not isinstance(height, int):
        return None
    if width <= 0 or height <= 0 or width > 16_384 or height > 16_384:
        return None
    return {
        "ok": True,
        "display_name": display_name,
        "width": width,
        "height": height,
        "captured_at": captured_at,
        "screen_url": f"api/cockpit/screen?v={parse.quote(captured_at, safe='')}",
    }


def handle_capture(handler) -> bool:
    """Ask the local native bridge for one capture and return safe metadata."""
    upstream = request.Request(
        BRIDGE_CAPTURE_URL,
        data=b"",
        method="POST",
        headers={"Content-Length": "0"},
    )
    try:
        with request.urlopen(upstream, timeout=BRIDGE_TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_BRIDGE_RESPONSE_BYTES + 1)
    except (error.HTTPError, error.URLError, TimeoutError, OSError):
        logger.warning("EckOSMac screen bridge is unavailable")
        return _json_response(
            handler,
            {"error": "Mac screen capture is unavailable. Open EckOSMac and allow Screen Recording."},
            503,
        )
    except Exception:
        logger.exception("Unexpected EckOSMac screen bridge failure")
        return _json_response(handler, {"error": "Mac screen capture failed."}, 502)
    if len(raw) > MAX_BRIDGE_RESPONSE_BYTES:
        return _json_response(handler, {"error": "Mac screen capture response was too large."}, 502)
    payload = _capture_payload(raw)
    if payload is None:
        return _json_response(handler, {"error": "Mac screen capture returned an invalid response."}, 502)
    return _json_response(handler, payload)


def handle_screen(handler) -> bool:
    """Serve only EckOSMac's fixed latest-screen file, never a caller path."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(CAPTURE_PATH, flags)
    except OSError:
        return _json_response(handler, {"error": "No Mac screen capture is available yet."}, 404)
    try:
        stat = os.fstat(fd)
        if stat.st_size <= 0 or stat.st_size > MAX_SCREEN_BYTES:
            return _json_response(handler, {"error": "Mac screen capture is invalid."}, 502)
        with os.fdopen(fd, "rb", closefd=True) as stream:
            fd = -1
            body = stream.read(MAX_SCREEN_BYTES + 1)
    finally:
        if fd >= 0:
            os.close(fd)
    if len(body) > MAX_SCREEN_BYTES or not body.startswith(b"\x89PNG\r\n\x1a\n"):
        return _json_response(handler, {"error": "Mac screen capture is invalid."}, 502)
    handler.send_response(200)
    for name, value in (
        ("Content-Type", "image/png"),
        ("Cache-Control", "no-store"),
        ("Pragma", "no-cache"),
        ("X-Content-Type-Options", "nosniff"),
        ("Content-Length", str(len(body))),
    ):
        handler.send_header(name, value)
    handler.end_headers()
    handler.wfile.write(body)
    return True
