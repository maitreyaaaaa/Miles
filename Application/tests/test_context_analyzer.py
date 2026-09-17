import pytest
from src.context.analyzer import (
    _parse_numeric_value,
    _extract_metrics_heuristically,
    _heuristic_context_analysis,
    analyze_context_document,
    NumericMetric,
    ContextDossier,
)


def test_parse_numeric_value():
    assert _parse_numeric_value("$45") == 45.0
    assert _parse_numeric_value("$1.5M") == 1_500_000.0
    assert _parse_numeric_value("250k") == 250_000.0
    assert _parse_numeric_value("82%") == 82.0
    assert _parse_numeric_value("10B") == 10_000_000_000.0
    assert _parse_numeric_value("invalid") == 0.0


def test_extract_metrics_heuristically_pitch_deck():
    sample_deck = """
    Company: Miles Voice Systems Inc.
    Executive Summary:
    We provide real-time voice sparring.
    Our CAC is $50 and our LTV is $2500.
    Current ARR is $1.8M with 84% gross margin.
    We have 14 engineers on the core systems team.
    Our monthly churn is 1.5% with a 4-month payback window.
    """
    metrics = _extract_metrics_heuristically(sample_deck)
    metric_names = [m.name.lower() for m in metrics]

    assert any("cac" in name or "customer acquisition" in name for name in metric_names)
    assert any("arr" in name or "annual recurring" in name for name in metric_names)
    assert any("margin" in name for name in metric_names)
    assert any("engineers" in name for name in metric_names)

    cac_metric = next(m for m in metrics if "cac" in m.name.lower() or "customer acquisition" in m.name.lower())
    assert cac_metric.numeric_value == 50.0
    assert cac_metric.unit == "$"


def test_heuristic_context_analysis_pitch_deck():
    sample_deck = "Seed round pitch deck for investor presentation. Our CAC is $30, ARR is $500k, runway is 18 months."
    dossier = _heuristic_context_analysis(sample_deck, "pitch_deck_v1.pdf")

    assert dossier.doc_type == "pitch_deck"
    assert dossier.recommended_scenario == "vc_pitch"
    assert len(dossier.numeric_metrics) >= 2
    assert len(dossier.vulnerabilities) > 0
    assert len(dossier.cross_exam_traps) > 0


def test_heuristic_context_analysis_resume():
    sample_resume = "Curriculum Vitae: Jane Doe, Lead Systems Architect. Education: Bachelor of Science. Experience: 6 years. Led team of 12 developers."
    dossier = _heuristic_context_analysis(sample_resume, "resume_jane.docx")

    assert dossier.doc_type == "resume_cv"
    assert len(dossier.numeric_metrics) >= 1
    assert len(dossier.cross_exam_traps) > 0


from src.debate.llm_client import LLMClient


@pytest.mark.asyncio
async def test_analyze_context_document_async():
    text = "Pitch Deck: Our CAC is $45, Gross Margin is 80%, 20 engineers."
    mock_client = LLMClient(provider="mock")
    dossier = await analyze_context_document(text, "deck.txt", llm_client=mock_client)
    assert isinstance(dossier, ContextDossier)
    assert dossier.doc_type == "pitch_deck"
    assert len(dossier.numeric_metrics) >= 2
