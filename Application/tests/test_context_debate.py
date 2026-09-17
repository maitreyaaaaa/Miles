import pytest
from fastapi.testclient import TestClient

from src.api.server import app, SESSIONS
from src.context.analyzer import ContextDossier, NumericMetric
from src.debate.engine import DebateEngine
from src.debate.personas import get_persona


@pytest.fixture
def client():
    return TestClient(app)


def test_paste_context_endpoint(client):
    payload = {
        "text": "Pitch Deck for Miles AI. Our CAC is $50, our ARR is $2.5M, and we have 18 engineers.",
        "filename": "deck.txt",
    }
    resp = client.post("/api/context/paste", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "context_id" in data
    assert data["doc_type"] == "pitch_deck"
    assert len(data["numeric_metrics"]) >= 2
    assert "vulnerabilities" in data
    assert "cross_exam_traps" in data


def test_get_context_endpoint(client):
    payload = {
        "text": "Technical RFC. Systems latency is 15ms. Peak throughput is 50000 requests per second.",
        "filename": "rfc.txt",
    }
    create_resp = client.post("/api/context/paste", json=payload)
    ctx_id = create_resp.json()["context_id"]

    get_resp = client.get(f"/api/context/{ctx_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["context_id"] == ctx_id


def test_list_contexts_endpoint(client):
    resp = client.get("/api/contexts")
    assert resp.status_code == 200
    assert "contexts" in resp.json()
    assert isinstance(resp.json()["contexts"], list)


def test_persona_with_context_dossier():
    dossier = {
        "title": "Seed Deck 2024",
        "doc_type": "pitch_deck",
        "numeric_metrics": [
            {"name": "Customer Acquisition Cost", "raw_value": "$45", "context": "B2B SaaS"},
            {"name": "Gross Margin", "raw_value": "85%", "context": "Software gross margin"},
        ],
        "vulnerabilities": [
            {"category": "Unit Economics", "issue": "Paid marketing saturation buffer missing"},
        ],
        "cross_exam_traps": [
            "Your deck claims an 85% gross margin. What is your compute cost once inference scales?",
        ],
    }
    persona = get_persona("vc_pitch", context_dossier=dossier)
    assert "GROUND-TRUTH" in persona.system_prompt
    assert "$45" in persona.system_prompt
    assert "85%" in persona.system_prompt
    assert persona.opening_statement == dossier["cross_exam_traps"][0]


def test_debate_engine_with_context_dossier_fact_discrepancy():
    dossier = {
        "title": "Seed Deck 2024",
        "doc_type": "pitch_deck",
        "numeric_metrics": [
            {"name": "Customer Acquisition Cost", "raw_value": "$45", "numeric_value": 45.0, "unit": "$", "category": "Financials", "context": "Paid CAC"},
        ],
        "vulnerabilities": [],
        "cross_exam_traps": ["What is your CAC?"],
    }
    engine = DebateEngine(scenario_id="vc_pitch", context_dossier=dossier)
    engine.start_debate()

    # User falsely claims: "Our customer acquisition cost is only ten dollars."
    snapshot = engine.record_user_turn(
        transcript="Our customer acquisition cost is only ten dollars.",
        duration_sec=3.0,
    )

    # Discrepancy should be flagged in bookmarks
    discrepancy_bookmarks = [b for b in engine.bookmarks if b.get("type") == "fact_discrepancy"]
    assert len(discrepancy_bookmarks) >= 1
    assert engine.pending_rectification is not None
    assert "$45" in engine.pending_rectification

    # Debrief report should contain ground truth audit
    report = engine.get_debrief_report()
    assert report["has_context"] is True
    assert "ground_truth_audit" in report
    assert report["ground_truth_audit"]["discrepancy_count"] >= 1
