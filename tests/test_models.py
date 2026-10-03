from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy import inspect

from app.db import create_db_engine, read_session_factory, write_session_factory
from app.domain import Actor, create_request
from app.models import Application, Base, ExceptionRequest, Role, User


def test_schema_can_be_created(tmp_path):
    engine = create_db_engine(str(tmp_path / "test.db"))

    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "applications",
        "users",
        "user_roles",
        "exception_requests",
        "revisions",
        "decisions",
    }
    engine.dispose()


def test_timestamps_are_read_back_as_utc(tmp_path):
    engine = create_db_engine(str(tmp_path / "test.db"))
    Base.metadata.create_all(engine)
    amsterdam_summer = timezone(timedelta(hours=2))
    alice = Actor("alice", frozenset({Role.RELATIONSHIP_MANAGER}))

    with write_session_factory(engine)() as session:
        session.add_all([Application(id="APP-1", customer_name="A"), User(id="alice", name="A")])
        session.flush()
        request = create_request(
            alice,
            application_id="APP-1",
            discount_bps=10,
            reason="r",
            now=datetime(2026, 10, 5, 11, 0, tzinfo=amsterdam_summer),
        )
        session.add(request)
        request_id = request.id
        session.commit()

    with read_session_factory(engine)() as session:
        created_at = session.get(ExceptionRequest, request_id).created_at

    assert created_at == datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
    assert created_at.tzinfo is UTC
    engine.dispose()
