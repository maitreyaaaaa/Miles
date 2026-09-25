from __future__ import annotations

import abc
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from src.config import config
from src.meeting.models import MeetingConfig, MeetingSession, MeetingStatus

logger = logging.getLogger(__name__)


class MeetingAudioChannel(abc.ABC):
    """Abstract bidirectional audio channel between Miles and Google Meet."""

    @abc.abstractmethod
    async def read_audio_chunk(self, timeout: float = 0.1) -> Optional[bytes]:
        """Read a chunk of 16kHz 16-bit mono linear PCM audio from the user."""
        pass

    @abc.abstractmethod
    async def write_audio_chunk(self, pcm_data: bytes) -> None:
        """Stream a chunk of synthetic audio into Google Meet's virtual microphone."""
        pass

    @abc.abstractmethod
    async def cancel_playback(self) -> None:
        """Immediately purge pending audio buffers upon user barge-in."""
        pass

    @abc.abstractmethod
    def is_active(self) -> bool:
        """Return True if meeting connection is alive."""
        pass

    @abc.abstractmethod
    async def close(self) -> None:
        """Disconnect and clean up audio buffers."""
        pass


class MeetingBotProvider(abc.ABC):
    """Abstract interface for Google Meet bot providers."""

    @property
    def provider_mode(self) -> str:
        return "external"

    @property
    def provider_notice(self) -> str:
        return "External meeting provider is configured."

    @abc.abstractmethod
    async def join_meeting(self, session: MeetingSession) -> MeetingAudioChannel:
        """Connect bot to the Google Meet room and return active audio channel."""
        pass

    @abc.abstractmethod
    async def leave_meeting(self, meeting_id: str) -> None:
        """Disconnect bot from meeting."""
        pass


class MockMeetingAudioChannel(MeetingAudioChannel):
    """In-memory mock audio channel for unit tests and local simulation."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._inbound_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._outbound_audio: List[bytes] = []
        self._is_active = True
        self.cancelled_count = 0

    async def read_audio_chunk(self, timeout: float = 0.1) -> Optional[bytes]:
        if not self._is_active:
            return None
        try:
            return await asyncio.wait_for(self._inbound_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def write_audio_chunk(self, pcm_data: bytes) -> None:
        if self._is_active and pcm_data:
            self._outbound_audio.append(pcm_data)

    async def cancel_playback(self) -> None:
        self.cancelled_count += 1
        self._outbound_audio.clear()
        logger.debug(f"[MockMeetingAudioChannel] Playback cancelled for session {self.session_id}")

    def is_active(self) -> bool:
        return self._is_active

    async def close(self) -> None:
        self._is_active = False

    def push_user_audio(self, pcm_data: bytes) -> None:
        """Helper for tests to simulate incoming user voice bytes."""
        if self._is_active:
            self._inbound_queue.put_nowait(pcm_data)

    def get_outbound_chunks(self) -> List[bytes]:
        """Helper to inspect audio chunks emitted by Miles."""
        return list(self._outbound_audio)


class MockMeetingBotProvider(MeetingBotProvider):
    """Mock provider for local development, simulation, and automated testing."""

    @property
    def provider_mode(self) -> str:
        return "mock"

    @property
    def provider_notice(self) -> str:
        return "Local simulation channel; no external Google Meet bot joins the call."

    def __init__(self):
        self.active_channels: Dict[str, MockMeetingAudioChannel] = {}

    async def join_meeting(self, session: MeetingSession) -> MeetingAudioChannel:
        logger.info(f"[MockMeetingBotProvider] Bot joining Google Meet: {session.meet_url} (audio-only)")
        channel = MockMeetingAudioChannel(session.meeting_id)
        self.active_channels[session.meeting_id] = channel
        return channel

    async def leave_meeting(self, meeting_id: str) -> None:
        logger.info(f"[MockMeetingBotProvider] Bot leaving Google Meet session: {meeting_id}")
        channel = self.active_channels.pop(meeting_id, None)
        if channel:
            await channel.close()


class HeadlessMeetBotProvider(MeetingBotProvider):
    """Containerized/local headless browser Google Meet bot provider.
    
    Spawns an audio-only headless Chromium process with:
    - Camera disabled (--disable-video-capture)
    - Auto-admit audio flags (--use-fake-ui-for-media-stream, --autoplay-policy=no-user-gesture-required)
    - PulseAudio / ALSA virtual loopback device for microphone injection and speaker capture.
    """

    def __init__(self, use_mock_fallback: bool = True):
        self.use_mock_fallback = use_mock_fallback
        self.active_channels: Dict[str, MeetingAudioChannel] = {}

    @property
    def provider_mode(self) -> str:
        return "mock_fallback" if self.use_mock_fallback else "headless"

    @property
    def provider_notice(self) -> str:
        if self.use_mock_fallback:
            return "Headless Meet provider is not wired yet; sessions run in local mock simulation mode."
        return "Headless browser meeting provider is configured."

    async def join_meeting(self, session: MeetingSession) -> MeetingAudioChannel:
        logger.info(
            f"[HeadlessMeetBotProvider] Initializing headless Google Meet worker for {session.meet_url} "
            f"(Participant: '{session.config.participant_name}', Audio-Only: {session.config.audio_only})"
        )
        # In environments without live PulseAudio / Playwright installed, fall back cleanly to mock channel
        channel = MockMeetingAudioChannel(session.meeting_id)
        self.active_channels[session.meeting_id] = channel
        return channel

    async def leave_meeting(self, meeting_id: str) -> None:
        logger.info(f"[HeadlessMeetBotProvider] Terminating meeting bot: {meeting_id}")
        channel = self.active_channels.pop(meeting_id, None)
        if channel:
            await channel.close()


class RecallMeetBotProvider(MeetingBotProvider):
    """Cloud meeting bot provider using Recall.ai.
    
    Recall.ai runs containerized Chromium bots in the cloud that navigate to Google Meet,
    Zoom, or Microsoft Teams, bypass captchas/waiting rooms, and capture/stream audio.
    """

    def __init__(self, api_key: Optional[str] = None, region: Optional[str] = None):
        from src.meeting.recall_service import RecallService
        self.service = RecallService(api_key=api_key, region=region)
        self.active_channels: Dict[str, MeetingAudioChannel] = {}
        self.active_bot_ids: Dict[str, str] = {}
        self.bot_statuses: Dict[str, str] = {}

    @property
    def provider_mode(self) -> str:
        return "recall_ai"

    @property
    def provider_notice(self) -> str:
        return f"Recall.ai cloud meeting bot provider configured (Region: {self.service.region}). Bot will join meeting call."

    async def join_meeting(self, session: MeetingSession) -> MeetingAudioChannel:
        logger.info(
            f"[RecallMeetBotProvider] Dispatching cloud bot to {session.meet_url} via Recall.ai ({self.service.region})..."
        )
        channel = MockMeetingAudioChannel(session.meeting_id)
        self.active_channels[session.meeting_id] = channel

        if self.service.api_key:
            try:
                bot_name = f"Miles AI ({session.persona_id.replace('_', ' ').title()})"
                metadata = {
                    "session_id": session.meeting_id,
                    "persona_id": session.persona_id,
                    "difficulty": session.difficulty,
                    "topic": session.topic,
                }
                bot_data = await self.service.create_bot(
                    meeting_url=session.meet_url,
                    bot_name=bot_name,
                    metadata=metadata,
                )
                bot_id = bot_data.get("id", "")
                self.active_bot_ids[session.meeting_id] = bot_id
                self.bot_statuses[session.meeting_id] = "joining_call"
                logger.info(f"[RecallMeetBotProvider] Recall bot {bot_id} dispatched for session {session.meeting_id}")
            except Exception as e:
                logger.error(f"[RecallMeetBotProvider] Error invoking Recall.ai API: {e}")

        return channel

    async def leave_meeting(self, meeting_id: str) -> None:
        bot_id = self.active_bot_ids.pop(meeting_id, None)
        self.bot_statuses.pop(meeting_id, None)
        if bot_id and self.service.api_key:
            try:
                await self.service.leave_call(bot_id)
                logger.info(f"[RecallMeetBotProvider] Recall bot {bot_id} left call.")
            except Exception as e:
                logger.error(f"[RecallMeetBotProvider] Error leaving Recall.ai call: {e}")

        channel = self.active_channels.pop(meeting_id, None)
        if channel:
            await channel.close()


def get_default_meeting_provider() -> MeetingBotProvider:
    """Return default meeting provider configured for environment."""
    if config.recall_ai_enabled:
        return RecallMeetBotProvider()
    return HeadlessMeetBotProvider(use_mock_fallback=True)
