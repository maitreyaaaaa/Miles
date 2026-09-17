from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from src.config import config
from src.context.store import get_context_store
from src.debate.engine import DebateEngine
from src.meeting.audio_bridge import MeetingAudioBridge
from src.meeting.debrief_dispatcher import get_debrief_dispatcher
from src.meeting.models import MeetingSession, MeetingStatus
from src.meeting.provider import MeetingAudioChannel, MeetingBotProvider, get_default_meeting_provider
from src.voice.assemblyai_stream import AssemblyAIStreamingClient
from src.voice.interruption_manager import InterruptionManager
from src.voice.rime_stream import RimeStreamingTTSClient

logger = logging.getLogger(__name__)


class MeetingEngineCoordinator:
    """Coordinates a live Google Meet sparring session for Miles."""

    def __init__(
        self,
        session: MeetingSession,
        bot_provider: Optional[MeetingBotProvider] = None,
        tts_client: Optional[RimeStreamingTTSClient] = None,
        stt_client: Optional[AssemblyAIStreamingClient] = None,
    ):
        self.session = session
        self.bot_provider = bot_provider or get_default_meeting_provider()
        self.tts_client = tts_client or RimeStreamingTTSClient()
        self.stt_client = stt_client
        if self.stt_client is None and config.assemblyai_api_key:
            self.stt_client = AssemblyAIStreamingClient(
                api_key=config.assemblyai_api_key,
                sample_rate=config.sample_rate,
            )

        # Load attached context dossier if present
        self.context_dossier: Optional[Dict[str, Any]] = None
        if self.session.context_id:
            dossier_obj = get_context_store().get_context(self.session.context_id)
            if dossier_obj:
                self.context_dossier = dossier_obj.to_dict()
                if not self.session.context_filename:
                    self.session.context_filename = dossier_obj.filename

        # Initialize core debate engine with scenario, persona, and context
        self.engine: DebateEngine = DebateEngine(
            scenario_id=self.session.persona_id,
            topic=self.session.topic,
            difficulty=self.session.difficulty,
            session_id=self.session.meeting_id,
            persona_tone=self.session.persona_tone,
            context_dossier=self.context_dossier,
        )

        self.channel: Optional[MeetingAudioChannel] = None
        self.bridge: Optional[MeetingAudioBridge] = None
        self.interruption_mgr = InterruptionManager(tts_client=self.tts_client)

        self.user_speech_start_time: float = 0.0
        self.ai_speech_end_time: float = 0.0
        self.current_turn_was_barge_in: bool = False
        self._active_ai_turn_task: Optional[asyncio.Task] = None
        self._session_timer_task: Optional[asyncio.Task] = None
        self._is_running = False

    async def start(self) -> str:
        """Connect bot to Google Meet, speak opening adversarial challenge, and start listening."""
        logger.info(f"[MeetingEngine] Starting Google Meet session {self.session.meeting_id} ({self.session.meet_url})")
        self.session.status = MeetingStatus.CONNECTING
        self.session.started_at = time.time()
        self._is_running = True

        # Connect to Google Meet (audio-only)
        self.channel = await self.bot_provider.join_meeting(self.session)

        # Wire and connect STT client
        if self.stt_client:
            self.stt_client.on_speech_start = self._on_user_speech_start
            self.stt_client.on_final = self._on_user_speech_final
            if not self.stt_client._is_connected:
                await self.stt_client.connect()

        # Build audio bridge
        self.bridge = MeetingAudioBridge(
            channel=self.channel,
            tts_client=self.tts_client,
            stt_client=self.stt_client,
            interruption_manager=self.interruption_mgr,
            on_user_speech_start=self._on_user_speech_start,
            on_user_speech_final=self._on_user_speech_final,
            on_user_barge_in=self._on_user_barge_in,
        )
        await self.bridge.start()

        self.session.status = MeetingStatus.IN_CALL

        # Deliver opening salvo into Google Meet
        opening_salvo = self.engine.start_debate()
        logger.info(f"[MeetingEngine] Opening salvo delivered: '{opening_salvo[:60]}...'")
        await self.bridge.stream_ai_speech(opening_salvo)
        self.ai_speech_end_time = time.time()

        # Start max duration watchdog
        if self.session.config.max_duration_seconds > 0:
            self._session_timer_task = asyncio.create_task(self._duration_watchdog())

        return opening_salvo

    def _on_user_speech_start(self) -> None:
        if self.user_speech_start_time <= 0:
            self.user_speech_start_time = time.time()

    def _on_user_barge_in(self) -> None:
        self.current_turn_was_barge_in = True
        self.engine.record_barge_in(actual_spoken_words="", latency_ms=65.0)

    def _on_user_speech_final(self, transcript: str, confidence: float) -> None:
        if not self._is_running or not transcript.strip():
            return
        asyncio.create_task(self.handle_user_turn(transcript, confidence))

    async def handle_user_turn(self, transcript: str, confidence: float = 1.0) -> None:
        """Process spoken user statement: evaluate metrics, audit ground truth facts, and counter-attack."""
        if not self._is_running:
            return

        now = time.time()
        start_ref = self.user_speech_start_time if self.user_speech_start_time > 0 else (now - 3.0)
        duration = max(0.5, now - start_ref)

        hesitation = max(0.0, self.user_speech_start_time - self.ai_speech_end_time) if (
            self.user_speech_start_time > 0 and self.ai_speech_end_time > 0
        ) else 0.0

        was_barge_in = self.current_turn_was_barge_in

        # Update engine history and run fact auditor
        snapshot = self.engine.record_user_turn(
            transcript=transcript,
            duration_sec=duration,
            hesitation_sec=hesitation,
            was_barge_in=was_barge_in,
        )
        logger.info(
            f"[MeetingEngine] Turn recorded: '{transcript[:50]}...' | Composure: {snapshot.composure_score:.1f} | "
            f"Barge-in: {was_barge_in}"
        )

        # Reset turn markers
        self.current_turn_was_barge_in = False
        self.user_speech_start_time = 0.0

        # Generate adversary counter-argument / rectification salvo
        if self._active_ai_turn_task and not self._active_ai_turn_task.done():
            self._active_ai_turn_task.cancel()

        self._active_ai_turn_task = asyncio.create_task(self._execute_ai_counter_attack())

    async def _execute_ai_counter_attack(self) -> None:
        """Stream adversarial clauses directly into Google Meet virtual mic."""
        self.interruption_mgr.mark_ai_thinking()
        accumulated_clauses = []
        try:
            async for clause in self.engine.generate_adversary_clauses():
                if not self._is_running:
                    break
                accumulated_clauses.append(clause)
                self.interruption_mgr.mark_ai_thinking_done()
                if self.bridge:
                    await self.bridge.stream_ai_speech(clause)
        except asyncio.CancelledError:
            logger.debug("[MeetingEngine] Counter attack cancelled.")
        finally:
            self.ai_speech_end_time = time.time()
            self.interruption_mgr.mark_ai_finished()

    async def _duration_watchdog(self) -> None:
        """Auto-terminate meeting and generate debrief when time limit expires."""
        try:
            await asyncio.sleep(self.session.config.max_duration_seconds)
            logger.info(f"[MeetingEngine] Max duration reached for meeting {self.session.meeting_id}. Concluding call.")
            await self.stop()
        except asyncio.CancelledError:
            pass

    async def stop(self) -> Dict[str, Any]:
        """Terminate call, leave Google Meet, and compute complete post-meeting debrief."""
        if not self._is_running and self.session.status == MeetingStatus.COMPLETED:
            return self.session.debrief_report or {}

        self._is_running = False
        now = time.time()
        self.session.ended_at = now
        if self.session.started_at:
            self.session.duration_seconds = max(0.0, now - self.session.started_at)

        if self._session_timer_task and not self._session_timer_task.done():
            self._session_timer_task.cancel()
        if self._active_ai_turn_task and not self._active_ai_turn_task.done():
            self._active_ai_turn_task.cancel()

        # Stop audio bridge, STT client, and leave meeting
        if self.bridge:
            await self.bridge.stop()
        if self.stt_client:
            await self.stt_client.stop()
        if self.channel:
            await self.channel.close()
        await self.bot_provider.leave_meeting(self.session.meeting_id)

        # Generate debrief report
        report = await get_debrief_dispatcher().compile_and_save(self.session, self.engine)
        logger.info(f"[MeetingEngine] Meeting {self.session.meeting_id} completed. Debrief generated successfully.")
        return report
