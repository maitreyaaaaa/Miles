import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from src.api.server import app
from src.context.analyzer import ContextDossier, NumericMetric
from src.context.google_drive import (
    extract_google_drive_file_id,
    get_google_auth_url,
    GoogleDriveService,
)
from src.meeting.google_meet import GoogleMeetProvisioner
from src.meeting.models import MeetingConfig, MeetingSession, MeetingStatus
from src.meeting.provider import RecallMeetBotProvider

client = TestClient(app)


def test_extract_google_drive_file_id():
    doc_url = "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
    assert extract_google_drive_file_id(doc_url) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    sheet_url = "https://docs.google.com/spreadsheets/d/2CxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0"
    assert extract_google_drive_file_id(sheet_url) == "2CxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    slide_url = "https://docs.google.com/presentation/d/3DxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
    assert extract_google_drive_file_id(slide_url) == "3DxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    drive_url = "https://drive.google.com/file/d/4ExiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view?usp=sharing"
    assert extract_google_drive_file_id(drive_url) == "4ExiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    raw_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    assert extract_google_drive_file_id(raw_id) == raw_id

    assert extract_google_drive_file_id("") is None
    assert extract_google_drive_file_id("invalid-short-id") is None


def test_google_auth_config_endpoint():
    resp = client.get("/api/auth/google/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "client_id" in data
    assert "drive_enabled" in data
    assert "calendar_enabled" in data


def test_google_auth_url_endpoint_unconfigured():
    mock_cfg = MagicMock(google_client_id="")
    with patch("src.api.server.config", mock_cfg):
        resp = client.get("/api/auth/google/url")
        assert resp.status_code == 400
        assert "GOOGLE_CLIENT_ID is not configured" in resp.json()["detail"]


def test_google_auth_url_endpoint_configured():
    mock_cfg = MagicMock(
        google_client_id="test-client-id.apps.googleusercontent.com",
        google_redirect_uri="http://localhost:5173",
    )
    with patch("src.api.server.config", mock_cfg), patch("src.context.google_drive.config", mock_cfg):
        resp = client.get("/api/auth/google/url")
        assert resp.status_code == 200
        auth_url = resp.json()["auth_url"]
        assert "accounts.google.com/o/oauth2/v2/auth" in auth_url
        assert "test-client-id" in auth_url


@pytest.mark.asyncio
async def test_google_drive_service_fetch_document_mock():
    service = GoogleDriveService(access_token="mock_token")
    mock_bytes = b"Pitch Deck for Acme Corp. ARR is $3.2M. Blended CAC is $60. 12 full-time engineers."

    with patch.object(service, "_fetch_via_api", return_value={
        "file_id": "test_file_id",
        "filename": "Acme Pitch Deck.txt",
        "mime_type": "text/plain",
        "file_bytes": mock_bytes,
        "source": "google_drive_api",
    }):
        res = await service.fetch_document("test_file_id")
        assert res["filename"] == "Acme Pitch Deck.txt"
        assert res["file_bytes"] == mock_bytes


def test_google_drive_import_endpoint_success():
    mock_bytes = b"Acme AI pitch deck. Current ARR is $4M with 80% margins. We have 15 engineers."
    mock_dossier = ContextDossier(
        context_id="test_ctx_123",
        filename="Deck.txt",
        doc_type="pitch_deck",
        title="Acme Pitch Deck",
        executive_summary="Acme AI summary",
        target_role_or_company="Acme AI",
        numeric_metrics=[
            NumericMetric(name="ARR", raw_value="$4M", numeric_value=4000000.0, unit="$", category="Financials", context="B2B ARR"),
            NumericMetric(name="Margin", raw_value="80%", numeric_value=80.0, unit="%", category="Financials", context="Gross margin"),
        ],
        vulnerabilities=[{"category": "Scale", "issue": "High server load"}],
        cross_exam_traps=["Defend your 80% margin claim."],
    )

    with patch.object(GoogleDriveService, "fetch_document", return_value={
        "file_id": "test_id_12345678901234567890",
        "filename": "Deck.txt",
        "mime_type": "text/plain",
        "file_bytes": mock_bytes,
        "source": "google_drive_api",
    }), patch("src.api.server.analyze_context_document", return_value=mock_dossier):
        resp = client.post("/api/context/google-drive/import", json={
            "url_or_id": "https://docs.google.com/document/d/test_id_12345678901234567890/edit",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "context_id" in data
        assert len(data["numeric_metrics"]) == 2
        assert "vulnerabilities" in data


def test_google_drive_import_invalid_id():
    resp = client.post("/api/context/google-drive/import", json={
        "url_or_id": "not-a-valid-url",
    })
    assert resp.status_code == 400
    assert "Invalid Google Drive link" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_google_meet_provisioner_simulation_fallback():
    provisioner = GoogleMeetProvisioner()
    with patch.object(provisioner, "_sync_create_meeting", side_effect=RuntimeError("Calendar error")):
        res = await provisioner.create_meeting_room()
        assert "meet_url" in res
        assert "meet.google.com" in res["meet_url"]
        assert res["is_real_meet"] is False


@pytest.mark.asyncio
async def test_google_meet_provisioner_calendar_api():
    provisioner = GoogleMeetProvisioner(access_token="mock_token")
    mock_result = {
        "meet_url": "https://meet.google.com/abc-defg-hij",
        "event_id": "calendar_evt_123",
        "is_real_meet": True,
        "html_link": "https://calendar.google.com/event?eid=123",
        "provider_notice": "Live Google Meet room provisioned via Google Calendar.",
    }
    with patch.object(provisioner, "_sync_create_meeting", return_value=mock_result):
        res = await provisioner.create_meeting_room()
        assert res["is_real_meet"] is True
        assert res["meet_url"] == "https://meet.google.com/abc-defg-hij"


def test_generate_instant_link_endpoint():
    resp = client.get("/api/meeting/generate-link")
    assert resp.status_code == 200
    data = resp.json()
    assert "meet_url" in data
    assert "meet.google.com" in data["meet_url"]


@pytest.mark.asyncio
async def test_recall_meet_bot_provider():
    provider = RecallMeetBotProvider(api_key="mock_recall_key")
    assert provider.provider_mode == "recall_ai"

    session = MeetingSession(
        meet_url="https://meet.google.com/xyz-uvwx-rst",
        persona_id="vc_pitch",
    )
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"id": "recall_bot_999"}
        mock_post.return_value = mock_resp

        channel = await provider.join_meeting(session)
        assert channel.is_active() is True
        assert provider.active_bot_ids[session.meeting_id] == "recall_bot_999"

        await provider.leave_meeting(session.meeting_id)
        assert channel.is_active() is False
