from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import math
import struct
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, Response, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.meeting.models import MeetingConfig, MeetingSession, MeetingStatus
from src.meeting.scheduler import get_meeting_scheduler, generate_meet_code
from src.meeting.debrief_dispatcher import get_debrief_dispatcher

from src.analytics.composure_scorer import ComposureScorer
from src.config import config
from src.context.analyzer import analyze_context_document
from src.context.extractor import extract_text_from_bytes
from src.context.store import get_context_store
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

app = FastAPI(
    title="Miles Backend",
    description="Full-Duplex Adversarial Verbal Sparring & Speech Cadence Engine",
    version="0.1.0",
)

ALLOWED_ORIGIN_REGEX = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]


def is_allowed_origin(origin: str) -> bool:
    if not origin:
        return True
    norm = origin.rstrip("/")
    if any(norm == o.rstrip("/") for o in ALLOWED_ORIGINS):
        return True
    import re
    return bool(re.match(ALLOWED_ORIGIN_REGEX, norm))


# Enable CORS for browser frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


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
    max_duration_seconds: Optional[int] = 1800


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


@app.get("/api/health")
async def health_check():
    """System health check & active provider status."""
    return {
        "status": "healthy",
        "service": "Miles Voice Engine",
        "active_providers": {
            "stt": config.active_stt_provider,
            "tts": config.active_tts_provider,
            "llm": config.active_llm_provider,
        },
        "config": {
            "sample_rate": config.sample_rate,
            "tts_sample_rate": config.tts_sample_rate,
            "rime_speaker": config.rime_speaker,
            "barge_in_threshold_ms": config.barge_in_threshold_ms,
        },
        "active_sessions_count": len(SESSIONS),
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
    original_score: Optional[int] = 55
    wpm: Optional[float] = None
    fillers: Optional[List[str]] = None


@app.post("/api/debate/rematch/evaluate")
async def evaluate_rematch_endpoint(req: RematchEvaluateRequest):
    """Evaluate a 30-second rapid-fire retry against an adversarial trap.
    
    Returns new score, composure delta (+points), filler reductions, and adversary concession.
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
            original_score=req.original_score or 55,
            wpm=req.wpm,
            fillers=req.fillers,
        )
        return result
    except Exception as e:
        logger.error(f"[Rematch] Error evaluating turn: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rematch evaluation failed: {e}")


class ShareDebriefRequest(BaseModel):
    report: Dict[str, Any]
    share_id: Optional[str] = None


@app.post("/api/debrief/share")
async def share_debrief_endpoint(req: ShareDebriefRequest):
    """Persist a debrief report and return a permanent read-only shareable ID and URL."""
    try:
        store = get_debrief_store()
        share_id = store.save_debrief(req.report, custom_share_id=req.share_id)
        return {
            "share_id": share_id,
            "share_url": f"/?share={share_id}",
            "share_scope": "unguessable_read_only_link",
            "privacy_notice": "Anyone with this local share URL can view the debrief report.",
            "title": req.report.get("topic", "Adversarial Debrief"),
        }
    except Exception as e:
        logger.error(f"[Debrief Share] Error saving debrief: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/debrief/share/{share_id}")
async def get_shared_debrief_endpoint(share_id: str):
    """Retrieve saved read-only debrief report by its share token."""
    store = get_debrief_store()
    report = store.get_debrief(share_id)
    if not report:
        raise HTTPException(status_code=404, detail="Debrief report not found or expired.")
    return JSONResponse(content=report, headers={"Cache-Control": "no-store"})


@app.get("/api/debrief/{session_id}/pdf")
async def export_debrief_pdf_endpoint(session_id: str):
    """Generate and stream a pixel-perfect ReportLab Executive Summary PDF."""
    report = None
    if session_id in SESSIONS:
        engine = SESSIONS[session_id]
        report = getattr(engine, "_cached_report", None) or engine.get_debrief_report()
    if not report:
        store = get_debrief_store()
        report = store.get_debrief(session_id)
    if not report:
        dispatcher = get_debrief_dispatcher()
        report = dispatcher.get_saved_debrief(session_id)
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
async def upload_context_document(file: UploadFile = File(...)):
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
    store.save_context(dossier)
    return dossier.to_dict()


class PasteContextRequest(BaseModel):
    text: str
    filename: Optional[str] = "Pasted Context.txt"


@app.post("/api/context/paste")
async def paste_context_text(req: PasteContextRequest):
    """Ingest raw pasted text/resume/pitch deck notes and generate structured forensic Context Dossier."""
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty.")

    filename = req.filename or "Pasted Context.txt"
    store = get_context_store()
    dossier = await analyze_context_document(text, filename)
    store.save_context(dossier)
    return dossier.to_dict()


@app.get("/api/context/{context_id}")
async def get_context_by_id(context_id: str):
    """Retrieve an existing context dossier by ID."""
    store = get_context_store()
    dossier = store.get_context(context_id)
    if not dossier:
        raise HTTPException(status_code=404, detail="Context not found.")
    return dossier.to_dict()


@app.get("/api/contexts")
async def list_available_contexts():
    """List all previously ingested context dossiers."""
    store = get_context_store()
    return {"contexts": store.list_contexts()}


@app.get("/api/session/{session_id}/report")
async def get_session_report(session_id: str):
    """Retrieve the post-debate debrief report for a completed session."""
    engine = SESSIONS.get(session_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Debate session not found.")
    return engine.get_debrief_report()


# ==========================================
# Google Meet Sparring Endpoints
# ==========================================


@app.post("/api/meeting/schedule")
async def schedule_google_meet(req: ScheduleMeetingRequest):
    """Schedule a Google Meet sparring session for Miles."""
    scheduler = get_meeting_scheduler()
    cfg = MeetingConfig(
        max_duration_seconds=req.max_duration_seconds or 1800,
        audio_only=True,
    )
    session = scheduler.schedule_meeting(
        meet_url=req.meet_url,
        context_id=req.context_id,
        persona_id=req.persona_id or "vc_pitch",
        difficulty=req.difficulty or "hard",
        topic=req.topic,
        persona_tone=req.persona_tone,
        config=cfg,
    )
    return session.to_dict()


@app.post("/api/meeting/{meeting_id}/start")
async def start_google_meet_session(meeting_id: str):
    """Deploy Miles bot into the Google Meet call (audio-only)."""
    scheduler = get_meeting_scheduler()
    try:
        coordinator = await scheduler.start_meeting(meeting_id)
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
async def stop_google_meet_session(meeting_id: str):
    """Conclude Google Meet session, disconnect bot, and generate deep debrief report."""
    scheduler = get_meeting_scheduler()
    try:
        report = await scheduler.stop_meeting(meeting_id)
        session = scheduler.get_session(meeting_id)
        return {
            "status": "completed",
            "meeting_id": meeting_id,
            "debrief_report": report,
            "session": session.to_dict() if session else None,
        }
    except Exception as e:
        logger.error(f"[API] Error stopping meeting {meeting_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/meeting/generate-link")
async def generate_instant_link():
    """Generate a Meet-shaped local demo link.

    This does not provision a real Google Meet room. It exists for local scheduling
    simulations until an external calendar/Meet provider is connected.
    """
    scheduler = get_meeting_scheduler()
    return {
        "meet_url": generate_meet_code(),
        "provisioned": False,
        "provider_mode": scheduler.bot_provider.provider_mode,
        "provider_notice": scheduler.bot_provider.provider_notice,
    }


@app.get("/api/meetings")
async def list_google_meet_sessions():
    """List all scheduled and historical Google Meet sessions."""
    scheduler = get_meeting_scheduler()
    sessions = scheduler.list_sessions()
    return {"meetings": [s.to_dict() for s in sessions]}


@app.get("/api/meeting/{meeting_id}")
async def get_google_meet_session(meeting_id: str):
    """Retrieve Google Meet session details and status."""
    scheduler = get_meeting_scheduler()
    session = scheduler.get_session(meeting_id)
    if not session:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return session.to_dict()


@app.get("/api/meeting/{meeting_id}/debrief")
async def get_google_meet_debrief(meeting_id: str):
    """Retrieve debrief report for a completed Google Meet session."""
    scheduler = get_meeting_scheduler()
    session = scheduler.get_session(meeting_id)
    if not session:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    if session.debrief_report:
        return session.debrief_report

    dispatcher = get_debrief_dispatcher()
    saved = dispatcher.get_saved_debrief(meeting_id)
    if saved:
        return saved
    raise HTTPException(status_code=404, detail="Debate debrief report not available for this meeting yet.")


@app.get("/api/meeting/{meeting_id}/debrief/html")
async def get_google_meet_debrief_html(meeting_id: str):
    """Retrieve HTML formatted debrief email report."""
    scheduler = get_meeting_scheduler()
    session = scheduler.get_session(meeting_id)
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
):
    """Full-Duplex live audio & telemetry stream for Miles."""
    origin = websocket.headers.get("origin")
    if origin and not is_allowed_origin(origin):
        logger.warning(f"[WebSocket] Rejected connection from unauthorized origin: {origin}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    install_stream_shutdown_filter()
    await websocket.accept()

    # Load context dossier if provided
    context_dossier = None
    if context_id:
        store = get_context_store()
        stored = store.get_context(context_id)
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
        persona_tone=persona_tone,
        context_dossier=context_dossier,
        is_panel_mode=is_panel_mode,
    )
    if len(SESSIONS) > 50:
        oldest_key = next(iter(SESSIONS))
        SESSIONS.pop(oldest_key, None)
    SESSIONS[engine.session_id] = engine

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

                        # Inform UI that GPT-4o is deeply analyzing the debate transcript
                        await safe_send_json({
                            "type": "debrief_status",
                            "status": "generating",
                            "message": "Analyzing debate transcript with GPT-4o...",
                        })

                        # Deep evaluation via GPT-4o
                        report = await engine.generate_llm_debrief_report()
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
        await engine.llm_client.close()
