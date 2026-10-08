"""Reading a request and deciding on it, from docs/api-contract.md."""

import uuid

import pytest

from tests.helpers import create, decide, get, is_utc, request_id_for

APPROVE = {"outcome": "APPROVED", "comment": "Fits policy."}


def pending_request(client) -> str:
    """Alice's request on APP-1001: PENDING, version 1, 20 bps."""
    response = create(client)
    assert response.status_code == 201
    return response.json()["id"]


def current_version(client, request_id: str) -> int:
    return get(client, request_id).json()["version"]


def test_request_detail_shows_the_full_history(client):
    # Seed: APP-1004 was created by alice, declined once, revised, then approved.
    response = get(client, request_id_for(client, "APP-1004"))

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["created_by"]) == ("APPROVED", "alice")
    assert [(r["number"], r["decision"]["outcome"]) for r in body["revisions"]] == [
        (1, "DECLINED"),
        (2, "APPROVED"),
    ]
    assert all(is_utc(r["decision"]["decided_at"]) for r in body["revisions"])


@pytest.mark.parametrize(
    ("application_id", "approval_in_force"),
    [("APP-1002", (None, None)), ("APP-1003", (None, None)), ("APP-1004", (2, 20))],
    ids=["pending", "declined", "approved"],
)
def test_request_detail_names_the_approval_in_force(client, application_id, approval_in_force):
    # Seed: APP-1002 is PENDING, APP-1003 is DECLINED, APP-1004 was approved at 20 bps
    # in revision 2, after revision 1 at 35 bps was declined.
    body = get(client, request_id_for(client, application_id)).json()

    assert (body["approved_revision_number"], body["approved_discount_bps"]) == approval_in_force


def test_unknown_request_is_not_found(client):
    response = get(client, str(uuid.uuid4()))

    assert response.status_code == 404
    assert response.json()["code"] == "REQUEST_NOT_FOUND"


@pytest.mark.parametrize("call", ["get", "decide"])
def test_malformed_request_id_is_a_validation_error(client, call):
    if call == "get":
        response = get(client, "not-a-uuid")
    else:
        response = decide(client, "not-a-uuid", expected_version=1, **APPROVE)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


# Deciding.


def test_reviewer_approves_a_pending_request(client):
    request_id = pending_request(client)

    response = decide(client, request_id, expected_version=1, **APPROVE)

    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["version"]) == ("APPROVED", 2)
    decision = body["revisions"][-1]["decision"]
    assert (decision["outcome"], decision["decided_by"], decision["comment"]) == (
        "APPROVED",
        "carol",
        "Fits policy.",
    )
    assert is_utc(decision["decided_at"])
    assert get(client, request_id).json() == body


def test_reviewer_declines_with_a_comment(client):
    request_id = pending_request(client)

    response = decide(
        client,
        request_id,
        user="dave",
        expected_version=1,
        outcome="DECLINED",
        comment="  Too high.  ",
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["version"]) == ("DECLINED", 2)
    [revision] = body["revisions"]
    assert (revision["number"], revision["discount_bps"], revision["reason"]) == (
        1,
        20,
        "Competing offer.",
    )
    assert (revision["decision"]["decided_by"], revision["decision"]["comment"]) == (
        "dave",
        "Too high.",
    )
    assert get(client, request_id).json() == body


@pytest.mark.parametrize("outcome", ["APPROVED", "DECLINED"])
@pytest.mark.parametrize(
    "comment", ["missing", None, "", "   "], ids=["missing", "null", "empty", "blank"]
)
def test_decision_needs_a_comment(client, outcome, comment):
    body = {"expected_version": 1, "outcome": outcome}
    if comment != "missing":
        body["comment"] = comment

    response = decide(client, pending_request(client), **body)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("outcome", ["APPROVED", "DECLINED"])
@pytest.mark.parametrize("length", [1, 1000])
def test_comment_at_its_length_limits_is_accepted(client, outcome, length):
    response = decide(
        client, pending_request(client), expected_version=1, outcome=outcome, comment="x" * length
    )

    assert response.status_code == 201
    assert response.json()["revisions"][-1]["decision"]["comment"] == "x" * length


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outcome", "PENDING"),
        ("outcome", " APPROVED "),
        ("expected_version", "1"),
        ("expected_version", True),
        ("expected_version", 1.0),
        ("expected_version", 0),
        ("comment", "x" * 1001),
        ("decided_by", "carol"),
    ],
)
def test_invalid_decision_is_rejected(client, field, value):
    body = {"expected_version": 1, **APPROVE, field: value}

    response = decide(client, pending_request(client), **body)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("field", ["expected_version", "outcome"])
def test_decision_with_a_missing_field_is_rejected(client, field):
    body = {k: v for k, v in ({"expected_version": 1} | APPROVE).items() if k != field}

    response = decide(client, pending_request(client), **body)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_relationship_manager_cannot_decide(client):
    response = decide(client, pending_request(client), user="bob", expected_version=1, **APPROVE)

    assert response.status_code == 403
    assert response.json()["code"] == "ROLE_NOT_ALLOWED"


def test_role_is_checked_before_the_request_is_looked_up(client):
    response = decide(client, str(uuid.uuid4()), user="bob", expected_version=1, **APPROVE)

    assert response.status_code == 403
    assert response.json()["code"] == "ROLE_NOT_ALLOWED"


def test_creator_cannot_decide_on_their_own_request(client):
    # Seed: APP-1005 is PENDING, created by dave, who is also a reviewer.
    request_id = request_id_for(client, "APP-1005")

    response = decide(
        client,
        request_id,
        user="dave",
        expected_version=current_version(client, request_id),
        **APPROVE,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FOUR_EYES_VIOLATION"


def test_stale_version_cannot_approve(client):
    response = decide(client, pending_request(client), expected_version=2, **APPROVE)

    assert response.status_code == 409
    assert response.json()["code"] == "STALE_VERSION"


@pytest.mark.parametrize(
    ("application_id", "user", "version_offset", "status", "code"),
    [
        ("APP-1004", "carol", -1, 409, "STALE_VERSION"),
        ("APP-1004", "carol", 0, 409, "INVALID_STATE"),
        ("APP-1003", "carol", 0, 409, "INVALID_STATE"),
        ("APP-1005", "dave", 1, 403, "FOUR_EYES_VIOLATION"),
    ],
    ids=[
        "stale-on-approved",
        "current-on-approved",
        "current-on-declined",
        "own-request-with-stale-version",
    ],
)
def test_business_checks_are_reported_in_contract_order(
    client, application_id, user, version_offset, status, code
):
    # Seed: APP-1003 is DECLINED, APP-1004 is APPROVED, APP-1005 is PENDING by dave.
    request_id = request_id_for(client, application_id)
    version = current_version(client, request_id) + version_offset

    response = decide(client, request_id, user=user, expected_version=version, **APPROVE)

    assert response.status_code == status
    assert response.json()["code"] == code


def test_retried_decision_is_reported_as_stale(client):
    request_id = pending_request(client)
    first = decide(client, request_id, expected_version=1, **APPROVE)
    assert first.status_code == 201

    retry = decide(client, request_id, expected_version=1, **APPROVE)

    assert retry.status_code == 409
    assert retry.json()["code"] == "STALE_VERSION"
    assert get(client, request_id).json() == first.json()


def test_decision_on_unknown_request_is_not_found(client):
    response = decide(client, str(uuid.uuid4()), expected_version=1, **APPROVE)

    assert response.status_code == 404
    assert response.json()["code"] == "REQUEST_NOT_FOUND"


def test_rejected_decision_changes_nothing(client):
    request_id = pending_request(client)
    before = get(client, request_id).json()

    rejected = decide(client, request_id, expected_version=2, **APPROVE)

    assert rejected.status_code == 409
    assert get(client, request_id).json() == before
