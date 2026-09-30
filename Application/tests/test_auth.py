from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from src.api import server
from src.auth import AuthConfigurationError, AuthenticatedUser, InvalidAccessToken, SupabaseTokenVerifier


class FakeTokenVerifier:
    def verify(self, token: str) -> AuthenticatedUser:
        if token != "valid-test-token":
            raise InvalidAccessToken("invalid")
        return AuthenticatedUser(
            user_id="00000000-0000-4000-8000-000000000123",
            email="person@example.com",
        )


def test_protected_api_requires_a_valid_bearer_token(monkeypatch):
    monkeypatch.setattr(server.app.state, "auth_test_bypass", False)
    monkeypatch.setattr(server.app.state, "token_verifier", FakeTokenVerifier())
    monkeypatch.setattr(server, "config", SimpleNamespace(supabase_url="https://auth.example"))
    client = TestClient(server.app)

    assert client.get("/api/scenarios").status_code == 401
    assert client.get("/api/scenarios", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert client.get(
        "/api/scenarios",
        headers={"Authorization": "Bearer valid-test-token"},
    ).status_code == 200


def test_health_and_capability_share_routes_remain_public(monkeypatch):
    monkeypatch.setattr(server.app.state, "auth_test_bypass", False)
    client = TestClient(server.app)

    health = client.get("/api/health")
    assert health.status_code == 200
    assert "active_sessions_count" not in health.json()
    assert "active_providers" not in health.json()
    assert client.get("/api/debrief/share/unknown-token").status_code == 404


def test_api_fails_closed_when_authentication_is_unconfigured(monkeypatch):
    monkeypatch.setattr(server.app.state, "auth_test_bypass", False)
    monkeypatch.setattr(server, "config", SimpleNamespace(supabase_url=""))
    client = TestClient(server.app)

    assert client.get("/api/scenarios").status_code == 503


@pytest.mark.parametrize("project_url", [
    "example.supabase.co",
    "SUPABASE_URL=https://example.supabase.co",
    '"https://example.supabase.co"',
    "https://",
    "ftp://example.supabase.co",
    "https://example.supabase.co/auth/v1",
    "https://example.supabase.co/rest/v1",
    "https://example.supabase.co?key=private-test-value",
    "https://example.supabase.co#fragment",
    "https://operator:private-test-value@example.supabase.co",
    "https://exa mple.supabase.co",
    "https://example.supabase.co:invalid",
    "https://[invalid",
])
def test_invalid_project_url_reports_configuration_error_without_echoing_input(project_url):
    with pytest.raises(AuthConfigurationError, match="SUPABASE_URL must be") as error:
        SupabaseTokenVerifier(project_url)
    assert str(error.value) == (
        "SUPABASE_URL must be a full HTTP(S) project URL, for example "
        "https://<project-ref>.supabase.co, without credentials or "
        "an /auth/v1 or /rest/v1 suffix."
    )
    assert "private-test-value" not in str(error.value)


@pytest.mark.parametrize("project_url, expected", [
    ("https://example.supabase.co", "https://example.supabase.co"),
    ("  https://example.supabase.co/\n", "https://example.supabase.co"),
    ("http://127.0.0.1:54321", "http://127.0.0.1:54321"),
])
def test_valid_project_url_builds_the_correct_jwks_endpoint(monkeypatch, project_url, expected):
    calls = []
    monkeypatch.setattr("src.auth.PyJWKClient", lambda url, **_kwargs: calls.append(url) or object())
    verifier = SupabaseTokenVerifier(project_url)
    assert verifier.issuer == f"{expected}/auth/v1"
    assert calls == [f"{expected}/auth/v1/.well-known/jwks.json"]


def test_empty_project_url_keeps_authentication_closed():
    verifier = SupabaseTokenVerifier(" \n")
    with pytest.raises(AuthConfigurationError, match="not configured"):
        verifier.verify("invalid-test-token")
