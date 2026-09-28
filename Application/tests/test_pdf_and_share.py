import pytest
from fastapi.testclient import TestClient

from src.api.server import app, SESSIONS, SESSION_OWNERS
from src.debate.engine import DebateEngine
from src.debate.debrief_store import get_debrief_store
from src.debate.pdf_generator import generate_executive_pdf


@pytest.fixture
def client():
    return TestClient(app)


def test_pdf_generation_bytes():
    dummy_report = {
        "session_id": "test-session-123456",
        "scenario": "vc_pitch",
        "topic": "Pitching Enterprise AI to Tier-1 VCs",
        "overall_score": 82,
        "verdict": "STRONG DEFENSE UNDER INTENSE PRESSURE",
        "verdict_description": "Founder defended gross margins with commanding clarity.",
        "metrics": {
            "composure_score": 82,
            "current_wpm": 142,
            "filler_word_count": 2,
            "barge_ins": 3,
            "turns_count": 6,
        },
        "weakest_answer": {
            "quote": "Our CAC payback is around twelve months, give or take.",
            "why_faltered": "Hedge words weakened credibility.",
        },
        "executive_reframes": [
            {
                "original_quote": "Our CAC payback is around twelve months.",
                "executive_reframe": "Our audited CAC payback is 9.4 months on net new enterprise logos.",
                "rationale": "Direct numbers silence skepticism.",
            }
        ],
        "coaching_tips": [
            "Anchor to gross margins before addressing overhead.",
            "Eliminate hedge words ('give or take', 'basically').",
        ],
    }

    pdf_bytes = generate_executive_pdf(dummy_report)
    assert pdf_bytes is not None
    assert len(pdf_bytes) > 500
    assert pdf_bytes[:4] == b"%PDF"


def test_pdf_generation_handles_unscored_session_metrics():
    pdf_bytes = generate_executive_pdf({
        "session_id": "empty-session-123",
        "scenario": "vc_pitch",
        "overall_score": None,
        "verdict": "NOT ENOUGH SPEECH TO SCORE",
        "verdict_description": "No participant speech was transcribed.",
        "metrics": {
            "composure_score": None,
            "current_wpm": None,
            "filler_word_count": None,
            "barge_ins": 0,
            "turns_count": 0,
        },
        "key_weaknesses": [],
        "coaching_tips": [],
    })

    assert pdf_bytes.startswith(b"%PDF")


def test_debrief_store_save_and_retrieve():
    store = get_debrief_store()
    report = {
        "topic": "Test Debrief",
        "overall_score": 90,
        "verdict": "DOMINANT PERFORMANCE",
    }
    share_id = store.save_debrief(report, owner_id="00000000-0000-4000-8000-000000000001")
    assert share_id.startswith("deb_")

    fetched = store.get_debrief(share_id)
    assert fetched is not None
    assert fetched["overall_score"] == 90
    assert fetched["share_id"] == share_id


def test_api_debrief_share_and_pdf_endpoints(client):
    owner_id = "00000000-0000-4000-8000-000000000001"
    engine = DebateEngine(scenario_id="vc_pitch", session_id="share-api-test-id")
    SESSIONS[engine.session_id] = engine
    SESSION_OWNERS[engine.session_id] = owner_id
    report_payload = {
        "report": {
            "session_id": engine.session_id,
            "scenario": "vc_pitch",
            "topic": "Testing Share API",
            "overall_score": 75,
            "verdict": "RESILIENT",
            "metrics": {
                "composure_score": 75,
                "current_wpm": 138,
                "filler_word_count": 4,
                "barge_ins": 1,
            },
        }
    }

    # 1. Share endpoint
    res = client.post("/api/debrief/share", json=report_payload)
    assert res.status_code == 200
    data = res.json()
    assert "share_id" in data
    share_id = data["share_id"]
    assert data["share_scope"] == "unguessable_read_only_link"
    assert len(share_id) > 20

    # 2. Get shared debrief
    get_res = client.get(f"/api/debrief/share/{share_id}")
    assert get_res.status_code == 200
    assert get_res.headers["cache-control"] == "no-store"
    fetched_data = get_res.json()
    assert fetched_data["overall_score"] == 75
    assert fetched_data["share_id"] == share_id

    # 3. PDF Export
    pdf_res = client.get(f"/api/debrief/{share_id}/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content[:4] == b"%PDF"


def test_saved_private_report_survives_live_session_cleanup(client):
    owner_id = "00000000-0000-4000-8000-000000000001"
    report = {
        "session_id": "completed-session-123",
        "topic": "Private report",
        "overall_score": 81,
    }
    get_debrief_store().save_report(report, owner_id)

    report_response = client.get(f"/api/session/{report['session_id']}/report")
    assert report_response.status_code == 200
    assert report_response.json()["overall_score"] == 81

    share_response = client.post("/api/debrief/share", json={"report": report})
    assert share_response.status_code == 200
    shared = client.get(f"/api/debrief/share/{share_response.json()['share_id']}")
    assert shared.status_code == 200
    assert "owner_id" not in shared.json()
