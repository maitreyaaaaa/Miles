from __future__ import annotations

import logging
import random
import string
from typing import Any, Dict, List, Optional

from src.context.store import get_context_store
from src.meeting.meeting_engine import MeetingEngineCoordinator
from src.meeting.models import MeetingConfig, MeetingSession, MeetingStatus
from src.meeting.provider import MeetingBotProvider, get_default_meeting_provider
from src.meeting.store import MeetingStore, get_meeting_store

logger = logging.getLogger(__name__)


def generate_meet_code() -> str:
    """Generate a realistic Google Meet link structure: https://meet.google.com/abc-defg-hij."""
    part1 = "".join(random.choices(string.ascii_lowercase, k=3))
    part2 = "".join(random.choices(string.ascii_lowercase, k=4))
    part3 = "".join(random.choices(string.ascii_lowercase, k=3))
    return f"https://meet.google.com/{part1}-{part2}-{part3}"


class MeetingScheduler:
    """Manages scheduling, starting, monitoring, and concluding Google Meet sparring sessions."""

    def __init__(
        self,
        store: Optional[MeetingStore] = None,
        bot_provider: Optional[MeetingBotProvider] = None,
    ):
        self.store = store or get_meeting_store()
        self.bot_provider = bot_provider or get_default_meeting_provider()
        self._active_coordinators: Dict[str, MeetingEngineCoordinator] = {}

    def schedule_meeting(
        self,
        meet_url: Optional[str] = None,
        context_id: Optional[str] = None,
        persona_id: str = "vc_pitch",
        difficulty: str = "hard",
        topic: Optional[str] = None,
        persona_tone: Optional[str] = None,
        config: Optional[MeetingConfig] = None,
    ) -> MeetingSession:
        """Schedule a new Google Meet sparring session."""
        final_url = (meet_url or "").strip()
        if not final_url:
            final_url = generate_meet_code()
        elif not final_url.startswith("http"):
            final_url = f"https://meet.google.com/{final_url}"

        context_filename = None
        if context_id:
            dossier = get_context_store().get_context(context_id)
            if dossier:
                context_filename = dossier.filename

        session = MeetingSession(
            meet_url=final_url,
            context_id=context_id,
            context_filename=context_filename,
            persona_id=persona_id,
            difficulty=difficulty,
            topic=topic,
            persona_tone=persona_tone,
            status=MeetingStatus.SCHEDULED,
            config=config or MeetingConfig(),
            provider_mode=self.bot_provider.provider_mode,
            provider_notice=self.bot_provider.provider_notice,
        )

        self.store.save_session(session)
        logger.info(f"[MeetingScheduler] Scheduled Google Meet session: {session.meeting_id} ({session.meet_url})")
        return session

    async def start_meeting(self, meeting_id: str) -> MeetingEngineCoordinator:
        """Launch bot into the scheduled Google Meet room."""
        session = self.store.get_session(meeting_id)
        if not session:
            raise ValueError(f"Meeting session {meeting_id} not found.")

        if meeting_id in self._active_coordinators:
            return self._active_coordinators[meeting_id]

        coordinator = MeetingEngineCoordinator(
            session=session,
            bot_provider=self.bot_provider,
        )
        self._active_coordinators[meeting_id] = coordinator

        # Start the coordinator (joins call and delivers opening salvo)
        await coordinator.start()
        self.store.save_session(session)
        return coordinator

    async def stop_meeting(self, meeting_id: str) -> Dict[str, Any]:
        """Conclude active Google Meet call and retrieve the finalized debrief report."""
        coordinator = self._active_coordinators.pop(meeting_id, None)
        if coordinator:
            report = await coordinator.stop()
            self.store.save_session(coordinator.session)
            return report

        session = self.store.get_session(meeting_id)
        if not session:
            raise ValueError(f"Meeting session {meeting_id} not found.")

        if session.debrief_report:
            return session.debrief_report

        raise ValueError(f"Meeting {meeting_id} is not actively running and has no debrief.")

    def get_coordinator(self, meeting_id: str) -> Optional[MeetingEngineCoordinator]:
        return self._active_coordinators.get(meeting_id)

    def get_session(self, meeting_id: str) -> Optional[MeetingSession]:
        return self.store.get_session(meeting_id)

    def list_sessions(self) -> List[MeetingSession]:
        return self.store.list_sessions()


_SCHEDULER_INSTANCE: Optional[MeetingScheduler] = None


def get_meeting_scheduler() -> MeetingScheduler:
    global _SCHEDULER_INSTANCE
    if _SCHEDULER_INSTANCE is None:
        _SCHEDULER_INSTANCE = MeetingScheduler()
    return _SCHEDULER_INSTANCE
