"""Preview or import owner-verified JSON records into the PostgreSQL schema."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from src.config import DATA_DIR
from src.context.analyzer import ContextDossier
from src.context.store import is_safe_identifier as is_safe_context_id
from src.debate.debrief_store import is_safe_identifier as is_safe_debrief_id
from src.meeting.models import MeetingSession
from src.meeting.store import is_safe_identifier as is_safe_meeting_id

logger = logging.getLogger(__name__)


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read JSON file: {path}") from exc


def _canonical_uuid(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def collect_legacy_records(data_dir: Path) -> dict[str, Any]:
    """Read only structurally valid owner-scoped records; never infer ownership."""
    records: dict[str, Any] = {
        "contexts": [],
        "meetings": [],
        "reports": [],
        "shares": [],
        "skipped": {
            "unowned_contexts": 0,
            "unowned_meetings": 0,
            "unowned_reports": 0,
            "orphan_meeting_debriefs": 0,
        },
    }

    contexts_dir = data_dir / "contexts"
    if contexts_dir.exists():
        for path in sorted(contexts_dir.glob("*/*.json")):
            owner_id = _canonical_uuid(path.parent.name)
            data = _read_json(path)
            if owner_id is None:
                records["skipped"]["unowned_contexts"] += 1
                continue
            if not isinstance(data, dict):
                continue
            dossier = ContextDossier.from_dict(data)
            if not is_safe_context_id(dossier.context_id) or dossier.context_id != path.stem:
                continue
            records["contexts"].append({
                "owner_id": owner_id,
                "context_id": dossier.context_id,
                "dossier": dossier.to_dict(),
                "created_at": float(dossier.created_at),
            })

    meetings_by_id: dict[str, dict[str, Any]] = {}
    sessions_path = data_dir / "meetings" / "sessions.json"
    if sessions_path.exists():
        raw_sessions = _read_json(sessions_path)
        if not isinstance(raw_sessions, list):
            raise ValueError(f"Expected a JSON array in {sessions_path}")
        for raw in raw_sessions:
            if not isinstance(raw, dict):
                continue
            session = MeetingSession.from_dict(raw)
            owner_id = _canonical_uuid(session.owner_id)
            if owner_id is None:
                records["skipped"]["unowned_meetings"] += 1
                continue
            if not is_safe_meeting_id(session.meeting_id):
                continue
            session.owner_id = owner_id
            item = {
                "meeting_id": session.meeting_id,
                "owner_id": owner_id,
                "session_data": session.to_dict(include_owner=True),
                "created_at": float(session.created_at),
            }
            records["meetings"].append(item)
            meetings_by_id[session.meeting_id] = item

    for path in sorted((data_dir / "meetings").glob("*/debrief.json")):
        meeting = meetings_by_id.get(path.parent.name)
        if meeting is None:
            records["skipped"]["orphan_meeting_debriefs"] += 1
            continue
        report = _read_json(path)
        if isinstance(report, dict):
            meeting["session_data"]["debrief_report"] = report

    reports_dir = data_dir / "debriefs" / "reports"
    if reports_dir.exists():
        for path in sorted(reports_dir.glob("*/*.json")):
            owner_id = _canonical_uuid(path.parent.name)
            report = _read_json(path)
            session_id = report.get("session_id") if isinstance(report, dict) else None
            if (
                owner_id is None
                or not is_safe_debrief_id(session_id)
                or session_id != path.stem
            ):
                if owner_id is None:
                    records["skipped"]["unowned_reports"] += 1
                continue
            records["reports"].append({
                "owner_id": owner_id,
                "session_id": session_id,
                "report": report,
            })

    shares_dir = data_dir / "debriefs"
    if shares_dir.exists():
        for path in sorted(shares_dir.glob("*.json")):
            data = _read_json(path)
            if not isinstance(data, dict):
                continue
            share_id = data.get("share_id") or path.stem
            if not is_safe_debrief_id(share_id) or share_id != path.stem:
                continue
            owner_id = _canonical_uuid(data.get("owner_id"))
            data["share_id"] = share_id
            data["owner_id"] = owner_id
            data.setdefault("share_scope", "unguessable_read_only_link")
            records["shares"].append({
                "share_id": share_id,
                "owner_id": owner_id,
                "report": data,
                "created_at": float(data.get("share_created_at") or path.stat().st_mtime),
            })

    return records


def import_records(records: dict[str, Any], migration_url: str) -> dict[str, int]:
    names = ("contexts", "meetings", "reports", "shares")
    inserted = {name: 0 for name in names}
    owner_ids = {
        item["owner_id"]
        for name in names
        for item in records[name]
        if item.get("owner_id") is not None
    }
    with psycopg.connect(migration_url, connect_timeout=10) as connection:
        with connection.transaction():
            if owner_ids:
                existing = {
                    str(row[0])
                    for row in connection.execute(
                        "SELECT id FROM auth.users WHERE id = ANY(%s::uuid[])",
                        ([UUID(owner_id) for owner_id in sorted(owner_ids)],),
                    ).fetchall()
                }
                missing = owner_ids - existing
                if missing:
                    raise ValueError(
                        f"{len(missing)} data owner IDs are absent from the target Supabase Auth project; "
                        "no records were imported."
                    )

            for item in records["contexts"]:
                cursor = connection.execute(
                    """
                    INSERT INTO public.user_contexts (owner_id, context_id, dossier, created_at)
                    VALUES (%s::uuid, %s, %s, to_timestamp(%s))
                    ON CONFLICT (owner_id, context_id) DO NOTHING
                    """,
                    (item["owner_id"], item["context_id"], Jsonb(item["dossier"]), item["created_at"]),
                )
                inserted["contexts"] += cursor.rowcount

            for item in records["meetings"]:
                cursor = connection.execute(
                    """
                    INSERT INTO public.meeting_sessions (meeting_id, owner_id, session_data, created_at)
                    VALUES (%s, %s::uuid, %s, to_timestamp(%s))
                    ON CONFLICT (meeting_id) DO NOTHING
                    """,
                    (
                        item["meeting_id"], item["owner_id"],
                        Jsonb(item["session_data"]), item["created_at"],
                    ),
                )
                inserted["meetings"] += cursor.rowcount

            for item in records["reports"]:
                cursor = connection.execute(
                    """
                    INSERT INTO public.debate_reports (owner_id, session_id, report)
                    VALUES (%s::uuid, %s, %s)
                    ON CONFLICT (owner_id, session_id) DO NOTHING
                    """,
                    (item["owner_id"], item["session_id"], Jsonb(item["report"])),
                )
                inserted["reports"] += cursor.rowcount

            for item in records["shares"]:
                cursor = connection.execute(
                    """
                    INSERT INTO public.debrief_shares (share_id, owner_id, report, created_at)
                    VALUES (%s, %s::uuid, %s, to_timestamp(%s))
                    ON CONFLICT (share_id) DO NOTHING
                    """,
                    (
                        item["share_id"], item["owner_id"], Jsonb(item["report"]), item["created_at"],
                    ),
                )
                inserted["shares"] += cursor.rowcount
    return inserted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="Existing MILES_DATA_DIR to import.")
    parser.add_argument("--apply", action="store_true", help="Insert the previewed records into PostgreSQL.")
    args = parser.parse_args(argv)

    try:
        records = collect_legacy_records(args.data_dir)
        skipped = records.pop("skipped")
        counts = {name: len(items) for name, items in records.items()}
        if args.apply:
            migration_url = os.getenv("MILES_MIGRATION_DATABASE_URL", "")
            if not migration_url:
                print("Set MILES_MIGRATION_DATABASE_URL to a direct administrative database URL before --apply.")
                return 2
            counts = import_records(records, migration_url)
            print("Imported records (existing database rows were preserved):")
        else:
            print("Dry run only. Source files were not changed; use --apply after reviewing this summary:")
        for name, count in counts.items():
            print(f"  {name}: {count}")
        if any(skipped.values()):
            print("Skipped legacy files:")
            for name, count in skipped.items():
                if count:
                    print(f"  {name}: {count}")
        if not any(counts.values()):
            print("  No owner-verified records found.")
        print("Unowned legacy contexts and meetings are skipped. Share links without an owner keep their capability ID.")
    except Exception as exc:
        # Errors identify the source path or operation, never include record contents.
        print(f"Legacy data import failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
