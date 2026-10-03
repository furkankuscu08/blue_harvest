"""Regression tests for the version check on approval (I3, I5), tested without a database."""

from datetime import UTC, datetime

import pytest

from app.domain import Actor, DomainError, ErrorCode, create_request, decide, revise
from app.models import Outcome, Role

ALICE = Actor("alice", frozenset({Role.RELATIONSHIP_MANAGER}))
CAROL = Actor("carol", frozenset({Role.REVIEWER}))

T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 10, 5, 11, 0, tzinfo=UTC)


def snapshot(request) -> tuple:
    return (
        request.status,
        request.version,
        request.updated_at,
        [(r.number, r.discount_bps, r.reason, r.decision) for r in request.revisions],
    )


@pytest.mark.parametrize("expected_version", [1, 3], ids=["older", "newer"])
def test_stale_version_cannot_approve(expected_version):
    # The reviewer saw version 1, but the manager has since revised to version 2.
    request = create_request(
        ALICE, application_id="APP-1001", discount_bps=35, reason="Competing offer.", now=T0
    )
    revise(request, ALICE, expected_version=1, discount_bps=50, reason="Higher ask.", now=T1)
    before = snapshot(request)

    with pytest.raises(DomainError) as error:
        decide(
            request,
            CAROL,
            expected_version=expected_version,
            outcome=Outcome.APPROVED,
            comment=None,
            now=T2,
        )

    assert error.value.code == ErrorCode.STALE_VERSION
    assert snapshot(request) == before


@pytest.mark.parametrize("first_outcome", list(Outcome))
def test_stale_version_is_reported_before_state_when_approving(first_outcome):
    # A stale version is always STALE_VERSION, even when the status also forbids the action.
    request = create_request(
        ALICE, application_id="APP-1001", discount_bps=35, reason="Competing offer.", now=T0
    )
    decide(request, CAROL, expected_version=1, outcome=first_outcome, comment="x", now=T1)
    before = snapshot(request)

    with pytest.raises(DomainError) as error:
        decide(
            request, CAROL, expected_version=1, outcome=Outcome.APPROVED, comment=None, now=T2
        )

    assert error.value.code == ErrorCode.STALE_VERSION
    assert snapshot(request) == before
