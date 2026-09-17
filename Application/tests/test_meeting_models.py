import pytest
from src.meeting.models import MeetingConfig, MeetingSession, MeetingStatus


def test_meeting_config_defaults():
    cfg = MeetingConfig()
    assert cfg.max_duration_seconds == 1800
    assert cfg.audio_only is True
    assert cfg.participant_name == "Miles (Adversary)"

    data = cfg.to_dict()
    assert data["audio_only"] is True

    recovered = MeetingConfig.from_dict(data)
    assert recovered.max_duration_seconds == 1800
    assert recovered.audio_only is True


def test_meeting_session_serialization():
    session = MeetingSession(
        meet_url="https://meet.google.com/abc-defg-hij",
        persona_id="vc_pitch",
        difficulty="ruthless",
        context_id="ctx_test123",
        context_filename="Deck.pdf",
    )
    assert session.status == MeetingStatus.SCHEDULED
    assert session.meet_url == "https://meet.google.com/abc-defg-hij"

    d = session.to_dict()
    assert d["status"] == "scheduled"
    assert d["meet_url"] == "https://meet.google.com/abc-defg-hij"
    assert d["context_id"] == "ctx_test123"

    restored = MeetingSession.from_dict(d)
    assert restored.meeting_id == session.meeting_id
    assert restored.status == MeetingStatus.SCHEDULED
    assert restored.context_filename == "Deck.pdf"
