from __future__ import annotations

from contextlib import contextmanager
import logging
import re
from threading import Lock
from typing import Iterator
from uuid import UUID

from psycopg.rows import tuple_row
from psycopg_pool import ConnectionPool

from src.config import config

logger = logging.getLogger(__name__)

_SHARE_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class PostgresDatabase:
    """Small pooled connection boundary with transaction-scoped RLS identity."""

    def __init__(self, database_url: str, *, max_size: int = 8):
        if not database_url:
            raise ValueError("A PostgreSQL connection URL is required.")
        if not 1 <= max_size <= 32:
            raise ValueError("Database pool size must be between 1 and 32.")
        self._database_url = database_url
        self._max_size = max_size
        self._pool: ConnectionPool | None = None
        self._lock = Lock()

    def open(self) -> None:
        """Open the pool and fail fast if the configured database is unavailable."""
        with self._lock:
            if self._pool is not None:
                return
            pool = ConnectionPool(
                conninfo=self._database_url,
                min_size=1,
                max_size=self._max_size,
                kwargs={"connect_timeout": 5, "prepare_threshold": None, "row_factory": tuple_row},
                timeout=5,
                open=False,
                name="miles-postgres",
            )
            try:
                pool.open(wait=True, timeout=10)
            except Exception:
                pool.close()
                logger.exception("Could not open the PostgreSQL connection pool.")
                raise
            self._pool = pool

    def check(self) -> None:
        """Fail startup if the schema or either RLS role is not ready."""
        self.open()
        owner_id = "00000000-0000-4000-8000-000000000001"
        with self.for_user(owner_id) as connection:
            for table in ("user_contexts", "meeting_sessions", "debate_reports", "debrief_shares"):
                connection.execute(f"SELECT 1 FROM public.{table} LIMIT 0")
        with self.for_public_share("deb_healthcheck") as connection:
            connection.execute("SELECT 1 FROM public.debrief_shares LIMIT 0")

    def close(self) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
        if pool is not None:
            pool.close(timeout=5)

    @contextmanager
    def for_user(self, owner_id: str) -> Iterator:
        """Run one short transaction as Supabase authenticated with owner context."""
        canonical_owner = str(UUID(owner_id))
        with self._connection_as("authenticated", "miles.user_id", canonical_owner) as connection:
            yield connection

    @contextmanager
    def for_public_share(self, share_id: str) -> Iterator:
        """Allow a capability lookup for exactly one public share token."""
        if not isinstance(share_id, str) or not re.fullmatch(_SHARE_ID_PATTERN, share_id):
            raise ValueError("Invalid share_id.")
        with self._connection_as("anon", "miles.public_share_id", share_id) as connection:
            yield connection

    @contextmanager
    def _connection_as(self, role: str, setting: str, value: str) -> Iterator:
        if role not in {"authenticated", "anon"}:
            raise ValueError("Unsupported database role.")
        self.open()
        pool = self._pool
        if pool is None:
            raise RuntimeError("PostgreSQL connection pool was not initialized.")
        with pool.connection(timeout=5) as connection:
            with connection.transaction():
                # Role and identity are LOCAL to this transaction so transaction
                # poolers never leak one request's RLS context to another.
                connection.execute(f"SET LOCAL ROLE {role}")
                connection.execute(
                    "SELECT set_config(%s, %s, true)",
                    (setting, value),
                )
                yield connection


_DATABASE: PostgresDatabase | None = None
_DATABASE_LOCK = Lock()


def get_postgres_database() -> PostgresDatabase:
    global _DATABASE
    if not config.database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    with _DATABASE_LOCK:
        if _DATABASE is None:
            _DATABASE = PostgresDatabase(
                config.database_url,
                max_size=config.database_pool_max_size,
            )
        return _DATABASE


def close_postgres_database() -> None:
    global _DATABASE
    with _DATABASE_LOCK:
        database, _DATABASE = _DATABASE, None
    if database is not None:
        database.close()
