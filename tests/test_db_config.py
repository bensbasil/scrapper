"""
tests/test_db_config.py
-----------------------
Tests for database configuration resolution, credential safety,
and initialization semantics (Phase 5C).
"""

import os
import pytest
from database.db import (
    DatabaseManager,
    DatabaseConfigurationError,
    DatabaseConnectionError,
    resolve_database_url,
    sanitize_db_url,
)


def test_resolve_database_url_from_explicit_arg():
    url = "postgresql://myuser:secret123@db.example.com:5432/prospects"
    resolved = resolve_database_url(url)
    assert resolved == url


def test_resolve_database_url_from_env_var(monkeypatch):
    url = "postgresql://envuser:envpass@db.example.com:5432/prospects"
    monkeypatch.setenv("DATABASE_URL", url)
    resolved = resolve_database_url()
    assert resolved == url


def test_resolve_database_url_from_discrete_env_vars(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_USER", "discrete_user")
    monkeypatch.setenv("DB_PASSWORD", "discrete_pass")
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "discrete_db")

    resolved = resolve_database_url()
    assert resolved == "postgresql://discrete_user:discrete_pass@db.internal:5433/discrete_db"


def test_resolve_database_url_missing_raises_configuration_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    with pytest.raises(DatabaseConfigurationError) as exc_info:
        resolve_database_url()

    assert "Missing required database configuration" in str(exc_info.value)
    # Ensure no credentials or partial strings are leaked
    assert "password" not in str(exc_info.value).lower() or "not set" in str(exc_info.value)


def test_sanitize_db_url_redacts_password():
    raw_url = "postgresql://prod_user:SuperSecretPassword123!@10.0.1.50:5432/prod_db"
    sanitized = sanitize_db_url(raw_url)

    assert "SuperSecretPassword123!" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "postgresql://prod_user:[REDACTED]@10.0.1.50:5432/prod_db" == sanitized


def test_sanitize_db_url_safe_when_no_password():
    raw_url = "postgresql://localhost:5432/mydb"
    sanitized = sanitize_db_url(raw_url)
    assert sanitized == raw_url


def test_sanitize_db_url_safe_when_empty():
    assert sanitize_db_url("") == ""
    assert sanitize_db_url(None) == ""


def test_lazy_database_manager_does_not_connect_on_init(monkeypatch):
    # Unset all DB config
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    # Lazy instantiation should not fail on creation
    mgr = DatabaseManager(lazy=True)
    assert mgr.pool is None

    # Only when attempting connection does it fail closed
    with pytest.raises(DatabaseConfigurationError):
        with mgr.get_connection():
            pass


def test_eager_database_manager_fails_fast_on_missing_config(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    with pytest.raises(DatabaseConfigurationError):
        DatabaseManager(lazy=False)


def test_database_connection_error_redacts_credentials():
    secret_url = "postgresql://admin:TopSecretKeyXYZ@127.0.0.1:59998/testdb"
    # Non-existent port to force immediate failure
    with pytest.raises(DatabaseConnectionError) as exc_info:
        mgr = DatabaseManager(db_url=secret_url, lazy=False, timeout=1.0)

    # Exception message must NOT contain TopSecretKeyXYZ
    assert "TopSecretKeyXYZ" not in str(exc_info.value)
    assert "[REDACTED]" in str(exc_info.value)
