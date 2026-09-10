import pytest
from src.analytics.composure_scorer import ComposureScorer, TelemetrySnapshot


def test_filler_word_detection():
    scorer = ComposureScorer()
    text = "Well, um, our revenue is like, basically fifty thousand dollars, you know?"
    fillers = scorer.detect_fillers(text)
    assert "um" in fillers
    assert "like" in fillers
    assert "basically" in fillers
    assert "you know" in fillers
    assert len(fillers) == 4


def test_buzzword_detection():
    scorer = ComposureScorer()
    text = "We are delivering a revolutionary, disruptive paradigm for seamless synergy."
    buzzwords = scorer.detect_buzzwords(text)
    assert "revolutionary" in buzzwords
    assert "disruptive" in buzzwords or "disrupt" in buzzwords
    assert "paradigm" in buzzwords
    assert "seamless" in buzzwords
    assert "synergy" in buzzwords


def test_composure_scoring_penalties():
    scorer = ComposureScorer(initial_score=85)
    
    # Flustered utterance with multiple fillers and 3-second hesitation
    snap = scorer.evaluate_turn(
        transcript="Um, uh, basically we sort of don't have that number yet.",
        duration_seconds=5.0,
        hesitation_seconds=3.0,
        pressure_level=3,
    )
    assert snap.composure_score < 80
    assert snap.filler_word_count >= 4
    assert len(snap.recent_fillers) > 0
    assert len(scorer.turn_weaknesses) > 0


def test_composure_scoring_rewards():
    scorer = ComposureScorer(initial_score=70)
    
    # Crisp, confident, direct response (15 words, ~150 WPM, zero fillers, barge-in)
    snap = scorer.evaluate_turn(
        transcript="Our gross margin is eighty-four percent, and our payback period is five months.",
        duration_seconds=5.0,
        hesitation_seconds=0.2,
        pressure_level=3,
        was_barge_in=True,
    )
    assert snap.composure_score > 70
    assert snap.filler_word_count == 0


def test_debrief_report_generation():
    scorer = ComposureScorer(initial_score=85)
    scorer.evaluate_turn("Our CAC is sixty dollars.", duration_seconds=3.0)
    scorer.evaluate_turn("Um, we are sort of testing that, like, right now.", duration_seconds=4.0, hesitation_seconds=2.5)
    scorer.record_ai_interruption()

    report = scorer.generate_debrief_report()
    assert report["type"] == "debate_report"
    assert "overall_score" in report
    assert "verdict" in report
    assert "metrics" in report
    assert report["metrics"]["total_words"] > 0
    assert report["metrics"]["ai_interruptions"] == 1
    assert len(report["key_weaknesses"]) > 0
    assert len(report["coaching_tips"]) > 0
