from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import struct
import time
from typing import Any, Callable, List, Optional

from src.config import config
from src.meeting.provider import MeetingAudioChannel
from src.voice.assemblyai_stream import AssemblyAIStreamingClient
from src.voice.interruption_manager import InterruptionManager
from src.voice.rime_stream import RimeStreamingTTSClient

logger = logging.getLogger(__name__)


def calculate_pcm_rms(pcm_bytes: bytes) -> float:
    """Calculate Root Mean Square (RMS) energy of 16-bit linear PCM audio frame."""
    if len(pcm_bytes) < 2:
        return 0.0
    count = len(pcm_bytes) // 2
    shorts = struct.unpack(f"<{count}h", pcm_bytes[: count * 2])
    sum_squares = sum(s * s for s in shorts)
    mean_squares = sum_squares / count
    return math.sqrt(mean_squares)


class MeetingAudioBridge:
    """Bridges bidirectional audio between Google Meet and Miles's voice stack."""

    def __init__(
        self,
        channel: MeetingAudioChannel,
        tts_client: RimeStreamingTTSClient,
        stt_client: Optional[AssemblyAIStreamingClient] = None,
        interruption_manager: Optional[InterruptionManager] = None,
        on_user_speech_start: Optional[Callable[[], None]] = None,
        on_user_speech_final: Optional[Callable[[str, float], None]] = None,
        on_user_barge_in: Optional[Callable[[], None]] = None,
        rms_threshold: float = 550.0,
    ):
        self.channel = channel
        self.tts_client = tts_client
        self.stt_client = stt_client
        self.interruption_mgr = interruption_manager or InterruptionManager(tts_client=self.tts_client)
        self.on_user_speech_start = on_user_speech_start
        self.on_user_speech_final = on_user_speech_final
        self.on_user_barge_in = on_user_barge_in
        self.rms_threshold = rms_threshold

        self._running = False
        self._listen_task: Optional[asyncio.Task] = None
        self._active_tts_task: Optional[asyncio.Task] = None
        self._last_barge_in_time = 0.0

    async def start(self) -> None:
        """Start ingesting audio from the Google Meet channel."""
        self._running = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info("[MeetingAudioBridge] Audio bridge listening loop started.")

    async def stop(self) -> None:
        """Stop audio streaming and cancel pending tasks."""
        self._running = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task
        if self._active_tts_task and not self._active_tts_task.done():
            self._active_tts_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._active_tts_task
        self.tts_client.cancel()
        await self.channel.cancel_playback()
        logger.info("[MeetingAudioBridge] Audio bridge stopped.")

    async def _listen_loop(self) -> None:
        """Continuously read user audio chunks from Google Meet and route to STT/VAD."""
        while self._running and self.channel.is_active():
            try:
                pcm_data = await self.channel.read_audio_chunk(timeout=0.1)
                if not pcm_data:
                    await asyncio.sleep(0.01)
                    continue

                # If adversary has seized floor during an adversarial interjection, drop inbound mic bytes
                if self.interruption_mgr.ai_interruption_active:
                    continue

                # Energy-based VAD for instant sub-100ms barge-in detection
                rms = calculate_pcm_rms(pcm_data)
                if rms > self.rms_threshold:
                    if self.interruption_mgr.ai_is_speaking or self.interruption_mgr.ai_is_thinking:
                        await self.trigger_barge_in()
                    if self.on_user_speech_start:
                        self.on_user_speech_start()

                # Stream audio to AssemblyAI
                if self.stt_client:
                    await self.stt_client.send_audio_chunk(pcm_data)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MeetingAudioBridge] Error in listen loop: {e}", exc_info=True)
                await asyncio.sleep(0.05)

    async def trigger_barge_in(self) -> None:
        """Execute instantaneous conversational cut-off when user interrupts Miles."""
        now = time.time()
        if now - self._last_barge_in_time < 0.3:
            return  # Debounce
        self._last_barge_in_time = now

        logger.info("[MeetingAudioBridge] User barge-in detected in Google Meet! Purging audio buffer.")
        await self.channel.cancel_playback()
        self.tts_client.cancel()
        if self._active_tts_task and not self._active_tts_task.done():
            self._active_tts_task.cancel()

        self.interruption_mgr.mark_ai_finished()
        self.interruption_mgr.trigger_user_barge_in()

        if self.on_user_barge_in:
            self.on_user_barge_in()

    async def stream_ai_speech(self, text: str, is_adversarial_interruption: bool = False) -> None:
        """Stream Rime TTS audio chunks directly into Google Meet virtual microphone."""
        if not text.strip():
            return

        self.interruption_mgr.mark_ai_speaking(text)
        try:
            async for pcm_chunk in self.tts_client.stream_audio_chunks(text):
                if not self._running or (self.interruption_mgr.ai_interruption_active and not is_adversarial_interruption):
                    break
                await self.channel.write_audio_chunk(pcm_chunk)
        except asyncio.CancelledError:
            logger.debug("[MeetingAudioBridge] Speech stream cancelled.")
        finally:
            self.interruption_mgr.mark_ai_finished()
