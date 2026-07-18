"""Behavioral contracts for the additive EckOS WebUI presentation mode."""

from __future__ import annotations

import json
import io
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).parent.parent.resolve()
INDEX_HTML = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
SESSIONS_JS = (ROOT / "static" / "sessions.js").read_text(encoding="utf-8")
STYLE_CSS = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
SERVICE_WORKER_JS = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
I18N_JS = (ROOT / "static" / "i18n.js").read_text(encoding="utf-8")
BOOT_JS = (ROOT / "static" / "boot.js").read_text(encoding="utf-8")
MESSAGES_JS = (ROOT / "static" / "messages.js").read_text(encoding="utf-8")
ARCHITECTURE_MD = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
TESTING_MD = (ROOT / "TESTING.md").read_text(encoding="utf-8")
ECKOS_JS_PATH = ROOT / "static" / "eckos.js"
NODE = shutil.which("node")


class _ShellHandler:
    def __init__(self) -> None:
        self.command = "GET"
        self.headers = {}
        self.status = None
        self.response_headers = []
        self.wfile = io.BytesIO()

    def send_response(self, status: int) -> None:
        self.status = status

    def send_header(self, name: str, value: str) -> None:
        self.response_headers.append((name, value))

    def end_headers(self) -> None:
        pass


def _render_shell(routes, path: str) -> tuple[int, str, bytes]:
    handler = _ShellHandler()
    routes.handle_get(handler, urlsplit(path))
    content_type = dict(handler.response_headers).get("Content-Type", "")
    return handler.status, content_type, handler.wfile.getvalue()


def _run_node(source: str) -> dict:
    if NODE is None:
        pytest.skip("node not on PATH")
    result = subprocess.run(
        [NODE],
        input=source,
        cwd=ROOT,
        capture_output=True,
        encoding="utf-8",
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def _session_url_harness() -> str:
    return f"""
const src = {SESSIONS_JS!r};
function extractFunc(name) {{
  const re = new RegExp('function\\\\s+' + name + '\\\\s*\\\\(');
  const start = src.search(re);
  if (start < 0) throw new Error(name + ' not found');
  let i = src.indexOf('{{', start), depth = 1;
  i += 1;
  while (depth > 0 && i < src.length) {{
    if (src[i] === '{{') depth += 1;
    else if (src[i] === '}}') depth -= 1;
    i += 1;
  }}
  return src.slice(start, i);
}}
function installLocation(href, baseURI, mode) {{
  const url = new URL(href);
  global.window = {{ location: {{
    href: url.href,
    origin: url.origin,
    pathname: url.pathname,
    search: url.search,
    hash: url.hash
  }} }};
  global.document = {{
    baseURI,
    documentElement: {{ dataset: mode ? {{ mode }} : {{}} }}
  }};
}}
globalThis._isEckosMode = (0, eval)('(' + extractFunc('_isEckosMode') + ')');
globalThis._sessionUrlForSid = (0, eval)('(' + extractFunc('_sessionUrlForSid') + ')');
globalThis._sessionIdFromLocation = (0, eval)('(' + extractFunc('_sessionIdFromLocation') + ')');
"""


def _eckos_js() -> str:
    assert ECKOS_JS_PATH.exists(), "static/eckos.js must define the EckOS projection"
    return ECKOS_JS_PATH.read_text(encoding="utf-8")


def test_eckos_routes_serve_the_existing_webui_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes-home"))
    monkeypatch.setenv("HERMES_BASE_HOME", str(tmp_path / "hermes-home"))
    monkeypatch.setenv("HERMES_WEBUI_STATE_DIR", str(tmp_path / "webui-state"))
    monkeypatch.setenv("HERMES_CONFIG_PATH", str(tmp_path / "hermes-home" / "config.yaml"))
    from api import routes

    root_status, root_type, root_html = _render_shell(routes, "/")
    for path in ("/eckos", "/eckos/"):
        status, content_type, html = _render_shell(routes, path)
        assert status == root_status == 200
        assert content_type == root_type == "text/html; charset=utf-8"
        assert html == root_html
        assert b'id="mainChat"' in html
        assert b'id="messages"' in html
        assert b'id="composerWrap"' in html


def test_eckos_mode_is_identified_before_stylesheet_paint():
    mode_assignment = re.search(
        r"document\.documentElement\.dataset\.mode\s*=\s*['\"]eckos['\"]",
        INDEX_HTML,
    )
    assert mode_assignment
    assert mode_assignment.start() < INDEX_HTML.index(
        '<link rel="stylesheet" href="static/style.css'
    )
    base_script = INDEX_HTML[: INDEX_HTML.index("</script>")]
    assert "/eckos" in base_script


def test_session_url_builder_preserves_eckos_and_normal_routes():
    payload = _run_node(
        _session_url_harness()
        + """
installLocation('https://example.test/eckos?profile=ops&session=old&q=draft#frag', 'https://example.test/', 'eckos');
const eckos = _sessionUrlForSid('abc 123');
installLocation('https://example.test/session/old?profile=ops&session=legacy#frag', 'https://example.test/', '');
const normal = _sessionUrlForSid('abc 123');
installLocation('https://example.test/app/eckos/?session=old&keep=1', 'https://example.test/app/', 'eckos');
const subpath = _sessionUrlForSid('next');
console.log(JSON.stringify({ eckos, normal, subpath }));
"""
    )
    assert payload == {
        "eckos": "/eckos?profile=ops&session=abc+123#frag",
        "normal": "/session/abc%20123?profile=ops#frag",
        "subpath": "/app/eckos?keep=1&session=next",
    }


def test_eckos_dashboard_keeps_native_conversation_and_action_cards():
    deck = INDEX_HTML.index('id="eckosCommandDeck"')
    messages = INDEX_HTML.index('id="messages"')
    composer = INDEX_HTML.index('id="composerWrap"')
    assert deck < messages < composer
    assert INDEX_HTML.count('id="messages"') == 1
    assert INDEX_HTML.count('id="approvalCard"') == 1
    assert INDEX_HTML.count('id="clarifyCard"') == 1
    assert 'data-eckos-voice-state="idle"' in INDEX_HTML
    assert 'id="eckosVoiceOrb"' in INDEX_HTML
    assert "eckos_voice_ready: 'Tap the orb to talk'" in I18N_JS


def test_eckos_panel_registry_is_closed_and_unknown_ids_fail_closed():
    source = _eckos_js()
    payload = _run_node(
        f"""
global.window = {{ location: {{ pathname: '/eckos' }} }};
global.document = {{
  readyState: 'loading',
  documentElement: {{ dataset: {{ mode: 'eckos', sentinel: 'unchanged' }} }},
  addEventListener() {{}},
  querySelector() {{ return null; }},
  getElementById() {{ return null; }}
}};
(0, eval)({source!r});
const defaults = window.EckOS.normalizeDashboard();
const ordered = window.EckOS.normalizeDashboard({{ panels: ['usage', 'conversation', 'usage'], focus: 'conversation' }});
const before = JSON.stringify(document.documentElement.dataset);
const rejected = window.EckOS.applyDashboard({{ panels: ['conversation', 'made-up-panel'] }});
const after = JSON.stringify(document.documentElement.dataset);
console.log(JSON.stringify({{
  ids: window.EckOS.panelIds,
  defaults,
  ordered,
  rejected,
  unchanged: before === after
}}));
"""
    )
    assert payload["ids"] == [
        "conversation",
        "activity",
        "approvals",
        "clarifications",
        "agents",
        "cron",
        "mcp",
        "workspace",
        "usage",
        "profile",
    ]
    assert payload["defaults"] == {
        "ok": True,
        "panels": ["conversation", "activity", "approvals", "clarifications"],
        "focus": "conversation",
    }
    assert payload["ordered"] == {
        "ok": True,
        "panels": ["usage", "conversation"],
        "focus": "conversation",
    }
    assert payload["rejected"] == {
        "ok": False,
        "error": "unknown_panel",
        "panel": "made-up-panel",
    }
    assert payload["unchanged"] is True


def test_eckos_projection_reuses_hermes_dom_and_only_bridges_realtime_offer():
    source = _eckos_js()
    for selector in (
        "#messages",
        "#liveRunStatus",
        "#approvalCard",
        "#clarifyCard",
        "#sessionList",
        "#cronList",
        "#mcpServerList",
        ".rightpanel",
        "#ctxIndicatorWrap",
        "#titlebarProfileBtn",
    ):
        assert selector in source
    assert source.count("global.fetch(") == 1
    assert "api/eckos/realtime/calls" in source
    assert "new EventSource" not in source
    assert "respondApproval(" not in source
    assert "respondClarify(" not in source


def test_eckos_styles_are_scoped_responsive_and_precached():
    assert ':root[data-mode="eckos"]' in STYLE_CSS
    assert "#eckosCommandDeck" in STYLE_CSS
    assert 'data-eckos-voice-state="idle"' in STYLE_CSS
    assert "@media (max-width: 1100px)" in STYLE_CSS
    assert "@media (max-width: 640px)" in STYLE_CSS
    assert "./static/eckos.js" in SERVICE_WORKER_JS
    assert '<script src="static/eckos.js?v=__WEBUI_VERSION__" defer></script>' in INDEX_HTML


def test_eckos_session_query_uses_native_boot_restore_and_survives_reload():
    payload = _run_node(
        _session_url_harness()
        + """
installLocation('https://example.test/eckos?session=active%2Fsession&profile=ops', 'https://example.test/', 'eckos');
const restored = _sessionIdFromLocation();
const reloadUrl = _sessionUrlForSid(restored);
installLocation('https://example.test/eckos?session_id=legacy-session', 'https://example.test/', 'eckos');
const legacy = _sessionIdFromLocation();
console.log(JSON.stringify({ restored, reloadUrl, legacy }));
"""
    )
    assert payload == {
        "restored": "active/session",
        "reloadUrl": "/eckos?profile=ops&session=active%2Fsession",
        "legacy": "legacy-session",
    }
    assert "const saved=urlSession||savedLocal;" in BOOT_JS
    assert "await loadSession(saved, {preserveActiveInput:true});" in BOOT_JS


def test_eckos_keeps_native_send_stream_and_action_required_contracts():
    eckos_source = _eckos_js()
    assert INDEX_HTML.count('id="msg"') == 1
    assert INDEX_HTML.count('id="composerWrap"') == 1
    assert INDEX_HTML.count('static/messages.js?v=__WEBUI_VERSION__') == 1
    assert "async function send()" in MESSAGES_JS
    assert "api('/api/chat/start'" in MESSAGES_JS
    assert "function startSessionStream(sid)" in MESSAGES_JS
    assert "async function respondApproval(choice)" in MESSAGES_JS
    assert "async function respondClarify(response)" in MESSAGES_JS
    assert eckos_source.count("global.fetch(") == 1
    assert "new EventSource" not in eckos_source
    assert "respondApproval(" not in eckos_source
    assert "respondClarify(" not in eckos_source


def test_eckos_voice_lifecycle_is_permission_and_stop_race_safe():
    source = _eckos_js()
    for contract in (
        "navigator.mediaDevices.getUserMedia", "new RTCPeerConnection()",
        "peer.createDataChannel('oai-events')", "generation!==voice.generation||voice.explicitStop",
        "voice.generation+=1", "['idle','error'].includes(voice.state)",
        "render_eckos_dashboard", "send_to_hermes", "pendingHumanAction()", ".slice(-4000)",
    ):
        assert contract in source


def test_eckos_mode_native_continuity_and_rollback_are_documented():
    for phrase in (
        "## EckOS alternate presentation mode",
        "same authenticated Hermes WebUI shell",
        "`S` remains the active client state owner",
        "Unknown panel IDs fail closed",
        "production port `8787` remains unchanged",
    ):
        assert phrase in ARCHITECTURE_MD

    for phrase in (
        "## EckOS mode verification",
        "`/eckos?session=<session_id>`",
        "desktop, notch-width, and phone-width",
        "feature branch/worktree",
        "Do not use real `~/.hermes` state",
    ):
        assert phrase in TESTING_MD
