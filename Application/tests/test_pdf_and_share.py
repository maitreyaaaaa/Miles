import pytest
from fastapi.testclient import TestClient

from src.api.server import app
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


def test_debrief_store_save_and_retrieve():
    store = get_debrief_store()
    report = {
        "topic": "Test Debrief",
        "overall_score": 90,
        "verdict": "DOMINANT PERFORMANCE",
    }
    share_id = store.save_debrief(report)
    assert share_id.startswith("deb_")

    fetched = store.get_debrief(share_id)
    assert fetched is not None
    assert fetched["overall_score"] == 90
    assert fetched["share_id"] == share_id


def test_api_debrief_share_and_pdf_endpoints(client):
    report_payload = {
        "report": {
            "session_id": "share-api-test-id",
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
