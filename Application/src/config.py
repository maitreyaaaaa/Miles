from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent.parent

# Load .env
load_dotenv(APP_DIR / ".env")

# Keep persistent stores under one configurable root. Tests and local instances
# can use separate directories without touching app data.
DATA_DIR = Path(os.getenv("MILES_DATA_DIR", str(APP_DIR / "data"))).expanduser().resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AppConfig:
    # Managed user authentication (the public/publishable key belongs in the frontend).
    supabase_url: str = os.getenv("SUPABASE_URL", "").rstrip("/")
    supabase_jwt_audience: str = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    app_environment: str = os.getenv("APP_ENV", "development").strip().lower()

    # PostgreSQL stores owner-scoped application data. Use the Supabase
    # transaction-pooler URL at runtime and keep migration credentials separate.
    database_url: str = os.getenv("DATABASE_URL", "")
    database_pool_max_size: int = int(os.getenv("DATABASE_POOL_MAX_SIZE", "8"))

    # API Keys
    assemblyai_api_key: str = os.getenv("ASSEMBLYAI_API_KEY", "")
    rime_api_key: str = os.getenv("RIME_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Google Cloud & Google Drive / Calendar Settings
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_api_key: str = os.getenv("GOOGLE_API_KEY", "")
    google_redirect_uri: str = os.getenv(
        "GOOGLE_REDIRECT_URI", "http://localhost:5173/google-integration-callback"
    )

    # Meeting Bot Provider (Recall.ai in production; explicit local simulation otherwise)
    recall_ai_api_key: str = os.getenv("RECALL_AI_API_KEY", "")
    recall_ai_region: str = os.getenv("RECALL_AI_REGION", "ap-northeast-1")
    recall_ai_webhook_secret: str = os.getenv("RECALL_AI_WEBHOOK_SECRET", "")
    recall_ai_svix_webhook_secret: str = os.getenv("RECALL_AI_SVIX_WEBHOOK_SECRET", "")
    recall_audio_bridge_url: str = os.getenv("RECALL_AUDIO_BRIDGE_URL", "").strip()
    recall_audio_bridge_secret: str = os.getenv("RECALL_AUDIO_BRIDGE_SECRET", "")

    # Server settings
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # Voice settings
    sample_rate: int = 16000  # Inbound mic linear PCM rate (AssemblyAI requirement)
    tts_sample_rate: int = 22050  # Outbound Rime TTS rate
    rime_speaker: str = os.getenv("RIME_SPEAKER", "alpine")
    rime_model_id: str = os.getenv("RIME_MODEL_ID", "coda")
    barge_in_threshold_ms: float = 100.0

    # LLM Settings
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "meta-llama/llama-3.3-70b-instruct" if os.getenv("OPENAI_API_KEY", "").startswith("sk-or-") else "gpt-4o-mini")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    @property
    def active_llm_provider(self) -> str:
        if self.openai_api_key:
            return "openai"
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        return "mock"

    @property
    def active_tts_provider(self) -> str:
        return "Rime" if self.rime_api_key else "System Fallback"

    @property
    def active_stt_provider(self) -> str:
        return "AssemblyAI v3" if self.assemblyai_api_key else "Simulation Fallback"

    @property
    def google_drive_enabled(self) -> bool:
        return bool((self.google_client_id and self.google_client_secret) or self.google_api_key)

    @property
    def google_calendar_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def recall_ai_enabled(self) -> bool:
        return bool(self.recall_ai_api_key)


config = AppConfig()
