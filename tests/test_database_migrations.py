"""
tests/test_database_migrations.py
---------------------------------
Comprehensive test suite for the database migration runner (Phase 6N-F.1).

Covers:
1. Deterministic SHA-256 checksum calculation & CRLF newline normalization.
2. Migration discovery (baseline schema.sql + optional migrations directory).
3. Bookkeeping table initialization (`schema_migrations`).
4. Migration planning and checksum drift detection.
5. Transactional execution & rollback on DDL errors.
6. Credential sanitization (zero password leakage in exceptions/logs).
7. Live PostgreSQL integration tests (clean bootstrap, idempotency, data preservation,
   drift detection, schema parity, rollback) against disposable schemas.
"""

import os
import sys
import uuid
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import psycopg2

from database.migrate import (
    Migration,
    AppliedMigration,
    MigrationRunner,
    MigrationError,
    MigrationConfigurationError,
    MigrationChecksumMismatchError,
    MigrationExecutionError,
    compute_checksum,
    validate_schema_name,
    main,
    DEFAULT_SCHEMA_PATH,
)
from database.db import DatabaseConnectionError, DatabaseConfigurationError


# =============================================================================
# 1. Offline Unit Tests (No Database Required)
# =============================================================================

def test_compute_checksum_deterministic():
    """Checksums must be deterministic and sensitive to content modifications."""
    sql1 = "CREATE TABLE users (id SERIAL PRIMARY KEY);"
    sql2 = "CREATE TABLE users (id SERIAL PRIMARY KEY);"
    sql3 = "CREATE TABLE users (id SERIAL PRIMARY KEY, name TEXT);"

    assert compute_checksum(sql1) == compute_checksum(sql2)
    assert compute_checksum(sql1) != compute_checksum(sql3)
    assert len(compute_checksum(sql1)) == 64  # SHA-256 hex digest length


def test_compute_checksum_normalizes_crlf():
    """CRLF and LF line endings must produce identical checksums to prevent false drift."""
    sql_lf = "CREATE TABLE foo (\n    id INT\n);\n"
    sql_crlf = "CREATE TABLE foo (\r\n    id INT\r\n);\r\n"

    assert compute_checksum(sql_lf) == compute_checksum(sql_crlf)


def test_get_available_migrations_baseline():
    """Default discovery must locate baseline migration pointing to database/schema.sql."""
    runner = MigrationRunner(schema_path=DEFAULT_SCHEMA_PATH)
    migrations = runner.get_available_migrations()

    assert len(migrations) >= 1
    baseline = migrations[0]
    assert baseline.version == "001_initial_schema"
    assert baseline.name == "initial_schema"
    assert baseline.source_path == DEFAULT_SCHEMA_PATH
    assert len(baseline.checksum) == 64
    assert len(baseline.sql_content) > 1000


def test_get_available_migrations_missing_schema_raises():
    """Missing schema file must raise MigrationConfigurationError."""
    runner = MigrationRunner(schema_path="/path/to/nonexistent/schema.sql")
    with pytest.raises(MigrationConfigurationError) as exc:
        runner.get_available_migrations()
    assert "not found" in str(exc.value)


def test_get_available_migrations_with_custom_directory():
    """Additional *.sql files in migrations_dir must be discovered in sorted order."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        schema_file = os.path.join(tmp_dir, "schema.sql")
        with open(schema_file, "w") as f:
            f.write("CREATE TABLE baseline (id INT);")

        migrations_dir = os.path.join(tmp_dir, "migrations")
        os.makedirs(migrations_dir)

        m2_file = os.path.join(migrations_dir, "002_add_index.sql")
        with open(m2_file, "w") as f:
            f.write("CREATE INDEX idx_test ON baseline(id);")

        m3_file = os.path.join(migrations_dir, "003_extra_table.sql")
        with open(m3_file, "w") as f:
            f.write("CREATE TABLE extra (id INT);")

        runner = MigrationRunner(schema_path=schema_file, migrations_dir=migrations_dir)
        migrations = runner.get_available_migrations()

        assert len(migrations) == 3
        assert migrations[0].version == "001_initial_schema"
        assert migrations[1].version == "002_add_index"
        assert migrations[1].name == "add_index"
        assert migrations[2].version == "003_extra_table"
        assert migrations[2].name == "extra_table"


def test_ensure_schema_migrations_table_mock():
    """Runner must execute CREATE TABLE IF NOT EXISTS schema_migrations."""
    mock_cur = MagicMock()
    runner = MigrationRunner()
    runner.ensure_schema_migrations_table(mock_cur)

    assert mock_cur.execute.called
    executed_sql = mock_cur.execute.call_args[0][0]
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in executed_sql
    assert "version VARCHAR(100) PRIMARY KEY" in executed_sql
    assert "checksum VARCHAR(64) NOT NULL" in executed_sql


def test_plan_all_pending_when_clean():
    """When schema_migrations is empty, all available migrations must be planned as pending."""
    mock_cur = MagicMock()
    runner = MigrationRunner()

    with patch.object(runner, "get_applied_migrations", return_value={}):
        pending, applied = runner.plan(mock_cur)

        assert len(pending) >= 1
        assert pending[0].version == "001_initial_schema"
        assert len(applied) == 0


def test_plan_skips_applied_when_checksum_matches():
    """Already-applied migrations with matching checksums must be skipped."""
    mock_cur = MagicMock()
    runner = MigrationRunner()
    available = runner.get_available_migrations()
    baseline = available[0]

    applied_rec = {
        baseline.version: AppliedMigration(
            version=baseline.version,
            name=baseline.name,
            checksum=baseline.checksum,
            applied_at=datetime.now(timezone.utc),
            execution_time_ms=50,
        )
    }

    with patch.object(runner, "get_applied_migrations", return_value=applied_rec):
        pending, applied = runner.plan(mock_cur)

        assert len(pending) == 0
        assert len(applied) == 1
        assert applied[0].version == baseline.version


def test_plan_raises_checksum_mismatch_error():
    """If an applied migration's checksum differs from the file, plan must fail with MigrationChecksumMismatchError."""
    mock_cur = MagicMock()
    runner = MigrationRunner()
    available = runner.get_available_migrations()
    baseline = available[0]

    applied_rec = {
        baseline.version: AppliedMigration(
            version=baseline.version,
            name=baseline.name,
            checksum="different_hash_from_db_1234567890abcdef1234567890abcdef12345678",
            applied_at=datetime.now(timezone.utc),
            execution_time_ms=50,
        )
    }

    with patch.object(runner, "get_applied_migrations", return_value=applied_rec):
        with pytest.raises(MigrationChecksumMismatchError) as exc:
            runner.plan(mock_cur)

        assert "checksum mismatch" in str(exc.value).lower()
        assert baseline.version in str(exc.value)


def test_apply_pending_rolls_back_on_execution_error():
    """If DDL execution fails, transaction must be rolled back and MigrationExecutionError raised."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.closed = False

    def mock_execute(sql, *args, **kwargs):
        if "schema_migrations" in sql or "pg_advisory" in sql:
            return None
        # Raise error when executing migration SQL
        raise psycopg2.DatabaseError("Syntax error in DDL statement")

    mock_cur.execute.side_effect = mock_execute

    runner = MigrationRunner(connection=mock_conn, use_advisory_lock=True)

    with pytest.raises(MigrationExecutionError) as exc:
        runner.apply_pending()

    assert "Syntax error in DDL" in str(exc.value)
    assert mock_conn.rollback.called


def test_credential_sanitization_in_connection_errors(monkeypatch):
    """Database passwords must never be disclosed in connection exception messages."""
    sensitive_url = "postgresql://secret_user:super_secret_password_123@127.0.0.1:5432/sensitive_db"
    monkeypatch.setenv("DATABASE_URL", sensitive_url)

    runner = MigrationRunner()

    with patch("psycopg2.connect", side_effect=Exception(f"Connection refused to {sensitive_url}")):
        with pytest.raises(DatabaseConnectionError) as exc:
            runner.get_connection()

        err_text = str(exc.value)
        assert "super_secret_password_123" not in err_text
        assert "[REDACTED]" in err_text


def test_cli_dry_run_offline():
    """CLI --dry-run must report planned migrations with exit code 0."""
    with patch("database.migrate.MigrationRunner.get_connection") as mock_get_conn:
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_conn.closed = False
        mock_get_conn.return_value = mock_conn

        with patch("database.migrate.MigrationRunner.get_applied_migrations", return_value={}):
            code = main(["--dry-run", "--db-url", "postgresql://mock_user:mock_pass@localhost:5432/mock_db"])
            assert code == 0


def test_cli_check_fails_when_pending_offline():
    """CLI --check must return exit code 1 if pending migrations exist."""
    with patch("database.migrate.MigrationRunner.status") as mock_status:
        mock_status.return_value = {
            "migrations": [{"version": "001_initial_schema", "name": "initial_schema", "status": "pending", "checksum": "abc", "recorded_checksum": None, "applied_at": None, "execution_time_ms": None}],
            "orphaned": [],
            "applied_count": 0,
            "pending_count": 1,
            "drift_detected": False,
        }
        code = main(["--check", "--db-url", "postgresql://mock_user:mock_pass@localhost:5432/mock_db"])
        assert code == 1


def test_cli_check_passes_when_clean_offline():
    """CLI --check must return exit code 0 when all migrations are applied with no drift."""
    with patch("database.migrate.MigrationRunner.status") as mock_status:
        mock_status.return_value = {
            "migrations": [{"version": "001_initial_schema", "name": "initial_schema", "status": "applied", "checksum": "abc", "recorded_checksum": "abc", "applied_at": "2026-10-24T00:00:00Z", "execution_time_ms": 25}],
            "orphaned": [],
            "applied_count": 1,
            "pending_count": 0,
            "drift_detected": False,
        }
        code = main(["--check", "--db-url", "postgresql://mock_user:mock_pass@localhost:5432/mock_db"])
        assert code == 0


def test_cli_status_fails_on_drift_offline():
    """CLI --status must return exit code 1 when checksum drift is detected."""
    with patch("database.migrate.MigrationRunner.status") as mock_status:
        mock_status.return_value = {
            "migrations": [{"version": "001_initial_schema", "name": "initial_schema", "status": "checksum_mismatch", "checksum": "abc", "recorded_checksum": "def", "applied_at": "2026-10-24T00:00:00Z", "execution_time_ms": 25}],
            "orphaned": [],
            "applied_count": 0,
            "pending_count": 0,
            "drift_detected": True,
        }
        code = main(["--status", "--db-url", "postgresql://mock_user:mock_pass@localhost:5432/mock_db"])
        assert code == 1


def test_validate_schema_name_rules():
    """Schema names must conform to PostgreSQL identifier rules."""
    # Valid names should not raise
    for valid_name in ["public", "my_schema", "test_123", "_private", "A_1"]:
        validate_schema_name(valid_name)

    # Invalid names must raise MigrationConfigurationError
    for invalid_name in [
        "123start_digit",
        "bad;drop_table",
        "hyphen-not-allowed",
        "space not allowed",
        "evil'quote",
        "a" * 64,  # exceeds 63 characters
    ]:
        with pytest.raises(MigrationConfigurationError):
            validate_schema_name(invalid_name)


def test_cli_invalid_schema_name_fails():
    """CLI must fail with exit code 1 if an invalid schema name is supplied."""
    code = main(["--schema", "123invalid;schema", "--db-url", "postgresql://mock_user:mock_pass@localhost:5432/mock_db"])
    assert code == 1


def test_advisory_lock_failure_rolls_back_and_fails_closed():
    """If advisory lock acquisition fails with an error, connection must be rolled back and fail closed."""
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_conn.closed = False

    # Simulate query failure during advisory lock acquisition
    mock_cur.execute.side_effect = psycopg2.DatabaseError("Lock acquisition failed: deadlocked or timeout")

    runner = MigrationRunner(connection=mock_conn, use_advisory_lock=True)

    with pytest.raises(MigrationExecutionError) as exc:
        runner.apply_pending()

    assert "Failed to acquire advisory lock" in str(exc.value)
    # Must have rolled back the connection to clear aborted transaction
    assert mock_conn.rollback.called



# =============================================================================
# 2. Live PostgreSQL Integration Tests (Requires Running PostgreSQL)
# =============================================================================

@pytest.fixture
def postgres_disposable_schema():
    """
    Creates an isolated disposable PostgreSQL schema for testing migrations.
    Safely tears down and drops the schema cascade on fixture completion.
    Skips cleanly if no PostgreSQL server is available.
    """
    real_db_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not real_db_url or "mock" in real_db_url:
        # Check local default if running on developer machine
        try:
            test_conn = psycopg2.connect("postgresql://bistto@localhost:5432/postgres", connect_timeout=1)
            test_conn.close()
            real_db_url = "postgresql://bistto@localhost:5432/postgres"
        except Exception:
            pytest.skip("No real PostgreSQL instance configured (set TEST_DATABASE_URL to run)")

    schema_name = f"test_mig_{uuid.uuid4().hex[:12]}"
    try:
        conn = psycopg2.connect(real_db_url, connect_timeout=2)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'CREATE SCHEMA "{schema_name}";')
        conn.close()
    except Exception as e:
        pytest.skip(f"Live PostgreSQL server unavailable at {real_db_url}: {e}")

    try:
        yield real_db_url, schema_name
    finally:
        try:
            conn = psycopg2.connect(real_db_url, connect_timeout=2)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE;')
            conn.close()
        except Exception:
            pass


@pytest.mark.postgres_integration
def test_real_postgres_initial_schema_application(postgres_disposable_schema):
    """Applying migrations to a clean schema must create all tables and record migration."""
    db_url, schema_name = postgres_disposable_schema
    runner = MigrationRunner(db_url=db_url, schema_name=schema_name)

    applied = runner.apply_pending()
    assert len(applied) == 1
    assert applied[0].version == "001_initial_schema"
    assert applied[0].execution_time_ms >= 0

    # Verify schema_migrations table contents
    conn = runner.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT version, name, checksum FROM schema_migrations;")
        rows = cur.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "001_initial_schema"
        assert rows[0][1] == "initial_schema"
        assert rows[0][2] == applied[0].checksum

        # Verify created application tables
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name;
            """,
            (schema_name,),
        )
        tables = [r[0] for r in cur.fetchall()]
        assert "schema_migrations" in tables
        assert "businesses" in tables
        assert "website_analyses" in tables
        assert "scoring_results" in tables
        assert "business_reports" in tables
        assert "pipeline_runs" in tables
        assert "change_events" in tables
        assert len(tables) >= 20  # 19 application tables + 1 schema_migrations table
    conn.close()


@pytest.mark.postgres_integration
def test_real_postgres_schema_parity(postgres_disposable_schema):
    """Verify that all 19 application tables and essential columns exist in the migrated database."""
    db_url, schema_name = postgres_disposable_schema
    runner = MigrationRunner(db_url=db_url, schema_name=schema_name)
    runner.apply_pending()

    expected_tables = [
        "businesses",
        "website_analyses",
        "scoring_results",
        "business_reports",
        "outreach_drafts",
        "email_intelligence",
        "tech_stacks",
        "social_profiles",
        "intent_profiles",
        "decision_makers",
        "company_registry",
        "pipeline_runs",
        "change_events",
        "customer_pain_signals",
        "competitor_analysis",
        "business_health_profiles",
        "seo_profiles",
        "review_snapshots",
        "deep_social_audits",
    ]

    conn = runner.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s;",
            (schema_name,),
        )
        actual_tables = set(r[0] for r in cur.fetchall())

        for tbl in expected_tables:
            assert tbl in actual_tables, f"Expected table '{tbl}' was not found in schema '{schema_name}'"

        # Verify specific critical columns added across phases
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'businesses';
            """,
            (schema_name,),
        )
        biz_cols = {r[0]: r[1] for r in cur.fetchall()}
        assert "id" in biz_cols
        assert "business_name" in biz_cols
        assert "outreach_status" in biz_cols
        assert "recrawl_tier" in biz_cols
        assert "source_platforms" in biz_cols

        # Verify pipeline_runs JSONB columns
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'pipeline_runs';
            """,
            (schema_name,),
        )
        run_cols = {r[0]: r[1] for r in cur.fetchall()}
        assert "stage_failure_counts" in run_cols
        assert run_cols["stage_failure_counts"] == "jsonb"

        # Verify deep_social_audits normalized column
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'deep_social_audits';
            """,
            (schema_name,),
        )
        social_cols = {r[0]: r[1] for r in cur.fetchall()}
        assert "follower_count_normalized" in social_cols
    conn.close()


@pytest.mark.postgres_integration
def test_real_postgres_idempotent_reexecution(postgres_disposable_schema):
    """Running migrations twice must be completely safe, apply 0 new migrations, and preserve state."""
    db_url, schema_name = postgres_disposable_schema
    runner = MigrationRunner(db_url=db_url, schema_name=schema_name)

    first_run = runner.apply_pending()
    assert len(first_run) == 1

    second_run = runner.apply_pending()
    assert len(second_run) == 0

    st = runner.status()
    assert st["applied_count"] == 1
    assert st["pending_count"] == 0
    assert st["drift_detected"] is False


@pytest.mark.postgres_integration
def test_real_postgres_preexisting_data_preservation(postgres_disposable_schema):
    """Re-running migrations must never drop or overwrite existing application business data."""
    db_url, schema_name = postgres_disposable_schema
    runner = MigrationRunner(db_url=db_url, schema_name=schema_name)
    runner.apply_pending()

    conn = runner.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO businesses (business_name, address, category, website)
            VALUES ('TEST_ACME_DENTAL', '123 Test Street, Austin, TX', 'Dentist', 'https://acmedental.test')
            RETURNING id;
            """
        )
        created_id = cur.fetchone()[0]
    conn.commit()
    conn.close()

    # Re-apply migrations
    runner.apply_pending()

    # Verify the row exists and was not erased
    conn = runner.get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT business_name, address FROM businesses WHERE id = %s;", (created_id,))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "TEST_ACME_DENTAL"
        assert row[1] == "123 Test Street, Austin, TX"
    conn.close()


@pytest.mark.postgres_integration
def test_real_postgres_checksum_drift_detection(postgres_disposable_schema):
    """Altering the recorded checksum must cause subsequent runs to abort with MigrationChecksumMismatchError."""
    db_url, schema_name = postgres_disposable_schema
    runner = MigrationRunner(db_url=db_url, schema_name=schema_name)
    runner.apply_pending()

    # Tamper with recorded checksum
    conn = runner.get_connection()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE schema_migrations SET checksum = 'tampered_hash_1234567890abcdef' WHERE version = '001_initial_schema';"
        )
    conn.commit()
    conn.close()

    with pytest.raises(MigrationChecksumMismatchError) as exc:
        runner.apply_pending()

    assert "checksum mismatch" in str(exc.value).lower()


@pytest.mark.postgres_integration
def test_real_postgres_transaction_rollback_on_failure(postgres_disposable_schema):
    """If a migration script contains invalid DDL, transaction must abort with no partial changes."""
    db_url, schema_name = postgres_disposable_schema

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Valid baseline schema
        schema_file = os.path.join(tmp_dir, "schema.sql")
        with open(schema_file, "w") as f:
            f.write("CREATE TABLE baseline_test (id INT PRIMARY KEY);")

        # Invalid second migration
        migrations_dir = os.path.join(tmp_dir, "migrations")
        os.makedirs(migrations_dir)
        bad_migration = os.path.join(migrations_dir, "002_bad_migration.sql")
        with open(bad_migration, "w") as f:
            f.write("CREATE TABLE partial_table (id INT); THIS IS INVALID SQL;")

        runner = MigrationRunner(
            db_url=db_url,
            schema_path=schema_file,
            migrations_dir=migrations_dir,
            schema_name=schema_name,
        )

        # First migration should fail when it reaches the bad migration
        with pytest.raises(MigrationExecutionError):
            runner.apply_pending()

        # Verify that partial_table was NOT left behind (was rolled back)
        conn = runner.get_connection()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = %s;",
                (schema_name,),
            )
            tables = [r[0] for r in cur.fetchall()]
            assert "partial_table" not in tables
            # baseline_test should have succeeded since it committed in its own transaction
            assert "baseline_test" in tables
        conn.close()


@pytest.mark.postgres_integration
def test_real_postgres_cli_commands(postgres_disposable_schema):
    """CLI commands (--check, --status, default apply) must execute cleanly against live PostgreSQL within target schema."""
    db_url, schema_name = postgres_disposable_schema

    # 1. Apply via CLI explicitly targeting the disposable schema
    code = main(["--db-url", db_url, "--schema", schema_name])
    assert code == 0

    # 2. Check status via CLI
    code = main(["--db-url", db_url, "--schema", schema_name, "--status"])
    assert code == 0

    # 3. Check clean via CLI
    code = main(["--db-url", db_url, "--schema", schema_name, "--check"])
    assert code == 0


@pytest.mark.postgres_integration
def test_real_postgres_cli_schema_isolation(postgres_disposable_schema):
    """
    Regression test: CLI migration execution with --schema must target ONLY the
    requested schema and must NOT create or alter tables in public or other schemas.
    """
    db_url, schema_name = postgres_disposable_schema

    # 1. Capture public tables before CLI migration
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
        public_tables_before = set(r[0] for r in cur.fetchall())
    conn.close()

    # 2. Execute migration targeting the disposable schema via CLI
    code = main(["--db-url", db_url, "--schema", schema_name])
    assert code == 0

    # 3. Assert all 20 tables were created in schema_name
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = %s ORDER BY table_name;",
            (schema_name,),
        )
        schema_tables = set(r[0] for r in cur.fetchall())
        assert len(schema_tables) >= 20
        assert "schema_migrations" in schema_tables
        assert "businesses" in schema_tables

        # 4. Assert public tables are completely unchanged
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
        public_tables_after = set(r[0] for r in cur.fetchall())
        assert public_tables_after == public_tables_before, "CLI migration leaked table creation into public schema!"
    conn.close()

