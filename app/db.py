"""Database engine and sessions.

Every connection enforces foreign keys, waits up to five seconds for a lock
and uses WAL, so readers and the single writer do not block each other.

The sqlite3 driver normally delays BEGIN until the first write, so a read
followed by a write is not one transaction. We turn that off and emit BEGIN
ourselves: write sessions use BEGIN IMMEDIATE and take the write lock before
reading anything; read sessions use a plain BEGIN and see one snapshot.
"""

from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

BUSY_TIMEOUT_MS = 5000


def create_db_engine(database_path: str) -> Engine:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{database_path}")

    @event.listens_for(engine, "connect")
    def configure_connection(dbapi_connection, _connection_record):
        dbapi_connection.isolation_level = None  # the driver no longer emits BEGIN
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def begin(conn):
        mode = conn.get_execution_options().get("sqlite_begin", "DEFERRED")
        conn.exec_driver_sql(f"BEGIN {mode}")

    return engine


def read_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine)


def write_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine.execution_options(sqlite_begin="IMMEDIATE"))


def get_read_session(request: Request) -> Iterator[Session]:
    with request.app.state.read_sessions() as session:
        yield session


def get_write_session(request: Request) -> Iterator[Session]:
    with request.app.state.write_sessions() as session:
        yield session
