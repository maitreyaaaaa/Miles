import pytest
from src.debate.engine import DebateEngine
from src.debate.llm_client import LLMClient


@pytest.mark.asyncio
async def test_debate_engine_lifecycle():
    engine = DebateEngine(scenario_id="vc_pitch", difficulty="hard")
    assert engine.status == "ready"
    assert engine.pressure_level == 3

    # Start debate
    opening = engine.start_debate()
    assert engine.status == "active"
    assert len(opening) > 0
    assert engine.round_number == 1
    assert len(engine.history) == 1
    assert engine.history[0]["role"] == "ai"

    # User turn
    snapshot = engine.record_user_turn(
        transcript="Our customer acquisition cost is forty dollars, and LTV is three hundred.",
        duration_sec=4.0,
        hesitation_sec=0.5,
    )
    assert snapshot.composure_score > 70
    assert len(engine.history) == 2
    assert engine.history[1]["role"] == "user"

    # Adversary response stream
    chunks = []
    async for token in engine.generate_adversary_response():
        chunks.append(token)
    response = "".join(chunks)
    assert len(response) > 0
    assert engine.round_number == 2
    assert len(engine.history) == 3
    assert engine.history[2]["role"] == "ai"


@pytest.mark.asyncio
async def test_fluff_interruption_trigger():
    engine = DebateEngine(scenario_id="salary_negotiation", difficulty="ruthless")
    engine.start_debate()

    # User stalls with fillers
    stall_text = "Um, well, like, basically I sort of feel that maybe..."
    interjection = engine.check_fluff_interruption(stall_text, hesitation_sec=2.5)
    assert interjection is not None
    assert any(interjection == fi for fi in engine.persona.fluff_interjections)


def test_barge_in_memory_truncation():
    engine = DebateEngine(scenario_id="hostile_cross_exam")
    engine.start_debate()

    # Simulate AI utterance interrupted mid-stream
    engine.record_barge_in(actual_spoken_words="You claim you were", latency_ms=12.5)
    assert engine.status == "interrupted"
    assert engine.history[0]["content"] == "You claim you were"
    assert engine.history[0]["interrupted"] is True
    assert engine.history[0]["barge_in_latency_ms"] == 12.5


def test_debrief_report():
    engine = DebateEngine(scenario_id="custom_debate", topic="Artificial Intelligence")
    engine.start_debate()
    engine.record_user_turn("AI creates more jobs than it destroys.", duration_sec=3.0)
    report = engine.get_debrief_report()

    assert report["type"] == "debate_report"
    assert report["scenario"] == "custom_debate"
    assert report["topic"] == "Artificial Intelligence"
    assert report["overall_score"] > 0
    assert len(report["coaching_tips"]) > 0
