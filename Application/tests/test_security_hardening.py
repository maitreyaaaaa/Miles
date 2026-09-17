import asyncio
import io
import json
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.server import app, WebSocketChannel, is_allowed_origin
from src.context.store import ContextStore, is_safe_identifier as is_safe_context_id
from src.context.analyzer import ContextDossier
from src.meeting.store import MeetingStore, is_safe_identifier as is_safe_meeting_id
from src.meeting.debrief_dispatcher import DebriefDispatcher, is_safe_identifier as is_safe_debrief_id
from src.meeting.models import MeetingSession, MeetingConfig


client = TestClient(app)


def test_safe_identifier_validators():
    """Verify regex identifier whitelist rejects path traversal vectors."""
    safe_ids = ["test_123", "a-b-c", "session42", "valid_ID_100"]
    unsafe_ids = [
        "../etc/passwd",
        "..\\windows\\system32",
        "../../test",
        "test/foo",
        "test\\bar",
        "test.json",
        "id with spaces",
        "id;injection",
        "id\x00null",
        "",
        "a" * 65,  # Exceeds max 64 chars
    ]

    for sid in safe_ids:
        assert is_safe_context_id(sid), f"Expected safe: {sid}"
        assert is_safe_meeting_id(sid), f"Expected safe: {sid}"
        assert is_safe_debrief_id(sid), f"Expected safe: {sid}"

    for usid in unsafe_ids:
        assert not is_safe_context_id(usid), f"Expected unsafe: {usid}"
        assert not is_safe_meeting_id(usid), f"Expected unsafe: {usid}"
        assert not is_safe_debrief_id(usid), f"Expected unsafe: {usid}"


def test_context_store_path_traversal_protection(tmp_path):
    """Verify ContextStore rejects traversal attempts on save and get."""
    store = ContextStore(storage_dir=tmp_path)

    # 1. Traversal in context_id rejected on get
    assert store.get_context("../evil") is None
    assert store.get_context("..\\evil") is None
    assert store.get_context("../../outside") is None

    # 2. Traversal in save_context raises ValueError
    dossier = ContextDossier(
        context_id="../traversal_id",
        filename="test.txt",
        doc_type="general_doc",
        title="Malicious",
        executive_summary="Exploit",
        target_role_or_company="",
    )
    with pytest.raises(ValueError, match="Invalid context_id"):
        store.save_context(dossier)


def test_meeting_store_path_traversal_protection(tmp_path):
    """Verify MeetingStore rejects unsafe meeting IDs."""
    data_file = tmp_path / "sessions.json"
    store = MeetingStore(data_file=data_file)

    assert store.get_session("../outside") is None
    assert store.get_session("../../evil") is None
    assert store.get_session("session/with/slashes") is None

    # Valid session saves cleanly
    session = MeetingSession(
        meeting_id="valid_session_1",
        meet_url="https://meet.google.com/abc-defg-hij",
        persona_id="vc_pitch",
        difficulty="hard",
        config=MeetingConfig(audio_only=True),
    )
    store.save_session(session)
    retrieved = store.get_session("valid_session_1")
    assert retrieved is not None
    assert retrieved.meeting_id == "valid_session_1"


def test_debrief_dispatcher_path_traversal_protection(tmp_path):
    """Verify DebriefDispatcher rejects unsafe meeting IDs."""
    dispatcher = DebriefDispatcher(data_dir=tmp_path)

    assert dispatcher.get_saved_debrief("../malicious") is None
    assert dispatcher.get_saved_debrief("..\\malicious") is None


def test_origin_validation():
    """Verify allowed and disallowed origins for WebSocket security."""
    assert is_allowed_origin("http://localhost:5173")
    assert is_allowed_origin("http://localhost:3000")
    assert is_allowed_origin("http://127.0.0.1:5173")
    assert is_allowed_origin("http://127.0.0.1:8000")
    assert is_allowed_origin("http://localhost:8080")
    assert is_allowed_origin("")  # Non-browser or direct curl/script

    # Malicious external origins
    assert not is_allowed_origin("https://evil-hacker.com")
    assert not is_allowed_origin("http://malicious.site.io")
    assert not is_allowed_origin("https://phishing-miles.com")


def test_upload_context_document_oversize_rejected():
    """Verify upload endpoint enforces 10MB maximum limit and returns HTTP 413."""
    # Create payload slightly exceeding 10MB limit (10MB + 128KB)
    oversize_bytes = b"X" * (10 * 1024 * 1024 + 128 * 1024)
    file_payload = ("large_file.txt", io.BytesIO(oversize_bytes), "text/plain")

    response = client.post(
        "/api/context/upload",
        files={"file": file_payload},
    )
    assert response.status_code == 413
    assert "exceeds maximum allowed size" in response.json().get("detail", "")


def test_upload_context_document_empty_rejected():
    """Verify upload endpoint rejects 0-byte file."""
    empty_payload = ("empty.txt", io.BytesIO(b""), "text/plain")
    response = client.post(
        "/api/context/upload",
        files={"file": empty_payload},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_websocket_channel_concurrent_writes():
    """Verify WebSocketChannel serializes concurrent writes without data races."""
    sent_items = []

    class MockWebSocket:
        async def send_text(self, text: str):
            # Simulate slight async I/O yield
            await asyncio.sleep(0.001)
            sent_items.append(text)

        async def send_bytes(self, data: bytes):
            await asyncio.sleep(0.001)
            sent_items.append(data)

    stop_event = asyncio.Event()
    mock_ws = MockWebSocket()
    channel = WebSocketChannel(mock_ws, stop_event)

    # Spawn 50 concurrent writes
    tasks = []
    for i in range(25):
        tasks.append(channel.send_json({"idx": i}))
        tasks.append(channel.send_bytes(f"chunk_{i}".encode("utf-8")))

    await asyncio.gather(*tasks)

    assert len(sent_items) == 50
    # Stop event suppression
    stop_event.set()
    await channel.send_json({"should_not_send": True})
    assert len(sent_items) == 50
    await channel.cleanup()
