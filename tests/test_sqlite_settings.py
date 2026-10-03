"""SQLite settings that the domain code relies on.

Write transactions must take the write lock when they begin, so that a
read-check-write sequence cannot act on stale data. Reads must neither
block writers nor see changes made after they began.
"""

import sqlite3
import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import create_db_engine, read_session_factory, write_session_factory


@pytest.fixture
def engine(tmp_path):
    engine = create_db_engine(str(tmp_path / "test.db"))
    yield engine
    engine.dispose()


def create_counter(engine):
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE counter (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)"
        )
        conn.exec_driver_sql("INSERT INTO counter (id, value) VALUES (1, 0)")


def other_connection(engine) -> sqlite3.Connection:
    """A plain connection outside the app's settings that fails at once on a lock."""
    return sqlite3.connect(engine.url.database, timeout=0, isolation_level=None)


@pytest.mark.parametrize(
    ("pragma", "expected"),
    [("foreign_keys", 1), ("busy_timeout", 5000), ("journal_mode", "wal")],
)
def test_every_connection_has_the_sqlite_settings(engine, pragma, expected):
    with engine.connect() as first, engine.connect() as second:
        values = [conn.exec_driver_sql(f"PRAGMA {pragma}").scalar() for conn in (first, second)]

    assert values == [expected, expected]


def test_foreign_keys_are_enforced(engine):
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        conn.exec_driver_sql(
            "CREATE TABLE child (id INTEGER PRIMARY KEY,"
            " parent_id INTEGER NOT NULL REFERENCES parent (id))"
        )

    with write_session_factory(engine)() as session, pytest.raises(IntegrityError):
        session.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 99)"))


def test_write_transaction_takes_the_write_lock_at_begin(engine):
    create_counter(engine)

    with write_session_factory(engine)() as session:
        session.execute(text("SELECT value FROM counter"))
        other = other_connection(engine)
        try:
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                other.execute("BEGIN IMMEDIATE")
        finally:
            other.close()


def test_read_transaction_keeps_its_snapshot_without_blocking_writers(engine):
    create_counter(engine)

    with read_session_factory(engine)() as session:
        before = session.execute(text("SELECT value FROM counter")).scalar_one()

        other = other_connection(engine)
        try:
            other.execute("BEGIN IMMEDIATE")
            other.execute("UPDATE counter SET value = 1")
            other.execute("COMMIT")
        finally:
            other.close()

        after = session.execute(text("SELECT value FROM counter")).scalar_one()

    assert (before, after) == (0, 0)


def test_concurrent_read_modify_write_loses_no_update(engine):
    create_counter(engine)
    sessions = write_session_factory(engine)
    start = threading.Barrier(2)
    errors = []

    def increment():
        try:
            start.wait()
            with sessions() as session:
                value = session.execute(text("SELECT value FROM counter")).scalar_one()
                time.sleep(0.1)  # widens the race window; no assertion depends on timing
                session.execute(text("UPDATE counter SET value = :value"), {"value": value + 1})
                session.commit()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=increment) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT value FROM counter").scalar_one() == 2
