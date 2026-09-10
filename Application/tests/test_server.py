import json
import pytest
from fastapi.testclient import TestClient
from src.api.server import app, SESSIONS
from src.debate.engine import DebateEngine

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "active_providers" in data
    assert "config" in data


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
    assert len(data["scenarios"]) >= 4


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
