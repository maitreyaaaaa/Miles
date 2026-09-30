from contextlib import nullcontext

import pytest

from scripts import configure_postgres_runtime_role as setup


class FakeConnection:
    def __init__(self, privileges):
        self.privileges = privileges
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return self

    def fetchone(self):
        return self.privileges


def configure_operator(monkeypatch, privileges):
    connection = FakeConnection(privileges)
    monkeypatch.setenv("MILES_MIGRATION_DATABASE_URL", "postgresql://operator.invalid")
    monkeypatch.setenv("MILES_RUNTIME_DB_PASSWORD", "test-runtime-password-with-at-least-32-characters")
    monkeypatch.setattr(setup.psycopg, "connect", lambda *_args, **_kwargs: nullcontext(connection))
    return connection


@pytest.mark.parametrize("unsafe_flag", range(6))
def test_refuses_to_provision_a_role_with_unsafe_privileges(monkeypatch, unsafe_flag):
    privileges = [False] * 6
    privileges[unsafe_flag] = True
    connection = configure_operator(monkeypatch, tuple(privileges))

    assert setup.main() == 1
    assert len(connection.statements) == 1  # Only the privilege inspection ran.


def test_refuses_a_missing_runtime_role(monkeypatch):
    connection = configure_operator(monkeypatch, None)

    assert setup.main() == 1
    assert len(connection.statements) == 1


def test_safe_role_is_provisioned_without_superuser_only_attributes(monkeypatch, capsys):
    connection = configure_operator(monkeypatch, (False,) * 6)

    assert setup.main() == 0
    alter_statement = connection.statements[1].as_string()
    assert "WITH LOGIN PASSWORD" in alter_statement
    for attribute in ("NOSUPERUSER", "NOBYPASSRLS", "NOREPLICATION"):
        assert attribute not in alter_statement
    assert "test-runtime-password" not in capsys.readouterr().out


def test_connection_failure_does_not_echo_credentials(monkeypatch, capsys):
    configure_operator(monkeypatch, (False,) * 6)

    def fail(*_args, **_kwargs):
        raise RuntimeError("postgresql://operator.invalid test-runtime-password-with-at-least-32-characters")

    monkeypatch.setattr(setup.psycopg, "connect", fail)
    assert setup.main() == 1
    output = capsys.readouterr().out
    assert "postgresql://" not in output
    assert "test-runtime-password" not in output
