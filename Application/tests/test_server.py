import json
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from src.api import server
from src.api.server import app, SESSIONS, SESSION_OWNERS
from src.debate.engine import DebateEngine
from src.debate.llm_client import LLMClient
from src.meeting.bridge_ticket import create_bridge_ticket
from src.meeting.models import MeetingSession
from src.meeting.scheduler import get_meeting_scheduler

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "active_providers" not in data
    assert "config" not in data


def test_preflight_endpoint():
    response = client.get("/api/preflight")
    assert response.status_code == 200
    data = response.json()
    assert data["backend_status"] == "healthy"
    assert "assemblyai_status" in data
    assert "assemblyai_model" in data
    assert "rime_status" in data
    assert "rime_model" in data
    assert "rime_speaker" in data
    assert "active_llm" in data


def test_scenarios_endpoint():
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    data = response.json()
    assert "scenarios" in data
    assert "difficulties" in data
    assert "persona_tones" in data
    assert len(data["scenarios"]) == 8
    assert len(data["persona_tones"]) == 5


def test_persona_tones_endpoint():
    response = client.get("/api/personas/tones")
    assert response.status_code == 200
    data = response.json()
    assert "tones" in data
    assert len(data["tones"]) == 5



def test_custom_scenario_endpoint():
    payload = {
        "topic": "Remote work is destroying corporate loyalty",
        "difficulty": "ruthless",
    }
    response = client.post("/api/scenarios/custom", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["scenario_id"] == "custom_debate"
    assert data["topic"] == payload["topic"]
    assert len(data["contrarian_thesis"]) > 0
    assert len(data["opening_statement"]) > 0
    assert len(data["attack_vectors"]) == 5
    assert len(data["trap_questions"]) == 3
    assert "scoring_rubric" in data
    assert "difficulty_profile" in data


def test_session_report_endpoint():
    # Pre-populate dummy session
    engine = DebateEngine(scenario_id="vc_pitch")
    engine.start_debate()
    engine.record_user_turn("Our CAC is low.", duration_sec=2.0)
    SESSIONS[engine.session_id] = engine
    SESSION_OWNERS[engine.session_id] = "00000000-0000-4000-8000-000000000001"

    response = client.get(f"/api/session/{engine.session_id}/report")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == engine.session_id
    assert "overall_score" in data


def _receive_event(ws):
    frame = ws.receive()
    if "text" in frame and frame["text"]:
        try:
            return json.loads(frame["text"])
        except Exception:
            return {"type": "raw_text", "text": frame["text"]}
    elif "bytes" in frame and frame["bytes"]:
        return {"type": "audio_bytes", "size": len(frame["bytes"])}
    return {}


def test_websocket_debate_lifecycle():
    with client.websocket_connect("/ws/debate?scenario=vc_pitch&difficulty=hard&audio_format=base64") as ws:
        received_types = set()

        # Read initial events until we receive opening transcript and telemetry
        for _ in range(20):
            msg = _receive_event(ws)
            mtype = msg.get("type")
            if mtype:
                received_types.add(mtype)
            if "transcript" in received_types and "composure_telemetry" in received_types:
                break

        assert "transcript" in received_types
        assert "composure_telemetry" in received_types

        # Send simulated user statement
        ws.send_text(json.dumps({
            "type": "user_text",
            "text": "Our customer acquisition cost is forty dollars with seven month payback.",
        }))

        # Collect subsequent events until user transcript and response are processed
        user_transcript_confirmed = False
        for _ in range(25):
            msg = _receive_event(ws)
            mtype = msg.get("type")
            if mtype:
                received_types.add(mtype)
            if msg.get("type") == "transcript" and msg.get("role") == "user":
                user_transcript_confirmed = True
                break

        assert user_transcript_confirmed, "Expected user transcript confirmation in WebSocket stream"

        # Verify AI counter-attack response is generated and streamed
        ai_response_confirmed = False
        for _ in range(35):
            msg = _receive_event(ws)
            if msg.get("type") == "transcript" and msg.get("role") == "ai":
                ai_response_confirmed = True
                break

        assert ai_response_confirmed, "Expected AI counter-response after user statement"

        # Request end debate and debrief report
        ws.send_text(json.dumps({"type": "end_debate"}))

        report_found = False
        for _ in range(25):
            msg = _receive_event(ws)
            if msg.get("type") == "debate_report":
                assert "overall_score" in msg
                assert "verdict" in msg
                assert "metrics" in msg
                report_found = True
                break

        assert report_found, "Debate report not received after end_debate command"


def test_meeting_bridge_websocket_authenticates_and_saves_debrief(monkeypatch):
    owner_id = "00000000-0000-4000-8000-000000000001"
    secret = "bridge-test-secret-" * 3
    scheduler = get_meeting_scheduler()
    session = MeetingSession(
        owner_id=owner_id,
        recall_bot_id="bot_bridge_test",
        meet_url="https://meet.google.com/test-room-123",
    )
    scheduler.store.save_session(session)
    ticket = create_bridge_ticket(
        meeting_id=session.meeting_id,
        owner_id=owner_id,
        secret=secret,
        expires_at=int(time.time()) + 300,
    )
    monkeypatch.setattr(server, "config", SimpleNamespace(
        google_meet_enabled=True,
        recall_audio_bridge_secret=secret,
        assemblyai_api_key="",
        sample_rate=16000,
        rime_model_id="test",
        tts_sample_rate=22050,
        openai_model="test",
        openai_api_key="",
        gemini_model="test",
        gemini_api_key="",
    ))

    real_debate_engine = server.DebateEngine

    def make_mock_engine(**kwargs):
        engine = real_debate_engine(**kwargs)
        engine.llm_client = LLMClient(provider="mock")
        return engine

    class TestTTS:
        def __init__(self, **_kwargs):
            pass

        async def stream_audio_chunks(self, _text, **_kwargs):
            yield b"\x00\x00"

        def cancel(self):
            pass

        async def close(self):
            pass

    class TestSTT:
        def __init__(self, **_kwargs):
            pass

        async def connect(self):
            return True

        async def stop(self):
            pass

        async def send_audio_chunk(self, _chunk):
            pass

        async def flush_final_turn(self):
            return True

    leave_requests = []

    class TestRecallService:
        async def leave_call(self, bot_id):
            leave_requests.append(bot_id)
            return True

    monkeypatch.setattr(server, "DebateEngine", make_mock_engine)
    monkeypatch.setattr(server, "RimeStreamingTTSClient", TestTTS)
    monkeypatch.setattr(server, "AssemblyAIStreamingClient", TestSTT)
    monkeypatch.setattr(server, "RecallService", TestRecallService)

    with client.websocket_connect("/ws/debate?meeting_bridge=true") as ws:
        ws.send_text(json.dumps({"type": "meeting_bridge_auth", "ticket": ticket}))
        bridge_ready = False
        for _ in range(20):
            message = _receive_event(ws)
            if message.get("type") == "meeting_bridge_ready":
                bridge_ready = True
                break
        assert bridge_ready
        ws.send_text(json.dumps({"type": "meeting_bridge_audio_ready"}))
        started = False
        opening_received = False
        for _ in range(20):
            message = _receive_event(ws)
            if message.get("type") == "meeting_bridge_started":
                started = True
            if message.get("type") == "transcript" and message.get("role") == "ai":
                opening_received = True
                break
        assert started
        assert opening_received
        assert session.meeting_id in SESSIONS

        ws.send_text(json.dumps({"type": "end_debate"}))
        report_received = False
        for _ in range(30):
            message = _receive_event(ws)
            if message.get("type") == "debate_report":
                report_received = True
                break
        assert report_received

    stored = scheduler.get_session(owner_id, session.meeting_id)
    assert stored is not None
    assert stored.debrief_report is not None
    assert stored.status.value == "completed"
    assert leave_requests == ["bot_bridge_test"]


def test_meeting_bridge_fails_closed_when_speech_recognition_is_unavailable(monkeypatch):
    owner_id = "00000000-0000-4000-8000-000000000001"
    secret = "bridge-test-secret-" * 3
    scheduler = get_meeting_scheduler()
    session = MeetingSession(owner_id=owner_id, recall_bot_id="bot_bridge_failure")
    scheduler.store.save_session(session)
    ticket = create_bridge_ticket(
        meeting_id=session.meeting_id,
        owner_id=owner_id,
        secret=secret,
        expires_at=int(time.time()) + 300,
    )
    monkeypatch.setattr(server, "config", SimpleNamespace(
        google_meet_enabled=True,
        recall_audio_bridge_secret=secret,
        assemblyai_api_key="test-assembly-key",
        sample_rate=16000,
        rime_model_id="test",
        tts_sample_rate=22050,
        openai_model="test",
        openai_api_key="",
        gemini_model="test",
        gemini_api_key="",
    ))

    real_debate_engine = server.DebateEngine

    def make_mock_engine(**kwargs):
        engine = real_debate_engine(**kwargs)
        engine.llm_client = LLMClient(provider="mock")
        return engine

    class TestTTS:
        def __init__(self, **_kwargs):
            pass

        def cancel(self):
            pass

        async def close(self):
            pass

    class FailedSTT:
        def __init__(self, **_kwargs):
            pass

        async def connect(self):
            return False

        async def stop(self):
            pass

    class TestRecallService:
        async def leave_call(self, bot_id):
            assert bot_id == "bot_bridge_failure"
            return True

    monkeypatch.setattr(server, "DebateEngine", make_mock_engine)
    monkeypatch.setattr(server, "RimeStreamingTTSClient", TestTTS)
    monkeypatch.setattr(server, "AssemblyAIStreamingClient", FailedSTT)
    monkeypatch.setattr(server, "RecallService", TestRecallService)

    with client.websocket_connect("/ws/debate?meeting_bridge=true") as ws:
        ws.send_text(json.dumps({"type": "meeting_bridge_auth", "ticket": ticket}))
        error = _receive_event(ws)
        assert error["type"] == "meeting_bridge_error"
        assert "speech recognition" in error["message"]

    stored = scheduler.get_session(owner_id, session.meeting_id)
    assert stored is not None
    assert stored.status.value == "failed"
    assert session.meeting_id not in SESSIONS


def test_websocket_barge_in_and_debrief_metrics():
    """Verify that user barge-in cuts off AI speech and correctly increments debrief metrics."""
    with client.websocket_connect("/ws/debate?scenario=hostile_cross_exam&difficulty=ruthless&audio_format=base64") as ws:
        # Wait until AI opening salvo starts
        opened = False
        for _ in range(10):
            msg = _receive_event(ws)
            if msg.get("type") == "transcript" and msg.get("role") == "ai":
                opened = True
                break
        assert opened

        # Simulate user barging in while AI is speaking
        ws.send_text(json.dumps({
            "type": "user_text",
            "text": "Objection! The ledger discrepancy was caused by bank wire delays, not fraud.",
        }))

        # Collect interruption event and user turn confirmation
        interruption_seen = False
        user_turn_recorded = False
        for _ in range(25):
            msg = _receive_event(ws)
            if msg.get("type") == "interruption" and msg.get("by") == "user":
                interruption_seen = True
            if msg.get("type") == "composure_telemetry":
                user_turn_recorded = True
            if interruption_seen and user_turn_recorded:
                break

        assert interruption_seen, "Expected user barge-in interruption event"

        # Conclude debate and verify debrief report records the barge-in
        ws.send_text(json.dumps({"type": "end_debate"}))
        report = None
        for _ in range(25):
            msg = _receive_event(ws)
            if msg.get("type") == "debate_report":
                report = msg
                break

        assert report is not None, "Debrief report must be emitted"
        assert report["metrics"]["barge_ins"] >= 1, f"Expected barge_ins >= 1, got {report['metrics']['barge_ins']}"


def test_interruption_manager_adversarial_floor_control():
    """Verify that InterruptionManager suppresses user barge-in while AI interruption is active."""
    from unittest.mock import MagicMock
    from src.voice.interruption_manager import InterruptionManager

    mock_tts = MagicMock()
    mgr = InterruptionManager(tts_client=mock_tts)

    # 1. Normal AI speaking state -> user barge-in should succeed
    mgr.mark_ai_speaking("Our market cap is five billion dollars.")
    assert mgr.ai_is_speaking is True
    event = mgr.handle_user_speech_detected()
    assert event is not None
    assert event["by"] == "user"
    assert event["reason"] == "user_barge_in"
    assert mock_tts.cancel.called

    # 2. Adversarial interruption state -> user barge-in MUST be suppressed!
    mock_tts.reset_mock()
    cut_event = mgr.trigger_ai_interruption("Hold on, cut the buzzwords.", reason="fluff_detected")
    assert cut_event["by"] == "ai"
    assert mgr.ai_interruption_active is True

    mgr.mark_ai_speaking("Hold on, cut the buzzwords.")
    # Inbound user speech attempt while adversary holds floor
    suppressed_event = mgr.handle_user_speech_detected()
    assert suppressed_event is None, "User barge-in must be suppressed during adversarial AI interruption"
    assert not mock_tts.cancel.called, "TTS stream must NOT be cancelled by user speech during AI cut-in"

    # 3. Interruption concludes -> floor released
    mgr.end_ai_interruption()
    assert mgr.ai_interruption_active is False
    mgr.mark_ai_speaking("Now answer: what is your retention rate?")
    barge_after = mgr.handle_user_speech_detected()
    assert barge_after is not None
    assert barge_after["by"] == "user"
    assert mock_tts.cancel.called


def test_websocket_speech_intelligence_event():
    with client.websocket_connect("/ws/debate?scenario=vc_pitch&difficulty=hard&audio_format=base64") as ws:
        intelligence_event = None
        for _ in range(25):
            msg = _receive_event(ws)
            if msg.get("type") == "speech_intelligence":
                intelligence_event = msg
                break
        assert intelligence_event is not None
        assert "user_talk_time_sec" in intelligence_event
        assert "ai_talk_time_sec" in intelligence_event
        assert "dominance_ratio" in intelligence_event
        assert "user_pct" in intelligence_event
        assert "ai_pct" in intelligence_event


def test_websocket_turn_telemetry_event():
    with client.websocket_connect("/ws/debate?scenario=senior_interview&difficulty=hard&audio_format=base64") as ws:
        telemetry_event = None
        for _ in range(25):
            msg = _receive_event(ws)
            if msg.get("type") == "turn_telemetry":
                telemetry_event = msg
                break
        assert telemetry_event is not None, "Expected turn_telemetry event in WebSocket stream"
        assert "ttfa_ms" in telemetry_event
        assert "barge_in_latency_ms" in telemetry_event
        assert "stt_provider" in telemetry_event
        assert "tts_provider" in telemetry_event
        assert "llm_provider" in telemetry_event
        assert telemetry_event["ttfa_ms"] > 0


def test_synthesize_endpoint():
    """Verify that /api/tts/synthesize returns standard WAV audio bytes."""
    resp = client.post(
        "/api/tts/synthesize",
        json={"text": "Our unit economics are fully profitable.", "speaker": "alpine"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/wav"
    assert len(resp.content) >= 44
    assert resp.content[:4] == b"RIFF"
    assert resp.content[8:12] == b"WAVE"

    # Verify empty text validation
    empty_resp = client.post("/api/tts/synthesize", json={"text": "   "})
    assert empty_resp.status_code == 400


def test_rematch_evaluate_endpoint():
    """Verify that /api/debate/rematch/evaluate scores an upgraded retry."""
    payload = {
        "scenario": "vc_pitch",
        "opponent": "Marcus Vance",
        "trap": "Stop right there. Wrap it up and give me the bottom line.",
        "original_quote": "Well, um, basically we are kinda growing, you know, sort of fast.",
        "upgraded_answer": "Our gross margin is eighty-four percent with a four-month CAC payback across two thousand accounts.",
        "duration_seconds": 12.0,
    }
    resp = client.post("/api/debate/rematch/evaluate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "new_score" in data
    assert data["assessment_method"] in {"ai", "heuristic"}
    assert "delta_score" not in data
    assert "original_score" not in data
    assert data["fillers_before"] >= 3
    assert data["fillers_after"] == 0
    assert "adversary_reaction" in data
    assert "pacing_verdict" in data

    # Empty upgraded answer validation
    bad_resp = client.post("/api/debate/rematch/evaluate", json={
        "trap": "Why?",
        "original_quote": "Uh",
        "upgraded_answer": "   ",
    })
    assert bad_resp.status_code == 400
