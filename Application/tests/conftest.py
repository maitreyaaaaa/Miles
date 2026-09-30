import os
from pathlib import Path
import tempfile

import pytest

# Config reads this before application modules load during collection. Keep test
# persistence outside the repository and away from any developer's app data.
_TEST_DATA_DIR = Path(tempfile.gettempdir()) / f"miles-pytest-{os.getpid()}"
_TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
os.environ["MILES_DATA_DIR"] = str(_TEST_DATA_DIR)
# Retained meeting integration tests exercise the opt-in feature. Disabled-mode
# tests override server.config explicitly; normal deployments default to off.
os.environ["GOOGLE_MEET_ENABLED"] = "true"
for _provider_key in ("ASSEMBLYAI_API_KEY", "RIME_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
    os.environ[_provider_key] = ""


@pytest.fixture(autouse=True)
def enable_test_identity():
    """Keep the existing endpoint tests isolated from the external auth service."""
    from src.api.server import app, SESSIONS, SESSION_OWNERS

    original = app.state.auth_test_bypass
    sessions_before = dict(SESSIONS)
    owners_before = dict(SESSION_OWNERS)
    app.state.auth_test_bypass = True
    try:
        yield
    finally:
        # Endpoint tests often seed these maps directly. Restore their baseline
        # so one test's fake owner cannot consume a later test's session slot.
        SESSIONS.clear()
        SESSIONS.update(sessions_before)
        SESSION_OWNERS.clear()
        SESSION_OWNERS.update(owners_before)
        app.state.auth_test_bypass = original
