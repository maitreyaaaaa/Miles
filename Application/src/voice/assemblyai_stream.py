from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

import httpx
import websockets

from src.analytics.composure_scorer import FILLER_WORDS

logger = logging.getLogger(__name__)

ASSEMBLYAI_TOKEN_URL = "https://streaming.assemblyai.com/v3/token?expires_in_seconds=480"
ASSEMBLYAI_WS_BASE = "wss://streaming.assemblyai.com/v3/ws"


SCENARIO_VOCABULARY: Dict[str, List[str]] = {
    "vc_pitch": ["CAC", "LTV", "churn rate", "payback window", "EBITDA", "TAM", "SAM", "burn multiple", "runway", "seed round"],
    "salary_negotiation": ["base salary", "equity grant", "RSUs", "vesting schedule", "cliff", "strike price", "409A valuation", "signing bonus"],
    "hostile_cross_exam": ["subpoena", "affidavit", "admissibility", "perjury", "chain of custody", "exculpatory", "deposition", "preponderance"],
    "senior_interview": ["systems design", "distributed systems", "CAP theorem", "eventual consistency", "sharding", "microservices"],
    "sales_objections": ["procurement", "annual contract value", "SLA", "SOC2 compliance", "seat licensing", "implementation timeline"],
    "media_crisis": ["data breach", "negligence", "containment", "exfiltration", "forensics", "disclosure"],
    "hostile_boardroom": ["margin collapse", "activist investor", "capital allocation", "dividend", "governance", "fiduciary duty"],
    "custom_debate": ["first principles", "second-order effects", "counterparty risk", "empirical evidence", "fallacy"],
}


def detect_micro_hesitations(words: List[Dict[str, Any]], threshold_ms: int = 750) -> List[Dict[str, Any]]:
    """Detect micro-hesitation gaps (>750ms silence between consecutive words within single utterance)."""
    hesitations = []
    if not words or len(words) < 2:
        return hesitations

    for i in range(len(words) - 1):
        w1 = words[i]
        w2 = words[i + 1]
        w1_end = w1.get("end", 0)
        w2_start = w2.get("start", 0)
        gap = w2_start - w1_end
        if gap > threshold_ms:
            hesitations.append({
                "gap_ms": gap,
                "word_before": w1.get("word", ""),
                "word_after": w2.get("word", ""),
                "timestamp_ms": w1_end,
                "context": f"{w1.get('word', '')} [{gap}ms] {w2.get('word', '')}",
                "severity": "high" if gap > 1200 else "medium",
            })
    return hesitations


@dataclass
class AssemblyAITurnEvent:
    text: str
    is_final: bool
    confidence: float = 1.0
    words: List[Dict[str, Any]] = field(default_factory=list)


class AssemblyAIStreamingClient:
    """Real-time Universal-Streaming v3 client for AssemblyAI.
    
    Provides partial and final transcripts plus speech-onset events when connected;
    end-to-end latency depends on the browser, network, and provider response,
    word-level timestamps, micro-hesitations, vocabulary boosting, and composure intelligence.
    """

    def __init__(
        self,
        api_key: str,
        sample_rate: int = 16000,
        word_boost: Optional[List[str]] = None,
        on_partial: Optional[Callable[[str, float], None]] = None,
        on_final: Optional[Callable[[str, float], None]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,
        on_filler_detected: Optional[Callable[[str], None]] = None,
        on_words: Optional[Callable[[List[Dict[str, Any]], List[Dict[str, Any]]], None]] = None,
        on_disconnected: Optional[Callable[[], None]] = None,
    ):
        self.api_key = api_key
        self.sample_rate = sample_rate
        self.word_boost = word_boost or []
        self.on_partial = on_partial
        self.on_final = on_final
        self.on_speech_start = on_speech_start
        self.on_filler_detected = on_filler_detected
        self.on_words = on_words
        self.on_disconnected = on_disconnected

        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._stopping = False
        self._is_connected = False
        self._send_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
        self._send_task: Optional[asyncio.Task] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._speech_active = False
        self._begin_event = asyncio.Event()
        self._final_event = asyncio.Event()
        self._audio_since_final = False
        self.pending_transcript = ""
        self._last_final_turn_order = None

    async def fetch_token(self) -> str:
        """Fetch short-lived streaming token from AssemblyAI v3."""
        if not self.api_key:
            raise ValueError("AssemblyAI API key is missing.")

        headers = {"authorization": self.api_key}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(ASSEMBLYAI_TOKEN_URL, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            token = data.get("token")
            if not token:
                raise RuntimeError(f"No streaming token returned by AssemblyAI: {data}")
            return token

    async def connect(self) -> bool:
        """Establish WebSocket connection to AssemblyAI Universal-Streaming v3."""
        if not self.api_key:
            logger.warning("No AssemblyAI API key configured. STT will operate in fallback mode.")
            return False

        try:
            token = await self.fetch_token()
            ws_url = (
                f"{ASSEMBLYAI_WS_BASE}"
                f"?token={token}"
                f"&sample_rate={self.sample_rate}"
                f"&encoding=pcm_s16le"
                f"&speech_model=universal-3-5-pro"
            )
            if self.word_boost:
                import urllib.parse
                boost_param = urllib.parse.quote(json.dumps(self.word_boost))
                ws_url += f"&keyterms_prompt={boost_param}"

            logger.info("Connecting to AssemblyAI Universal-Streaming v3...")
            self._ws = await websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=20,
                max_size=10 * 1024 * 1024,
            )
            self._is_connected = True
            self._stopping = False
            self._send_task = asyncio.create_task(self._send_loop())
            self._recv_task = asyncio.create_task(self._recv_loop())
            await asyncio.wait_for(self._begin_event.wait(), timeout=10)
            if not self._is_connected:
                await self.stop()
                return False
            logger.info("Successfully connected to AssemblyAI Universal-Streaming v3.")
            return True
        except Exception:
            logger.error("Failed to connect to AssemblyAI.")
            self._is_connected = False
            await self.stop()
            return False

    async def send_audio_chunk(self, chunk: bytes):
        """Enqueue PCM audio chunk from browser mic for transmission to AssemblyAI."""
        if self._is_connected and not self._stopping:
            self._audio_since_final = True
            try:
                self._send_queue.put_nowait(chunk)
            except asyncio.QueueFull:
                # Drop oldest frame to avoid latency lag in live voice pipeline
                try:
                    self._send_queue.get_nowait()
                    self._send_queue.task_done()
                except asyncio.QueueEmpty:
                    pass
                self._send_queue.put_nowait(chunk)

    async def _send_loop(self):
        """Asynchronously stream PCM chunks to AssemblyAI WebSocket."""
        try:
            while not self._stopping and self._ws is not None:
                chunk = await self._send_queue.get()
                try:
                    if self._ws is not None:
                        await self._ws.send(chunk)
                finally:
                    self._send_queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self._stopping:
                logger.error(f"Error in AssemblyAI send loop: {e}")

    async def _recv_loop(self):
        """Listen for real-time speech events and transcripts from AssemblyAI."""
        try:
            while not self._stopping and self._ws is not None:
                try:
                    msg_raw = await self._ws.recv()
                except (websockets.ConnectionClosed, asyncio.CancelledError):
                    break
                except Exception as e:
                    if not self._stopping:
                        logger.warning(f"AssemblyAI recv socket error: {e}")
                    break

                try:
                    msg = json.loads(msg_raw)
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = (msg.get("type") or msg.get("message_type") or "").lower()

                if msg_type == "begin":
                    self._begin_event.set()
                elif msg_type == "turn":
                    transcript = msg.get("transcript", "").strip()
                    is_final = bool(msg.get("end_of_turn"))
                    turn_order = msg.get("turn_order")
                    if is_final and turn_order is not None and turn_order == self._last_final_turn_order:
                        continue
                    if is_final:
                        self._last_final_turn_order = turn_order
                    confidence = float(msg.get("confidence", 0.95))
                    self.pending_transcript = "" if is_final else transcript
                    if is_final:
                        self._audio_since_final = False
                    words = msg.get("words", [])

                    hesitations = detect_micro_hesitations(words, threshold_ms=750)
                    if self.on_words and (words or hesitations):
                        self.on_words(words, hesitations)

                    if transcript:
                        # User started speaking -> Trigger immediate barge-in callback!
                        if not self._speech_active:
                            self._speech_active = True
                            if self.on_speech_start:
                                self.on_speech_start()

                        # Check for disfluency/fillers in live stream if callback active
                        if self.on_filler_detected:
                            for filler in FILLER_WORDS:
                                if filler in transcript.lower():
                                    self.on_filler_detected(filler)

                        if is_final:
                            self._speech_active = False
                            if self.on_final:
                                self.on_final(transcript, confidence)
                        else:
                            if self.on_partial:
                                self.on_partial(transcript, confidence)
                    if is_final:
                        self._final_event.set()

                elif msg_type == "error":
                    logger.error("AssemblyAI reported a streaming error.")
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self._stopping:
                logger.warning(f"Error in AssemblyAI recv loop: {e}")
        finally:
            self._speech_active = False
            self._is_connected = False
            self._begin_event.set()
            if self.on_disconnected and not self._stopping:
                try:
                    self.on_disconnected()
                except Exception as exc:
                    logger.debug(f"Error in on_disconnected callback: {exc}")

    async def flush_final_turn(self, timeout: float = 5.0) -> bool:
        """Drain captured audio and finish the last turn before report evaluation."""
        if not self._is_connected or self._ws is None:
            return not bool(self.pending_transcript)
        if not self._audio_since_final and not self.pending_transcript:
            return True
        try:
            await asyncio.wait_for(self._send_queue.join(), timeout=timeout)
            if not self._audio_since_final and not self.pending_transcript:
                return True
            self._final_event.clear()
            await asyncio.wait_for(self._ws.send(json.dumps({"type": "ForceEndpoint"})), timeout=timeout)
            await asyncio.wait_for(self._final_event.wait(), timeout=timeout)
            return True
        except Exception:
            logger.warning("Final transcription could not be confirmed before session end.")
            return False

    async def stop(self):
        """Terminate streaming session cleanly."""
        if self._stopping:
            return
        self._stopping = True
        self._is_connected = False

        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "Terminate"}))
                await asyncio.sleep(0.1)
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

        tasks_to_cancel = [task for task in (self._send_task, self._recv_task) if task and not task.done()]
        for task in tasks_to_cancel:
            task.cancel()
        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
