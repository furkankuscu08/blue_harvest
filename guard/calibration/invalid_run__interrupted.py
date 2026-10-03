"""Calibration: pytest stops after the first test. The partial report must not count.

The first test would be caught on its own; the run as a whole is still an invalid run.
"""

from datetime import UTC, datetime

import pytest

from app.domain import Actor, DomainError, ErrorCode, create_request, decide, revise
from app.models import Outcome, Role

ALICE = Actor("alice", frozenset({Role.RELATIONSHIP_MANAGER}))
CAROL = Actor("carol", frozenset({Role.REVIEWER}))
NOW = datetime(2026, 10, 5, tzinfo=UTC)


@pytest.fixture
def stop_the_run():
    yield
    pytest.exit("stopped on purpose", returncode=2)


def test_approval_with_an_old_version_is_rejected(stop_the_run):
    request = create_request(
        ALICE, application_id="APP-1001", discount_bps=35, reason="Offer.", now=NOW
    )
    revise(request, ALICE, expected_version=1, discount_bps=50, reason="Higher.", now=NOW)

    with pytest.raises(DomainError) as error:
        decide(request, CAROL, expected_version=1, outcome=Outcome.APPROVED, comment=None, now=NOW)

    assert error.value.code == ErrorCode.STALE_VERSION


def test_never_reached():
    assert True
