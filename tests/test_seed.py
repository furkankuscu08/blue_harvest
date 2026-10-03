"""Seed data from docs/api-contract.md, section "Seed data"."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.db import create_db_engine, read_session_factory, write_session_factory
from app.domain import Actor, create_request
from app.models import Application, Base, ExceptionRequest, Role, User
from app.seed import reset, seed_if_empty

EXPECTED_REQUESTS = {
    "APP-1001": None,
    "APP-1002": ("PENDING", 1, 1, "alice"),
    "APP-1003": ("DECLINED", 1, 2, "bob"),
    "APP-1004": ("APPROVED", 2, 4, "alice"),
    "APP-1005": ("PENDING", 1, 1, "dave"),
}


@pytest.fixture
def engine(tmp_path):
    engine = create_db_engine(str(tmp_path / "test.db"))
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def seed(engine) -> bool:
    with write_session_factory(engine)() as session:
        seeded = seed_if_empty(session)
        session.commit()
    return seeded


def request_states(engine) -> dict:
    """Per application: status, number of revisions, version and creator, or None."""
    with read_session_factory(engine)() as session:
        states = {}
        for application in session.scalars(select(Application)):
            request = session.scalar(
                select(ExceptionRequest).where(ExceptionRequest.application_id == application.id)
            )
            states[application.id] = request and (
                request.status,
                len(request.revisions),
                request.version,
                request.created_by,
            )
        return states


def row_counts(engine) -> dict[str, int]:
    with read_session_factory(engine)() as session:
        return {
            table.name: session.scalar(select(func.count()).select_from(table))
            for table in Base.metadata.sorted_tables
        }


def test_seed_sets_up_each_application_in_its_documented_state(engine):
    seed(engine)

    assert request_states(engine) == EXPECTED_REQUESTS


def test_seeded_approved_request_was_declined_revised_then_approved(engine):
    seed(engine)

    with read_session_factory(engine)() as session:
        request = session.scalar(
            select(ExceptionRequest).where(ExceptionRequest.application_id == "APP-1004")
        )
        history = [(r.number, r.decision.outcome, r.decision.decided_by) for r in request.revisions]

    assert history == [(1, "DECLINED", "carol"), (2, "APPROVED", "carol")]


def test_seed_creates_the_documented_users_and_roles(engine):
    seed(engine)

    with read_session_factory(engine)() as session:
        users = {user.id: {r.role for r in user.roles} for user in session.scalars(select(User))}

    assert users == {
        "alice": {Role.RELATIONSHIP_MANAGER},
        "bob": {Role.RELATIONSHIP_MANAGER},
        "carol": {Role.REVIEWER},
        "dave": {Role.RELATIONSHIP_MANAGER, Role.REVIEWER},
        "mortgage-process": {Role.MORTGAGE_PROCESS},
    }


def test_seeding_again_adds_no_rows(engine):
    assert seed(engine) is True
    before = row_counts(engine)

    assert seed(engine) is False
    assert row_counts(engine) == before


def test_reset_restores_the_seed_state(engine):
    seed(engine)
    seeded = row_counts(engine)
    with write_session_factory(engine)() as session:
        alice = Actor("alice", frozenset({Role.RELATIONSHIP_MANAGER}))
        session.add(
            create_request(
                alice,
                application_id="APP-1001",
                discount_bps=10,
                reason="Changed after seeding.",
                now=datetime.now(UTC),
            )
        )
        session.commit()

    with write_session_factory(engine)() as session:
        reset(session)
        session.commit()

    assert request_states(engine) == EXPECTED_REQUESTS
    assert row_counts(engine) == seeded
