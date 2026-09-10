from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import struct
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.analytics.composure_scorer import ComposureScorer
from src.config import config
from src.debate.engine import DebateEngine
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

# Enable CORS for browser frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory registry of debate sessions
SESSIONS: Dict[str, DebateEngine] = {}


class CustomTopicRequest(BaseModel):
    topic: str
    difficulty: Optional[str] = "hard"
    persona_tone: Optional[str] = "calm_ruthless"


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


@app.get("/api/session/{session_id}/report")
async def get_session_report(session_id: str):
    """Retrieve the post-debate debrief report for a completed session."""
    engine = SESSIONS.get(session_id)
    if not engine:
        raise HTTPException(status_code=404, detail="Debate session not found.")
    return engine.get_debrief_report()


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
):
    """Full-Duplex live audio & telemetry stream for Miles."""
    await websocket.accept()

    # 1. Initialize Debate Engine & Services
    engine = DebateEngine(
        scenario_id=scenario,
        topic=topic,
        difficulty=difficulty,
        persona_tone=persona_tone,
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

    async def safe_send_json(payload: Dict):
        if stop_event.is_set():
            return
        try:
            await websocket.send_text(json.dumps(payload))
        except Exception as e:
            logger.debug(f"[WebSocket] safe_send_json suppressed: {e}")

    async def safe_send_bytes(data: bytes):
        if stop_event.is_set():
            return
        try:
            await websocket.send_bytes(data)
        except Exception as e:
            logger.debug(f"[WebSocket] safe_send_bytes suppressed: {e}")

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
                async for chunk in tts_client.stream_audio_chunks(text):
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
                asyncio.create_task(safe_send_json(event))
                asyncio.create_task(safe_send_json({"type": "ai_state", "state": "interrupted"}))

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
        asyncio.create_task(safe_send_json({
            "type": "transcript",
            "role": "user",
            "text": transcript,
            "is_final": False,
            "confidence": confidence,
        }))

        # Check for adversarial fluff interjection (only if not already speaking)
        interjection = engine.check_fluff_interruption(transcript, mid_hesitation)
        if interjection and not interruption_mgr.ai_is_speaking and not interruption_mgr.ai_is_thinking and not interruption_mgr.ai_interruption_active:
            engine.record_ai_cut_in("fluff_detected", interjection)
            cut_event = interruption_mgr.trigger_ai_interruption(interjection, reason="fluff_detected")
            asyncio.create_task(safe_send_json(cut_event))
            asyncio.create_task(safe_send_json({
                "type": "transcript",
                "role": "ai",
                "speaker": engine.persona.name,
                "text": interjection,
                "is_final": True,
                "confidence": 1.0,
            }))
            asyncio.create_task(stream_ai_audio(interjection, is_adversarial_interruption=True))

    def on_stt_final(transcript: str, confidence: float):
        """Finalized user statement."""
        if interruption_mgr.ai_interruption_active:
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
        asyncio.create_task(safe_send_json({
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
        asyncio.create_task(safe_send_json(snapshot.to_dict()))

        # Update talk-time & speech intelligence
        nonlocal user_talk_time_sec, turn_round
        turn_round += 1
        user_talk_time_sec += duration
        asyncio.create_task(emit_speech_intelligence())

        # Reset turn markers
        current_turn_was_barge_in = False
        user_speech_start_time = 0.0

        # Cancel any previous AI task and trigger new counter-attack
        if active_ai_turn_task and not active_ai_turn_task.done():
            active_ai_turn_task.cancel()
        active_ai_turn_task = asyncio.create_task(execute_ai_turn(trigger_time=now))

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
            asyncio.create_task(emit_speech_intelligence())

    async def execute_ai_turn(trigger_time: Optional[float] = None):
        """Pipelined adversarial generation: stream clauses into TTS immediately for sub-second TTFA."""
        nonlocal turn_start_time, ai_speech_end_time
        calc_trigger = trigger_time or time.time()
        interruption_mgr.mark_ai_thinking()
        await safe_send_json({"type": "ai_state", "state": "thinking"})

        accumulated_clauses: List[str] = []
        first_clause = True

        try:
            async for clause in engine.generate_adversary_clauses():
                if stop_event.is_set():
                    return

                accumulated_clauses.append(clause)
                current_full_text = " ".join(accumulated_clauses)

                # Send streaming subtitle text to UI immediately
                await safe_send_json({
                    "type": "transcript",
                    "role": "ai",
                    "speaker": engine.persona.name,
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
                    "speaker": engine.persona.name,
                    "text": final_text,
                    "is_final": True,
                    "confidence": 1.0,
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
                    await stream_ai_audio(rambling_cut, is_adversarial_interruption=True)
                    user_speech_start_time = 0.0
                    continue

                # 2. Mid-speech freeze (>2.0s silence mid-answer)
                if mid_speech_pause >= 2.0:
                    hesitation_cut = engine.check_hesitation_interruption(mid_speech_pause)
                    if hesitation_cut:
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
                        await stream_ai_audio(hesitation_cut, is_adversarial_interruption=True)
                        user_speech_start_time = 0.0
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

    asyncio.create_task(connect_stt_background())

    # 3. Deliver opening salvo immediately
    opening_start = time.time()
    opening = engine.start_debate()
    await safe_send_json({
        "type": "transcript",
        "role": "ai",
        "speaker": engine.persona.name,
        "text": opening,
        "is_final": True,
        "confidence": 1.0,
    })
    init_snapshot = engine.scorer.evaluate_turn("", duration_seconds=1.0)
    await safe_send_json(init_snapshot.to_dict())
    asyncio.create_task(emit_speech_intelligence())
    asyncio.create_task(emit_turn_telemetry(opening_start))

    # Stream opening audio and launch active presence monitor
    asyncio.create_task(stream_ai_audio(opening))
    monitor_task = asyncio.create_task(monitor_user_presence_loop())

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

    except WebSocketDisconnect:
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
        if active_ai_turn_task and not active_ai_turn_task.done():
            active_ai_turn_task.cancel()
        if stt_client:
            await stt_client.stop()
        tts_client.cancel()
        await tts_client.close()
