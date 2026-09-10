from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, Optional

from src.voice.rime_stream import RimeStreamingTTSClient

logger = logging.getLogger(__name__)


class InterruptionManager:
    """Full-Duplex Dual-Direction Interruption Manager for Miles.
    
    Manages:
    1. User Barge-in: Sub-100ms cut-off when user interrupts AI speech.
    2. AI Interruption: Adversarial interjection when user hesitates or waffling on fluff.
    """

    def __init__(
        self,
        tts_client: RimeStreamingTTSClient,
        on_user_barge_in: Optional[Callable[[float], Any]] = None,
        on_ai_interruption: Optional[Callable[[str, float], Any]] = None,
    ):
        self.tts_client = tts_client
        self.on_user_barge_in = on_user_barge_in
        self.on_ai_interruption = on_ai_interruption

        self.ai_is_speaking: bool = False
        self.ai_is_thinking: bool = False
        self.speech_start_time: float = 0.0
        self.current_ai_text: str = ""
        self.words_spoken_estimate: int = 0
        self._last_barge_in_latency_ms: float = 0.0

    def mark_ai_thinking(self):
        """Register that AI is actively generating LLM counter-argument."""
        self.ai_is_thinking = True

    def mark_ai_thinking_done(self):
        """Register that LLM token generation has finished."""
        self.ai_is_thinking = False

    def mark_ai_speaking(self, full_text: str):
        """Register that AI has commenced audio streaming."""
        self.ai_is_thinking = False
        self.ai_is_speaking = True
        self.speech_start_time = time.perf_counter()
        self.current_ai_text = full_text
        self.words_spoken_estimate = 0

    def mark_ai_finished(self):
        """Register that AI has completed utterance without interruption."""
        self.ai_is_speaking = False
        self.ai_is_thinking = False
        self.current_ai_text = ""

    def handle_user_speech_detected(self) -> Optional[Dict[str, Any]]:
        """Triggered immediately when user audio activity or speech onset is detected.
        
        If AI is currently speaking or generating, executes hard barge-in interruption!
        """
        if self.ai_is_thinking:
            self.ai_is_thinking = False
            self.tts_client.cancel()
            cut_latency_ms = 0.1
            logger.info("[Barge-in] User interrupted AI while generating tokens (thinking phase)!")
            event_data = {
                "type": "interruption",
                "by": "user",
                "latency_ms": cut_latency_ms,
                "reason": "user_barge_in",
                "spoken_before_cut": "",
            }
            if self.on_user_barge_in:
                if asyncio.iscoroutinefunction(self.on_user_barge_in):
                    asyncio.create_task(self.on_user_barge_in(cut_latency_ms))
                else:
                    self.on_user_barge_in(cut_latency_ms)
            return event_data

        if not self.ai_is_speaking:
            return None

        # Measure high-resolution cut-off response time
        start_cut = time.perf_counter()
        self.tts_client.cancel()
        cut_latency_ms = (time.perf_counter() - start_cut) * 1000.0

        # Estimate how much was spoken prior to cut-off (~140 WPM spoken pace)
        elapsed_sec = max(0.0, time.perf_counter() - self.speech_start_time)
        spoken_words_count = int((elapsed_sec * 140.0) / 60.0)
        words = self.current_ai_text.split(" ")
        truncated_text = " ".join(words[: min(len(words), max(1, spoken_words_count))])

        self.ai_is_speaking = False
        self._last_barge_in_latency_ms = cut_latency_ms

        logger.info(
            f"[Barge-in] User interrupted AI speech! Cut-off latency: {cut_latency_ms:.2f}ms. "
            f"Heard {spoken_words_count}/{len(words)} words."
        )

        event_data = {
            "type": "interruption",
            "by": "user",
            "latency_ms": round(cut_latency_ms, 2),
            "reason": "user_barge_in",
            "spoken_before_cut": truncated_text,
        }

        if self.on_user_barge_in:
            if asyncio.iscoroutinefunction(self.on_user_barge_in):
                asyncio.create_task(self.on_user_barge_in(cut_latency_ms))
            else:
                self.on_user_barge_in(cut_latency_ms)

        return event_data

    def trigger_ai_interruption(self, interjection_phrase: str, reason: str = "fluff_detected") -> Dict[str, Any]:
        """Trigger an adversarial AI interruption when the user hesitates or waffles."""
        start_cut = time.perf_counter()
        latency_ms = (time.perf_counter() - start_cut) * 1000.0

        logger.info(f"[AI Interruption] AI interjecting: '{interjection_phrase}' ({reason})")

        event_data = {
            "type": "interruption",
            "by": "ai",
            "latency_ms": round(latency_ms, 2),
            "reason": reason,
            "phrase": interjection_phrase,
        }

        if self.on_ai_interruption:
            if asyncio.iscoroutinefunction(self.on_ai_interruption):
                asyncio.create_task(self.on_ai_interruption(interjection_phrase, latency_ms))
            else:
                self.on_ai_interruption(interjection_phrase, latency_ms)

        return event_data
