"""Creating a request, from docs/api-contract.md, "Create a request"."""

import pytest
from sqlalchemy import event

from app.models import IdempotencyRecord
from tests.helpers import (
    VALID_CREATE,
    add_application,
    create,
    decide,
    get,
    is_utc,
    request_id_for,
)


def test_relationship_manager_creates_a_pending_request(client):
    response = create(client)

    assert response.status_code == 201
    body = response.json()
    assert (body["application_id"], body["status"], body["version"], body["created_by"]) == (
        "APP-1001",
        "PENDING",
        1,
        "alice",
    )
    assert [
        (r["number"], r["discount_bps"], r["reason"], r["decision"]) for r in body["revisions"]
    ] == [(1, 20, "Competing offer.", None)]
    assert is_utc(body["created_at"])
    assert body["created_at"] == body["updated_at"] == body["revisions"][0]["created_at"]
    assert get(client, body["id"]).json() == body


def test_reviewer_cannot_create_a_request(client):
    response = create(client, user="carol")

    assert response.status_code == 403
    assert response.json()["code"] == "ROLE_NOT_ALLOWED"


@pytest.mark.parametrize("key", [None, "", "k" * 256], ids=["missing", "empty", "too-long"])
def test_invalid_idempotency_key_is_rejected(client, key):
    response = create(client, key=key)

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IDEMPOTENCY_KEY"


def test_idempotency_key_of_255_characters_is_accepted(client):
    assert create(client, key="k" * 255).status_code == 201


def test_invalid_key_is_reported_before_the_application_is_looked_up(client):
    response = create(client, VALID_CREATE | {"application_id": "APP-9999"}, key="")

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_IDEMPOTENCY_KEY"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("discount_bps", "20"),
        ("discount_bps", 20.0),
        ("discount_bps", True),
        ("discount_bps", 0),
        ("discount_bps", 201),
        ("reason", "   "),
        ("reason", "x" * 1001),
        ("decided_by", "carol"),
    ],
)
def test_invalid_field_is_rejected(client, field, value):
    response = create(client, VALID_CREATE | {field: value})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert [error["field"] for error in body["details"]["errors"]] == [field]


@pytest.mark.parametrize("field", ["application_id", "discount_bps", "reason"])
def test_missing_field_is_rejected(client, field):
    body = {k: v for k, v in VALID_CREATE.items() if k != field}

    response = create(client, body)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_discount_at_the_limit_is_accepted(client):
    assert create(client, VALID_CREATE | {"discount_bps": 200}).status_code == 201


@pytest.mark.parametrize("length", [1, 1000])
def test_reason_at_its_length_limits_is_accepted(client, length):
    response = create(client, VALID_CREATE | {"reason": "x" * length})

    assert response.status_code == 201
    assert response.json()["revisions"][0]["reason"] == "x" * length


def test_unknown_application_is_not_found(client):
    response = create(client, VALID_CREATE | {"application_id": "APP-9999"})

    assert response.status_code == 404
    assert response.json()["code"] == "APPLICATION_NOT_FOUND"


def test_second_request_for_an_application_is_rejected(client):
    response = create(client, VALID_CREATE | {"application_id": "APP-1002"})

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "REQUEST_ALREADY_EXISTS"
    assert body["details"] == {"request_id": request_id_for(client, "APP-1002")}


# Idempotency: one logical submission is one key and one fixed payload.


def test_same_key_and_fields_replays_the_original_response(client):
    first = create(client)

    second = create(client)

    assert second.status_code == 201
    assert second.json() == first.json()
    assert request_id_for(client, "APP-1001") == first.json()["id"]


def test_replay_returns_the_original_response_after_the_request_changed(client):
    first = create(client)
    request_id = first.json()["id"]
    approved = decide(
        client, request_id, expected_version=1, outcome="APPROVED", comment="Fits policy."
    )
    assert approved.status_code == 201

    replay = create(client)

    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert get(client, request_id).json() == approved.json()


@pytest.mark.parametrize(
    "change",
    [{"application_id": "APP-9999"}, {"discount_bps": 25}, {"reason": "Another reason."}],
    ids=["application_id", "discount_bps", "reason"],
)
def test_same_key_with_different_fields_is_rejected(client, change):
    create(client)

    response = create(client, VALID_CREATE | change)

    assert response.status_code == 422
    assert response.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_whitespace_around_reason_does_not_change_the_payload(client):
    first = create(client)

    second = create(client, VALID_CREATE | {"reason": "  Competing offer.  "})

    assert second.status_code == 201
    assert second.json() == first.json()


def test_idempotency_key_is_scoped_to_the_caller(client):
    add_application(client, "APP-2001")
    alices = VALID_CREATE
    bobs = VALID_CREATE | {"application_id": "APP-2001"}

    alice_first = create(client, alices, user="alice", key="shared")
    bob_first = create(client, bobs, user="bob", key="shared")

    assert (alice_first.status_code, bob_first.status_code) == (201, 201)
    assert create(client, alices, user="alice", key="shared").json() == alice_first.json()
    assert create(client, bobs, user="bob", key="shared").json() == bob_first.json()


def test_failed_create_is_not_stored(client):
    body = VALID_CREATE | {"application_id": "APP-2001"}
    failed = create(client, body)
    assert failed.status_code == 404
    add_application(client, "APP-2001")

    retried = create(client, body)

    assert retried.status_code == 201


class RecordNotStored(Exception):
    """Raised only by the test below, so no other failure can satisfy it."""


def test_request_is_not_stored_without_its_idempotency_record(client):
    def fail(*_args):
        raise RecordNotStored

    event.listen(IdempotencyRecord, "before_insert", fail)
    try:
        with pytest.raises(RecordNotStored):
            create(client)
    finally:
        event.remove(IdempotencyRecord, "before_insert", fail)

    assert request_id_for(client, "APP-1001") is None
