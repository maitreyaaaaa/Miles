import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api import server
from src.debate.engine import DebateEngine
from src.debate.llm_client import LLMClient
from src.voice.assemblyai_stream import AssemblyAIStreamingClient
from src.voice.errors import VoiceProviderError
from src.voice.rime_stream import RimeStreamingTTSClient


@pytest.mark.parametrize("path,payload", [
    ("/api/meeting/schedule", {}),
    ("/api/meeting/generate-link", {}),
    ("/api/meeting/example/start", {}),
    ("/api/meeting/bot/launch", {"meeting_url": "https://meet.google.com/abc-defg-hij"}),
])
def test_disabled_meet_rejects_before_any_provider_or_storage_call(monkeypatch, path, payload):
    monkeypatch.setattr(server, "config", replace(server.config, google_meet_enabled=False))
    def unexpected_call():
        pytest.fail("Disabled meeting routes must not initialize the scheduler.")
    monkeypatch.setattr(server, "get_meeting_scheduler", unexpected_call)
    response = TestClient(server.app).post(path, json=payload)
    assert response.status_code == 404


def test_disabled_meet_blocks_calendar_but_not_drive_or_public_capabilities(monkeypatch):
    monkeypatch.setattr(server, "config", replace(server.config, google_meet_enabled=False,
        google_client_id="test-client", google_client_secret="test-secret"))
    client = TestClient(server.app)
    assert client.get("/api/auth/google/url", params={"purpose": "calendar", "state": "s" * 32}).status_code == 404
    assert client.get("/api/auth/google/url", params={"purpose": "drive", "state": "s" * 32}).status_code == 200
    server.app.state.auth_test_bypass = False
    response = client.get("/api/capabilities")
    assert response.status_code == 200
    assert response.json() == {"google_meet_enabled": False}


def test_disabled_meet_rejects_audio_bridge(monkeypatch):
    monkeypatch.setattr(server, "config", replace(server.config, google_meet_enabled=False))
    with pytest.raises(WebSocketDisconnect):
        with TestClient(server.app).websocket_connect("/ws/debate?meeting_bridge=true"):
            pytest.fail("A disabled bridge must not open.")


def install_live_flow_doubles(monkeypatch, *, stt_ready=True):
    """Exercise production authentication/readiness branches with test-only providers."""
    server.app.state.auth_test_bypass = False
    monkeypatch.setattr(server, "config", replace(server.config,
        supabase_url="https://auth.example.test", assemblyai_api_key="test-key",
        rime_api_key="test-key", openai_api_key="test-key"))
    monkeypatch.setattr(server.app.state, "token_verifier", SimpleNamespace(
        verify=lambda _: SimpleNamespace(user_id="00000000-0000-4000-8000-000000000001", email=None)))
    state = {"flushed": False, "closed": False}

    class TestLLM(LLMClient):
        def __init__(self):
            super().__init__(provider="mock")
            self.provider = "test"

    def make_engine(**kwargs):
        engine = DebateEngine(**kwargs)
        engine.llm_client = TestLLM()
        return engine

    class TestSTT:
        def __init__(self, **kwargs):
            self.on_final = kwargs["on_final"]
        async def connect(self):
            await asyncio.sleep(0)
            return stt_ready
        async def send_audio_chunk(self, _):
            pass
        async def flush_final_turn(self):
            state["flushed"] = True
            self.on_final("Our last answer has forty dollars acquisition cost and seven month payback.", 0.95)
            return True
        async def stop(self):
            state["closed"] = True

    class TestTTS:
        active_provider = "Test voice"
        def __init__(self, **_):
            pass
        async def stream_audio_chunks(self, *_args, **_kwargs):
            yield b"\x01\x00" * 32
        def cancel(self):
            pass
        async def close(self):
            pass

    async def connected():
        return "connected"
    monkeypatch.setattr(server, "DebateEngine", make_engine)
    monkeypatch.setattr(server, "AssemblyAIStreamingClient", TestSTT)
    monkeypatch.setattr(server, "RimeStreamingTTSClient", TestTTS)
    monkeypatch.setattr(server, "probe_rime", connected)
    monkeypatch.setattr(server, "probe_llm", connected)
    return state


@pytest.mark.parametrize("scenario", [
    "vc_pitch", "salary_negotiation", "hostile_cross_exam", "senior_interview",
    "sales_objections", "media_crisis", "hostile_boardroom", "custom_debate",
])
def test_each_scenario_waits_for_readiness_and_reports_the_final_answer(monkeypatch, scenario):
    state = install_live_flow_doubles(monkeypatch)
    query = urlencode({"scenario": scenario, "topic": "Test a clear product decision"})
    client = TestClient(server.app)
    with client.websocket_connect(f"/ws/debate?{query}") as ws:
        ws.send_json({"type": "authenticate", "access_token": "test-token"})
        ready = ws.receive_json()
        assert ready["type"] == "session_ready"
        ws.send_bytes(b"\x01\x00" * 32)
        ws.send_json({"type": "end_debate"})
        report = None
        for _ in range(30):
            frame = ws.receive()
            if frame.get("text"):
                event = json.loads(frame["text"])
                if event["type"] == "debate_report":
                    report = event
                    break
        assert report is not None
        assert report["scenario"] == scenario
        assert report["rounds_completed"] == 1
        assert report["transcript_complete"] is True
        assert state["flushed"]
    assert state["closed"]
    assert not server.SESSION_OWNERS
    saved = client.get(f"/api/session/{report['session_id']}/report", headers={"Authorization": "Bearer test-token"})
    assert saved.status_code == 200
    pdf = client.get(f"/api/debrief/{report['session_id']}/pdf", headers={"Authorization": "Bearer test-token"})
    assert pdf.content.startswith(b"%PDF")


def test_speech_startup_failure_never_emits_live_or_opening(monkeypatch):
    state = install_live_flow_doubles(monkeypatch, stt_ready=False)
    with TestClient(server.app).websocket_connect("/ws/debate") as ws:
        ws.send_json({"type": "authenticate", "access_token": "test-token"})
        event = ws.receive_json()
        assert event["type"] == "session_error"
        assert event["recoverable"] is False
    assert state["closed"]
    assert not server.SESSION_OWNERS


def finish_test_round(client):
    with client.websocket_connect("/ws/debate") as ws:
        ws.send_json({"type": "authenticate", "access_token": "test-token"})
        assert ws.receive_json()["type"] == "session_ready"
        ws.send_json({"type": "end_debate"})
        for _ in range(30):
            frame = ws.receive()
            if frame.get("text"):
                event = json.loads(frame["text"])
                if event["type"] == "debate_report":
                    return event
    pytest.fail("A finished round must produce a report.")


def test_unsaved_report_can_be_downloaded_and_does_not_block_the_next_round(monkeypatch):
    install_live_flow_doubles(monkeypatch)
    def unavailable(*_):
        raise RuntimeError("Test storage unavailable")
    monkeypatch.setattr(server.get_debrief_store(), "save_report", unavailable)
    client = TestClient(server.app)
    report = finish_test_round(client)
    assert report["persistence_status"] == "temporary"
    pdf = client.get(f"/api/debrief/{report['session_id']}/pdf", headers={"Authorization": "Bearer test-token"})
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    next_report = finish_test_round(client)
    assert next_report["session_id"] != report["session_id"]


def test_evaluator_timeout_returns_unscored_feedback_instead_of_hanging(monkeypatch):
    install_live_flow_doubles(monkeypatch)
    factory = server.DebateEngine
    def timed_out_engine(**kwargs):
        engine = factory(**kwargs)
        async def timeout():
            raise asyncio.TimeoutError()
        engine.generate_llm_debrief_report = timeout
        return engine
    monkeypatch.setattr(server, "DebateEngine", timed_out_engine)
    report = finish_test_round(TestClient(server.app))
    assert report["overall_score"] is None
    assert report["assessment_method"] == "heuristic"
    assert "timed out" in report["assessment_note"]
    assert report["transcript_complete"] is True


@pytest.mark.asyncio
async def test_endpointing_drains_audio_and_records_final_before_returning():
    order = []
    client = AssemblyAIStreamingClient(api_key="test", on_final=lambda text, _: order.append(text))
    class Socket:
        async def send(self, value):
            if isinstance(value, bytes):
                order.append("audio")
            else:
                assert json.loads(value)["type"] == "ForceEndpoint"
                order.append("endpoint")
                client.on_final("final answer", 1.0)
                client._final_event.set()
    client._ws = Socket()
    client._is_connected = True
    client.pending_transcript = "final"
    await client.send_audio_chunk(b"audio")
    task = asyncio.create_task(client._send_loop())
    try:
        assert await client.flush_final_turn(timeout=0.2)
        assert order == ["audio", "endpoint", "final answer"]
    finally:
        task.cancel()
        await task


@pytest.mark.asyncio
async def test_formatted_turn_is_not_endpoint_and_final_turn_is_not_duplicated():
    finals, partials = [], []
    client = AssemblyAIStreamingClient(api_key="test", on_final=lambda text, _: finals.append(text),
        on_partial=lambda text, _: partials.append(text))
    frames = iter([
        {"type": "Turn", "transcript": "partial", "turn_is_formatted": True, "end_of_turn": False},
        {"type": "Turn", "transcript": "complete", "end_of_turn": True, "turn_order": 1},
        {"type": "Turn", "transcript": "Complete.", "end_of_turn": True, "turn_order": 1},
    ])
    class Socket:
        async def recv(self):
            return json.dumps(next(frames))
    client._ws = Socket()
    await client._recv_loop()
    assert partials == ["partial"]
    assert finals == ["complete"]


@pytest.mark.asyncio
async def test_unconfirmed_audio_is_not_reported_as_complete_transcription():
    client = AssemblyAIStreamingClient(api_key="test")
    class Socket:
        async def send(self, _):
            pass
    client._ws = Socket()
    client._is_connected = True
    client._audio_since_final = True
    assert await client.flush_final_turn(timeout=0.01) is False


@pytest.mark.asyncio
async def test_live_tts_without_key_does_not_yield_silent_fallback():
    client = RimeStreamingTTSClient()
    with pytest.raises(VoiceProviderError):
        async for _ in client.stream_audio_chunks("Do not simulate a working voice."):
            pytest.fail("Missing voice credentials must not yield audio.")


def test_preflight_reports_provider_failures_honestly(monkeypatch):
    async def ready(): return "connected"
    async def failed(): return "offline"
    monkeypatch.setattr(server, "probe_assemblyai", ready)
    monkeypatch.setattr(server, "probe_rime", failed)
    monkeypatch.setattr(server, "probe_llm", ready)
    result = TestClient(server.app).get("/api/preflight").json()
    assert result["voice_ready"] is False
    assert result["rime_status"] == "offline"
