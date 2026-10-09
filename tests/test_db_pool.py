"""
tests/test_db_pool.py
---------------------
Tests for BoundedConnectionPool behavior, bounded waiting on exhaustion,
timeouts, connection reclamation, and transaction rollback (Phase 5C).
"""

import time
import threading
import pytest
from unittest.mock import MagicMock
import psycopg2.pool

from database.db import (
    BoundedConnectionPool,
    DatabaseManager,
    DatabasePoolTimeoutError,
    DatabaseConnectionError,
)


class MockUnderlyingPool:
    """Simulates psycopg2.pool.ThreadedConnectionPool semantics for deterministic testing."""

    def __init__(self, minconn, maxconn, dsn=""):
        self.minconn = minconn
        self.maxconn = maxconn
        self.dsn = dsn
        self._available = [MagicMock(name=f"conn_{i}") for i in range(maxconn)]
        self._in_use = set()
        self.closed = False

    def getconn(self):
        if self.closed:
            raise psycopg2.pool.PoolError("Connection pool is closed")
        if not self._available:
            raise psycopg2.pool.PoolError("connection pool exhausted")
        conn = self._available.pop(0)
        self._in_use.add(conn)
        return conn

    def putconn(self, conn, close=False):
        if conn in self._in_use:
            self._in_use.remove(conn)
        if not close and not self.closed:
            self._available.append(conn)

    def closeall(self):
        self.closed = True
        self._available.clear()
        self._in_use.clear()


def test_bounded_pool_basic_checkout_and_return():
    pool = BoundedConnectionPool(
        minconn=1,
        maxconn=2,
        dsn="mock_dsn",
        timeout=1.0,
        pool_factory=MockUnderlyingPool,
    )
    conn = pool.getconn()
    assert conn is not None
    # Pool now has 1 available connection
    conn2 = pool.getconn()
    assert conn2 is not None

    # Return connections
    pool.putconn(conn)
    pool.putconn(conn2)

    # Can acquire again
    conn3 = pool.getconn()
    assert conn3 is not None
    pool.putconn(conn3)


def test_bounded_pool_exhaustion_timeout():
    """Verifies that when all connections are exhausted, getconn raises DatabasePoolTimeoutError after timeout."""
    pool = BoundedConnectionPool(
        minconn=1,
        maxconn=2,
        dsn="mock_dsn",
        timeout=0.2,
        pool_factory=MockUnderlyingPool,
    )

    c1 = pool.getconn()
    c2 = pool.getconn()

    start = time.monotonic()
    with pytest.raises(DatabasePoolTimeoutError) as exc_info:
        pool.getconn()

    elapsed = time.monotonic() - start
    assert elapsed >= 0.18  # Waited bounded duration
    assert "Database connection pool exhausted" in str(exc_info.value)
    assert "configured max 2 connections" in str(exc_info.value)

    pool.putconn(c1)
    pool.putconn(c2)


def test_bounded_pool_waiting_thread_wakes_on_return():
    """Verifies that a blocked thread waiting on pool exhaustion acquires connection once another thread releases it."""
    pool = BoundedConnectionPool(
        minconn=1,
        maxconn=1,
        dsn="mock_dsn",
        timeout=2.0,
        pool_factory=MockUnderlyingPool,
    )

    c1 = pool.getconn()
    acquired_in_thread = []

    def background_acquirer():
        conn = pool.getconn()
        acquired_in_thread.append(conn)
        pool.putconn(conn)

    t = threading.Thread(target=background_acquirer)
    t.start()

    # Give background thread time to block
    time.sleep(0.1)
    assert len(acquired_in_thread) == 0

    # Release connection in main thread
    pool.putconn(c1)
    t.join(timeout=1.0)

    assert len(acquired_in_thread) == 1
    assert acquired_in_thread[0] == c1


def test_database_manager_reclaims_connection_in_finally():
    """Verifies that DatabaseManager.get_connection always returns connection even on unhandled exception."""
    mock_pool_instance = MockUnderlyingPool(minconn=1, maxconn=1)

    mgr = DatabaseManager(
        db_url="postgresql://mock_user:mock_pass@127.0.0.1:5432/mock_db",
        min_conn=1,
        max_conn=1,
        timeout=0.5,
        pool_factory=lambda *a, **kw: mock_pool_instance,
        lazy=False,
    )

    # Initial state: 1 available connection
    assert len(mock_pool_instance._available) == 1

    # Exception raised within context manager
    with pytest.raises(ValueError, match="intentional failure"):
        with mgr.get_connection() as conn:
            assert len(mock_pool_instance._available) == 0
            raise ValueError("intentional failure")

    # Connection MUST be returned to available pool
    assert len(mock_pool_instance._available) == 1


def test_database_manager_transaction_rollback_on_error():
    """Verifies that conn.rollback() is invoked if an exception is raised within get_connection block."""
    mock_pool_instance = MockUnderlyingPool(minconn=1, maxconn=1)

    mgr = DatabaseManager(
        db_url="postgresql://mock_user:mock_pass@127.0.0.1:5432/mock_db",
        min_conn=1,
        max_conn=1,
        timeout=0.5,
        pool_factory=lambda *a, **kw: mock_pool_instance,
        lazy=False,
    )

    mock_conn = None
    with pytest.raises(RuntimeError):
        with mgr.get_connection() as conn:
            mock_conn = conn
            raise RuntimeError("Database error")

    assert mock_conn is not None
    mock_conn.rollback.assert_called_once()
    mock_conn.commit.assert_not_called()


def test_bounded_pool_closed_raises_database_connection_error():
    pool = BoundedConnectionPool(
        minconn=1,
        maxconn=2,
        dsn="mock_dsn",
        timeout=0.5,
        pool_factory=MockUnderlyingPool,
    )
    pool.closeall()

    with pytest.raises(DatabaseConnectionError, match="has been closed"):
        pool.getconn()
