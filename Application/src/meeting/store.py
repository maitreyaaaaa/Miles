from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from src.meeting.models import MeetingSession

logger = logging.getLogger(__name__)

MEETINGS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "meetings"
SESSIONS_FILE = MEETINGS_DIR / "sessions.json"


import re
import threading

SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_safe_identifier(identifier: str) -> bool:
    return bool(identifier and SAFE_ID_REGEX.match(identifier))


class MeetingStore:
    """Thread-safe persistent store for Google Meet sparring sessions."""

    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or SESSIONS_FILE
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._cache: Dict[str, MeetingSession] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self.data_file.exists():
            return
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                for item in raw_data:
                    session = MeetingSession.from_dict(item)
                    self._cache[session.meeting_id] = session
            logger.info(f"[MeetingStore] Loaded {len(self._cache)} meeting sessions from disk.")
        except Exception as e:
            logger.error(f"[MeetingStore] Failed to load meetings from {self.data_file}: {e}")

    def _save_to_disk(self) -> None:
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                data = [s.to_dict() for s in self._cache.values()]
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[MeetingStore] Failed to persist meetings to {self.data_file}: {e}")

    def save_session(self, session: MeetingSession) -> MeetingSession:
        if not is_safe_identifier(session.meeting_id):
            raise ValueError(f"Invalid meeting_id: {session.meeting_id}")
        with self._lock:
            self._cache[session.meeting_id] = session
            # Execute disk write in background thread to avoid stalling event loop
            threading.Thread(target=self._save_to_disk, daemon=True).start()
            return session

    def get_session(self, meeting_id: str) -> Optional[MeetingSession]:
        if not is_safe_identifier(meeting_id):
            return None
        with self._lock:
            return self._cache.get(meeting_id)

    def list_sessions(self) -> List[MeetingSession]:
        with self._lock:
            # Sorted newest first
            return sorted(
                list(self._cache.values()),
                key=lambda s: s.created_at,
                reverse=True,
            )

    def delete_session(self, meeting_id: str) -> bool:
        with self._lock:
            if meeting_id in self._cache:
                del self._cache[meeting_id]
                self._save_to_disk()
                return True
            return False


_STORE_INSTANCE: Optional[MeetingStore] = None


def get_meeting_store() -> MeetingStore:
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        _STORE_INSTANCE = MeetingStore()
    return _STORE_INSTANCE
