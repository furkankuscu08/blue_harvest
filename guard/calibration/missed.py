"""Calibration: a valid test that does not touch the broken rule. It must be missed."""

from datetime import UTC, datetime

from app.domain import Actor, create_request, decide
from app.models import Outcome, Role, Status

ALICE = Actor("alice", frozenset({Role.RELATIONSHIP_MANAGER}))
CAROL = Actor("carol", frozenset({Role.REVIEWER}))
NOW = datetime(2026, 10, 5, tzinfo=UTC)


def test_approval_with_the_current_version_succeeds():
    request = create_request(
        ALICE, application_id="APP-1001", discount_bps=35, reason="Offer.", now=NOW
    )

    decide(request, CAROL, expected_version=1, outcome=Outcome.APPROVED, comment=None, now=NOW)

    assert request.status == Status.APPROVED
