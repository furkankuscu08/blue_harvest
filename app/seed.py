"""Seed data from docs/api-contract.md, section "Seed data".

Requests are built with the same domain functions as the API, so every seeded
history is one that real operations can reach.

    python -m app.seed            # seed only if the database is empty
    python -m app.seed --reset    # empty the database and seed it again

The functions here do not commit; the caller owns the transaction.
"""

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import create_db_engine, write_session_factory
from app.domain import Actor, create_request, decide, revise
from app.models import Application, Base, Outcome, Role, User, UserRole

USERS = [
    ("alice", "Alice", [Role.RELATIONSHIP_MANAGER]),
    ("bob", "Bob", [Role.RELATIONSHIP_MANAGER]),
    ("carol", "Carol", [Role.REVIEWER]),
    ("dave", "Dave", [Role.RELATIONSHIP_MANAGER, Role.REVIEWER]),
    ("mortgage-process", "Mortgage process", [Role.MORTGAGE_PROCESS]),
]

# Fictional customers.
APPLICATIONS = [
    ("APP-1001", "J. de Vries"),
    ("APP-1002", "M. Jansen"),
    ("APP-1003", "S. Bakker"),
    ("APP-1004", "L. Visser"),
    ("APP-1005", "P. Smit"),
]


def seed_if_empty(session: Session) -> bool:
    """Seed an empty database. Returns False and changes nothing otherwise."""
    if session.scalar(select(User.id).limit(1)) is not None:
        return False
    _seed(session)
    return True


def reset(session: Session) -> None:
    """Delete every row and seed again, in the caller's transaction."""
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    _seed(session)


def _seed(session: Session) -> None:
    for user_id, name, roles in USERS:
        session.add(User(id=user_id, name=name, roles=[UserRole(role=role) for role in roles]))
    for application_id, customer_name in APPLICATIONS:
        session.add(Application(id=application_id, customer_name=customer_name))
    session.flush()

    actors = {user_id: Actor(user_id, frozenset(roles)) for user_id, _, roles in USERS}
    alice, bob, carol, dave = (actors[u] for u in ("alice", "bob", "carol", "dave"))
    start = datetime.now(UTC) - timedelta(days=1)

    def at(hours: int) -> datetime:
        return start + timedelta(hours=hours)

    # APP-1002: pending, created by alice.
    pending = create_request(
        alice, application_id="APP-1002", discount_bps=25, reason="Loyal customer.", now=at(1)
    )

    # APP-1003: declined, created by bob.
    declined = create_request(
        bob, application_id="APP-1003", discount_bps=60, reason="Customer asked.", now=at(2)
    )
    decide(
        declined,
        carol,
        expected_version=1,
        outcome=Outcome.DECLINED,
        comment="No competing offer on file.",
        now=at(3),
    )

    # APP-1004: declined once, revised, then approved; created by alice.
    approved = create_request(
        alice,
        application_id="APP-1004",
        discount_bps=35,
        reason="Competing offer from another lender.",
        now=at(4),
    )
    decide(
        approved,
        carol,
        expected_version=1,
        outcome=Outcome.DECLINED,
        comment="Above what the competing offer justifies.",
        now=at(5),
    )
    revise(
        approved,
        alice,
        expected_version=2,
        discount_bps=20,
        reason="Matches the competing offer.",
        now=at(6),
    )
    decide(approved, carol, expected_version=3, outcome=Outcome.APPROVED, comment=None, now=at(7))

    # APP-1005: pending, created by dave, who also holds the reviewer role.
    held_by_dave = create_request(
        dave, application_id="APP-1005", discount_bps=15, reason="Rate match.", now=at(8)
    )

    session.add_all([pending, declined, approved, held_by_dave])


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the pricing exception database.")
    parser.add_argument("--reset", action="store_true", help="empty the database first")
    args = parser.parse_args()

    engine = create_db_engine(Settings.from_env().database_path)
    Base.metadata.create_all(engine)
    with write_session_factory(engine)() as session:
        if args.reset:
            reset(session)
            message = "Database emptied and seeded again."
        elif seed_if_empty(session):
            message = "Database seeded."
        else:
            message = "Database is not empty; nothing changed."
        session.commit()
    engine.dispose()
    print(message)


if __name__ == "__main__":
    main()
