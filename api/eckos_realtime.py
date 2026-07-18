"""Server-held OpenAI Realtime WebRTC session exchange for EckOS."""
from __future__ import annotations
import json
import logging
import os
import secrets
from urllib import error, request

logger = logging.getLogger(__name__)
REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"
REALTIME_MODEL = "gpt-realtime-2.1"
MAX_OFFER_BYTES = 64 * 1024
MAX_ANSWER_BYTES = 128 * 1024


def build_session() -> dict:
    panels = ["conversation", "activity", "approvals", "clarifications", "agents", "cron", "mcp", "workspace", "usage", "profile"]
    return {
        "type": "realtime",
        "model": REALTIME_MODEL,
        "instructions": (
            "You are the concise live voice controller for EckOS, a native Hermes dashboard. "
            "Use render_eckos_dashboard to change dashboard emphasis and send_to_hermes for agent or MCP work. "
            "Never approve an approval request, answer a clarification, or claim Hermes completed work unless its transcript confirms it."
        ),
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "turn_detection": {"type": "semantic_vad", "eagerness": "auto", "create_response": True, "interrupt_response": True},
                "transcription": {"model": "gpt-4o-mini-transcribe"},
            },
            "output": {"voice": "marin"},
        },
        "tools": [
            {"type": "function", "name": "render_eckos_dashboard", "description": "Reorder and focus allowlisted native EckOS panels.", "parameters": {
                "type": "object", "properties": {"panels": {"type": "array", "items": {"type": "string", "enum": panels}}, "focus": {"type": "string", "enum": panels}},
                "required": ["panels", "focus"], "additionalProperties": False}},
            {"type": "function", "name": "send_to_hermes", "description": "Send a natural-language task into the current native Hermes session.", "parameters": {
                "type": "object", "properties": {"message": {"type": "string", "minLength": 1, "maxLength": 8000}},
                "required": ["message"], "additionalProperties": False}},
        ],
        "tool_choice": "auto",
    }


def _json_error(handler, message: str, status: int) -> bool:
    body = json.dumps({"error": message}, separators=(",", ":")).encode()
    handler.send_response(status)
    for name, value in (("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), ("Content-Length", str(len(body)))):
        handler.send_header(name, value)
    handler.end_headers(); handler.wfile.write(body); return True


def _multipart_sdp(offer: bytes, session: dict) -> tuple[bytes, str]:
    boundary = "----hermes-eckos-" + secrets.token_hex(16)
    chunks = []
    for name, kind, value in (("sdp", "application/sdp", offer), ("session", "application/json", json.dumps(session, separators=(",", ":")).encode())):
        chunks += [f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n'.encode(), f"Content-Type: {kind}\r\n\r\n".encode(), value, b"\r\n"]
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def handle_realtime_call(handler) -> bool:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return _json_error(handler, "Realtime voice is not configured", 503)
    try:
        length = int(handler.headers.get("Content-Length", "0"))
    except (TypeError, ValueError):
        return _json_error(handler, "Invalid SDP offer", 400)
    if length <= 0 or length > MAX_OFFER_BYTES:
        return _json_error(handler, "Invalid SDP offer", 413 if length > MAX_OFFER_BYTES else 400)
    if "application/sdp" not in str(handler.headers.get("Content-Type", "")):
        return _json_error(handler, "Expected application/sdp", 415)
    payload, boundary = _multipart_sdp(handler.rfile.read(length), build_session())
    upstream = request.Request(REALTIME_CALLS_URL, data=payload, method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with request.urlopen(upstream, timeout=15) as response:
            answer = response.read(MAX_ANSWER_BYTES + 1)
            if len(answer) > MAX_ANSWER_BYTES:
                return _json_error(handler, "OpenAI Realtime response was too large", 502)
    except error.HTTPError as exc:
        logger.warning("OpenAI Realtime request failed with status %s", exc.code)
        return _json_error(handler, "OpenAI Realtime connection failed", 502)
    except (error.URLError, TimeoutError):
        logger.warning("OpenAI Realtime request timed out or was unreachable")
        return _json_error(handler, "OpenAI Realtime connection timed out", 504)
    except Exception:
        logger.exception("Unexpected OpenAI Realtime connection failure")
        return _json_error(handler, "OpenAI Realtime connection failed", 502)
    handler.send_response(200)
    for name, value in (("Content-Type", "application/sdp"), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), ("Content-Length", str(len(answer)))):
        handler.send_header(name, value)
    handler.end_headers(); handler.wfile.write(answer); return True
