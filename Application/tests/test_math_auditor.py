import pytest
from src.debate.math_auditor import MathAuditor
from src.debate.engine import DebateEngine


def test_math_auditor_pricing_contradiction():
    auditor = MathAuditor()

    # Round 1: User claims $1M in revenue
    res1 = auditor.audit_user_turn("We did $1M in revenue last year across our customer base.", round_number=1)
    assert not res1.has_contradiction
    assert "revenue" in auditor.ledger
    assert auditor.ledger["revenue"].value == 1_000_000.0

    # Round 2: User claims 50 customers paying $10k a year (50 * 10k = 500k != 1M)
    res2 = auditor.audit_user_turn("We currently have 50 customers paying $10k a year.", round_number=2)
    assert res2.has_contradiction
    assert res2.discrepancy is not None
    assert res2.discrepancy.rule_type == "revenue_volume_price"
    assert "50 customers at $10,000 is $500,000, not $1,000,000" in res2.immediate_rectification_salvo


def test_math_auditor_runway_burn_contradiction():
    auditor = MathAuditor()

    # Turn 1: User claims $2M in cash
    auditor.audit_user_turn("We have $2M in the bank right now.", round_number=1)

    # Turn 2: User claims $200k monthly burn and 18 months runway (2M / 200k = 10 mos != 18 mos)
    res = auditor.audit_user_turn("Our monthly burn is $200k a month, and we have 18 months of runway.", round_number=2)
    assert res.has_contradiction
    assert res.discrepancy.rule_type == "runway_cash_burn"
    assert "10.0 months of runway, not 18" in res.immediate_rectification_salvo


def test_math_auditor_historical_drift():
    auditor = MathAuditor()

    # Round 1: $1.5M revenue
    auditor.audit_user_turn("We generated 1.5 million in revenue.", round_number=1)

    # Round 3: drops to 500k revenue without explanation
    res = auditor.audit_user_turn("Our revenue is 500k.", round_number=3)
    assert res.has_contradiction
    assert res.discrepancy.rule_type == "historical_drift"
    assert "In round 1 you claimed" in res.immediate_rectification_salvo


def test_engine_math_contradiction_integration():
    engine = DebateEngine(scenario_id="vc_pitch")

    # Round 1
    engine.record_user_turn("We hit $1M in revenue.", duration_sec=5.0)
    assert len(engine.math_auditor.discrepancy_history) == 0

    # Round 2: Trap triggered
    snap = engine.record_user_turn("We have 50 customers paying $10k a year.", duration_sec=5.0)
    assert len(engine.math_auditor.discrepancy_history) == 1
    assert any(b["type"] == "math_contradiction" for b in engine.bookmarks)
    assert "Wait. Stop right there" in engine.pending_rectification
