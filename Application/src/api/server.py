from __future__ import annotations

import asyncio
import base64
import contextlib
from contextlib import asynccontextmanager
import datetime
import json
import logging
import math
import os
import re
import struct
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from src.auth import AuthConfigurationError, InvalidAccessToken, SupabaseTokenVerifier
from src.meeting.models import MeetingConfig, MeetingSession, MeetingStatus
from src.meeting.scheduler import get_meeting_scheduler, generate_meet_code
from src.meeting.debrief_dispatcher import get_debrief_dispatcher
from src.meeting.provider import RecallMeetBotProvider
from src.meeting.recall_service import RecallService, RecallAPIError
from src.meeting.bridge_ticket import (
    InvalidBridgeTicket,
    add_ticket_to_bridge_url,
    create_bridge_ticket,
    verify_bridge_ticket,
)

from src.analytics.composure_scorer import ComposureScorer
from src.config import config
from src.context.analyzer import analyze_context_document
from src.context.extractor import extract_text_from_bytes
from src.context.store import get_context_store
from src.context.google_drive import (
    GoogleDriveService,
    extract_google_drive_file_id,
    get_google_auth_url,
    exchange_google_code_for_tokens,
)
from src.meeting.google_meet import GoogleMeetProvisioner
from src.debate.engine import DebateEngine
from src.debate.llm_client import LLMClient
from src.debate.personas import (
    build_custom_debate_persona,
    get_persona,
    infer_contrarian_thesis,
    list_scenarios,
    list_persona_tones,
)
from src.debate.dossier import generate_fallback_dossier
from src.voice.assemblyai_stream import AssemblyAIStreamingClient, SCENARIO_VOCABULARY
from src.voice.interruption_manager import InterruptionManager
from src.voice.rime_stream import RimeStreamingTTSClient, pcm_to_wav_bytes
from src.debate.debrief_store import get_debrief_store
from src.debate.pdf_generator import generate_executive_pdf
from src.debate.interviewer_panel import get_interviewer_panel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("miles_server")


@asynccontextmanager
async def app_lifespan(_: FastAPI):
    """Require durable storage in production and verify the pool at startup."""
    from src.storage.postgres import close_postgres_database, get_postgres_database

    try:
        if config.app_environment == "production" and not config.database_url:
            raise RuntimeError("DATABASE_URL is required when APP_ENV=production.")
        if config.database_url:
            database = get_postgres_database()
            await asyncio.to_thread(database.check)
        yield
    finally:
        await asyncio.to_thread(close_postgres_database)

app = FastAPI(
    title="Miles Backend",
    description="Full-Duplex Adversarial Verbal Sparring & Speech Cadence Engine",
    version="0.1.0",
    docs_url=None if config.app_environment == "production" else "/docs",
    redoc_url=None if config.app_environment == "production" else "/redoc",
    openapi_url=None if config.app_environment == "production" else "/openapi.json",
    lifespan=app_lifespan,
)

DEVELOPMENT_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
extra_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
ALLOWED_ORIGINS = extra_origins or (
    DEVELOPMENT_ORIGINS if config.app_environment != "production" else []
)


def is_allowed_origin(origin: str) -> bool:
    if not origin:
        return True
    norm = origin.rstrip("/")
    return any(norm == allowed.rstrip("/") for allowed in ALLOWED_ORIGINS)


# Enable CORS for browser frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.state.token_verifier = SupabaseTokenVerifier(
    config.supabase_url,
    audience=config.supabase_jwt_audience,
)
app.state.auth_test_bypass = False


def _is_public_http_route(method: str, path: str) -> bool:
    if method == "OPTIONS" or path in {"/", "/health", "/api/health"}:
        return True
    if path == "/api/webhook/recall":
        return True  # This route verifies Recall's webhook signature itself.
    return method == "GET" and re.fullmatch(r"/api/debrief/share/[A-Za-z0-9_-]{1,64}", path) is not None


@app.middleware("http")
async def authenticate_api_request(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/") or _is_public_http_route(request.method, path):
        return await call_next(request)

    if app.state.auth_test_bypass:
        request.state.user_id = "00000000-0000-4000-8000-000000000001"
        return await call_next(request)

    verifier: SupabaseTokenVerifier = app.state.token_verifier
    if not config.supabase_url:
        return JSONResponse(
            status_code=503,
            content={"detail": "Authentication is not configured for this deployment."},
        )

    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return JSONResponse(status_code=401, content={"detail": "Authentication required."})

    try:
        user = await asyncio.to_thread(verifier.verify, token.strip())
    except AuthConfigurationError:
        return JSONResponse(
            status_code=503,
            content={"detail": "Authentication is not configured for this deployment."},
        )
    except InvalidAccessToken:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired access token."})
    except Exception:
        logger.exception("Authentication token verification failed.")
        return JSONResponse(status_code=503, content={"detail": "Authentication service unavailable."})

    request.state.user_id = user.user_id
    request.state.user_email = user.email
    return await call_next(request)



class WebSocketChannel:
    """Thread-safe and concurrency-safe WebSocket dispatcher with task tracking."""

    def __init__(self, websocket: WebSocket, stop_event: asyncio.Event):
        self._ws = websocket
        self._stop = stop_event
        self._lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    async def send_json(self, payload: Dict[str, Any]) -> None:
        if self._stop.is_set():
            return
        async with self._lock:
            try:
                await self._ws.send_text(json.dumps(payload))
            except Exception as e:
                logger.debug(f"[WebSocket] send_json error: {e}")

    async def send_bytes(self, data: bytes) -> None:
        if self._stop.is_set():
            return
        async with self._lock:
            try:
                await self._ws.send_bytes(data)
            except Exception as e:
                logger.debug(f"[WebSocket] send_bytes error: {e}")

    def dispatch(self, coro) -> asyncio.Task:
        """Spawn background task with strong reference to prevent GC eviction."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def cleanup(self) -> None:
        for task in list(self._tasks):
            if not task.done():
                task.cancel()
        if self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.gather(*self._tasks, return_exceptions=True)


# In-memory registry of debate sessions
SESSIONS: Dict[str, DebateEngine] = {}
SESSION_OWNERS: Dict[str, str] = {}
MAX_ACTIVE_DEBATE_SESSIONS = 50
MAX_ACTIVE_SESSIONS_PER_USER = 1


def install_stream_shutdown_filter() -> None:
    """Suppress known provider async-generator noise when clients disconnect mid-stream."""
    loop = asyncio.get_running_loop()
    if getattr(loop, "_miles_shutdown_filter_installed", False):
        return

    previous_handler = loop.get_exception_handler()

    def handle_exception(loop: asyncio.AbstractEventLoop, context: Dict[str, Any]) -> None:
        exception = context.get("exception")
        message = str(context.get("message", ""))
        if (
            isinstance(exception, RuntimeError)
            and "asynchronous generator" in message
            and (
                "generator didn't stop after athrow" in str(exception)
                or "aclose(): asynchronous generator is already running" in str(exception)
            )
        ):
            logger.debug(f"[WebSocket] Suppressed provider stream shutdown noise: {exception}")
            return
        if previous_handler:
            previous_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(handle_exception)
    setattr(loop, "_miles_shutdown_filter_installed", True)


class CustomTopicRequest(BaseModel):
    topic: str
    difficulty: Optional[str] = "hard"
    persona_tone: Optional[str] = "calm_ruthless"


class ScheduleMeetingRequest(BaseModel):
    meet_url: Optional[str] = None
    context_id: Optional[str] = None
    persona_id: Optional[str] = "vc_pitch"
    difficulty: Optional[str] = "hard"
    topic: Optional[str] = None
    persona_tone: Optional[str] = None
    max_duration_seconds: Optional[int] = Field(default=1800, ge=60, le=7200)
    join_at: Optional[str] = None
    schedule_recall_bot: Optional[bool] = True
    google_access_token: Optional[str] = None


class LaunchRecallBotRequest(BaseModel):
    meeting_url: str
    persona_id: Optional[str] = "vc_pitch"
    bot_name: Optional[str] = Field(default=None, max_length=100)
    max_duration_seconds: Optional[int] = Field(default=1800, ge=60, le=7200)
    join_at: Optional[str] = None
    topic: Optional[str] = None
    difficulty: Optional[str] = "hard"
    context_id: Optional[str] = None


class GoogleDriveImportRequest(BaseModel):
    url_or_id: str
    access_token: Optional[str] = None
    doc_type_hint: Optional[str] = None


class GoogleDriveExportRequest(BaseModel):
    access_token: str
    filename: Optional[str] = "Miles_Debrief_Report.pdf"


class GoogleAuthExchangeRequest(BaseModel):
    code: str


class GoogleCalendarLinkRequest(BaseModel):
    access_token: Optional[str] = None


def _require_live_meeting_configuration() -> None:
    missing = []
    if not config.recall_ai_api_key:
        missing.append("RECALL_AI_API_KEY")
    if not (config.recall_ai_webhook_secret or config.recall_ai_svix_webhook_secret):
        missing.append("RECALL_AI_WEBHOOK_SECRET (or RECALL_AI_SVIX_WEBHOOK_SECRET for legacy workspaces)")
    if not config.recall_audio_bridge_url:
        missing.append("RECALL_AUDIO_BRIDGE_URL")
    elif not config.recall_audio_bridge_url.startswith("https://"):
        missing.append("RECALL_AUDIO_BRIDGE_URL (must be a public HTTPS URL)")
    if len(config.recall_audio_bridge_secret) < 32:
        missing.append("RECALL_AUDIO_BRIDGE_SECRET (at least 32 characters)")
    if not config.assemblyai_api_key:
        missing.append("ASSEMBLYAI_API_KEY")
    if not config.rime_api_key:
        missing.append("RIME_API_KEY")
    if not (config.openai_api_key or config.gemini_api_key or config.anthropic_api_key):
        missing.append("OPENAI_API_KEY, GEMINI_API_KEY, or ANTHROPIC_API_KEY")
    if missing:
        raise HTTPException(
            status_code=503,
            detail="Live meeting audio is not configured. Set: " + ", ".join(missing),
        )


def _validate_meeting_url(meeting_url: str) -> str:
    value = meeting_url.strip()
    parts = urlsplit(value)
    host = (parts.hostname or "").lower().rstrip(".")
    supported = (
        host == "meet.google.com"
        or host == "zoom.us"
        or host.endswith(".zoom.us")
        or host == "teams.microsoft.com"
        or host.endswith(".teams.microsoft.com")
        or host == "teams.live.com"
        or host == "webex.com"
        or host.endswith(".webex.com")
    )
    if parts.scheme != "https" or not supported or parts.username or parts.password:
        raise HTTPException(
            status_code=400,
            detail="A valid meeting URL on Google Meet, Zoom, Microsoft Teams, or Webex is required.",
        )
    return value


def _bridge_ticket_expiry(join_at: Optional[str], max_duration_seconds: int) -> int:
    now = int(time.time())
    expiry = now + max(3600, max_duration_seconds + 900)
    if not join_at:
        return expiry
    try:
        scheduled_at = datetime.datetime.fromisoformat(join_at.replace("Z", "+00:00"))
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=datetime.timezone.utc)
        scheduled_epoch = int(scheduled_at.timestamp())
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="join_at must be a valid ISO 8601 date-time.") from exc
    if scheduled_epoch < now - 60:
        raise HTTPException(status_code=400, detail="join_at must be in the future.")
    if scheduled_epoch > now + 30 * 24 * 60 * 60:
        raise HTTPException(status_code=400, detail="Meetings can be scheduled up to 30 days ahead.")
    return max(expiry, scheduled_epoch + max_duration_seconds + 900)


async def _dispatch_recall_bot(
    session: MeetingSession,
    *,
    bot_name: str,
    join_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Create the Recall bot with its authenticated live audio webpage."""
    _require_live_meeting_configuration()
    scheduler = get_meeting_scheduler()
    other_active_bots = [
        current for current in await asyncio.to_thread(scheduler.list_sessions, session.owner_id or "")
        if current.meeting_id != session.meeting_id
        and current.recall_bot_id
        and current.status in {MeetingStatus.SCHEDULED, MeetingStatus.CONNECTING, MeetingStatus.IN_CALL}
    ]
    if other_active_bots:
        raise HTTPException(status_code=429, detail="This account already has an active or scheduled meeting bot.")
    expiry = _bridge_ticket_expiry(join_at, session.config.max_duration_seconds)
    ticket = create_bridge_ticket(
        meeting_id=session.meeting_id,
        owner_id=session.owner_id or "",
        secret=config.recall_audio_bridge_secret,
        expires_at=expiry,
    )
    bridge_url = add_ticket_to_bridge_url(config.recall_audio_bridge_url, ticket)
    metadata = {
        "session_id": session.meeting_id,
        "owner_id": session.owner_id,
        "persona_id": session.persona_id,
        "difficulty": session.difficulty,
        "topic": session.topic or "Sparring",
    }
    service = RecallService()
    bot_data = await service.create_bot(
        meeting_url=session.meet_url,
        bot_name=bot_name,
        join_at=join_at,
        metadata=metadata,
        output_media_url=bridge_url,
        max_duration_seconds=session.config.max_duration_seconds,
    )
    bot_id = bot_data.get("id")
    if not isinstance(bot_id, str) or not bot_id:
        raise RecallAPIError("Recall.ai accepted the request without returning a bot ID.", status_code=502)

    provider_notice = (
        f"Live audio bridge configured in {service.region}. Recall Output Media displays a visual feed in the call."
    )

    try:
        persisted_session = await asyncio.to_thread(
            scheduler.store.attach_recall_bot,
            session,
            bot_id,
            join_at=join_at,
            provider_notice=provider_notice,
        )
        session.__dict__.update(persisted_session.__dict__)
    except Exception:
        logger.exception("Could not persist Recall bot ID for meeting %s.", session.meeting_id)
        with contextlib.suppress(Exception):
            if join_at:
                await service.delete_scheduled_bot(bot_id)
            else:
                await service.leave_call(bot_id)
        raise

    if isinstance(scheduler.bot_provider, RecallMeetBotProvider):
        scheduler.bot_provider.active_bot_ids[session.meeting_id] = bot_id
        scheduler.bot_provider.bot_statuses[session.meeting_id] = "ready"
    return {"bot_id": bot_id, "bot_data": bot_data, "region": service.region}


async def _end_recall_bot(session: MeetingSession) -> str:
    service = RecallService()
    if session.status == MeetingStatus.SCHEDULED and session.recall_status in {None, "ready", "scheduled"}:
        if await service.delete_scheduled_bot(session.recall_bot_id or ""):
            session.status = MeetingStatus.CANCELLED
            session.recall_status = "cancelled_by_user"
            session.recall_status_message = "The scheduled bot was cancelled by the user."
            session.recall_status_updated_at = time.time()
            session.ended_at = time.time()
            await asyncio.to_thread(get_meeting_scheduler().store.save_session, session)
            return "cancelled"
    if await service.leave_call(session.recall_bot_id or ""):
        return "leave_requested"
    raise HTTPException(status_code=502, detail="Recall.ai could not end the meeting bot.")


def calculate_pcm_rms(pcm_bytes: bytes) -> float:
    """Calculate Root Mean Square (RMS) energy of 16-bit PCM audio frame."""
    if len(pcm_bytes) < 2:
        return 0.0
    count = len(pcm_bytes) // 2
    shorts = struct.unpack(f"<{count}h", pcm_bytes[: count * 2])
    sum_squares = sum(s * s for s in shorts)
    mean_squares = sum_squares / count
    return math.sqrt(mean_squares)


# ==========================================
# REST API Endpoints
# ==========================================


@app.get("/")
@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Minimal public liveness response; provider diagnostics require sign-in."""
    return {
        "status": "healthy",
        "service": "Miles Voice Engine",
    }


async def probe_assemblyai() -> str:
    """Probe AssemblyAI streaming token generation."""
    if not config.assemblyai_api_key:
        return "simulation_fallback"
    try:
        client = AssemblyAIStreamingClient(api_key=config.assemblyai_api_key)
        token = await asyncio.wait_for(client.fetch_token(), timeout=3.0)
        return "connected" if token else "degraded"
    except Exception as e:
        logger.warning(f"[Preflight] AssemblyAI probe failed: {e}")
        return "offline"


async def probe_rime() -> str:
    """Probe Rime Coda connection pool readiness."""
    if not config.rime_api_key:
        return "system_fallback"
    client = RimeStreamingTTSClient(api_key=config.rime_api_key)
    try:
        http_client = await client.get_http_client()
        return "connected" if http_client and not http_client.is_closed else "degraded"
    except Exception as e:
        logger.warning(f"[Preflight] Rime probe failed: {e}")
        return "system_fallback"
    finally:
        await client.close()


@app.get("/api/preflight")
async def get_preflight_status():
    """Hardware & cloud provider preflight verification for audio sparring."""
    stt_status = await probe_assemblyai()
    rime_status = await probe_rime()
    active_llm = (
        config.openai_model
        if config.openai_api_key
        else (config.gemini_model if config.gemini_api_key else "meta-llama/llama-3.3-70b-instruct")
    )
    return {
        "backend_status": "healthy",
        "assemblyai_status": stt_status,
        "assemblyai_model": "universal-3-5-pro",
        "rime_status": rime_status,
        "rime_model": config.rime_model_id,
        "rime_speaker": config.rime_speaker,
        "active_llm": active_llm,
    }


@app.get("/api/scenarios")
async def get_scenarios():
    """Retrieve all available debate scenarios and personas."""
    return {
        "scenarios": list_scenarios(),
        "difficulties": ["easy", "medium", "hard", "ruthless"],
        "persona_tones": list_persona_tones(),
    }


@app.get("/api/personas/tones")
async def get_persona_tones():
    """Retrieve available persona tone modifiers."""
    return {"tones": list_persona_tones()}


class SynthesizeTTSRequest(BaseModel):
    text: str
    speaker: Optional[str] = None
    speed_alpha: Optional[float] = 1.0


@app.post("/api/tts/synthesize")
async def synthesize_speech_endpoint(req: SynthesizeTTSRequest):
    """Synthesize text into standard WAV audio using Rime neural TTS (with system fallback).
    
    Used by Debrief 2.0 'Listen to the Tape' to vocalize executive reframes with
    authoritative adversary cadence and tone.
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    speaker = req.speaker or config.rime_speaker
    tts_client = RimeStreamingTTSClient(
        speaker=speaker,
        model_id=config.rime_model_id,
        sample_rate=config.tts_sample_rate,
    )
    chunks: List[bytes] = []
    try:
        async for chunk in tts_client.stream_audio_chunks(text, speed_alpha=req.speed_alpha or 1.0):
            chunks.append(chunk)
    except Exception as e:
        logger.error(f"[TTS Synthesize] Error synthesizing speech: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {e}")
    finally:
        await tts_client.close()

    raw_pcm = b"".join(chunks)
    wav_bytes = pcm_to_wav_bytes(raw_pcm, sample_rate=config.tts_sample_rate)
    return Response(content=wav_bytes, media_type="audio/wav")


class RematchEvaluateRequest(BaseModel):
    scenario: Optional[str] = "vc_pitch"
    opponent: Optional[str] = "Marcus Vance"
    trap: str
    original_quote: str
    upgraded_answer: str
    duration_seconds: Optional[float] = 10.0
    wpm: Optional[float] = None
    fillers: Optional[List[str]] = None


@app.post("/api/debate/rematch/evaluate")
async def evaluate_rematch_endpoint(req: RematchEvaluateRequest):
    """Evaluate a 30-second rapid-fire retry against an adversarial trap.
    
    Returns a standalone retry assessment and transcript-based speech metrics.
    """
    upgraded = req.upgraded_answer.strip()
    if not upgraded:
        raise HTTPException(status_code=400, detail="Upgraded answer cannot be empty.")

    llm_client = LLMClient()
    try:
        result = await llm_client.evaluate_rematch_turn(
            scenario=req.scenario or "vc_pitch",
            opponent=req.opponent or "Marcus Vance",
            trap=req.trap,
            original_quote=req.original_quote,
            upgraded_answer=upgraded,
            duration_seconds=req.duration_seconds or 10.0,
            wpm=req.wpm,
            fillers=req.fillers,
        )
        return result
    except Exception as e:
        logger.error(f"[Rematch] Error evaluating turn: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rematch evaluation failed: {e}")


class ShareDebriefRequest(BaseModel):
    report: Dict[str, Any]


@app.post("/api/debrief/share")
async def share_debrief_endpoint(req: ShareDebriefRequest, request: Request):
    """Persist a debrief report and return a permanent read-only shareable ID and URL."""
    try:
        store = get_debrief_store()
        owner_id = request.state.user_id
        report_session_id = req.report.get("session_id")
        if not isinstance(report_session_id, str):
            raise HTTPException(status_code=404, detail="Debrief report not found.")
        owned_debate = report_session_id and (
            SESSION_OWNERS.get(report_session_id) == owner_id
            or await asyncio.to_thread(store.get_report, report_session_id, owner_id)
        )
        owned_meeting = report_session_id and await asyncio.to_thread(
            get_meeting_scheduler().get_session, owner_id, report_session_id
        )
        if not owned_debate and not owned_meeting:
            raise HTTPException(status_code=404, detail="Debrief report not found.")
        share_id = await asyncio.to_thread(store.save_debrief, req.report, owner_id)
        return {
            "share_id": share_id,
            "share_url": f"/?share={share_id}",
            "share_scope": "unguessable_read_only_link",
            "privacy_notice": "Anyone with this share link can view the debrief report.",
            "title": req.report.get("topic", "Adversarial Debrief"),
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"[Debrief Share] Error saving debrief: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/debrief/share/{share_id}")
async def get_shared_debrief_endpoint(share_id: str):
    """Retrieve saved read-only debrief report by its share token."""
    store = get_debrief_store()
    report = await asyncio.to_thread(store.get_debrief, share_id)
    if not report:
        raise HTTPException(status_code=404, detail="Debrief report not found or expired.")
    public_report = {key: value for key, value in report.items() if key != "owner_id"}
    return JSONResponse(content=public_report, headers={"Cache-Control": "no-store"})


@app.get("/api/debrief/{session_id}/pdf")
async def export_debrief_pdf_endpoint(session_id: str, request: Request):
    """Generate and stream a pixel-perfect ReportLab Executive Summary PDF."""
    report = None
    owner_id = request.state.user_id
    if SESSION_OWNERS.get(session_id) == owner_id and session_id in SESSIONS:
        engine = SESSIONS[session_id]
        report = getattr(engine, "_cached_report", None) or engine.get_debrief_report()
    if not report:
        store = get_debrief_store()
        report = await asyncio.to_thread(store.get_report, session_id, owner_id)
        if not report:
            report = await asyncio.to_thread(store.get_debrief, session_id, owner_id)
    if not report:
        meeting = await asyncio.to_thread(get_meeting_scheduler().get_session, owner_id, session_id)
        if meeting:
            report = meeting.debrief_report or await asyncio.to_thread(
                get_debrief_dispatcher().get_saved_debrief, session_id, owner_id
            )
    if not report:
        raise HTTPException(status_code=404, detail=f"Session or debrief report '{session_id}' not found for PDF export.")

    try:
        pdf_bytes = generate_executive_pdf(report)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="miles-executive-debrief-{session_id[:12]}.pdf"',
                "Cache-Control": "no-cache",
            },
        )
    except Exception as e:
        logger.error(f"[Debrief PDF] Error generating PDF for {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")


@app.post("/api/scenarios/custom")
async def setup_custom_topic(req: CustomTopicRequest):
    """Register and validate a custom debate topic, generating structured 5-vector battle dossier."""
    topic = req.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic cannot be empty.")

    difficulty = req.difficulty or "hard"
    persona_tone = req.persona_tone or "calm_ruthless"
    dossier = generate_fallback_dossier(topic, difficulty=difficulty, persona_tone=persona_tone)
    return dossier


MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB


@app.post("/api/context/upload")
async def upload_context_document(request: Request, file: UploadFile = File(...)):
    """Ingest uploaded document (PDF, DOCX, TXT, MD, CSV) with bounded streaming size."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename.")

    chunks = []
    bytes_read = 0
    while chunk := await file.read(64 * 1024):
        bytes_read += len(chunk)
        if bytes_read > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="File exceeds maximum allowed size (10MB).")
        chunks.append(chunk)

    content = b"".join(chunks)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    extracted = extract_text_from_bytes(content, file.filename)
    if not extracted.get("text"):
        raise HTTPException(status_code=400, detail="Could not extract readable text from uploaded document.")

    store = get_context_store()
    dossier = await analyze_context_document(extracted["text"], file.filename)
    await asyncio.to_thread(store.save_context, request.state.user_id, dossier)
    return dossier.to_dict()


class PasteContextRequest(BaseModel):
    text: str
    filename: Optional[str] = "Pasted Context.txt"


@app.post("/api/context/paste")
async def paste_context_text(req: PasteContextRequest, request: Request):
    """Ingest raw pasted text/resume/pitch deck notes and generate structured forensic Context Dossier."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    filename = req.filename or "Pasted Context.txt"
    store = get_context_store()
    dossier = await analyze_context_document(text, filename)
    await asyncio.to_thread(store.save_context, request.state.user_id, dossier)
    return dossier.to_dict()


@app.get("/api/context/{context_id}")
async def get_context_by_id(context_id: str, request: Request):
    """Retrieve an existing context dossier by ID."""
    store = get_context_store()
    dossier = await asyncio.to_thread(store.get_context, request.state.user_id, context_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Context not found.")
    return dossier.to_dict()


@app.get("/api/contexts")
async def list_available_contexts(request: Request):
    """List all previously ingested context dossiers."""
    store = get_context_store()
    return {"contexts": await asyncio.to_thread(store.list_contexts, request.state.user_id)}


# ==========================================
# Google Drive & Google OAuth Endpoints
# ==========================================


@app.get("/api/auth/google/config")
async def get_google_auth_config():
    """Return public Google OAuth and Picker client configuration."""
    return {
        "client_id": config.google_client_id,
        "api_key": config.google_api_key,
        "redirect_uri": config.google_redirect_uri,
        "drive_enabled": config.google_drive_enabled,
        "calendar_enabled": config.google_calendar_enabled,
        "oauth_enabled": bool(config.google_client_id and config.google_client_secret),
    }


@app.get("/api/auth/google/url")
async def get_google_authorization_url(purpose: str = Query(...), state: str = Query(..., min_length=16, max_length=256)):
    """Generate a scoped Google OAuth consent URL for a signed-in integration."""
    if not config.google_client_id or not config.google_client_secret:
        raise HTTPException(
            status_code=400,
            detail="Google OAuth is not configured for this deployment.",
        )
    try:
        url = get_google_auth_url(purpose=purpose, state=state)
        return {"auth_url": url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Could not create Google integration consent URL.")
        raise HTTPException(status_code=500, detail="Could not start Google authorization.")


@app.post("/api/auth/google/callback")
async def handle_google_oauth_callback(req: GoogleAuthExchangeRequest):
    """Exchange a user-authorized code and return only the short-lived access token."""
    try:
        tokens = await exchange_google_code_for_tokens(code=req.code)
        return {
            key: tokens[key]
            for key in ("access_token", "token_type", "expires_in", "scope")
            if key in tokens
        }
    except Exception as e:
        logger.warning("Google integration authorization-code exchange failed: %s", e)
        raise HTTPException(status_code=400, detail="Google authorization could not be completed.")


@app.post("/api/context/google-drive/import")
async def import_from_google_drive(req: GoogleDriveImportRequest, request: Request):
    """Fetch, extract, and analyze a document directly from Google Drive, Docs, Sheets, or Slides."""
    file_id = extract_google_drive_file_id(req.url_or_id)
    if not file_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid Google Drive link or file ID. Provide a valid Google Docs/Drive URL or ID.",
        )

    try:
        drive_service = GoogleDriveService(access_token=req.access_token)
        fetched = await drive_service.fetch_document(file_id)

        filename = fetched["filename"]
        file_bytes = fetched["file_bytes"]

        if not file_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Google Drive file '{filename}' was empty or inaccessible.",
            )

        extracted = extract_text_from_bytes(file_bytes, filename)
        text = extracted.get("text", "")
        if not text.strip():
            raise HTTPException(
                status_code=400,
                detail=f"Could not extract readable text from Google Drive document '{filename}'.",
            )

        dossier = await analyze_context_document(text, filename, req.doc_type_hint)
        store = get_context_store()
        await asyncio.to_thread(store.save_context, request.state.user_id, dossier)
        return dossier.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GoogleDrive] Error importing file {file_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/debrief/{session_id}/export-drive")
async def export_debrief_to_google_drive(session_id: str, req: GoogleDriveExportRequest, request: Request):
    """Export the finalized debrief report as an Executive PDF directly to Google Drive."""
    report = None
    owner_id = request.state.user_id
    engine = SESSIONS.get(session_id) if SESSION_OWNERS.get(session_id) == owner_id else None
    if engine:
        report = engine.get_debrief_report()

    if not report:
        report = await asyncio.to_thread(get_debrief_store().get_report, session_id, owner_id)
    if not report:
        meeting = await asyncio.to_thread(get_meeting_scheduler().get_session, owner_id, session_id)
        if meeting:
            report = meeting.debrief_report

    if not report:
        raise HTTPException(status_code=404, detail="Debrief report not found for this session.")

    try:
        pdf_bytes = generate_executive_pdf(report)
        filename = req.filename or f"Miles_Debrief_{session_id[:8]}.pdf"
        drive_service = GoogleDriveService(access_token=req.access_token)
        result = await drive_service.export_debrief_pdf(pdf_bytes, filename=filename)
        return result
    except Exception as e:
        logger.error(f"[GoogleDrive] Error uploading debrief to Drive: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/session/{session_id}/report")
async def get_session_report(session_id: str, request: Request):
    """Retrieve the post-debate debrief report for a completed session."""
    owner_id = request.state.user_id
    engine = SESSIONS.get(session_id) if SESSION_OWNERS.get(session_id) == owner_id else None
    report = engine.get_debrief_report() if engine else await asyncio.to_thread(
        get_debrief_store().get_report, session_id, owner_id
    )
    if not report:
        raise HTTPException(status_code=404, detail="Debate report not found.")
    return report


# ==========================================
# Google Meet Sparring Endpoints
# ==========================================


@app.post("/api/meeting/schedule")
async def schedule_google_meet(req: ScheduleMeetingRequest, request: Request):
    """Schedule a Google Meet sparring session for Miles, with optional Google Calendar provisioning & Recall bot scheduling."""
    scheduler = get_meeting_scheduler()
    meet_url = req.meet_url

    calendar_provisioned = False
    event_id = None
    if not meet_url and config.google_calendar_enabled:
        try:
            provisioner = GoogleMeetProvisioner(access_token=req.google_access_token)
            res = await provisioner.create_meeting_room(
                title=f"Miles Sparring: {req.topic or 'Debate'}",
                duration_minutes=int((req.max_duration_seconds or 1800) / 60),
            )
            meet_url = res.get("meet_url")
            calendar_provisioned = res.get("is_real_meet", False)
            event_id = res.get("event_id")
        except Exception as e:
            logger.warning(f"[API] Error auto-provisioning Google Meet for schedule: {e}")

    cfg = MeetingConfig(
        max_duration_seconds=req.max_duration_seconds or 1800,
        audio_only=True,
    )
    session = await asyncio.to_thread(
        scheduler.schedule_meeting,
        owner_id=request.state.user_id,
        meet_url=meet_url,
        context_id=req.context_id,
        persona_id=req.persona_id or "vc_pitch",
        difficulty=req.difficulty or "hard",
        topic=req.topic,
        persona_tone=req.persona_tone,
        config=cfg,
    )

    scheduled_bot_id = None
    if req.schedule_recall_bot and req.join_at and meet_url and config.recall_ai_enabled:
        try:
            meet_url = _validate_meeting_url(meet_url)
            session.meet_url = meet_url
            dispatched = await _dispatch_recall_bot(
                session,
                bot_name=f"Miles AI ({session.persona_id.replace('_', ' ').title()})",
                join_at=req.join_at,
            )
            scheduled_bot_id = dispatched["bot_id"]
            logger.info(f"[API] Scheduled Recall bot {scheduled_bot_id} for join_at: {req.join_at}")
        except Exception:
            await asyncio.to_thread(scheduler.store.delete_session, request.state.user_id, session.meeting_id)
            raise

    result = session.to_dict()
    if calendar_provisioned:
        result["calendar_event_id"] = event_id
        result["is_real_meet"] = True
    if scheduled_bot_id:
        result["recall_bot_id"] = scheduled_bot_id
        result["scheduled_join_at"] = req.join_at
    return result


@app.post("/api/meeting/{meeting_id}/start")
async def start_google_meet_session(meeting_id: str, request: Request):
    """Start Miles through Recall Output Media, or the local development simulator."""
    scheduler = get_meeting_scheduler()
    session = await asyncio.to_thread(scheduler.get_session, request.state.user_id, meeting_id)
    if not session:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    if session.recall_bot_id:
        return {
            "status": session.status.value,
            "meeting_id": meeting_id,
            "bot_id": session.recall_bot_id,
            "recall_status": session.recall_status,
            "session": session.to_dict(),
        }
    if scheduler.bot_provider.provider_mode == "unconfigured":
        raise HTTPException(
            status_code=503,
            detail="No live meeting bot provider is configured for this deployment.",
        )
    if isinstance(scheduler.bot_provider, RecallMeetBotProvider):
        try:
            dispatched = await _dispatch_recall_bot(
                session,
                bot_name=f"Miles AI ({session.persona_id.replace('_', ' ').title()})",
            )
            return {
                "status": session.status.value,
                "meeting_id": meeting_id,
                "bot_id": dispatched["bot_id"],
                "recall_status": session.recall_status,
                "region": dispatched["region"],
                "session": session.to_dict(),
            }
        except (HTTPException, RecallAPIError) as exc:
            raise HTTPException(
                status_code=exc.status_code if isinstance(exc, RecallAPIError) else exc.status_code,
                detail=exc.detail if isinstance(exc, RecallAPIError) else exc.detail,
            ) from exc
    try:
        coordinator = await scheduler.start_meeting(request.state.user_id, meeting_id)
        return {
            "status": "in_call",
            "meeting_id": meeting_id,
            "meet_url": coordinator.session.meet_url,
            "opening_statement": coordinator.engine.last_ai_text,
            "session": coordinator.session.to_dict(),
        }
    except Exception as e:
        logger.error(f"[API] Error starting meeting {meeting_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/meeting/{meeting_id}/stop")
async def stop_google_meet_session(meeting_id: str, request: Request):
    """End a live Recall call or stop a local session and return its debrief."""
    scheduler = get_meeting_scheduler()
    session = await asyncio.to_thread(scheduler.get_session, request.state.user_id, meeting_id)
    if not session:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    if session.recall_bot_id:
        if session.debrief_report:
            return {"status": "completed", "meeting_id": meeting_id, "debrief_report": session.debrief_report}
        try:
            stop_status = await _end_recall_bot(session)
        except RecallAPIError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return {"status": stop_status, "meeting_id": meeting_id, "debrief_report": None}
    try:
        report = await scheduler.stop_meeting(request.state.user_id, meeting_id)
        session = await asyncio.to_thread(scheduler.get_session, request.state.user_id, meeting_id)
        return {
            "status": "completed",
            "meeting_id": meeting_id,
            "debrief_report": report,
            "session": session.to_dict() if session else None,
        }
    except Exception as e:
        logger.error(f"[API] Error stopping meeting {meeting_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/meeting/generate-link")
async def generate_instant_link(req: GoogleCalendarLinkRequest):
    """Generate a real Google Meet room (via Google Calendar) or fall back cleanly to a local simulation link."""
    scheduler = get_meeting_scheduler()
    provisioner = GoogleMeetProvisioner(access_token=req.access_token)
    res = await provisioner.create_meeting_room()
    return {
        "meet_url": res["meet_url"],
        "provisioned": res.get("is_real_meet", False),
        "event_id": res.get("event_id"),
        "provider_mode": scheduler.bot_provider.provider_mode,
        "provider_notice": res.get("provider_notice") or scheduler.bot_provider.provider_notice,
    }


# ==========================================
# Recall.ai Meeting Bot Endpoints
# ==========================================


@app.post("/api/meeting/bot/launch")
async def launch_meeting_bot(req: LaunchRecallBotRequest, request: Request):
    """Launch an ad-hoc or scheduled Recall.ai bot into a supported meeting platform."""
    meeting_url = _validate_meeting_url(req.meeting_url)

    recall_svc = RecallService()
    if not recall_svc.api_key:
        raise HTTPException(
            status_code=400,
            detail="RECALL_AI_API_KEY is not configured in .env. Please configure your Recall.ai API key.",
        )

    _require_live_meeting_configuration()
    persona_id = req.persona_id or "vc_pitch"
    persona_title = persona_id.replace("_", " ").title()
    bot_name = req.bot_name or f"Miles AI ({persona_title})"

    scheduler = get_meeting_scheduler()
    cfg = MeetingConfig(max_duration_seconds=req.max_duration_seconds or 1800, audio_only=True)
    session = await asyncio.to_thread(
        scheduler.schedule_meeting,
        owner_id=request.state.user_id,
        meet_url=meeting_url,
        context_id=req.context_id,
        persona_id=persona_id,
        difficulty=req.difficulty or "hard",
        topic=req.topic,
        config=cfg,
    )

    try:
        dispatched = await _dispatch_recall_bot(
            session,
            bot_name=bot_name,
            join_at=req.join_at,
        )
        return {
            "status": session.status.value,
            "bot_id": dispatched["bot_id"],
            "meeting_id": session.meeting_id,
            "meeting_url": meeting_url,
            "bot_name": bot_name,
            "join_at": req.join_at,
            "recall_status": session.recall_status,
            "region": dispatched["region"],
        }
    except RecallAPIError as e:
        await asyncio.to_thread(scheduler.store.delete_session, request.state.user_id, session.meeting_id)
        raise HTTPException(status_code=e.status_code, detail=f"Recall.ai error: {e.detail}")
    except HTTPException:
        await asyncio.to_thread(scheduler.store.delete_session, request.state.user_id, session.meeting_id)
        raise
    except Exception as e:
        await asyncio.to_thread(scheduler.store.delete_session, request.state.user_id, session.meeting_id)
        logger.error(f"[API] Error launching Recall bot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/meeting/bot/{bot_id}")
async def get_bot_status(bot_id: str, request: Request):
    """Return the latest lifecycle state delivered by Recall's signed webhook."""
    owner_id = request.state.user_id
    session = await asyncio.to_thread(get_meeting_scheduler().find_session_by_bot, owner_id, bot_id)
    if not session:
        raise HTTPException(status_code=404, detail="Meeting bot not found.")
    return {
        "id": session.recall_bot_id,
        "status": session.recall_status or "ready",
        "status_message": session.recall_status_message,
        "meeting_status": session.status.value,
        "updated_at": session.recall_status_updated_at,
    }


@app.post("/api/meeting/bot/{bot_id}/leave")
async def leave_meeting_bot(bot_id: str, request: Request):
    """Instruct an active Recall.ai bot to exit the meeting room."""
    session = await asyncio.to_thread(
        get_meeting_scheduler().find_session_by_bot, request.state.user_id, bot_id
    )
    if not session:
        raise HTTPException(status_code=404, detail="Meeting bot not found.")
    try:
        action = await _end_recall_bot(session)
        return {"success": True, "bot_id": bot_id, "action": action, "message": "Recall.ai accepted the request."}
    except RecallAPIError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


@app.get("/api/meeting/bots")
async def list_recall_bots(request: Request, limit: int = Query(20, ge=1, le=100)):
    """List only Recall bots owned by the authenticated user."""
    recall_svc = RecallService()
    bots = await recall_svc.list_bots(limit=limit)
    owned_bot_ids = {
        session.recall_bot_id
        for session in await asyncio.to_thread(
            get_meeting_scheduler().list_sessions, request.state.user_id
        )
        if session.recall_bot_id
    }
    return {"bots": [bot for bot in bots if bot.get("id") in owned_bot_ids], "region": recall_svc.region}


@app.post("/api/webhook/recall")
async def handle_recall_webhook(request: Request):
    """Receive and process Recall.ai webhook events with cryptographic HMAC signature verification."""
    raw_body = await request.body()
    headers = dict(request.headers)

    if not RecallService.verify_webhook_signature(headers, raw_body):
        logger.warning("[RecallWebhook] Unauthorized webhook signature received.")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body)
        event_type = payload.get("event", "")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        bot_data = data.get("bot") if isinstance(data.get("bot"), dict) else {}
        status_data = data.get("status") if isinstance(data.get("status"), dict) else {}
        nested_status = data.get("data") if isinstance(data.get("data"), dict) else {}
        bot_id = data.get("bot_id") or bot_data.get("id")
        status_code = (
            status_data.get("code")
            or nested_status.get("code")
            or (event_type[4:] if event_type.startswith("bot.") and event_type != "bot.status_change" else None)
        )
        metadata = bot_data.get("metadata") or data.get("metadata") or {}
        meeting_id = metadata.get("session_id") or metadata.get("meeting_id")
        owner_id = metadata.get("owner_id")

        if not (isinstance(bot_id, str) and isinstance(status_code, str)):
            return {"status": "ignored", "event": event_type}

        updated_at = status_data.get("created_at") or nested_status.get("updated_at")
        try:
            changed_at = datetime.datetime.fromisoformat(str(updated_at).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            changed_at = time.time()

        session = None
        if isinstance(meeting_id, str) and isinstance(owner_id, str):
            scheduler = get_meeting_scheduler()
            session = await asyncio.to_thread(scheduler.get_session, owner_id, meeting_id)

        if not session:
            logger.info("[RecallWebhook] Verified but unlinked event %s for bot %s", event_type, bot_id)
            return {"status": "received", "event": event_type, "bot_id": bot_id}
        if session.recall_bot_id and session.recall_bot_id != bot_id:
            logger.warning("[RecallWebhook] Ignored bot ID mismatch for meeting %s", session.meeting_id)
            return {"status": "ignored", "event": event_type}
        if session.recall_status_updated_at and changed_at < session.recall_status_updated_at:
            return {"status": "ignored", "event": event_type, "reason": "stale_status"}

        session.recall_bot_id = bot_id
        session.recall_status = status_code
        session.recall_status_updated_at = changed_at
        session.recall_status_message = (
            status_data.get("message") or status_data.get("sub_code")
            or nested_status.get("message") or nested_status.get("sub_code")
        )
        now = time.time()
        if session.status in {MeetingStatus.COMPLETED, MeetingStatus.FAILED, MeetingStatus.CANCELLED}:
            pass
        elif status_code in {"in_call_recording", "in_call_not_recording", "recording_permission_allowed", "recording_permission_denied"}:
            session.status = MeetingStatus.IN_CALL
            session.started_at = session.started_at or changed_at or now
            session.error_message = None
        elif status_code in {"joining_call", "in_waiting_room"}:
            if session.status == MeetingStatus.SCHEDULED:
                session.status = MeetingStatus.CONNECTING
        elif status_code in {"call_ended", "done"}:
            if session.status != MeetingStatus.FAILED:
                session.status = MeetingStatus.COMPLETED
                session.error_message = None
            session.ended_at = session.ended_at or changed_at or now
            if session.started_at:
                session.duration_seconds = max(0.0, session.ended_at - session.started_at)
        elif status_code == "fatal":
            session.status = MeetingStatus.FAILED
            session.error_message = session.recall_status_message or "Recall.ai could not join or continue the meeting."
            session.ended_at = session.ended_at or changed_at or now
            if session.started_at:
                session.duration_seconds = max(0.0, session.ended_at - session.started_at)

        await asyncio.to_thread(get_meeting_scheduler().store.save_session, session)
        logger.info("[RecallWebhook] Updated meeting %s to Recall status %s", session.meeting_id, status_code)
        return {"status": "received", "event": event_type, "bot_id": bot_id}
    except Exception as e:
        logger.error(f"[RecallWebhook] Error processing webhook: {e}")
        raise HTTPException(status_code=400, detail="Invalid Recall webhook payload.") from e


@app.get("/api/meetings")
async def list_google_meet_sessions(request: Request):
    """List the authenticated user's scheduled and historical Google Meet sessions."""
    scheduler = get_meeting_scheduler()
    sessions = await asyncio.to_thread(scheduler.list_sessions, request.state.user_id)
    return {"meetings": [s.to_dict() for s in sessions]}


@app.get("/api/meeting/{meeting_id}")
async def get_google_meet_session(meeting_id: str, request: Request):
    """Retrieve Google Meet session details and status."""
    scheduler = get_meeting_scheduler()
    session = await asyncio.to_thread(scheduler.get_session, request.state.user_id, meeting_id)
    if not session:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return session.to_dict()


@app.get("/api/meeting/{meeting_id}/debrief")
async def get_google_meet_debrief(meeting_id: str, request: Request):
    """Retrieve debrief report for a completed Google Meet session."""
    scheduler = get_meeting_scheduler()
    session = await asyncio.to_thread(scheduler.get_session, request.state.user_id, meeting_id)
    if not session:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    if session.debrief_report:
        return session.debrief_report

    dispatcher = get_debrief_dispatcher()
    saved = await asyncio.to_thread(
        dispatcher.get_saved_debrief, meeting_id, request.state.user_id
    )
    if saved:
        return saved
    raise HTTPException(status_code=404, detail="Debate debrief report not available for this meeting yet.")


@app.get("/api/meeting/{meeting_id}/debrief/html")
async def get_google_meet_debrief_html(meeting_id: str, request: Request):
    """Retrieve HTML formatted debrief email report."""
    scheduler = get_meeting_scheduler()
    session = await asyncio.to_thread(scheduler.get_session, request.state.user_id, meeting_id)
    if not session or not session.debrief_report:
        raise HTTPException(status_code=404, detail="Meeting or debrief report not found.")
    dispatcher = get_debrief_dispatcher()
    html_content = dispatcher.format_html_summary(session)
    return HTMLResponse(content=html_content)


# ==========================================
# Full-Duplex WebSocket Endpoint (`/ws/debate`)
# ==========================================


@app.websocket("/ws/debate")
async def websocket_debate(
    websocket: WebSocket,
    scenario: str = Query("vc_pitch"),
    topic: Optional[str] = Query(None),
    difficulty: str = Query("hard"),
    persona_tone: Optional[str] = Query(None),
    audio_format: str = Query("binary"),
    context_id: Optional[str] = Query(None),
    is_panel_mode: bool = Query(False),
    meeting_bridge: bool = Query(False),
):
    """Full-Duplex live audio & telemetry stream for Miles."""
    origin = websocket.headers.get("origin")
    if origin and not is_allowed_origin(origin):
        logger.warning(f"[WebSocket] Rejected connection from unauthorized origin: {origin}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    bridge_session: Optional[MeetingSession] = None
    if meeting_bridge:
        try:
            if not config.recall_audio_bridge_secret:
                raise InvalidBridgeTicket("Meeting audio bridge is not configured.")
            auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=5)
            if auth_message.get("type") != "meeting_bridge_auth" or not isinstance(auth_message.get("ticket"), str):
                raise InvalidBridgeTicket("Missing meeting audio bridge ticket.")
            claims = verify_bridge_ticket(auth_message["ticket"], config.recall_audio_bridge_secret)
            user_id = claims["owner_id"]
            bridge_session = await asyncio.to_thread(
                get_meeting_scheduler().get_session, user_id, claims["meeting_id"]
            )
            if not bridge_session or bridge_session.status in {
                MeetingStatus.COMPLETED, MeetingStatus.FAILED, MeetingStatus.CANCELLED
            }:
                raise InvalidBridgeTicket("Meeting session is unavailable.")
        except (InvalidBridgeTicket, asyncio.TimeoutError, WebSocketDisconnect):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        except Exception:
            logger.exception("Meeting audio bridge authentication failed.")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return
    elif app.state.auth_test_bypass:
        user_id = "00000000-0000-4000-8000-000000000001"
    else:
        if not config.supabase_url:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        try:
            auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=5)
            if auth_message.get("type") != "authenticate" or not isinstance(auth_message.get("access_token"), str):
                raise InvalidAccessToken("Missing WebSocket access token.")
            verified_user = await asyncio.to_thread(
                app.state.token_verifier.verify,
                auth_message["access_token"],
            )
        except (AuthConfigurationError, InvalidAccessToken, asyncio.TimeoutError, WebSocketDisconnect):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        except Exception:
            logger.exception("WebSocket authentication failed.")
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
            return
        user_id = verified_user.user_id

    if bridge_session and bridge_session.meeting_id in SESSIONS:
        await websocket.close(code=1008, reason="This meeting already has an active audio bridge.")
        return
    user_session_count = sum(owner_id == user_id for owner_id in SESSION_OWNERS.values())
    if user_session_count >= MAX_ACTIVE_SESSIONS_PER_USER:
        await websocket.close(code=1008, reason="This account already has an active debate session.")
        return
    if len(SESSIONS) >= MAX_ACTIVE_DEBATE_SESSIONS:
        await websocket.close(code=1013, reason="The service is at its concurrent session limit. Try again shortly.")
        return

    install_stream_shutdown_filter()

    if bridge_session:
        scenario = bridge_session.persona_id
        topic = bridge_session.topic
        difficulty = bridge_session.difficulty
        persona_tone = bridge_session.persona_tone
        context_id = bridge_session.context_id
        audio_format = "binary"
        is_panel_mode = False

    # Load context dossier if provided
    context_dossier = None
    if context_id:
        store = get_context_store()
        stored = await asyncio.to_thread(store.get_context, user_id, context_id)
        if stored:
            context_dossier = stored.to_dict()
            logger.info(
                f"[WebSocket] Loaded Context Dossier '{stored.title}' "
                f"({len(stored.numeric_metrics)} metrics, doc_type: {stored.doc_type})"
            )

    # 1. Initialize Debate Engine & Services
    engine = DebateEngine(
        scenario_id=scenario,
        topic=topic,
        difficulty=difficulty,
        session_id=bridge_session.meeting_id if bridge_session else None,
        persona_tone=persona_tone,
        context_dossier=context_dossier,
        is_panel_mode=is_panel_mode,
    )
    SESSIONS[engine.session_id] = engine
    SESSION_OWNERS[engine.session_id] = user_id
    report_persisted = False
    meeting_leave_error: Optional[str] = None

    # Configure Rime TTS with persona-specific speaker and chosen model
    tts_client = RimeStreamingTTSClient(
        speaker=engine.persona.speaker,
        model_id=config.rime_model_id,
        sample_rate=config.tts_sample_rate,
    )
    interruption_mgr = InterruptionManager(tts_client=tts_client)

    logger.info(
        f"[WebSocket] Connected session '{engine.session_id}' "
        f"| Scenario: {scenario} | Speaker: {engine.persona.speaker} | Model: {config.rime_model_id} | Format: {audio_format}"
    )

    # Session timing & state tracking
    turn_start_time = time.time()
    ai_speech_end_time = time.time()
    user_speech_start_time = 0.0
    last_partial_time = time.time()
    current_turn_was_barge_in = False
    last_barge_in_latency_ms = 0.018
    last_ai_interruption_time = 0.0

    # Audio Intelligence & Conversational Dominance Tracking
    user_talk_time_sec = 0.0
    ai_talk_time_sec = 0.0
    recent_micro_hesitations: List[Dict[str, Any]] = []
    turn_round = 0

    active_ai_turn_task: Optional[asyncio.Task] = None
    monitor_task: Optional[asyncio.Task] = None
    audio_stream_lock = asyncio.Lock()
    stt_client: Optional[AssemblyAIStreamingClient] = None
    stt_connected = False
    stop_event = asyncio.Event()
    ws_channel = WebSocketChannel(websocket, stop_event)

    async def safe_send_json(payload: Dict):
        await ws_channel.send_json(payload)

    async def safe_send_bytes(data: bytes):
        await ws_channel.send_bytes(data)

    async def fail_bridge_startup(message: str):
        """Fail closed before opening the meeting audio stream if a dependency is unavailable."""
        if bridge_session is None:
            return

        await safe_send_json({"type": "meeting_bridge_error", "message": message})
        bridge_session.status = MeetingStatus.FAILED
        bridge_session.error_message = message
        bridge_session.ended_at = time.time()
        bridge_session.recall_status = "bridge_start_failed"
        bridge_session.recall_status_message = message
        bridge_session.recall_status_updated_at = bridge_session.ended_at

        try:
            if bridge_session.recall_bot_id and not await RecallService().leave_call(bridge_session.recall_bot_id):
                bridge_session.error_message += " Recall.ai did not confirm the leave request."
        except Exception:
            logger.exception("Could not ask Recall.ai to leave after meeting bridge startup failed.")
            bridge_session.error_message += " Recall.ai leave could not be confirmed."
        with contextlib.suppress(Exception):
            await asyncio.to_thread(get_meeting_scheduler().store.save_session, bridge_session)

        stop_event.set()
        if stt_client:
            with contextlib.suppress(Exception):
                await stt_client.stop()
        tts_client.cancel()
        with contextlib.suppress(Exception):
            await tts_client.close()
        with contextlib.suppress(Exception):
            await engine.llm_client.close()
        if SESSIONS.get(engine.session_id) is engine:
            SESSIONS.pop(engine.session_id, None)
            SESSION_OWNERS.pop(engine.session_id, None)
        with contextlib.suppress(Exception):
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Meeting audio bridge startup failed.")

    async def emit_speech_intelligence():
        total = user_talk_time_sec + ai_talk_time_sec
        dom_ratio = round(user_talk_time_sec / total, 2) if total > 0 else 0.50
        user_pct = max(5, min(95, round(dom_ratio * 100)))
        ai_pct = 100 - user_pct
        payload = {
            "type": "speech_intelligence",
            "round": turn_round,
            "user_talk_time_sec": round(user_talk_time_sec, 1),
            "ai_talk_time_sec": round(ai_talk_time_sec, 1),
            "dominance_ratio": dom_ratio,
            "user_pct": user_pct,
            "ai_pct": ai_pct,
            "micro_hesitations": recent_micro_hesitations[-5:],
            "confidence_mean": 0.96,
            "stress_indicator": "elevated" if len(recent_micro_hesitations) >= 2 else "steady",
        }
        await safe_send_json(payload)

    async def emit_turn_telemetry(trigger_time: float):
        ttfa_ms = max(15.0, round((time.time() - trigger_time) * 1000, 1))
        active_llm = (
            config.openai_model
            if config.openai_api_key
            else (config.gemini_model if config.gemini_api_key else "meta-llama/llama-3.3-70b-instruct")
        )
        await safe_send_json({
            "type": "turn_telemetry",
            "ttfa_ms": ttfa_ms,
            "barge_in_latency_ms": round(last_barge_in_latency_ms, 3),
            "stt_provider": "AssemblyAI v3 (universal-3-5-pro)",
            "tts_provider": f"Rime Coda ({engine.persona.speaker})",
            "llm_provider": active_llm,
        })

    async def stream_ai_audio(
        text: str,
        mark_finished_at_end: bool = True,
        is_adversarial_interruption: bool = False,
    ):
        """Synthesize and stream audio chunks to browser without stream collisions."""
        async with audio_stream_lock:
            ai_stream_start = time.time()
            if is_adversarial_interruption:
                interruption_mgr.start_ai_interruption()
                await safe_send_json({"type": "mic_lock", "locked": True, "reason": "ai_interruption"})

            interruption_mgr.mark_ai_speaking(text)
            await safe_send_json({"type": "ai_state", "state": "speaking"})

            try:
                active_speaker_voice = engine.current_speaker_voice or engine.persona.speaker
                async for chunk in tts_client.stream_audio_chunks(text, speaker=active_speaker_voice):
                    if interruption_mgr.ai_is_speaking and not stop_event.is_set():
                        if audio_format in ("binary", "both"):
                            await safe_send_bytes(chunk)
                        if audio_format in ("base64", "both"):
                            b64 = base64.b64encode(chunk).decode("ascii")
                            await safe_send_json({"type": "audio_chunk", "data": b64})
                    else:
                        break
            finally:
                nonlocal ai_talk_time_sec
                ai_duration = max(0.4, time.time() - ai_stream_start)
                ai_talk_time_sec += ai_duration

                if is_adversarial_interruption:
                    nonlocal last_ai_interruption_time
                    last_ai_interruption_time = time.time()
                    interruption_mgr.end_ai_interruption()
                    await safe_send_json({"type": "mic_lock", "locked": False})

                if mark_finished_at_end and interruption_mgr.ai_is_speaking:
                    interruption_mgr.mark_ai_finished()
                    nonlocal ai_speech_end_time, user_speech_start_time, last_partial_time
                    ai_speech_end_time = time.time()
                    if is_adversarial_interruption:
                        user_speech_start_time = 0.0
                        last_partial_time = 0.0
                    await safe_send_json({"type": "ai_state", "state": "listening"})

                await emit_speech_intelligence()

    def perform_barge_in_sync() -> Optional[Dict[str, Any]]:
        """Synchronously execute barge-in cut-off, state truncation, and set was_barge_in flag."""
        if interruption_mgr.ai_interruption_active:
            # AI holds adversarial right-of-way; suppress user barge-in
            return None

        nonlocal current_turn_was_barge_in, last_barge_in_latency_ms
        current_turn_was_barge_in = True

        if active_ai_turn_task and not active_ai_turn_task.done():
            active_ai_turn_task.cancel()

        event = interruption_mgr.handle_user_speech_detected()
        if event:
            last_barge_in_latency_ms = event["latency_ms"]
            engine.record_barge_in(event.get("spoken_before_cut", ""), event["latency_ms"])
        return event

    async def trigger_barge_in():
        """Handle user barge-in during active AI speech or in-flight generation."""
        event = perform_barge_in_sync()
        if event:
            await safe_send_json(event)
            await safe_send_json({"type": "ai_state", "state": "interrupted"})

    # Callbacks for AssemblyAI STT
    def on_stt_speech_start():
        """User started speaking into mic."""
        if interruption_mgr.ai_interruption_active:
            return

        nonlocal user_speech_start_time, last_partial_time
        now = time.time()
        if user_speech_start_time <= 0:
            user_speech_start_time = now
        last_partial_time = now

        if interruption_mgr.ai_is_speaking or interruption_mgr.ai_is_thinking:
            event = perform_barge_in_sync()
            if event:
                ws_channel.dispatch(safe_send_json(event))
                ws_channel.dispatch(safe_send_json({"type": "ai_state", "state": "interrupted"}))

    def on_stt_partial(transcript: str, confidence: float):
        """Interim user speech transcript."""
        if interruption_mgr.ai_interruption_active:
            return

        nonlocal last_partial_time, user_speech_start_time
        now = time.time()
        if user_speech_start_time <= 0:
            user_speech_start_time = now
        mid_hesitation = max(0.0, now - last_partial_time - 0.5)
        last_partial_time = now

        # Broadcast interim transcript (for user speech telemetry)
        ws_channel.dispatch(safe_send_json({
            "type": "transcript",
            "role": "user",
            "text": transcript,
            "is_final": False,
            "confidence": confidence,
        }))

        # Check for adversarial fluff interjection (only if not already speaking)
        interjection = engine.check_fluff_interruption(transcript, mid_hesitation)
        if interjection and not interruption_mgr.ai_is_speaking and not interruption_mgr.ai_is_thinking and not interruption_mgr.ai_interruption_active:
            interruption_mgr.start_ai_interruption()
            ws_channel.dispatch(safe_send_json({"type": "mic_lock", "locked": True, "reason": "ai_interruption"}))
            ws_channel.dispatch(safe_send_json({"type": "ai_state", "state": "speaking"}))

            engine.record_ai_cut_in("fluff_detected", interjection)
            cut_event = interruption_mgr.trigger_ai_interruption(interjection, reason="fluff_detected")
            ws_channel.dispatch(safe_send_json(cut_event))
            ws_channel.dispatch(safe_send_json({
                "type": "transcript",
                "role": "ai",
                "speaker": engine.persona.name,
                "text": interjection,
                "is_final": True,
                "confidence": 1.0,
            }))
            ws_channel.dispatch(stream_ai_audio(interjection, is_adversarial_interruption=True))

    def on_stt_final(transcript: str, confidence: float):
        """Finalized user statement."""
        nonlocal last_ai_interruption_time
        if interruption_mgr.ai_interruption_active or (time.time() - last_ai_interruption_time < 0.8):
            logger.info("[on_stt_final] Suppressing trailing user speech finalize received during/after AI interruption.")
            return
        nonlocal turn_start_time, user_speech_start_time, current_turn_was_barge_in, active_ai_turn_task
        now = time.time()
        start_reference = user_speech_start_time if user_speech_start_time > 0 else turn_start_time
        duration = max(0.5, now - start_reference)

        # Accurate hesitation: latency between AI speech conclusion and user answer onset
        if user_speech_start_time > 0 and ai_speech_end_time > 0:
            hesitation = max(0.0, user_speech_start_time - ai_speech_end_time)
        else:
            hesitation = 0.0

        was_barge_in = current_turn_was_barge_in

        # Broadcast finalized user transcript
        ws_channel.dispatch(safe_send_json({
            "type": "transcript",
            "role": "user",
            "text": transcript,
            "is_final": True,
            "confidence": confidence,
        }))

        # Update telemetry & composure score with barge-in reward
        snapshot = engine.record_user_turn(
            transcript=transcript,
            duration_sec=duration,
            hesitation_sec=hesitation,
            was_barge_in=was_barge_in,
        )
        ws_channel.dispatch(safe_send_json(snapshot.to_dict()))

        # Broadcast real-time ground truth audit telemetry if context is active
        if engine.fact_auditor and engine.fact_auditor.dossier:
            audit_summary = engine.fact_auditor.get_audit_summary()
            ws_channel.dispatch(safe_send_json({
                "type": "fact_audit_update",
                "factual_accuracy_score": audit_summary["factual_accuracy_score"],
                "verified_count": audit_summary["verified_count"],
                "discrepancy_count": audit_summary["discrepancy_count"],
                "verified_metrics": audit_summary["verified_metrics"],
                "discrepancies": audit_summary["discrepancies"],
            }))

        # Broadcast real-time math contradiction alert if triggered
        if engine.math_auditor and engine.math_auditor.discrepancy_history:
            last_math = engine.math_auditor.discrepancy_history[-1]
            if last_math.round_number == engine.round_number:
                ws_channel.dispatch(safe_send_json({
                    "type": "math_contradiction_alert",
                    "rule_type": last_math.rule_type,
                    "description": last_math.description,
                    "lethal_salvo": last_math.lethal_salvo,
                    "claimed_values": last_math.claimed_values,
                }))

        # Update talk-time & speech intelligence
        nonlocal user_talk_time_sec, turn_round
        turn_round += 1
        user_talk_time_sec += duration
        ws_channel.dispatch(emit_speech_intelligence())

        # Reset turn markers
        current_turn_was_barge_in = False
        user_speech_start_time = 0.0

        # Cancel any previous AI task and trigger new counter-attack
        if active_ai_turn_task and not active_ai_turn_task.done():
            active_ai_turn_task.cancel()
        active_ai_turn_task = ws_channel.dispatch(execute_ai_turn(trigger_time=now))

    def on_stt_words(words: List[Dict[str, Any]], hesitations: List[Dict[str, Any]]):
        """Process word-level timestamps and micro-hesitation events."""
        if hesitations:
            recent_micro_hesitations[:] = (recent_micro_hesitations + hesitations)[-20:]
            for h in hesitations:
                if h.get("gap_ms", 0) >= 1100:
                    engine.record_micro_hesitation(
                        gap_ms=h["gap_ms"],
                        word_before=h.get("word_before", ""),
                        word_after=h.get("word_after", ""),
                    )
            ws_channel.dispatch(emit_speech_intelligence())

    async def execute_ai_turn(trigger_time: Optional[float] = None):
        """Pipelined adversarial generation: stream clauses into TTS immediately for sub-second TTFA."""
        nonlocal turn_start_time, ai_speech_end_time
        calc_trigger = trigger_time or time.time()
        interruption_mgr.mark_ai_thinking()
        await safe_send_json({"type": "ai_state", "state": "thinking"})

        accumulated_clauses: List[str] = []
        first_clause = True

        try:
            async with contextlib.aclosing(engine.generate_adversary_clauses()) as clause_stream:
                async for clause in clause_stream:
                    if stop_event.is_set():
                        return

                    accumulated_clauses.append(clause)
                    current_full_text = " ".join(accumulated_clauses)

                    # Send streaming subtitle text to UI immediately
                    await safe_send_json({
                        "type": "transcript",
                        "role": "ai",
                        "speaker": engine.current_speaker_name,
                        "speaker_voice": engine.current_speaker_voice,
                        "is_panel_mode": engine.is_panel_mode,
                        "text": current_full_text,
                        "is_final": False,
                        "confidence": 1.0,
                    })

                    if first_clause:
                        interruption_mgr.mark_ai_thinking_done()
                        first_clause = False
                        await emit_turn_telemetry(calc_trigger)

                    # Stream this clause to TTS and browser
                    if not stop_event.is_set():
                        await stream_ai_audio(clause, mark_finished_at_end=False)

            # Mark final completed text
            final_text = " ".join(accumulated_clauses).strip()
            if final_text and not stop_event.is_set():
                await safe_send_json({
                    "type": "transcript",
                    "role": "ai",
                    "speaker": engine.current_speaker_name,
                    "speaker_voice": engine.current_speaker_voice,
                    "is_panel_mode": engine.is_panel_mode,
                    "text": final_text,
                    "is_final": True,
                    "confidence": 1.0,
                })

                # Broadcast detected rhetorical tactic for Training HUD
                if engine.last_detected_tactic:
                    await safe_send_json({
                        "type": "rhetorical_tactic",
                        "tactic": engine.last_detected_tactic.to_dict(),
                    })

        except asyncio.CancelledError:
            interruption_mgr.mark_ai_thinking_done()
            return
        finally:
            interruption_mgr.mark_ai_thinking_done()
            if interruption_mgr.ai_is_speaking:
                interruption_mgr.mark_ai_finished()
                ai_speech_end_time = time.time()
                await safe_send_json({"type": "ai_state", "state": "listening"})

        turn_start_time = time.time()

    async def monitor_user_presence_loop():
        """Proactively monitor user speech flow and trigger interruptions on stalling or rambling."""
        while not stop_event.is_set():
            await asyncio.sleep(0.35)
            if interruption_mgr.ai_is_speaking or interruption_mgr.ai_is_thinking or interruption_mgr.ai_interruption_active:
                continue

            now = time.time()

            # Case A: User is currently speaking into mic
            if user_speech_start_time > 0:
                speech_duration = now - user_speech_start_time
                mid_speech_pause = now - last_partial_time if last_partial_time > 0 else 0

                # 1. Rambling trigger (>11s without stopping)
                rambling_cut = engine.check_rambling_interruption(speech_duration)
                if rambling_cut:
                    interruption_mgr.start_ai_interruption()
                    await safe_send_json({"type": "mic_lock", "locked": True, "reason": "ai_interruption"})
                    await safe_send_json({"type": "ai_state", "state": "speaking"})
                    engine.record_ai_cut_in("rambling_detected", rambling_cut)
                    cut_event = interruption_mgr.trigger_ai_interruption(rambling_cut, reason="rambling_detected")
                    await safe_send_json(cut_event)
                    await safe_send_json({
                        "type": "transcript",
                        "role": "ai",
                        "speaker": engine.persona.name,
                        "text": rambling_cut,
                        "is_final": True,
                        "confidence": 1.0,
                    })
                    user_speech_start_time = 0.0
                    last_partial_time = 0.0
                    await stream_ai_audio(rambling_cut, is_adversarial_interruption=True)
                    continue

                # 2. Mid-speech freeze (>2.0s silence mid-answer)
                if mid_speech_pause >= 2.0:
                    hesitation_cut = engine.check_hesitation_interruption(mid_speech_pause)
                    if hesitation_cut:
                        interruption_mgr.start_ai_interruption()
                        await safe_send_json({"type": "mic_lock", "locked": True, "reason": "ai_interruption"})
                        await safe_send_json({"type": "ai_state", "state": "speaking"})
                        engine.record_ai_cut_in("hesitation_detected", hesitation_cut)
                        cut_event = interruption_mgr.trigger_ai_interruption(hesitation_cut, reason="hesitation_detected")
                        await safe_send_json(cut_event)
                        await safe_send_json({
                            "type": "transcript",
                            "role": "ai",
                            "speaker": engine.persona.name,
                            "text": hesitation_cut,
                            "is_final": True,
                            "confidence": 1.0,
                        })
                        user_speech_start_time = 0.0
                        last_partial_time = 0.0
                        await stream_ai_audio(hesitation_cut, is_adversarial_interruption=True)
                        continue

            # Case B: AI concluded its question, but user remained silent (>2.3s dead air)
            elif ai_speech_end_time > 0:
                dead_air = now - ai_speech_end_time
                if dead_air >= 2.3:
                    hesitation_cut = engine.check_hesitation_interruption(dead_air)
                    if hesitation_cut:
                        engine.record_ai_cut_in("silence_timeout", hesitation_cut)
                        cut_event = interruption_mgr.trigger_ai_interruption(hesitation_cut, reason="silence_timeout")
                        await safe_send_json(cut_event)
                        await safe_send_json({
                            "type": "transcript",
                            "role": "ai",
                            "speaker": engine.persona.name,
                            "text": hesitation_cut,
                            "is_final": True,
                            "confidence": 1.0,
                        })
                        await stream_ai_audio(hesitation_cut, is_adversarial_interruption=True)
                        ai_speech_end_time = time.time()
                        continue

    # 2. Connect AssemblyAI in background with scenario vocabulary boosting
    scenario_boost = SCENARIO_VOCABULARY.get(scenario, SCENARIO_VOCABULARY.get("vc_pitch", []))
    stt_client = AssemblyAIStreamingClient(
        api_key=config.assemblyai_api_key,
        sample_rate=config.sample_rate,
        word_boost=scenario_boost,
        on_partial=on_stt_partial,
        on_final=on_stt_final,
        on_speech_start=on_stt_speech_start,
        on_words=on_stt_words,
    )

    async def connect_stt_background():
        nonlocal stt_connected
        stt_connected = await stt_client.connect()

    if bridge_session:
        try:
            stt_connected = await asyncio.wait_for(stt_client.connect(), timeout=20)
        except asyncio.CancelledError:
            await fail_bridge_startup("Meeting audio startup was interrupted, so Miles left the meeting.")
            raise
        except Exception:
            logger.exception("Could not connect AssemblyAI before starting meeting %s.", bridge_session.meeting_id)
        if not stt_connected:
            await fail_bridge_startup("Miles could not connect to speech recognition and left the meeting.")
            return

        await safe_send_json({"type": "meeting_bridge_ready"})
        try:
            audio_ready = json.loads(await asyncio.wait_for(websocket.receive_text(), timeout=20))
        except asyncio.CancelledError:
            await fail_bridge_startup("Meeting audio startup was interrupted, so Miles left the meeting.")
            raise
        except (asyncio.TimeoutError, WebSocketDisconnect, json.JSONDecodeError):
            await fail_bridge_startup("Meeting audio could not start, so Miles left the meeting.")
            return
        if not isinstance(audio_ready, dict) or audio_ready.get("type") != "meeting_bridge_audio_ready":
            await fail_bridge_startup("Meeting audio could not start, so Miles left the meeting.")
            return
        await safe_send_json({"type": "meeting_bridge_started"})
    else:
        ws_channel.dispatch(connect_stt_background())

    # 3. Deliver opening salvo immediately
    opening_start = time.time()
    if context_dossier:
        await safe_send_json({
            "type": "context_loaded",
            "context_id": context_dossier.get("context_id"),
            "title": context_dossier.get("title"),
            "doc_type": context_dossier.get("doc_type"),
            "metric_count": len(context_dossier.get("numeric_metrics", [])),
            "metrics": context_dossier.get("numeric_metrics", []),
        })

    if engine.is_panel_mode and engine.panel:
        await safe_send_json({
            "type": "panel_init",
            "panel": engine.panel.to_dict(),
        })

    opening = engine.start_debate()
    await safe_send_json({
        "type": "transcript",
        "role": "ai",
        "speaker": engine.current_speaker_name,
        "speaker_voice": engine.current_speaker_voice,
        "is_panel_mode": engine.is_panel_mode,
        "text": opening,
        "is_final": True,
        "confidence": 1.0,
    })

    # Broadcast initial tactical attack profile for Training HUD
    init_tactic = engine.tactic_detector.detect_tactic(opening)
    await safe_send_json({
        "type": "rhetorical_tactic",
        "tactic": init_tactic.to_dict(),
    })

    init_snapshot = engine.scorer.evaluate_turn("", duration_seconds=1.0)
    await safe_send_json(init_snapshot.to_dict())
    ws_channel.dispatch(emit_speech_intelligence())
    ws_channel.dispatch(emit_turn_telemetry(opening_start))

    # Stream opening audio and launch active presence monitor
    active_ai_turn_task = ws_channel.dispatch(stream_ai_audio(opening))
    monitor_task = ws_channel.dispatch(monitor_user_presence_loop())

    # 4. Main WebSocket Message Pump
    try:
        while not stop_event.is_set():
            message = await websocket.receive()

            # Process binary audio from browser microphone
            if "bytes" in message and message["bytes"]:
                pcm_data = message["bytes"]

                # If adversary has seized floor during an adversarial interjection, drop inbound mic bytes
                if interruption_mgr.ai_interruption_active:
                    continue

                # Live Audio Energy / VAD for instant barge-in detection
                rms = calculate_pcm_rms(pcm_data)
                if rms > 550.0:
                    now = time.time()
                    if user_speech_start_time <= 0:
                        user_speech_start_time = now
                    if interruption_mgr.ai_is_speaking or interruption_mgr.ai_is_thinking:
                        await trigger_barge_in()

                # Stream to AssemblyAI
                if stt_connected and stt_client:
                    await stt_client.send_audio_chunk(pcm_data)

            # Process JSON control commands from browser
            elif "text" in message and message["text"]:
                try:
                    payload = json.loads(message["text"])
                    cmd_type = payload.get("type")

                    if cmd_type == "end_debate":
                        # Silence any ongoing AI speech and cancel monitoring loop
                        if monitor_task and not monitor_task.done():
                            monitor_task.cancel()
                        interruption_mgr.mark_ai_finished()
                        tts_client.cancel()
                        if active_ai_turn_task and not active_ai_turn_task.done():
                            active_ai_turn_task.cancel()

                        if bridge_session and bridge_session.recall_bot_id and bridge_session.status not in {
                            MeetingStatus.COMPLETED, MeetingStatus.FAILED, MeetingStatus.CANCELLED
                        }:
                            try:
                                if not await RecallService().leave_call(bridge_session.recall_bot_id):
                                    meeting_leave_error = "Recall.ai did not confirm that Miles left the meeting."
                            except Exception:
                                logger.exception("Could not ask Recall.ai to leave meeting %s.", bridge_session.meeting_id)
                                meeting_leave_error = "Recall.ai could not confirm that Miles left the meeting."

                        # Inform UI that GPT-4o is deeply analyzing the debate transcript
                        await safe_send_json({
                            "type": "debrief_status",
                            "status": "generating",
                            "message": "Analyzing debate transcript with GPT-4o...",
                        })

                        # Deep evaluation via GPT-4o
                        report = await engine.generate_llm_debrief_report()
                        try:
                            await asyncio.to_thread(get_debrief_store().save_report, report, user_id)
                            report_persisted = True
                            if bridge_session:
                                bridge_session.debrief_report = report
                                bridge_session.ended_at = time.time()
                                bridge_session.duration_seconds = max(
                                    0.0, bridge_session.ended_at - (bridge_session.started_at or bridge_session.created_at)
                                )
                                if bridge_session.status != MeetingStatus.FAILED:
                                    if meeting_leave_error:
                                        bridge_session.error_message = meeting_leave_error
                                    else:
                                        bridge_session.status = MeetingStatus.COMPLETED
                                        bridge_session.error_message = None
                                await asyncio.to_thread(
                                    get_meeting_scheduler().store.save_session, bridge_session
                                )
                        except Exception:
                            logger.exception("Could not persist completed debate report %s.", engine.session_id)
                            await safe_send_json({
                                "type": "debrief_status",
                                "status": "error",
                                "message": "The report is ready, but it could not be saved for later access.",
                            })
                        await safe_send_json(report)
                        logger.info(f"[DebateEngine] Debate concluded. GPT-4o report sent for session {engine.session_id}.")

                    elif cmd_type == "user_text":
                        # Text fallback input for testing without microphone
                        user_text = payload.get("text", "").strip()
                        if user_text:
                            on_stt_speech_start()
                            on_stt_final(user_text, 1.0)

                    elif cmd_type == "ping":
                        await safe_send_json({"type": "pong"})

                except json.JSONDecodeError:
                    pass

    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info(f"[WebSocket] Client disconnected: session {engine.session_id}")
    except RuntimeError as e:
        if "disconnect" in str(e).lower() or "closed" in str(e).lower():
            logger.info(f"[WebSocket] Connection closed: session {engine.session_id}")
        else:
            logger.error(f"[WebSocket] RuntimeError: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"[WebSocket] Error: {e}", exc_info=True)
    finally:
        stop_event.set()
        if monitor_task and not monitor_task.done():
            monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor_task
        if active_ai_turn_task and not active_ai_turn_task.done():
            active_ai_turn_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active_ai_turn_task
        await ws_channel.cleanup()
        if stt_client:
            await stt_client.stop()
        tts_client.cancel()
        await tts_client.close()
        if bridge_session and not report_persisted:
            try:
                report = await engine.generate_llm_debrief_report()
                await asyncio.to_thread(get_debrief_store().save_report, report, user_id)
                stored_meeting = await asyncio.to_thread(
                    get_meeting_scheduler().get_session, user_id, bridge_session.meeting_id
                )
                if stored_meeting:
                    if stored_meeting.recall_bot_id and stored_meeting.status not in {
                        MeetingStatus.COMPLETED, MeetingStatus.FAILED, MeetingStatus.CANCELLED
                    }:
                        try:
                            if not await RecallService().leave_call(stored_meeting.recall_bot_id):
                                meeting_leave_error = "Recall.ai did not confirm that Miles left the meeting."
                        except Exception:
                            logger.exception("Could not ask Recall.ai to leave after bridge disconnect for %s.", bridge_session.meeting_id)
                            meeting_leave_error = "Recall.ai could not confirm that Miles left the meeting."
                    stored_meeting.debrief_report = report
                    stored_meeting.ended_at = stored_meeting.ended_at or time.time()
                    stored_meeting.duration_seconds = max(
                        0.0,
                        stored_meeting.ended_at - (stored_meeting.started_at or stored_meeting.created_at),
                    )
                    if stored_meeting.status != MeetingStatus.FAILED:
                        if meeting_leave_error:
                            stored_meeting.error_message = meeting_leave_error
                        else:
                            stored_meeting.status = MeetingStatus.COMPLETED
                            stored_meeting.error_message = None
                    await asyncio.to_thread(get_meeting_scheduler().store.save_session, stored_meeting)
                report_persisted = True
            except Exception:
                logger.exception("Could not finalize meeting debrief for %s.", bridge_session.meeting_id)
        await engine.llm_client.close()
        if bridge_session or report_persisted or not getattr(engine, "_cached_report", None):
            if SESSIONS.get(engine.session_id) is engine:
                SESSIONS.pop(engine.session_id, None)
                SESSION_OWNERS.pop(engine.session_id, None)
