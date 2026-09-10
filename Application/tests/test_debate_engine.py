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


def test_debrief_2_bookmarks_and_chapters():
    engine = DebateEngine(scenario_id="vc_pitch")
    engine.start_debate()

    # 1. User barge-in
    engine.record_barge_in(actual_spoken_words="Wait Marcus, let me address that directly.", latency_ms=45.0)

    # 2. User answers with hesitation
    engine.record_user_turn(
        transcript="Um, we are seeing strong organic enterprise interest.",
        duration_sec=3.5,
        hesitation_sec=2.1,
    )

    # 3. AI cut-in
    engine.record_ai_cut_in(reason="fluff_detected", phrase="Cut the buzzwords. What is your net retention?")

    assert len(engine.bookmarks) >= 3
    types = [b["type"] for b in engine.bookmarks]
    assert "barge_in" in types
    assert "hesitation" in types
    assert "ai_cut_in" in types

    # 4. Debrief Report 2.0 structure
    report = engine.get_debrief_report()
    assert "bookmarks" in report
    assert len(report["bookmarks"]) >= 3
    assert "chapters" in report
    assert len(report["chapters"]) >= 1
    assert "weakest_answer" in report
    assert "quote" in report["weakest_answer"]
    assert "strongest_answer" in report
    assert "quote" in report["strongest_answer"]
    assert "executive_reframes" in report
    assert len(report["executive_reframes"]) >= 1


def test_record_micro_hesitation_bookmark():
    engine = DebateEngine(scenario_id="vc_pitch")
    engine.start_debate()

    engine.record_micro_hesitation(gap_ms=1350, word_before="our", word_after="burn")
    assert len(engine.bookmarks) == 1
    bm = engine.bookmarks[0]
    assert bm["type"] == "hesitation"
    assert "1.4s" in bm["label"]
    assert "our ... burn" == bm["quote"]

    # Deduplication within 2 seconds
    engine.record_micro_hesitation(gap_ms=1200, word_before="multiple", word_after="is")
    assert len(engine.bookmarks) == 1  # Deduplicated

    report = engine.get_debrief_report()
    assert any("our ... burn" in b.get("quote", "") for b in report["bookmarks"])


def test_extract_and_parse_json():
    from src.debate.llm_client import extract_and_parse_json

    # 1. Clean JSON
    res1 = extract_and_parse_json('{"overall_score": 88, "verdict": "DOMINANT"}')
    assert res1 is not None
    assert res1["overall_score"] == 88

    # 2. Markdown fenced JSON
    res2 = extract_and_parse_json('```json\n{"overall_score": 75, "verdict": "PRESSURE POINT"}\n```')
    assert res2 is not None
    assert res2["overall_score"] == 75

    # 3. Preamble text before JSON
    res3 = extract_and_parse_json('Here is the evaluation report:\n{"overall_score": 92}\nHope this helps.')
    assert res3 is not None
    assert res3["overall_score"] == 92

    # 4. Invalid input
    assert extract_and_parse_json("") is None
    assert extract_and_parse_json("Not a json at all") is None


def test_dossier_defensive_difficulty():
    from src.debate.dossier import generate_fallback_dossier

    dossier = generate_fallback_dossier("Autonomous Agents", difficulty=None)
    assert dossier is not None
    assert dossier["scenario_id"] == "custom_debate"
    assert dossier["topic"] == "Autonomous Agents"
    assert len(dossier["attack_vectors"]) == 5
    assert len(dossier["trap_questions"]) == 3


