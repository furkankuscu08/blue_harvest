"""Calibration: the reference test written again. The harness must report it as caught."""

from datetime import UTC, datetime

import pytest

from app.domain import Actor, DomainError, ErrorCode, create_request, decide, revise
from app.models import Outcome, Role

ALICE = Actor("alice", frozenset({Role.RELATIONSHIP_MANAGER}))
CAROL = Actor("carol", frozenset({Role.REVIEWER}))
NOW = datetime(2026, 10, 5, tzinfo=UTC)


def test_approval_with_an_old_version_is_rejected():
    request = create_request(
        ALICE, application_id="APP-1001", discount_bps=35, reason="Offer.", now=NOW
    )
    revise(request, ALICE, expected_version=1, discount_bps=50, reason="Higher.", now=NOW)

    with pytest.raises(DomainError) as error:
        decide(request, CAROL, expected_version=1, outcome=Outcome.APPROVED, comment=None, now=NOW)

    assert error.value.code == ErrorCode.STALE_VERSION
