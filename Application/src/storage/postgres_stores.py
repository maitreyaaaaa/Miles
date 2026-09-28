from __future__ import annotations

import logging
import secrets
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from psycopg.types.json import Jsonb

from src.context.analyzer import ContextDossier
from src.context.store import is_safe_identifier as is_safe_context_id
from src.debate.debrief_store import is_safe_identifier as is_safe_debrief_id
from src.meeting.models import MeetingSession, MeetingStatus
from src.meeting.store import is_safe_identifier as is_safe_meeting_id
from src.storage.postgres import PostgresDatabase, get_postgres_database

logger = logging.getLogger(__name__)


class PostgresContextStore:
    """Owner-scoped context dossier persistence in PostgreSQL."""

    def __init__(self, database: PostgresDatabase | None = None):
        self.database = database or get_postgres_database()

    def save_context(self, owner_id: str, dossier: ContextDossier) -> str:
        if not is_safe_context_id(dossier.context_id):
            raise ValueError(f"Invalid context_id: {dossier.context_id}")
        owner_id = str(UUID(owner_id))
        with self.database.for_user(owner_id) as connection:
            connection.execute(
                """
                INSERT INTO public.user_contexts (owner_id, context_id, dossier, created_at)
                VALUES (%s::uuid, %s, %s, to_timestamp(%s))
                ON CONFLICT (owner_id, context_id) DO UPDATE
                SET dossier = EXCLUDED.dossier, updated_at = now()
                """,
                (owner_id, dossier.context_id, Jsonb(dossier.to_dict()), float(dossier.created_at)),
            )
        return dossier.context_id

    def get_context(self, owner_id: str, context_id: str) -> Optional[ContextDossier]:
        if not is_safe_context_id(context_id):
            return None
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return None
        with self.database.for_user(owner_id) as connection:
            row = connection.execute(
                "SELECT dossier FROM public.user_contexts WHERE owner_id = %s::uuid AND context_id = %s",
                (owner_id, context_id),
            ).fetchone()
        return ContextDossier.from_dict(row[0]) if row else None

    def list_contexts(self, owner_id: str) -> List[Dict[str, Any]]:
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return []
        with self.database.for_user(owner_id) as connection:
            rows = connection.execute(
                "SELECT dossier FROM public.user_contexts WHERE owner_id = %s::uuid ORDER BY created_at DESC",
                (owner_id,),
            ).fetchall()
        results = []
        for (data,) in rows:
            dossier = ContextDossier.from_dict(data)
            results.append({
                "context_id": dossier.context_id,
                "filename": dossier.filename,
                "doc_type": dossier.doc_type,
                "title": dossier.title,
                "metric_count": len(dossier.numeric_metrics),
                "claim_count": len(dossier.core_claims),
                "recommended_scenario": dossier.recommended_scenario,
                "created_at": dossier.created_at,
            })
        return results

    def delete_context(self, owner_id: str, context_id: str) -> bool:
        if not is_safe_context_id(context_id):
            return False
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return False
        with self.database.for_user(owner_id) as connection:
            cursor = connection.execute(
                "DELETE FROM public.user_contexts WHERE owner_id = %s::uuid AND context_id = %s",
                (owner_id, context_id),
            )
            return cursor.rowcount > 0


class PostgresMeetingStore:
    """Owner-scoped meeting session persistence in PostgreSQL."""

    def __init__(self, database: PostgresDatabase | None = None):
        self.database = database or get_postgres_database()

    def save_session(self, session: MeetingSession) -> MeetingSession:
        if not is_safe_meeting_id(session.meeting_id):
            raise ValueError(f"Invalid meeting_id: {session.meeting_id}")
        if not session.owner_id:
            raise ValueError("A meeting session must have an owner.")
        owner_id = str(UUID(session.owner_id))
        session.owner_id = owner_id
        with self.database.for_user(owner_id) as connection:
            cursor = connection.execute(
                """
                INSERT INTO public.meeting_sessions (meeting_id, owner_id, session_data, created_at)
                VALUES (%s, %s::uuid, %s, to_timestamp(%s))
                ON CONFLICT (meeting_id) DO UPDATE
                SET session_data = EXCLUDED.session_data, updated_at = now()
                WHERE public.meeting_sessions.owner_id = EXCLUDED.owner_id
                """,
                (
                    session.meeting_id,
                    owner_id,
                    Jsonb(session.to_dict(include_owner=True)),
                    float(session.created_at),
                ),
            )
            if cursor.rowcount == 0:
                raise PermissionError("Meeting does not belong to this user.")
        return session

    def attach_recall_bot(
        self,
        session: MeetingSession,
        bot_id: str,
        *,
        join_at: Optional[str],
        provider_notice: str,
    ) -> MeetingSession:
        """Atomically attach the bot while preserving any webhook received first."""
        if not is_safe_meeting_id(session.meeting_id):
            raise ValueError(f"Invalid meeting_id: {session.meeting_id}")
        if not session.owner_id:
            raise ValueError("A meeting session must have an owner.")
        owner_id = str(UUID(session.owner_id))
        update = {
            "recall_bot_id": bot_id,
            "provider_mode": "recall_ai",
            "provider_notice": provider_notice,
        }
        initial_status = {
            "recall_status": "ready",
            "recall_status_message": None,
            "status": (MeetingStatus.SCHEDULED if join_at else MeetingStatus.CONNECTING).value,
        }
        with self.database.for_user(owner_id) as connection:
            row = connection.execute(
                """
                UPDATE public.meeting_sessions
                SET session_data = session_data || %s::jsonb ||
                    CASE WHEN session_data->>'recall_status_updated_at' IS NULL
                         THEN %s::jsonb ELSE '{}'::jsonb END,
                    updated_at = now()
                WHERE owner_id = %s::uuid AND meeting_id = %s
                RETURNING session_data
                """,
                (Jsonb(update), Jsonb(initial_status), owner_id, session.meeting_id),
            ).fetchone()
        if not row:
            raise PermissionError("Meeting does not belong to this user.")
        return MeetingSession.from_dict(row[0])

    def get_session(self, owner_id: str, meeting_id: str) -> Optional[MeetingSession]:
        if not is_safe_meeting_id(meeting_id):
            return None
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return None
        with self.database.for_user(owner_id) as connection:
            row = connection.execute(
                "SELECT session_data FROM public.meeting_sessions WHERE owner_id = %s::uuid AND meeting_id = %s",
                (owner_id, meeting_id),
            ).fetchone()
        return MeetingSession.from_dict(row[0]) if row else None

    def list_sessions(self, owner_id: str) -> List[MeetingSession]:
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return []
        with self.database.for_user(owner_id) as connection:
            rows = connection.execute(
                """
                SELECT session_data FROM public.meeting_sessions
                WHERE owner_id = %s::uuid ORDER BY created_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [MeetingSession.from_dict(row[0]) for row in rows]

    def delete_session(self, owner_id: str, meeting_id: str) -> bool:
        if not is_safe_meeting_id(meeting_id):
            return False
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return False
        with self.database.for_user(owner_id) as connection:
            cursor = connection.execute(
                "DELETE FROM public.meeting_sessions WHERE owner_id = %s::uuid AND meeting_id = %s",
                (owner_id, meeting_id),
            )
            return cursor.rowcount > 0

    def flush(self) -> None:
        """Database writes are committed before each synchronous store call returns."""


class PostgresDebriefReportStore:
    """Private reports and public capability links stored in PostgreSQL."""

    def __init__(self, database: PostgresDatabase | None = None):
        self.database = database or get_postgres_database()

    def save_debrief(self, report: Dict[str, Any], owner_id: str) -> str:
        owner_id = str(UUID(owner_id))
        report_copy = dict(report)
        report_copy.setdefault("share_created_at", time.time())
        report_copy["share_scope"] = "unguessable_read_only_link"
        for _ in range(4):
            share_id = f"deb_{secrets.token_urlsafe(18)}"
            report_copy["share_id"] = share_id
            report_copy["owner_id"] = owner_id
            with self.database.for_user(owner_id) as connection:
                row = connection.execute(
                    """
                    INSERT INTO public.debrief_shares (share_id, owner_id, report, created_at)
                    VALUES (%s, %s::uuid, %s, to_timestamp(%s))
                    ON CONFLICT (share_id) DO NOTHING
                    RETURNING share_id
                    """,
                    (share_id, owner_id, Jsonb(report_copy), float(report_copy["share_created_at"])),
                ).fetchone()
            if row:
                return row[0]
        raise RuntimeError("Could not allocate a unique debrief share id.")

    def save_report(self, report: Dict[str, Any], owner_id: str) -> None:
        session_id = report.get("session_id")
        if not is_safe_debrief_id(session_id):
            raise ValueError("A valid session_id is required to store a private report.")
        owner_id = str(UUID(owner_id))
        with self.database.for_user(owner_id) as connection:
            connection.execute(
                """
                INSERT INTO public.debate_reports (owner_id, session_id, report)
                VALUES (%s::uuid, %s, %s)
                ON CONFLICT (owner_id, session_id) DO UPDATE
                SET report = EXCLUDED.report, updated_at = now()
                """,
                (owner_id, session_id, Jsonb(dict(report))),
            )

    def get_report(self, session_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
        if not is_safe_debrief_id(session_id):
            return None
        try:
            owner_id = str(UUID(owner_id))
        except (TypeError, ValueError):
            return None
        with self.database.for_user(owner_id) as connection:
            row = connection.execute(
                """
                SELECT report FROM public.debate_reports
                WHERE owner_id = %s::uuid AND session_id = %s
                """,
                (owner_id, session_id),
            ).fetchone()
        return dict(row[0]) if row else None

    def get_debrief(self, share_id: str, owner_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not is_safe_debrief_id(share_id):
            return None
        if owner_id is not None:
            try:
                owner_id = str(UUID(owner_id))
            except (TypeError, ValueError):
                return None
            with self.database.for_user(owner_id) as connection:
                row = connection.execute(
                    """
                    SELECT report FROM public.debrief_shares
                    WHERE share_id = %s AND owner_id = %s::uuid
                    """,
                    (share_id, owner_id),
                ).fetchone()
        else:
            with self.database.for_public_share(share_id) as connection:
                row = connection.execute(
                    "SELECT report FROM public.debrief_shares WHERE share_id = %s",
                    (share_id,),
                ).fetchone()
        return dict(row[0]) if row else None
