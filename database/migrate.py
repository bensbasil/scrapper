"""
database/migrate.py
-------------------
Minimal, reliable, versioned PostgreSQL migration runner for the Business
Opportunity Intelligence Platform (Phase 6N-F).

Maintains a `schema_migrations` table tracking applied migration versions,
checksums, timestamps, and execution durations.

Key Capabilities:
- Clean database bootstrap from authoritative initial schema (`database/schema.sql`).
- Idempotent re-execution (safe no-op when migrations are already applied).
- Drift detection: detects unexpected changes to applied migration files via SHA-256.
- Transactional atomicity: DDL and bookkeeping applied in a managed transaction with rollback.
- Session-level advisory locking to prevent concurrent migration collisions across pods.
- Zero credential leakage in logs or exceptions (scrubbed via `sanitize_db_url`).
- Deterministic CLI interface: `python -m database.migrate`.
"""

import os
import re
import sys
import time
import hashlib
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple, Any

import psycopg2
from psycopg2 import sql
from dotenv import load_dotenv

from database.db import (
    resolve_database_url,
    sanitize_db_url,
    DatabaseConfigurationError,
    DatabaseConnectionError,
)
from scraper.utils.logger import get_scraper_logger

load_dotenv()
logger = get_scraper_logger(__name__)

# Valid PostgreSQL schema identifier: starts with letter/underscore, followed by alphanumerics/underscores, max 63 chars
SCHEMA_NAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$")


def validate_schema_name(schema_name: Optional[str]) -> None:
    """
    Validates that a schema name conforms to PostgreSQL identifier rules.
    Prevents SQL injection or malformed identifier strings.
    """
    if schema_name is not None and not SCHEMA_NAME_PATTERN.match(schema_name):
        raise MigrationConfigurationError(
            f"Invalid schema name '{schema_name}'. Schema name must match '^[a-zA-Z_][a-zA-Z0-9_]{{0,62}}$'."
        )

DEFAULT_SCHEMA_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "schema.sql")
)
DEFAULT_MIGRATIONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "migrations")
)


class MigrationError(Exception):
    """Base exception for database migration errors."""
    pass


class MigrationConfigurationError(MigrationError):
    """Raised when migration configuration or files are invalid or missing."""
    pass


class MigrationChecksumMismatchError(MigrationError):
    """Raised when an applied migration file has drifted from its recorded checksum."""
    pass


class MigrationExecutionError(MigrationError):
    """Raised when migration DDL execution fails."""
    pass


@dataclass(frozen=True)
class Migration:
    """Represents a discovered migration ready to be evaluated or applied."""
    version: str
    name: str
    sql_content: str
    checksum: str
    source_path: str


@dataclass(frozen=True)
class AppliedMigration:
    """Represents an applied migration record retrieved from schema_migrations."""
    version: str
    name: str
    checksum: str
    applied_at: datetime
    execution_time_ms: int


def compute_checksum(sql_content: str) -> str:
    """
    Computes a deterministic SHA-256 checksum of SQL content.
    Normalizes CRLF to LF to prevent cross-platform line-ending drift.
    """
    normalized = sql_content.replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class MigrationRunner:
    """
    Executes and tracks PostgreSQL migrations transactionally and idempotently.
    """

    def __init__(
        self,
        db_url: Optional[str] = None,
        schema_path: Optional[str] = None,
        migrations_dir: Optional[str] = None,
        schema_name: Optional[str] = None,
        connection: Optional[Any] = None,
        use_advisory_lock: bool = True,
    ):
        validate_schema_name(schema_name)
        self._custom_db_url = db_url
        self.schema_path = schema_path or DEFAULT_SCHEMA_PATH
        self.migrations_dir = migrations_dir or DEFAULT_MIGRATIONS_DIR
        self.schema_name = schema_name
        self._external_connection = connection
        self.use_advisory_lock = use_advisory_lock

    def get_connection(self) -> Any:
        """
        Creates or returns an active PostgreSQL connection.
        Ensures autocommit is False to guarantee transactional boundary control.
        """
        if self._external_connection is not None:
            return self._external_connection

        try:
            url = resolve_database_url(self._custom_db_url)
        except DatabaseConfigurationError as e:
            raise MigrationConfigurationError(str(e)) from e

        sanitized = sanitize_db_url(url)
        try:
            conn = psycopg2.connect(url)
            conn.autocommit = False
            if self.schema_name and self.schema_name != "public":
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL("SET search_path TO {}, public;").format(
                            sql.Identifier(self.schema_name)
                        )
                    )
                conn.commit()
            return conn
        except Exception as e:
            sanitized_err = sanitize_db_url(str(e))
            logger.error(f"Failed to connect to database at {sanitized}: {sanitized_err}")
            raise DatabaseConnectionError(
                f"Could not connect to database at {sanitized}."
            ) from e

    def ensure_schema_migrations_table(self, cur: Any) -> None:
        """Creates the schema_migrations table if it does not already exist."""
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(100) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                execution_time_ms INTEGER DEFAULT 0
            );
            """
        )

    def get_available_migrations(self) -> List[Migration]:
        """
        Discovers all available migrations in canonical order:
        1. Authoritative baseline migration ('001_initial_schema') from self.schema_path.
        2. Any subsequent migrations from self.migrations_dir (*.sql) sorted alphanumerically.
        """
        migrations: List[Migration] = []

        if not os.path.isfile(self.schema_path):
            raise MigrationConfigurationError(
                f"Authoritative schema file not found at: {self.schema_path}"
            )

        with open(self.schema_path, "r", encoding="utf-8") as f:
            baseline_sql = f.read()

        baseline_checksum = compute_checksum(baseline_sql)
        migrations.append(
            Migration(
                version="001_initial_schema",
                name="initial_schema",
                sql_content=baseline_sql,
                checksum=baseline_checksum,
                source_path=self.schema_path,
            )
        )

        if os.path.isdir(self.migrations_dir):
            files = sorted(
                f for f in os.listdir(self.migrations_dir)
                if f.endswith(".sql") and not f.startswith(".")
            )
            for fname in files:
                fpath = os.path.join(self.migrations_dir, fname)
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                stem = os.path.splitext(fname)[0]
                parts = stem.split("_", 1)
                version = stem
                name = parts[1] if len(parts) > 1 else stem
                if version == "001_initial_schema":
                    continue
                migrations.append(
                    Migration(
                        version=version,
                        name=name,
                        sql_content=content,
                        checksum=compute_checksum(content),
                        source_path=fpath,
                    )
                )

        return migrations

    def get_applied_migrations(self, cur: Any) -> Dict[str, AppliedMigration]:
        """Retrieves all applied migrations recorded in schema_migrations."""
        self.ensure_schema_migrations_table(cur)
        cur.execute(
            """
            SELECT version, name, checksum, applied_at, execution_time_ms
            FROM schema_migrations
            ORDER BY applied_at ASC, version ASC;
            """
        )
        rows = cur.fetchall()
        applied: Dict[str, AppliedMigration] = {}
        for r in rows:
            if isinstance(r, dict):
                v, n, c, a, e = r["version"], r["name"], r["checksum"], r["applied_at"], r["execution_time_ms"]
            else:
                v, n, c, a, e = r[0], r[1], r[2], r[3], r[4]
            applied[v] = AppliedMigration(
                version=v,
                name=n,
                checksum=c,
                applied_at=a,
                execution_time_ms=e or 0,
            )
        return applied

    def plan(
        self, cur: Any
    ) -> Tuple[List[Migration], List[AppliedMigration]]:
        """
        Plans pending migrations and verifies checksums of already-applied migrations.

        Raises:
            MigrationChecksumMismatchError: If any applied migration file has drifted from its recorded checksum.
        """
        applied = self.get_applied_migrations(cur)
        available = self.get_available_migrations()

        pending: List[Migration] = []
        already_applied: List[AppliedMigration] = []

        for migration in available:
            if migration.version in applied:
                rec = applied[migration.version]
                if rec.checksum != migration.checksum:
                    err_msg = (
                        f"Migration checksum mismatch for version '{migration.version}' ({migration.name}):\n"
                        f"  Database recorded: {rec.checksum}\n"
                        f"  Local file:        {migration.checksum}\n"
                        f"  File location:     {migration.source_path}\n"
                        f"The applied migration file has been modified after execution. Aborting to prevent schema drift."
                    )
                    logger.error(err_msg)
                    raise MigrationChecksumMismatchError(err_msg)
                already_applied.append(rec)
            else:
                pending.append(migration)

        return pending, already_applied

    def apply_pending(self) -> List[AppliedMigration]:
        """
        Applies all pending migrations in order, each within a managed transaction.
        Session-level advisory locking guarantees mutual exclusion against concurrent runner execution.
        """
        conn = self.get_connection()
        lock_acquired = False
        lock_key = f"schema_migrations_{self.schema_name or 'public'}"
        applied_results: List[AppliedMigration] = []

        try:
            with conn.cursor() as cur:
                if self.use_advisory_lock:
                    try:
                        cur.execute("SELECT pg_advisory_lock(hashtext(%s));", (lock_key,))
                        lock_acquired = True
                    except Exception as e:
                        conn.rollback()
                        sanitized_err = sanitize_db_url(str(e))
                        logger.error(f"Failed to acquire advisory lock for migration execution: {sanitized_err}")
                        raise MigrationExecutionError(
                            f"Failed to acquire advisory lock '{lock_key}': {sanitized_err}"
                        ) from e

                self.ensure_schema_migrations_table(cur)
                pending, already_applied = self.plan(cur)

                if not pending:
                    logger.info("Database schema is up to date. Zero migrations pending.")
                    conn.commit()
                    return []

                logger.info(f"Found {len(pending)} pending migration(s) to apply.")

                for migration in pending:
                    logger.info(f"Applying migration '{migration.version}' ({migration.name})...")
                    start_time = time.monotonic()
                    try:
                        cur.execute(migration.sql_content)
                        duration_ms = int((time.monotonic() - start_time) * 1000)

                        cur.execute(
                            """
                            INSERT INTO schema_migrations (version, name, checksum, applied_at, execution_time_ms)
                            VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s);
                            """,
                            (migration.version, migration.name, migration.checksum, duration_ms),
                        )
                        conn.commit()

                        applied_record = AppliedMigration(
                            version=migration.version,
                            name=migration.name,
                            checksum=migration.checksum,
                            applied_at=datetime.now(timezone.utc),
                            execution_time_ms=duration_ms,
                        )
                        applied_results.append(applied_record)
                        logger.info(
                            f"Successfully applied migration '{migration.version}' in {duration_ms}ms "
                            f"(checksum: {migration.checksum[:8]}...)"
                        )
                    except Exception as e:
                        conn.rollback()
                        sanitized_err = sanitize_db_url(str(e))
                        logger.error(
                            f"Failed executing migration '{migration.version}' ({migration.name}): {sanitized_err}"
                        )
                        raise MigrationExecutionError(
                            f"Failed executing migration '{migration.version}' ({migration.name}): {sanitized_err}"
                        ) from e

                return applied_results
        except Exception:
            if not conn.closed:
                try:
                    conn.rollback()
                except Exception:
                    pass
            raise
        finally:
            if lock_acquired and not conn.closed:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(hashtext(%s));", (lock_key,))
                    conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to release advisory lock: {e}")

            if not self._external_connection and not conn.closed:
                conn.close()

    def status(self) -> Dict[str, Any]:
        """
        Returns structured status of applied and pending migrations,
        and verifies checksums against recorded database state.
        """
        conn = self.get_connection()
        try:
            with conn.cursor() as cur:
                self.ensure_schema_migrations_table(cur)
                applied = self.get_applied_migrations(cur)
                available = self.get_available_migrations()

                status_list = []
                drift_detected = False

                for migration in available:
                    if migration.version in applied:
                        rec = applied[migration.version]
                        match = (rec.checksum == migration.checksum)
                        if not match:
                            drift_detected = True
                        status_list.append({
                            "version": migration.version,
                            "name": migration.name,
                            "status": "applied" if match else "checksum_mismatch",
                            "checksum": migration.checksum,
                            "recorded_checksum": rec.checksum,
                            "applied_at": rec.applied_at.isoformat() if rec.applied_at else None,
                            "execution_time_ms": rec.execution_time_ms,
                        })
                    else:
                        status_list.append({
                            "version": migration.version,
                            "name": migration.name,
                            "status": "pending",
                            "checksum": migration.checksum,
                            "recorded_checksum": None,
                            "applied_at": None,
                            "execution_time_ms": None,
                        })

                avail_versions = {m.version for m in available}
                orphaned = [
                    {
                        "version": v,
                        "name": r.name,
                        "status": "missing_local_file",
                        "recorded_checksum": r.checksum,
                        "applied_at": r.applied_at.isoformat() if r.applied_at else None,
                    }
                    for v, r in applied.items() if v not in avail_versions
                ]

                pending_count = sum(1 for s in status_list if s["status"] == "pending")
                applied_count = sum(1 for s in status_list if s["status"] == "applied")

                return {
                    "migrations": status_list,
                    "orphaned": orphaned,
                    "applied_count": applied_count,
                    "pending_count": pending_count,
                    "drift_detected": drift_detected,
                }
        finally:
            if not self._external_connection and not conn.closed:
                conn.close()


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for python -m database.migrate."""
    parser = argparse.ArgumentParser(
        prog="python -m database.migrate",
        description="Business Opportunity Intelligence Platform — Database Migration Runner",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Inspect migration status (applied vs pending) and verify checksums without applying changes.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 0 if database is fully migrated and clean; exit 1 if pending migrations or checksum drift exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan migrations and report what would be applied without modifying the database.",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Database connection URL (defaults to DATABASE_URL or DB_* environment variables).",
    )
    parser.add_argument(
        "--schema-path",
        type=str,
        default=None,
        help=f"Path to authoritative initial schema SQL file (defaults to {DEFAULT_SCHEMA_PATH}).",
    )
    parser.add_argument(
        "--migrations-dir",
        type=str,
        default=None,
        help=f"Path to migrations directory (defaults to {DEFAULT_MIGRATIONS_DIR}).",
    )
    parser.add_argument(
        "--schema",
        "--schema-name",
        type=str,
        default=None,
        help="Target PostgreSQL schema name (defaults to active search_path / public).",
    )

    args = parser.parse_args(argv)

    try:
        runner = MigrationRunner(
            db_url=args.db_url,
            schema_path=args.schema_path,
            migrations_dir=args.migrations_dir,
            schema_name=args.schema,
        )

        target_schema_str = f" [schema: {args.schema}]" if args.schema else ""

        if args.status or args.check:
            st = runner.status()
            print(f"\n=== Database Migration Status{target_schema_str} ===")
            for m in st["migrations"]:
                icon = "✔" if m["status"] == "applied" else ("✖" if m["status"] == "checksum_mismatch" else "○")
                applied_info = f"(applied {m['applied_at']}, {m['execution_time_ms']}ms)" if m['applied_at'] else "(pending)"
                print(f"  [{icon}] {m['version']} - {m['name']} {applied_info}")
                if m["status"] == "checksum_mismatch":
                    print(f"      ERROR: Recorded checksum {m['recorded_checksum']} != File checksum {m['checksum']}")

            for o in st["orphaned"]:
                print(f"  [?] {o['version']} - {o['name']} (recorded in DB but missing from migration files)")

            print(f"\nSummary: {st['applied_count']} applied, {st['pending_count']} pending.")

            if st["drift_detected"]:
                print("FAILED: Checksum drift detected in applied migrations.", file=sys.stderr)
                return 1

            if args.check:
                if st["pending_count"] > 0:
                    print(f"FAILED: {st['pending_count']} pending migration(s) need to be applied.", file=sys.stderr)
                    return 1
                print("PASSED: Database is fully migrated and clean.")
                return 0

            return 0

        if args.dry_run:
            conn = runner.get_connection()
            try:
                with conn.cursor() as cur:
                    runner.ensure_schema_migrations_table(cur)
                    pending, applied = runner.plan(cur)
                    print(f"\n=== Migration Dry-Run Plan{target_schema_str} ===")
                    print(f"Already applied: {len(applied)}")
                    for a in applied:
                        print(f"  [✔] {a.version} - {a.name} (checksum: {a.checksum[:8]}...)")
                    print(f"Pending to apply: {len(pending)}")
                    for p in pending:
                        print(f"  [+] {p.version} - {p.name} (checksum: {p.checksum[:8]}...)")
                    print(f"\nPlan complete: {len(pending)} migration(s) would be applied.")
                    return 0
            finally:
                if not conn.closed:
                    conn.close()

        # Default action: apply pending migrations
        applied = runner.apply_pending()
        if applied:
            print(f"Successfully applied {len(applied)} migration(s):")
            for a in applied:
                print(f"  - {a.version} ({a.name}) in {a.execution_time_ms}ms")
        else:
            print("Database is up to date. Zero migrations applied.")
        return 0

    except MigrationChecksumMismatchError as e:
        print(f"CHECKSUM DRIFT ERROR: {e}", file=sys.stderr)
        return 1
    except (MigrationError, DatabaseConnectionError, DatabaseConfigurationError) as e:
        sanitized = sanitize_db_url(str(e))
        print(f"MIGRATION ERROR: {sanitized}", file=sys.stderr)
        return 1
    except Exception as e:
        sanitized = sanitize_db_url(str(e))
        print(f"UNEXPECTED ERROR: {sanitized}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
