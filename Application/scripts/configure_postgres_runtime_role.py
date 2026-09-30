"""Provision the least-privileged Supabase database login used by Miles."""

from __future__ import annotations

import os
import sys

import psycopg
from psycopg import sql


def main() -> int:
    migration_url = os.getenv("MILES_MIGRATION_DATABASE_URL", "")
    runtime_password = os.getenv("MILES_RUNTIME_DB_PASSWORD", "")
    if not migration_url or not runtime_password:
        print("Set MILES_MIGRATION_DATABASE_URL and MILES_RUNTIME_DB_PASSWORD in the secure environment.")
        return 2
    if len(runtime_password) < 32:
        print("MILES_RUNTIME_DB_PASSWORD must contain at least 32 characters.")
        return 2

    # Supabase's postgres operator is not a superuser. Repeating NOSUPERUSER
    # or NOBYPASSRLS in ALTER ROLE fails even when the role already has those
    # restrictions. Verify the migration-created role, then change only login.
    statement = sql.SQL("ALTER ROLE miles_runtime WITH LOGIN PASSWORD {}").format(
        sql.Literal(runtime_password)
    )
    try:
        with psycopg.connect(migration_url, connect_timeout=10) as connection:
            role = connection.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, "
                "rolbypassrls, rolinherit FROM pg_roles WHERE rolname = 'miles_runtime'"
            ).fetchone()
            if role is None or any(role):
                print("Miles runtime role is missing or has unsafe privileges. Apply or repair the reviewed migration first.")
                return 1
            connection.execute(statement)
            connection.execute("GRANT anon, authenticated TO miles_runtime")
    except Exception:
        # Never include the connection URL or password in output.
        print("Could not provision the Miles runtime database role. Check the migration connection and role grants.")
        return 1

    print("Miles runtime role configured. Store its password in the backend secret manager.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
