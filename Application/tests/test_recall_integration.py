from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import pytest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock, MagicMock
from starlette.testclient import TestClient

from src.api.server import app
from src.config import config
from src.meeting.recall_service import RecallService, RecallAPIError
from src.meeting.provider import RecallMeetBotProvider
from src.meeting.models import MeetingConfig, MeetingSession
from src.meeting.scheduler import get_meeting_scheduler
from src.meeting.bridge_ticket import (
    InvalidBridgeTicket,
    add_ticket_to_bridge_url,
    create_bridge_ticket,
    verify_bridge_ticket,
)

client = TestClient(app)
TEST_OWNER_ID = "00000000-0000-4000-8000-000000000001"


def save_owned_bot(bot_id: str):
    session = get_meeting_scheduler().schedule_meeting(
        owner_id=TEST_OWNER_ID,
        meet_url="https://meet.google.com/test-room-123",
    )
    session.recall_bot_id = bot_id
    get_meeting_scheduler().store.save_session(session)
    return session


def install_live_config(monkeypatch):
    live_config = SimpleNamespace(
        recall_ai_api_key="test-recall-key",
        recall_ai_region="ap-northeast-1",
        recall_ai_webhook_secret="test-webhook-secret",
        recall_ai_svix_webhook_secret="",
        recall_audio_bridge_url="https://miles.example/meeting-bridge.html",
        recall_audio_bridge_secret="b" * 48,
        assemblyai_api_key="test-assembly-key",
        rime_api_key="test-rime-key",
        openai_api_key="test-llm-key",
        gemini_api_key="",
        anthropic_api_key="",
    )
    monkeypatch.setattr("src.api.server.config", live_config)
    monkeypatch.setattr("src.meeting.recall_service.config", live_config)
    return live_config


def test_recall_service_headers_and_region():
    svc = RecallService(api_key="mock_key", region="ap-northeast-1")
    assert svc.region == "ap-northeast-1"
    assert "https://ap-northeast-1.recall.ai/api/v1" == svc.base_url
    assert svc.headers["Authorization"] == "Token mock_key"


def test_recall_service_missing_api_key():
    svc = RecallService(api_key="")
    with pytest.raises(RecallAPIError) as exc:
        _ = svc.headers
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_recall_service_create_bot_mock():
    svc = RecallService(api_key="mock_key", region="ap-northeast-1")
    mock_resp = {
        "id": "bot_123456",
        "meeting_url": "https://meet.google.com/abc-defg-hij",
        "status_changes": [{"code": "ready"}],
    }
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=201, json=lambda: mock_resp)
        res = await svc.create_bot(
            meeting_url="https://meet.google.com/abc-defg-hij",
            bot_name="Miles AI Bot",
            output_media_url="https://miles.example/meeting-bridge.html?ticket=opaque",
            max_duration_seconds=900,
        )
        assert res["id"] == "bot_123456"
        assert res["meeting_url"] == "https://meet.google.com/abc-defg-hij"
        assert mock_post.call_args.kwargs["json"]["output_media"]["camera"] == {
            "kind": "webpage",
            "config": {"url": "https://miles.example/meeting-bridge.html?ticket=opaque"},
        }
        assert mock_post.call_args.kwargs["json"]["automatic_leave"] == {
            "in_call_recording_timeout": 900,
            "in_call_not_recording_timeout": 900,
        }


@pytest.mark.asyncio
async def test_recall_service_leave_and_get_bot():
    svc = RecallService(api_key="mock_key", region="ap-northeast-1")
    with patch("httpx.AsyncClient.get") as mock_get, patch("httpx.AsyncClient.post") as mock_post:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"id": "bot_123", "status_changes": [{"code": "in_call"}]})
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})

        bot = await svc.get_bot("bot_123")
        assert bot["id"] == "bot_123"

        left = await svc.leave_call("bot_123")
        assert left is True


def test_recall_webhook_signature_verification():
    secret = "whsec_MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE"
    msg_id = "msg_test_123"
    msg_timestamp = "1790000000"
    payload = '{"event":"bot.status_change","data":{"bot_id":"bot_123"}}'

    key_bytes = base64.b64decode("MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE")
    to_sign = f"{msg_id}.{msg_timestamp}.{payload}".encode("utf-8")
    sig = base64.b64encode(hmac.new(key_bytes, to_sign, hashlib.sha256).digest()).decode("utf-8")

    headers = {
        "webhook-id": msg_id,
        "webhook-timestamp": msg_timestamp,
        "webhook-signature": f"v1,{sig}",
    }

    assert RecallService.verify_webhook_signature(headers, payload, secret=secret) is True

    # Bad signature
    bad_headers = {
        "webhook-id": msg_id,
        "webhook-timestamp": msg_timestamp,
        "webhook-signature": "v1,invalid_signature",
    }
    assert RecallService.verify_webhook_signature(bad_headers, payload, secret=secret) is False


def test_recall_webhook_rejects_missing_secret():
    empty_config = SimpleNamespace(recall_ai_webhook_secret="")
    with patch("src.meeting.recall_service.config", empty_config):
        assert RecallService.verify_webhook_signature({}, "{}") is False


def test_recall_webhook_verifies_legacy_svix_secret():
    secret = "legacy-test-secret"
    payload = "{}"
    msg_id = "msg_legacy"
    timestamp = "1790000000"
    signature = base64.b64encode(
        hmac.new(secret.encode(), f"{msg_id}.{timestamp}.{payload}".encode(), hashlib.sha256).digest()
    ).decode()
    legacy_config = SimpleNamespace(
        recall_ai_webhook_secret="",
        recall_ai_svix_webhook_secret=secret,
    )
    with patch("src.meeting.recall_service.config", legacy_config):
        assert RecallService.verify_webhook_signature(
            {
                "svix-id": msg_id,
                "svix-timestamp": timestamp,
                "svix-signature": f"v1,{signature}",
            },
            payload,
        ) is True


def test_meeting_bridge_ticket_is_scoped_signed_and_expires():
    ticket = create_bridge_ticket(
        meeting_id="meeting-123",
        owner_id=TEST_OWNER_ID,
        secret="b" * 48,
        expires_at=2000,
    )
    claims = verify_bridge_ticket(ticket, "b" * 48, now=1000)
    assert claims == {"meeting_id": "meeting-123", "owner_id": TEST_OWNER_ID, "expires_at": 2000}
    assert add_ticket_to_bridge_url("https://miles.example/meeting-bridge.html", ticket).startswith(
        "https://miles.example/meeting-bridge.html?ticket="
    )
    with pytest.raises(InvalidBridgeTicket):
        verify_bridge_ticket(ticket + "x", "b" * 48, now=1000)
    with pytest.raises(InvalidBridgeTicket):
        verify_bridge_ticket(ticket, "b" * 48, now=2000)


def test_launch_meeting_bot_invalid_url():
    resp = client.post("/api/meeting/bot/launch", json={
        "meeting_url": "not-a-valid-url",
    })
    assert resp.status_code == 400
    assert "valid meeting URL" in resp.json()["detail"]


def test_launch_meeting_bot_success_mock(monkeypatch):
    install_live_config(monkeypatch)
    mock_bot_resp = {
        "id": "bot_xyz_999",
        "meeting_url": "https://meet.google.com/xyz-uvwx-rst",
        "bot_name": "Miles AI (VC Pitch)",
        "status_changes": [{"code": "ready"}],
    }
    with patch.object(RecallService, "create_bot", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_bot_resp
        resp = client.post("/api/meeting/bot/launch", json={
            "meeting_url": "https://meet.google.com/xyz-uvwx-rst",
            "persona_id": "vc_pitch",
            "max_duration_seconds": 900,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connecting"
        assert data["bot_id"] == "bot_xyz_999"
        assert data["meeting_url"] == "https://meet.google.com/xyz-uvwx-rst"
        assert mock_create.call_args.kwargs["output_media_url"].startswith(
            "https://miles.example/meeting-bridge.html?ticket="
        )
        assert mock_create.call_args.kwargs["max_duration_seconds"] == 900


def test_get_bot_status_endpoint():
    session = save_owned_bot("bot_999")
    session.recall_status = "in_call_recording"
    get_meeting_scheduler().store.save_session(session)
    resp = client.get("/api/meeting/bot/bot_999")
    assert resp.status_code == 200
    assert resp.json()["id"] == "bot_999"
    assert resp.json()["status"] == "in_call_recording"


def test_leave_meeting_bot_endpoint():
    save_owned_bot("bot_999")
    with patch.object(RecallService, "leave_call", new_callable=AsyncMock) as mock_leave:
        mock_leave.return_value = True
        resp = client.post("/api/meeting/bot/bot_999/leave")
        assert resp.status_code == 200
        assert resp.json()["success"] is True


def test_list_recall_bots_endpoint():
    save_owned_bot("bot_1")
    save_owned_bot("bot_2")
    with patch.object(RecallService, "list_bots", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [{"id": "bot_1"}, {"id": "bot_2"}]
        resp = client.get("/api/meeting/bots")
        assert resp.status_code == 200
        assert len(resp.json()["bots"]) == 2


def test_recall_webhook_endpoint():
    msg_id = "msg_live_001"
    msg_timestamp = "1790000000"
    payload = '{"event":"bot.status_change","data":{"bot_id":"bot_live_123","status":{"code":"joining_call"}}}'

    with patch.object(RecallService, "verify_webhook_signature", return_value=True):
        resp = client.post(
            "/api/webhook/recall",
            content=payload,
            headers={
                "content-type": "application/json",
                "webhook-id": msg_id,
                "webhook-timestamp": msg_timestamp,
                "webhook-signature": "v1,valid_sig",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"
        assert resp.json()["event"] == "bot.status_change"

    with patch.object(RecallService, "verify_webhook_signature", return_value=False):
        resp = client.post(
            "/api/webhook/recall",
            content=payload,
            headers={
                "content-type": "application/json",
                "webhook-id": msg_id,
                "webhook-timestamp": msg_timestamp,
                "webhook-signature": "v1,bad_sig",
            },
        )
        assert resp.status_code == 401


def test_recall_status_webhook_updates_meeting_record():
    session = save_owned_bot("bot_webhook_321")
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    payload = {
        "event": "bot.status_change",
        "data": {
            "bot_id": "bot_webhook_321",
            "status": {"code": "in_call_recording", "created_at": created_at},
            "bot": {
                "id": "bot_webhook_321",
                "metadata": {"session_id": session.meeting_id, "owner_id": TEST_OWNER_ID},
            },
        },
    }
    with patch.object(RecallService, "verify_webhook_signature", return_value=True):
        response = client.post("/api/webhook/recall", json=payload)
    assert response.status_code == 200
    stored = get_meeting_scheduler().get_session(TEST_OWNER_ID, session.meeting_id)
    assert stored is not None
    assert stored.recall_status == "in_call_recording"
    assert stored.status.value == "in_call"
    assert stored.started_at is not None


@pytest.mark.asyncio
async def test_recall_meet_bot_provider():
    provider = RecallMeetBotProvider(api_key="mock_key", region="ap-northeast-1")
    session = MeetingSession(
        meeting_id="session_meet_123",
        meet_url="https://meet.google.com/abc-defg-hij",
        persona_id="vc_pitch",
        topic="SaaS Valuation",
        config=MeetingConfig(audio_only=True),
    )
    with pytest.raises(RuntimeError, match="webpage bridge"):
        await provider.join_meeting(session)
    assert not provider.active_channels

    with patch.object(RecallService, "leave_call", new_callable=AsyncMock) as mock_leave:
        mock_leave.return_value = True
        await provider.leave_meeting("session_meet_123")
        assert "session_meet_123" not in provider.active_bot_ids
