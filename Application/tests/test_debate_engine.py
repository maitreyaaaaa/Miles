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


def test_detect_micro_hesitations():
    from src.voice.assemblyai_stream import detect_micro_hesitations, SCENARIO_VOCABULARY

    words = [
        {"word": "our", "start": 100, "end": 300, "confidence": 0.98},
        {"word": "CAC", "start": 1200, "end": 1500, "confidence": 0.99},  # 900ms gap (>750ms)
        {"word": "is", "start": 1550, "end": 1700, "confidence": 0.95},
        {"word": "forty", "start": 2600, "end": 2900, "confidence": 0.92},  # 900ms gap
    ]
    hesitations = detect_micro_hesitations(words, threshold_ms=750)
    assert len(hesitations) == 2
    assert hesitations[0]["word_before"] == "our"
    assert hesitations[0]["word_after"] == "CAC"
    assert hesitations[0]["gap_ms"] == 900
    assert hesitations[1]["gap_ms"] == 900

    assert "vc_pitch" in SCENARIO_VOCABULARY
    assert "CAC" in SCENARIO_VOCABULARY["vc_pitch"]
    assert "salary_negotiation" in SCENARIO_VOCABULARY
