import pytest
from fastapi.testclient import TestClient
from src.api.server import app
from src.debate.llm_client import LLMClient
from src.meeting.scheduler import get_meeting_scheduler

client = TestClient(app)


def test_generate_instant_link():
    res = client.get("/api/meeting/generate-link")
    assert res.status_code == 200
    data = res.json()
    assert "meet_url" in data
    assert "meet.google.com" in data["meet_url"]


def test_meeting_schedule_and_retrieve():
    payload = {
        "meet_url": "https://meet.google.com/xyz-uvwx-rst",
        "persona_id": "vc_pitch",
        "difficulty": "hard",
        "max_duration_seconds": 900,
    }
    res = client.post("/api/meeting/schedule", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["meet_url"] == "https://meet.google.com/xyz-uvwx-rst"
    assert data["status"] == "scheduled"
    meeting_id = data["meeting_id"]

    # Retrieve
    res_get = client.get(f"/api/meeting/{meeting_id}")
    assert res_get.status_code == 200
    assert res_get.json()["meeting_id"] == meeting_id

    # List
    res_list = client.get("/api/meetings")
    assert res_list.status_code == 200
    meetings = res_list.json()["meetings"]
    assert any(m["meeting_id"] == meeting_id for m in meetings)


def test_meeting_start_and_stop_lifecycle():
    # Schedule
    res = client.post("/api/meeting/schedule", json={"persona_id": "vc_pitch"})
    assert res.status_code == 200
    meeting_id = res.json()["meeting_id"]

    # Start
    res_start = client.post(f"/api/meeting/{meeting_id}/start")
    assert res_start.status_code == 200
    start_data = res_start.json()
    assert start_data["status"] == "in_call"
    assert "opening_statement" in start_data

    # Set mock LLM on active coordinator so stop generates report without real LLM key
    scheduler = get_meeting_scheduler()
    coordinator = scheduler.get_coordinator(meeting_id)
    if coordinator:
        coordinator.engine.llm_client = LLMClient(provider="mock")

    # Stop
    res_stop = client.post(f"/api/meeting/{meeting_id}/stop")
    assert res_stop.status_code == 200
    stop_data = res_stop.json()
    assert stop_data["status"] == "completed"
    assert "debrief_report" in stop_data

    # Retrieve debrief
    res_debrief = client.get(f"/api/meeting/{meeting_id}/debrief")
    assert res_debrief.status_code == 200
    assert "overall_score" in res_debrief.json()

    # Retrieve debrief HTML
    res_html = client.get(f"/api/meeting/{meeting_id}/debrief/html")
    assert res_html.status_code == 200
    assert "Miles Sparring Debrief" in res_html.text
