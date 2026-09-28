import pytest

from src.debate.engine import DebateEngine
from src.debate.llm_client import LLMClient


def test_sync_debrief_does_not_score_or_coach_a_session_without_user_speech():
    report = DebateEngine().get_debrief_report()

    assert report["overall_score"] is None
    assert report["assessment_status"] == "insufficient_data"
    assert report["assessment_method"] == "none"
    assert report["metrics"]["avg_wpm"] is None
    assert report["metrics"]["total_fillers"] is None
    assert report["key_weaknesses"] == []
    assert report["coaching_tips"] == []
    assert report["bookmarks"] == []


def test_sync_rule_based_debrief_keeps_performance_score_unscored():
    engine = DebateEngine()
    engine.record_user_turn("Um, our revenue reached eight million last year.", duration_sec=4)

    report = engine.get_debrief_report()

    assert report["overall_score"] is None
    assert report["assessment_method"] == "heuristic"
    assert report["metrics"]["composure_score"] is not None
    assert report["metrics"]["filler_word_count"] == 1


@pytest.mark.asyncio
async def test_async_debrief_does_not_score_a_session_without_user_speech():
    engine = DebateEngine(llm_client=LLMClient(provider="mock"))

    report = await engine.generate_llm_debrief_report()

    assert report["overall_score"] is None
    assert report["assessment_status"] == "insufficient_data"
    assert report["assessment_method"] == "none"
    assert report["metrics"]["current_wpm"] is None
    assert report["metrics"]["filler_word_count"] is None
    assert report["key_weaknesses"] == []
    assert report["coaching_tips"] == []
    assert report["bookmarks"] == []


@pytest.mark.asyncio
async def test_async_debrief_drops_model_quotes_that_are_not_in_the_user_transcript():
    class FakeEvaluator:
        async def generate_json_debrief(self, **_kwargs):
            return {
                "assessment_method": "ai",
                "overall_score": 90,
                "verdict": "STRONG DEFENSE",
                "key_weaknesses": [],
                "coaching_tips": [],
                "chapters": [],
                "weakest_answer": {"quote": "I invented this quote", "why_faltered": "Unsupported"},
                "strongest_answer": {"quote": "Our revenue reached eight million", "why_commanding": "Clear"},
                "executive_reframes": [
                    {
                        "original_quote": "The market is billions of dollars",
                        "executive_reframe": "We have a proven $50M opportunity.",
                    }
                ],
            }

    engine = DebateEngine(llm_client=FakeEvaluator())
    engine.record_user_turn("Our revenue reached eight million last year.", duration_sec=4)

    report = await engine.generate_llm_debrief_report()

    assert report["weakest_answer"] is None
    assert report["strongest_answer"]["quote"] == "Our revenue reached eight million"
    assert report["executive_reframes"] == []
