from __future__ import annotations

import base64
import hashlib
import hmac
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from starlette.testclient import TestClient

from src.api.server import app
from src.config import config
from src.meeting.recall_service import RecallService, RecallAPIError
from src.meeting.provider import RecallMeetBotProvider
from src.meeting.models import MeetingConfig, MeetingSession

client = TestClient(app)


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
        )
        assert res["id"] == "bot_123456"
        assert res["meeting_url"] == "https://meet.google.com/abc-defg-hij"


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


def test_launch_meeting_bot_invalid_url():
    resp = client.post("/api/meeting/bot/launch", json={
        "meeting_url": "not-a-valid-url",
    })
    assert resp.status_code == 400
    assert "valid meeting URL" in resp.json()["detail"]


def test_launch_meeting_bot_success_mock():
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
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["bot_id"] == "bot_xyz_999"
        assert data["meeting_url"] == "https://meet.google.com/xyz-uvwx-rst"


def test_get_bot_status_endpoint():
    with patch.object(RecallService, "get_bot", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"id": "bot_999", "status": "in_call"}
        resp = client.get("/api/meeting/bot/bot_999")
        assert resp.status_code == 200
        assert resp.json()["id"] == "bot_999"


def test_leave_meeting_bot_endpoint():
    with patch.object(RecallService, "leave_call", new_callable=AsyncMock) as mock_leave:
        mock_leave.return_value = True
        resp = client.post("/api/meeting/bot/bot_999/leave")
        assert resp.status_code == 200
        assert resp.json()["success"] is True


def test_list_recall_bots_endpoint():
    with patch.object(RecallService, "list_bots", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = [{"id": "bot_1"}, {"id": "bot_2"}]
        resp = client.get("/api/meeting/bots")
        assert resp.status_code == 200
        assert len(resp.json()["bots"]) == 2


def test_recall_webhook_endpoint():
    msg_id = "msg_live_001"
    msg_timestamp = "1790000000"
    payload = '{"event":"bot.status_change","data":{"bot_id":"bot_live_123"}}'

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
    with patch.object(RecallService, "create_bot", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = {"id": "bot_assigned_777", "status_changes": [{"code": "ready"}]}
        channel = await provider.join_meeting(session)
        assert channel is not None
        assert provider.active_bot_ids.get("session_meet_123") == "bot_assigned_777"
        assert provider.bot_statuses.get("session_meet_123") == "joining_call"

    with patch.object(RecallService, "leave_call", new_callable=AsyncMock) as mock_leave:
        mock_leave.return_value = True
        await provider.leave_meeting("session_meet_123")
        assert "session_meet_123" not in provider.active_bot_ids
