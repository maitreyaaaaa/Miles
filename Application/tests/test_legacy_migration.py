import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from src.storage import migrate_legacy


OWNER_ID = "00000000-0000-4000-8000-000000000001"
UNREGISTERED_OWNER = "00000000-0000-4000-8000-000000000099"


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_collect_legacy_records_preserves_owners_and_share_capabilities(tmp_path):
    dossier = {"context_id": "ctx-1", "filename": "brief.txt", "title": "Brief"}
    _write_json(tmp_path / "contexts" / OWNER_ID / "ctx-1.json", dossier)
    _write_json(tmp_path / "contexts" / "unknown-owner" / "ctx-old.json", dossier)

    meetings = [
        {"meeting_id": "meet-1", "owner_id": OWNER_ID, "created_at": 1.0},
        {"meeting_id": "meet-unowned", "created_at": 2.0},
    ]
    _write_json(tmp_path / "meetings" / "sessions.json", meetings)
    _write_json(tmp_path / "meetings" / "meet-1" / "debrief.json", {"overall_score": 83})
    _write_json(tmp_path / "meetings" / "orphan" / "debrief.json", {"overall_score": 20})

    _write_json(
        tmp_path / "debriefs" / "reports" / OWNER_ID / "session-1.json",
        {"session_id": "session-1", "overall_score": 91},
    )
    _write_json(
        tmp_path / "debriefs" / "deb_owner-share.json",
        {"share_id": "deb_owner-share", "owner_id": OWNER_ID, "overall_score": 75},
    )
    _write_json(
        tmp_path / "debriefs" / "deb_legacy-share.json",
        {"share_id": "deb_legacy-share", "overall_score": 60},
    )

    records = migrate_legacy.collect_legacy_records(tmp_path)

    assert len(records["contexts"]) == 1
    assert records["contexts"][0]["owner_id"] == OWNER_ID
    assert len(records["meetings"]) == 1
    assert records["meetings"][0]["session_data"]["debrief_report"]["overall_score"] == 83
    assert len(records["reports"]) == 1
    assert len(records["shares"]) == 2
    legacy_share = next(row for row in records["shares"] if row["share_id"] == "deb_legacy-share")
    assert legacy_share["owner_id"] is None
    assert records["skipped"] == {
        "unowned_contexts": 1,
        "unowned_meetings": 1,
        "unowned_reports": 0,
        "orphan_meeting_debriefs": 1,
    }


class FakeCursor:
    def __init__(self, rows=(), rowcount=1):
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows


class FakeConnection:
    def __init__(self, auth_users):
        self.auth_users = auth_users
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=None):
        self.statements.append((query, params))
        if "FROM auth.users" in query:
            asked = {str(user_id) for user_id in params[0]}
            return FakeCursor((user_id,) for user_id in asked & self.auth_users)
        return FakeCursor()


def test_import_refuses_owner_ids_missing_from_the_target_auth_project(monkeypatch):
    connection = FakeConnection(auth_users={OWNER_ID})
    monkeypatch.setattr(migrate_legacy.psycopg, "connect", lambda *_args, **_kwargs: connection)
    records = {
        "contexts": [],
        "meetings": [{"owner_id": UNREGISTERED_OWNER}],
        "reports": [],
        "shares": [],
    }

    with pytest.raises(ValueError, match="absent from the target Supabase Auth project"):
        migrate_legacy.import_records(records, "postgresql://unused")

    assert len(connection.statements) == 1
    assert "INSERT" not in connection.statements[0][0]
