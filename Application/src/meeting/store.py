from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from src.config import DATA_DIR
from src.meeting.models import MeetingSession, MeetingStatus

logger = logging.getLogger(__name__)

MEETINGS_DIR = DATA_DIR / "meetings"
SESSIONS_FILE = MEETINGS_DIR / "sessions.json"


SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def is_safe_identifier(identifier: str) -> bool:
    return isinstance(identifier, str) and bool(identifier and SAFE_ID_REGEX.match(identifier))


class MeetingStore:
    """Thread-safe persistent store for Google Meet sparring sessions."""

    def __init__(self, data_file: Optional[Path] = None):
        self.data_file = data_file or SESSIONS_FILE
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meeting-store")
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
        temp_path: Optional[Path] = None
        try:
            with self._lock:
                data = [session.to_dict(include_owner=True) for session in self._cache.values()]

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.data_file.parent,
                prefix=f".{self.data_file.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                json.dump(data, temp_file, indent=2)

            os.replace(temp_path, self.data_file)
        except Exception as e:
            logger.error(f"[MeetingStore] Failed to persist meetings to {self.data_file}: {e}")
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

    def save_session(self, session: MeetingSession) -> MeetingSession:
        if not is_safe_identifier(session.meeting_id):
            raise ValueError(f"Invalid meeting_id: {session.meeting_id}")
        if not session.owner_id:
            raise ValueError("A meeting session must have an owner.")
        try:
            session.owner_id = str(UUID(session.owner_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid meeting owner.") from exc
        with self._lock:
            self._cache[session.meeting_id] = session
        # One writer keeps file I/O off the event loop and preserves write order.
        self._writer.submit(self._save_to_disk)
        return session

    def attach_recall_bot(
        self,
        session: MeetingSession,
        bot_id: str,
        *,
        join_at: Optional[str],
        provider_notice: str,
    ) -> MeetingSession:
        """Attach the created bot without overwriting a faster webhook update."""
        if not session.owner_id:
            raise ValueError("A meeting session must have an owner.")
        with self._lock:
            current = self._cache.get(session.meeting_id)
            if not current or current.owner_id != session.owner_id:
                raise PermissionError("Meeting does not belong to this user.")
            current.recall_bot_id = bot_id
            current.provider_mode = "recall_ai"
            current.provider_notice = provider_notice
            if current.recall_status_updated_at is None:
                current.recall_status = "ready"
                current.recall_status_message = None
                current.status = MeetingStatus.SCHEDULED if join_at else MeetingStatus.CONNECTING
            result = current
        self._writer.submit(self._save_to_disk)
        return result

    def flush(self) -> None:
        """Wait until all queued session writes have reached disk."""
        self._writer.submit(self._save_to_disk).result()

    def get_session(self, owner_id: str, meeting_id: str) -> Optional[MeetingSession]:
        if not is_safe_identifier(meeting_id):
            return None
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return None
        with self._lock:
            session = self._cache.get(meeting_id)
            return session if session and session.owner_id == owner_id else None

    def list_sessions(self, owner_id: str) -> List[MeetingSession]:
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return []
        with self._lock:
            return sorted(
                [session for session in self._cache.values() if session.owner_id == owner_id],
                key=lambda s: s.created_at,
                reverse=True,
            )

    def delete_session(self, owner_id: str, meeting_id: str) -> bool:
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return False
        with self._lock:
            if meeting_id in self._cache and self._cache[meeting_id].owner_id == owner_id:
                del self._cache[meeting_id]
                deleted = True
            else:
                deleted = False
        if deleted:
            self._writer.submit(self._save_to_disk)
        return deleted


_STORE_INSTANCE: Optional[MeetingStore] = None


def get_meeting_store() -> MeetingStore:
    global _STORE_INSTANCE
    if _STORE_INSTANCE is None:
        from src.storage import use_postgres_storage

        if use_postgres_storage():
            from src.storage.postgres_stores import PostgresMeetingStore

            _STORE_INSTANCE = PostgresMeetingStore()
        else:
            _STORE_INSTANCE = MeetingStore()
    return _STORE_INSTANCE
