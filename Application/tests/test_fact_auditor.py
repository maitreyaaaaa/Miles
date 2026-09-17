import pytest
from src.context.analyzer import ContextDossier, NumericMetric
from src.context.fact_auditor import FactAuditor, _extract_numeric_mentions


def test_extract_numeric_mentions():
    text_1 = "Our CAC is forty five dollars and we have 15 engineers."
    mentions_1 = _extract_numeric_mentions(text_1)
    vals_1 = [v for _, v in mentions_1]
    assert 45.0 in vals_1 or 15.0 in vals_1

    text_2 = "We generated $1.5M in ARR and our churn is 2%."
    mentions_2 = _extract_numeric_mentions(text_2)
    vals_2 = [v for _, v in mentions_2]
    assert 1_500_000.0 in vals_2
    assert 2.0 in vals_2


def test_fact_auditor_accurate_turn():
    dossier = ContextDossier(
        context_id="ctx-test-1",
        filename="deck.pdf",
        doc_type="pitch_deck",
        title="Test Pitch Deck",
        executive_summary="Summary",
        target_role_or_company="",
        numeric_metrics=[
            NumericMetric(
                name="Customer Acquisition Cost",
                raw_value="$45",
                numeric_value=45.0,
                unit="$",
                category="Financials",
                context="Paid CAC across B2B channels",
            ),
            NumericMetric(
                name="Annual Recurring Revenue",
                raw_value="$1.2M",
                numeric_value=1_200_000.0,
                unit="$",
                category="Financials",
                context="Annual contract value run rate",
            ),
        ],
    )

    auditor = FactAuditor(dossier)

    # User says: "Our customer acquisition cost is forty five dollars"
    res = auditor.audit_user_turn("Our customer acquisition cost is forty five dollars.")
    assert res.has_audit_event is True
    assert len(res.verified_items) >= 1
    assert res.verified_items[0].is_accurate is True
    assert len(res.discrepancies) == 0


def test_fact_auditor_discrepancy_and_rectification():
    dossier = ContextDossier(
        context_id="ctx-test-2",
        filename="deck.pdf",
        doc_type="pitch_deck",
        title="Test Pitch Deck",
        executive_summary="Summary",
        target_role_or_company="",
        numeric_metrics=[
            NumericMetric(
                name="Customer Acquisition Cost",
                raw_value="$45",
                numeric_value=45.0,
                unit="$",
                category="Financials",
                context="Paid CAC across B2B channels",
            ),
        ],
    )

    auditor = FactAuditor(dossier)

    # User falsely claims: "Our customer acquisition cost is only ten dollars."
    res = auditor.audit_user_turn("Our customer acquisition cost is only ten dollars.")
    assert res.has_audit_event is True
    assert len(res.discrepancies) == 1
    assert res.discrepancies[0].is_accurate is False
    assert res.immediate_rectification is not None
    assert "$45" in res.immediate_rectification
    assert "ten dollars" in res.immediate_rectification or "10" in res.immediate_rectification

    # Check audit summary
    summary = auditor.get_audit_summary()
    assert summary["discrepancy_count"] == 1
    assert summary["factual_accuracy_score"] == 0
