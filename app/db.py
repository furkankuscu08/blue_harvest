"""Database engine and sessions.

SQLite connection settings (foreign keys, busy timeout, WAL, BEGIN IMMEDIATE)
are added separately, together with the test that proves them.
"""

from collections.abc import Iterator
from pathlib import Path

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_db_engine(database_path: str) -> Engine:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{database_path}")


def read_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine)


def write_session_factory(engine: Engine) -> sessionmaker[Session]:
    # Not yet different from reads: BEGIN IMMEDIATE comes with its tests.
    return sessionmaker(engine)


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session
