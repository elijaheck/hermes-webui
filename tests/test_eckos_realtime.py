"""Security and protocol contracts for the EckOS Realtime SDP exchange."""
import io
import json
from pathlib import Path
from unittest.mock import patch
from api import eckos_realtime

class Handler:
    def __init__(self, body=b"v=0\r\n", content_type="application/sdp"):
        self.headers={"Content-Length":str(len(body)),"Content-Type":content_type}; self.rfile=io.BytesIO(body); self.wfile=io.BytesIO(); self.status=None; self.response_headers=[]
    def send_response(self,status): self.status=status
    def send_header(self,name,value): self.response_headers.append((name,value))
    def end_headers(self): pass
class Response:
    def __init__(self,body=b"v=0\r\nanswer"): self.body=body
    def __enter__(self): return self
    def __exit__(self,*_): return False
    def read(self,_): return self.body

def test_session_uses_current_realtime_audio_and_closed_tools():
    session=eckos_realtime.build_session()
    assert session["model"]=="gpt-realtime-2.1" and session["output_modalities"]==["audio"]
    assert session["audio"]["input"]["turn_detection"]["type"]=="semantic_vad"
    assert session["audio"]["input"]["transcription"]["model"]=="gpt-4o-mini-transcribe"
    assert {tool["name"] for tool in session["tools"]}=={
        "render_eckos_dashboard",
        "send_to_hermes",
        "inspect_mac_screen",
        "control_mac",
        "delegate_to_agent",
    }
    control=next(tool for tool in session["tools"] if tool["name"]=="control_mac")
    assert control["description"].startswith("Ask the current Hermes session")
    assert "browser" not in control["description"].lower()
    assert "approve" in session["instructions"] and "api_key" not in json.dumps(session).lower()
def test_missing_key_fails_closed(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY",raising=False); handler=Handler(); assert eckos_realtime.handle_realtime_call(handler); assert handler.status==503
def test_offer_is_multipart_and_key_only_in_authorization(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY","test-secret"); handler=Handler(b"real-browser-sdp"); captured={}
    def fake_open(req,timeout): captured.update(url=req.full_url,headers=dict(req.header_items()),body=req.data,timeout=timeout); return Response()
    with patch("api.eckos_realtime.request.urlopen",fake_open): eckos_realtime.handle_realtime_call(handler)
    assert handler.status==200 and dict(handler.response_headers)["Content-Type"]=="application/sdp"
    assert captured["url"]=="https://api.openai.com/v1/realtime/calls" and captured["headers"]["Authorization"]=="Bearer test-secret"
    assert b"real-browser-sdp" in captured["body"] and b"gpt-realtime-2.1" in captured["body"] and b"test-secret" not in captured["body"]
def test_invalid_content_type_and_oversize(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY","test-secret"); wrong=Handler(content_type="application/json"); eckos_realtime.handle_realtime_call(wrong); assert wrong.status==415
    large=Handler(); large.headers["Content-Length"]=str(eckos_realtime.MAX_OFFER_BYTES+1); eckos_realtime.handle_realtime_call(large); assert large.status==413
def test_upstream_errors_are_redacted(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY","test-secret"); handler=Handler()
    def fail(*_a,**_k): raise eckos_realtime.error.HTTPError("url",400,"secret upstream detail",{},None)
    with patch("api.eckos_realtime.request.urlopen",fail): eckos_realtime.handle_realtime_call(handler)
    body=handler.wfile.getvalue().decode(); assert handler.status==502 and "secret upstream detail" not in body and "test-secret" not in body
def test_raw_sdp_route_precedes_json_parser():
    source=(Path(eckos_realtime.__file__).parent/"routes.py").read_text(); route=source.index('parsed.path == "/api/eckos/realtime/calls"'); parser=source.index("body = read_body(handler)",route); assert route<parser
