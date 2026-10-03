"""Revising a request, from docs/api-contract.md, "Revise a request"."""

import uuid

import pytest

from tests.helpers import get, is_utc, request_id_for, revise

CHANGE = {"discount_bps": 30, "reason": "Second competing offer."}


def current_version(client, request_id: str) -> int:
    return get(client, request_id).json()["version"]


def test_creator_revises_a_declined_request(client):
    # Seed: APP-1003 was created by bob and declined by carol; version 2.
    request_id = request_id_for(client, "APP-1003")
    before = get(client, request_id).json()

    response = revise(client, request_id, user="bob", expected_version=2, **CHANGE)

    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["version"]) == ("PENDING", 3)
    assert (body["created_by"], body["created_at"]) == ("bob", before["created_at"])
    first, second = body["revisions"]
    assert first == before["revisions"][0]
    assert (second["number"], second["discount_bps"], second["reason"], second["decision"]) == (
        2,
        30,
        "Second competing offer.",
        None,
    )
    assert is_utc(second["created_at"])
    assert body["updated_at"] == second["created_at"]
    assert get(client, request_id).json() == body


def test_creator_revises_a_pending_request(client):
    # Seed: APP-1002 is PENDING at 25 bps, created by alice; version 1.
    request_id = request_id_for(client, "APP-1002")
    [undecided] = get(client, request_id).json()["revisions"]

    response = revise(client, request_id, expected_version=1, **CHANGE)

    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["version"]) == ("PENDING", 2)
    first, second = body["revisions"]
    assert first == undecided
    assert (first["discount_bps"], first["decision"]) == (25, None)
    assert (second["number"], second["discount_bps"], second["decision"]) == (2, 30, None)


def test_creator_who_is_also_a_reviewer_revises_their_own_request(client):
    # Seed: APP-1005 is PENDING, created by dave, who holds both roles.
    request_id = request_id_for(client, "APP-1005")

    response = revise(client, request_id, user="dave", expected_version=1, **CHANGE)

    assert response.status_code == 201
    assert response.json()["revisions"][-1]["discount_bps"] == 30


@pytest.mark.parametrize(
    ("discount_bps", "reason", "stored_reason"),
    [(1, "x", "x"), (200, "x" * 1000, "x" * 1000), (30, "  Second offer.  ", "Second offer.")],
    ids=["lowest", "highest", "trimmed"],
)
def test_revision_within_the_input_rules_is_accepted(client, discount_bps, reason, stored_reason):
    request_id = request_id_for(client, "APP-1002")

    response = revise(
        client, request_id, expected_version=1, discount_bps=discount_bps, reason=reason
    )

    assert response.status_code == 201
    revision = response.json()["revisions"][-1]
    assert (revision["discount_bps"], revision["reason"]) == (discount_bps, stored_reason)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("discount_bps", "30"),
        ("discount_bps", 30.0),
        ("discount_bps", True),
        ("discount_bps", 0),
        ("discount_bps", 201),
        ("reason", ""),
        ("reason", "   "),
        ("reason", "x" * 1001),
        ("expected_version", "1"),
        ("expected_version", 1.0),
        ("expected_version", True),
        ("expected_version", 0),
        ("created_by", "bob"),
    ],
)
def test_invalid_revision_is_rejected(client, field, value):
    body = {"expected_version": 1, **CHANGE, field: value}

    response = revise(client, request_id_for(client, "APP-1002"), **body)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("field", ["expected_version", "discount_bps", "reason"])
def test_revision_with_a_missing_field_is_rejected(client, field):
    body = {k: v for k, v in ({"expected_version": 1} | CHANGE).items() if k != field}

    response = revise(client, request_id_for(client, "APP-1002"), **body)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_malformed_request_id_is_a_validation_error(client):
    response = revise(client, "not-a-uuid", expected_version=1, **CHANGE)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_reviewer_cannot_revise(client):
    response = revise(
        client, request_id_for(client, "APP-1002"), user="carol", expected_version=1, **CHANGE
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ROLE_NOT_ALLOWED"


def test_role_is_checked_before_the_request_is_looked_up(client):
    response = revise(client, str(uuid.uuid4()), user="carol", expected_version=1, **CHANGE)

    assert response.status_code == 403
    assert response.json()["code"] == "ROLE_NOT_ALLOWED"


def test_manager_cannot_revise_another_managers_request(client):
    # Seed: APP-1003 was created by bob.
    request_id = request_id_for(client, "APP-1003")

    response = revise(
        client,
        request_id,
        user="alice",
        expected_version=current_version(client, request_id),
        **CHANGE,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "NOT_REQUEST_OWNER"


def test_stale_version_cannot_revise(client):
    response = revise(client, request_id_for(client, "APP-1002"), expected_version=2, **CHANGE)

    assert response.status_code == 409
    assert response.json()["code"] == "STALE_VERSION"


def test_approved_request_cannot_be_revised(client):
    # Seed: APP-1004 is APPROVED, created by alice.
    request_id = request_id_for(client, "APP-1004")

    response = revise(
        client, request_id, expected_version=current_version(client, request_id), **CHANGE
    )

    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE"


@pytest.mark.parametrize(
    ("application_id", "user", "version_offset", "status", "code"),
    [
        ("APP-1003", "alice", 1, 403, "NOT_REQUEST_OWNER"),
        ("APP-1004", "alice", -1, 409, "STALE_VERSION"),
    ],
    ids=["not-owner-with-stale-version", "stale-on-approved"],
)
def test_business_checks_are_reported_in_contract_order(
    client, application_id, user, version_offset, status, code
):
    # Seed: APP-1003 was created by bob, APP-1004 is APPROVED and created by alice.
    request_id = request_id_for(client, application_id)
    version = current_version(client, request_id) + version_offset

    response = revise(client, request_id, user=user, expected_version=version, **CHANGE)

    assert response.status_code == status
    assert response.json()["code"] == code


def test_retried_revision_is_reported_as_stale(client):
    request_id = request_id_for(client, "APP-1002")
    first = revise(client, request_id, expected_version=1, **CHANGE)
    assert first.status_code == 201

    retry = revise(client, request_id, expected_version=1, **CHANGE)

    assert retry.status_code == 409
    assert retry.json()["code"] == "STALE_VERSION"
    assert get(client, request_id).json() == first.json()


def test_revision_on_unknown_request_is_not_found(client):
    response = revise(client, str(uuid.uuid4()), expected_version=1, **CHANGE)

    assert response.status_code == 404
    assert response.json()["code"] == "REQUEST_NOT_FOUND"


def test_rejected_revision_changes_nothing(client):
    request_id = request_id_for(client, "APP-1002")
    before = get(client, request_id).json()

    rejected = revise(client, request_id, expected_version=2, **CHANGE)

    assert rejected.status_code == 409
    assert get(client, request_id).json() == before
