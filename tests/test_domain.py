"""Domain rules from docs/state-model.md, tested without a database."""

import uuid
from datetime import UTC, datetime

import pytest

from app.domain import (
    Actor,
    DomainError,
    ErrorCode,
    approved_revision,
    create_request,
    decide,
    revise,
)
from app.models import ExceptionRequest, Outcome, Role, Status

# The seed users from docs/api-contract.md.
ALICE = Actor("alice", frozenset({Role.RELATIONSHIP_MANAGER}))
BOB = Actor("bob", frozenset({Role.RELATIONSHIP_MANAGER}))
CAROL = Actor("carol", frozenset({Role.REVIEWER}))
DAVE = Actor("dave", frozenset({Role.RELATIONSHIP_MANAGER, Role.REVIEWER}))
MORTGAGE_PROCESS = Actor("mortgage-process", frozenset({Role.MORTGAGE_PROCESS}))

T0 = datetime(2026, 10, 5, 9, 0, tzinfo=UTC)
T1 = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 10, 5, 11, 0, tzinfo=UTC)
T3 = datetime(2026, 10, 5, 11, 30, tzinfo=UTC)


def pending_request(by: Actor = ALICE) -> ExceptionRequest:
    """Version 1, revision 1, no decision."""
    return create_request(
        by, application_id="APP-1001", discount_bps=35, reason="Competing offer.", now=T0
    )


def declined_request() -> ExceptionRequest:
    """Version 2: alice's revision 1 declined by carol."""
    request = pending_request()
    decide(
        request, CAROL, expected_version=1, outcome=Outcome.DECLINED, comment="Too high.", now=T1
    )
    return request


def approved_request(by: Actor = ALICE) -> ExceptionRequest:
    """Version 2: revision 1 approved by carol."""
    request = pending_request(by=by)
    decide(
        request, CAROL, expected_version=1, outcome=Outcome.APPROVED, comment="Fits policy.", now=T1
    )
    return request


def revision_contents(request: ExceptionRequest) -> list[tuple]:
    """What a revision says. It never changes once written (I2)."""
    return [(r.number, r.discount_bps, r.reason, r.created_at) for r in request.revisions]


def snapshot(request: ExceptionRequest) -> tuple:
    """Everything a rejected call must leave unchanged (I4)."""
    return (
        request.id,
        request.application_id,
        request.created_by,
        request.created_at,
        request.status,
        request.version,
        request.updated_at,
        revision_contents(request),
        [
            (d.outcome, d.decided_by, d.decided_at, d.comment) if (d := r.decision) else None
            for r in request.revisions
        ],
    )


def assert_consistent(request: ExceptionRequest) -> None:
    """I8: status follows the latest revision. I3: every change added one to the version."""
    latest = request.revisions[-1]
    expected_status = Status.PENDING if latest.decision is None else Status(latest.decision.outcome)
    assert request.status == expected_status
    decisions = [r.decision for r in request.revisions if r.decision is not None]
    assert request.version == len(request.revisions) + len(decisions)
    assert [r.number for r in request.revisions] == list(range(1, len(request.revisions) + 1))


def assert_rejected(expected_code: ErrorCode, action) -> None:
    with pytest.raises(DomainError) as error:
        action()
    assert error.value.code == expected_code


def assert_rejected_without_change(request: ExceptionRequest, expected_code: ErrorCode, action):
    """The call fails with the expected code and changes nothing (I4)."""
    before = snapshot(request)

    assert_rejected(expected_code, action)

    assert snapshot(request) == before


# Used where the request is at version 2: any other expected version is a mismatch,
# whether older (the caller saw an earlier state) or newer.
VERSION_MISMATCH = pytest.mark.parametrize("expected_version", [1, 3], ids=["older", "newer"])


# Create


def test_manager_creates_pending_request_with_first_revision():
    request = create_request(
        ALICE, application_id="APP-1001", discount_bps=35, reason="Competing offer.", now=T0
    )

    assert uuid.UUID(request.id)
    assert request.application_id == "APP-1001"
    assert request.status == Status.PENDING
    assert request.version == 1
    assert request.created_by == "alice"
    assert request.created_at == request.updated_at == T0
    assert revision_contents(request) == [(1, 35, "Competing offer.", T0)]
    assert request.revisions[0].decision is None
    assert_consistent(request)


@pytest.mark.parametrize("actor", [CAROL, MORTGAGE_PROCESS], ids=["reviewer", "mortgage-process"])
def test_only_manager_can_create(actor):
    assert_rejected(ErrorCode.ROLE_NOT_ALLOWED, lambda: pending_request(by=actor))


# Revise


def test_creator_revises_pending_request():
    request = pending_request()
    before = revision_contents(request)

    revise(request, ALICE, expected_version=1, discount_bps=25, reason="Lower ask.", now=T1)

    assert revision_contents(request) == before + [(2, 25, "Lower ask.", T1)]
    assert request.revisions[-1].decision is None
    assert request.status == Status.PENDING
    assert request.version == 2
    assert request.updated_at == T1
    assert_consistent(request)


def test_creator_resubmits_declined_request():
    request = declined_request()
    before = revision_contents(request)

    revise(request, ALICE, expected_version=2, discount_bps=20, reason="Matches offer.", now=T2)

    assert revision_contents(request) == before + [(2, 20, "Matches offer.", T2)]
    assert request.status == Status.PENDING
    assert request.version == 3
    assert request.updated_at == T2
    assert_consistent(request)


def test_earlier_revisions_never_change():
    request = declined_request()
    first = request.revisions[0]

    def first_revision():
        d = first.decision
        return (first.number, first.discount_bps, first.reason, first.created_at) + (
            d.outcome,
            d.decided_by,
            d.decided_at,
            d.comment,
        )

    before = first_revision()

    revise(request, ALICE, expected_version=2, discount_bps=20, reason="Matches offer.", now=T2)
    decide(
        request, CAROL, expected_version=3, outcome=Outcome.APPROVED, comment="Fits policy.", now=T3
    )

    assert request.revisions[0] is first
    assert first_revision() == before


def test_approval_in_force_follows_the_revision_number_not_the_decision_time():
    # The server's clock was set back between the two approvals, so the second
    # one carries the earlier time. Wrong: the approval decided last by the clock.
    request = approved_request()
    revise(request, ALICE, expected_version=2, discount_bps=20, reason="Matches offer.", now=T2)
    decide(request, DAVE, expected_version=3, outcome=Outcome.APPROVED, comment="Fine.", now=T0)

    assert approved_revision(request).number == 2


def test_other_manager_cannot_revise():
    request = pending_request()

    assert_rejected_without_change(
        request,
        ErrorCode.NOT_REQUEST_OWNER,
        lambda: revise(request, BOB, expected_version=1, discount_bps=20, reason="x", now=T1),
    )


def test_reviewer_cannot_revise():
    request = pending_request()

    assert_rejected_without_change(
        request,
        ErrorCode.ROLE_NOT_ALLOWED,
        lambda: revise(request, CAROL, expected_version=1, discount_bps=20, reason="x", now=T1),
    )


@VERSION_MISMATCH
def test_stale_version_cannot_revise(expected_version):
    request = pending_request()
    revise(request, ALICE, expected_version=1, discount_bps=25, reason="Lower ask.", now=T1)

    assert_rejected_without_change(
        request,
        ErrorCode.STALE_VERSION,
        lambda: revise(
            request, ALICE, expected_version=expected_version, discount_bps=20, reason="x", now=T2
        ),
    )


def test_stale_version_cannot_revise_approved_request():
    request = approved_request()

    assert_rejected_without_change(
        request,
        ErrorCode.STALE_VERSION,
        lambda: revise(request, ALICE, expected_version=1, discount_bps=20, reason="x", now=T2),
    )


def test_creator_revises_approved_request():
    # A4: the negotiation can go on after an approval. I7: the approval is kept.
    request = approved_request()
    approval = request.revisions[0].decision
    kept = (approval.outcome, approval.decided_by, approval.decided_at, approval.comment)

    revise(request, ALICE, expected_version=2, discount_bps=40, reason="New offer.", now=T2)

    assert (request.status, request.version, request.updated_at) == (Status.PENDING, 3, T2)
    assert revision_contents(request) == [
        (1, 35, "Competing offer.", T0),
        (2, 40, "New offer.", T2),
    ]
    assert request.revisions[0].decision is approval
    assert (approval.outcome, approval.decided_by, approval.decided_at, approval.comment) == kept
    assert request.revisions[1].decision is None
    assert_consistent(request)


# Decide


def test_reviewer_approves_latest_revision():
    request = pending_request()
    revise(request, ALICE, expected_version=1, discount_bps=20, reason="Matches offer.", now=T1)
    before = revision_contents(request)

    decide(
        request, CAROL, expected_version=2, outcome=Outcome.APPROVED, comment="Fits policy.", now=T2
    )

    assert revision_contents(request) == before
    first, second = request.revisions
    assert first.decision is None
    decision = second.decision
    assert (decision.outcome, decision.decided_by, decision.decided_at, decision.comment) == (
        Outcome.APPROVED,
        "carol",
        T2,
        "Fits policy.",
    )
    assert request.status == Status.APPROVED
    assert request.version == 3
    assert request.updated_at == T2
    assert_consistent(request)


def test_reviewer_declines_latest_revision():
    request = pending_request()
    revise(request, ALICE, expected_version=1, discount_bps=20, reason="Matches offer.", now=T1)
    before = revision_contents(request)

    decide(
        request, CAROL, expected_version=2, outcome=Outcome.DECLINED, comment="Too high.", now=T2
    )

    assert revision_contents(request) == before
    first, second = request.revisions
    assert first.decision is None
    decision = second.decision
    assert (decision.outcome, decision.decided_by, decision.decided_at, decision.comment) == (
        Outcome.DECLINED,
        "carol",
        T2,
        "Too high.",
    )
    assert request.status == Status.DECLINED
    assert request.version == 3
    assert request.updated_at == T2
    assert_consistent(request)


@pytest.mark.parametrize("outcome", list(Outcome))
def test_creator_cannot_decide_own_request_even_as_reviewer(outcome):
    request = pending_request(by=DAVE)

    assert_rejected_without_change(
        request,
        ErrorCode.FOUR_EYES_VIOLATION,
        lambda: decide(request, DAVE, expected_version=1, outcome=outcome, comment="x", now=T1),
    )


@pytest.mark.parametrize("outcome", list(Outcome))
def test_manager_cannot_decide(outcome):
    request = pending_request()

    assert_rejected_without_change(
        request,
        ErrorCode.ROLE_NOT_ALLOWED,
        lambda: decide(request, BOB, expected_version=1, outcome=outcome, comment="x", now=T1),
    )


@VERSION_MISMATCH
def test_stale_version_cannot_approve(expected_version):
    # The manager changed the discount after version 1. Only version 2 may be approved.
    request = pending_request()
    revise(request, ALICE, expected_version=1, discount_bps=50, reason="Higher ask.", now=T1)

    assert_rejected_without_change(
        request,
        ErrorCode.STALE_VERSION,
        lambda: decide(
            request,
            CAROL,
            expected_version=expected_version,
            outcome=Outcome.APPROVED,
            comment="Fits policy.",
            now=T2,
        ),
    )


@VERSION_MISMATCH
def test_stale_version_cannot_decline(expected_version):
    request = pending_request()
    revise(request, ALICE, expected_version=1, discount_bps=50, reason="Higher ask.", now=T1)

    assert_rejected_without_change(
        request,
        ErrorCode.STALE_VERSION,
        lambda: decide(
            request,
            CAROL,
            expected_version=expected_version,
            outcome=Outcome.DECLINED,
            comment="No.",
            now=T2,
        ),
    )


@pytest.mark.parametrize("outcome", list(Outcome))
def test_declined_request_cannot_be_decided_again(outcome):
    request = declined_request()

    assert_rejected_without_change(
        request,
        ErrorCode.INVALID_STATE,
        lambda: decide(request, CAROL, expected_version=2, outcome=outcome, comment="x", now=T2),
    )


@pytest.mark.parametrize("outcome", list(Outcome))
def test_approved_request_cannot_be_decided_again(outcome):
    request = approved_request()

    assert_rejected_without_change(
        request,
        ErrorCode.INVALID_STATE,
        lambda: decide(request, CAROL, expected_version=2, outcome=outcome, comment="x", now=T2),
    )


# Order of checks: role, then relation to the request, then version, then, for a
# decision, state. A revise has no check on the state. Each scenario is set up so
# that every later check would fail too.


@pytest.mark.parametrize(
    "action",
    [
        # carol is not a manager, not the owner, and has a stale version.
        lambda r: revise(r, CAROL, expected_version=1, discount_bps=20, reason="x", now=T2),
        # alice is not a reviewer, is the creator, has a stale version, and the request is approved.
        lambda r: decide(
            r, ALICE, expected_version=1, outcome=Outcome.APPROVED, comment="Fits policy.", now=T2
        ),
    ],
    ids=["revise", "decide"],
)
def test_role_is_checked_first(action):
    request = approved_request(by=ALICE)

    assert_rejected_without_change(request, ErrorCode.ROLE_NOT_ALLOWED, lambda: action(request))


@pytest.mark.parametrize(
    ("creator", "action", "expected_code"),
    [
        (
            ALICE,
            lambda r: revise(r, BOB, expected_version=1, discount_bps=20, reason="x", now=T2),
            ErrorCode.NOT_REQUEST_OWNER,
        ),
        (
            DAVE,
            lambda r: decide(
                r,
                DAVE,
                expected_version=1,
                outcome=Outcome.APPROVED,
                comment="Fits policy.",
                now=T2,
            ),
            ErrorCode.FOUR_EYES_VIOLATION,
        ),
    ],
    ids=["owner", "four-eyes"],
)
def test_relation_is_checked_before_version_and_state(creator, action, expected_code):
    request = approved_request(by=creator)

    assert_rejected_without_change(request, expected_code, lambda: action(request))


def test_stale_version_is_reported_before_invalid_state():
    request = approved_request()

    assert_rejected_without_change(
        request,
        ErrorCode.STALE_VERSION,
        lambda: decide(
            request,
            CAROL,
            expected_version=1,
            outcome=Outcome.APPROVED,
            comment="Fits policy.",
            now=T2,
        ),
    )


# The worked example in docs/state-model.md


def test_worked_example_decline_revise_approve():
    request = create_request(
        ALICE,
        application_id="APP-1004",
        discount_bps=35,
        reason="Competing offer from another lender.",
        now=T0,
    )
    steps = []

    def record():
        assert_consistent(request)
        steps.append((request.status, request.revisions[-1].number, request.version))

    record()
    decide(
        request,
        CAROL,
        expected_version=1,
        outcome=Outcome.DECLINED,
        comment="Above what the competing offer justifies.",
        now=T1,
    )
    record()
    revise(
        request,
        ALICE,
        expected_version=2,
        discount_bps=20,
        reason="Matches the competing offer.",
        now=T2,
    )
    record()
    decide(
        request, CAROL, expected_version=3, outcome=Outcome.APPROVED, comment="Fits policy.", now=T3
    )
    record()

    assert steps == [
        (Status.PENDING, 1, 1),
        (Status.DECLINED, 1, 2),
        (Status.PENDING, 2, 3),
        (Status.APPROVED, 2, 4),
    ]
    assert [r.decision.outcome for r in request.revisions] == [Outcome.DECLINED, Outcome.APPROVED]
    assert request.revisions[-1].discount_bps == 20
