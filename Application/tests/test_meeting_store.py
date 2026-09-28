import json
import threading

from src.meeting.models import MeetingSession, MeetingStatus
from src.meeting.store import MeetingStore


def test_concurrent_meeting_saves_are_serialized_and_persisted(tmp_path):
    store = MeetingStore(tmp_path / "sessions.json")
    owner_id = "00000000-0000-4000-8000-000000000001"
    sessions = [MeetingSession(meeting_id=f"meeting_{index}", owner_id=owner_id) for index in range(20)]
    threads = [threading.Thread(target=store.save_session, args=(session,)) for session in sessions]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    store.flush()

    persisted = json.loads((tmp_path / "sessions.json").read_text(encoding="utf-8"))
    assert {item["meeting_id"] for item in persisted} == {session.meeting_id for session in sessions}
    assert not list(tmp_path.glob("*.tmp"))

    reloaded = MeetingStore(tmp_path / "sessions.json")
    assert len(reloaded.list_sessions(owner_id)) == len(sessions)


def test_meeting_store_only_returns_sessions_to_their_owner(tmp_path):
    store = MeetingStore(tmp_path / "sessions.json")
    first_owner = "00000000-0000-4000-8000-000000000001"
    second_owner = "00000000-0000-4000-8000-000000000002"
    store.save_session(MeetingSession(meeting_id="private_meeting", owner_id=first_owner))

    assert store.get_session(first_owner, "private_meeting") is not None
    assert store.get_session(second_owner, "private_meeting") is None
    assert store.list_sessions(second_owner) == []


def test_attaching_recall_bot_preserves_webhook_received_first(tmp_path):
    owner_id = "00000000-0000-4000-8000-000000000001"
    store = MeetingStore(tmp_path / "sessions.json")
    session = MeetingSession(meeting_id="webhook_race", owner_id=owner_id)
    store.save_session(session)
    session.recall_status = "in_call_recording"
    session.recall_status_updated_at = 2000.0
    session.status = MeetingStatus.IN_CALL
    store.save_session(session)

    saved = store.attach_recall_bot(
        session,
        "bot-race",
        join_at=None,
        provider_notice="Recall audio connected",
    )

    assert saved.recall_bot_id == "bot-race"
    assert saved.recall_status == "in_call_recording"
    assert saved.status == MeetingStatus.IN_CALL
