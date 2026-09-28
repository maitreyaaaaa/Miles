from types import SimpleNamespace

from fastapi.testclient import TestClient

from src.api import server
from src.auth import AuthenticatedUser, InvalidAccessToken


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
