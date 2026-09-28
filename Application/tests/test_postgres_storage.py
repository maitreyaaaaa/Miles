from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

from src.context.store import ContextStore
from src.meeting.models import MeetingSession, MeetingStatus
from src.storage.postgres import PostgresDatabase
from src.storage.postgres_stores import PostgresContextStore, PostgresMeetingStore


class FakeCursor:
    def __init__(self, row=None, rows=None, rowcount=0):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class FakeConnection:
    def __init__(self, response=None):
        self.calls = []
        self.response = response

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=None):
        self.calls.append((" ".join(query.split()), params))
        if query.lstrip().startswith("SELECT dossier"):
            return FakeCursor(row=(self.response,))
        if query.lstrip().startswith("UPDATE public.meeting_sessions"):
            updated = dict(self.response)
            updated.update(params[0].obj)
            if updated.get("recall_status_updated_at") is None:
                updated.update(params[1].obj)
            return FakeCursor(row=(updated,))
        return FakeCursor(rowcount=1)


class FakePool:
    def __init__(self, connection):
        self._connection = connection

    @contextmanager
    def connection(self, **_kwargs):
        yield self._connection


def test_database_scopes_role_and_owner_to_one_transaction():
    owner_id = "00000000-0000-4000-8000-000000000001"
    connection = FakeConnection()
    database = PostgresDatabase("postgresql://unused", max_size=1)
    database._pool = FakePool(connection)

    with database.for_user(owner_id):
        pass

    assert connection.calls[0] == ("SET LOCAL ROLE authenticated", None)
    assert connection.calls[1] == (
        "SELECT set_config(%s, %s, true)",
        ("miles.user_id", owner_id),
    )


def test_public_share_database_scope_is_limited_to_the_share_token():
    connection = FakeConnection()
    database = PostgresDatabase("postgresql://unused", max_size=1)
    database._pool = FakePool(connection)

    with database.for_public_share("deb_a-safe-token"):
        pass

    assert connection.calls[0] == ("SET LOCAL ROLE anon", None)
    assert connection.calls[1][1] == ("miles.public_share_id", "deb_a-safe-token")
    with pytest.raises(ValueError):
        with database.for_public_share("../other"):
            pass


def test_database_check_verifies_schema_and_both_runtime_roles():
    connection = FakeConnection()
    database = PostgresDatabase("postgresql://unused", max_size=1)
    database._pool = FakePool(connection)

    database.check()

    assert [call[0] for call in connection.calls].count("SET LOCAL ROLE authenticated") == 1
    assert [call[0] for call in connection.calls].count("SET LOCAL ROLE anon") == 1
    assert any("FROM public.user_contexts LIMIT 0" in call[0] for call in connection.calls)
    assert sum("FROM public.debrief_shares LIMIT 0" in call[0] for call in connection.calls) == 2


def test_postgres_context_queries_keep_owner_in_the_query_and_rls_context():
    owner_id = "00000000-0000-4000-8000-000000000001"
    dossier_data = {
        "context_id": "ctx-1",
        "filename": "brief.txt",
        "doc_type": "general_doc",
        "title": "Brief",
    }
    connection = FakeConnection(response=dossier_data)
    database = PostgresDatabase("postgresql://unused", max_size=1)
    database._pool = FakePool(connection)

    dossier = PostgresContextStore(database).get_context(owner_id, "ctx-1")

    assert dossier is not None
    assert dossier.context_id == "ctx-1"
    assert connection.calls[-1][1] == (owner_id, "ctx-1")
    assert "owner_id = %s::uuid AND context_id = %s" in connection.calls[-1][0]


def test_postgres_recall_attachment_is_owner_scoped_and_preserves_webhook_state():
    owner_id = "00000000-0000-4000-8000-000000000001"
    original = MeetingSession(
        meeting_id="meeting-race",
        owner_id=owner_id,
        recall_status="in_call_recording",
        recall_status_updated_at=2000.0,
        status=MeetingStatus.IN_CALL,
    )
    connection = FakeConnection(response=original.to_dict(include_owner=True))
    database = PostgresDatabase("postgresql://unused", max_size=1)
    database._pool = FakePool(connection)

    saved = PostgresMeetingStore(database).attach_recall_bot(
        original,
        "bot-race",
        join_at=None,
        provider_notice="Recall audio connected",
    )

    query, params = connection.calls[-1]
    assert "owner_id = %s::uuid AND meeting_id = %s" in query
    assert "session_data->>'recall_status_updated_at' IS NULL" in query
    assert params[2:] == (owner_id, "meeting-race")
    assert saved.recall_bot_id == "bot-race"
    assert saved.recall_status == "in_call_recording"
    assert saved.status == MeetingStatus.IN_CALL


def test_local_json_store_is_still_explicitly_available_for_development(tmp_path):
    store = ContextStore(tmp_path)
    assert store.storage_dir == tmp_path


def test_migration_enables_owner_rls_and_denies_default_public_access():
    migration = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "20260927000000_user_data.sql"
    sql = migration.read_text(encoding="utf-8")

    for table in ("user_contexts", "meeting_sessions", "debate_reports", "debrief_shares"):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY" in sql
    assert "REVOKE ALL ON TABLE" in sql
    assert "current_setting('miles.user_id', true)" in sql
    assert "current_setting('miles.public_share_id', true)" in sql
