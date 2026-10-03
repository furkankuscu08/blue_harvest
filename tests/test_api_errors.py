"""Error handling from docs/api-contract.md, "Errors" and "Order of checks"."""

import uuid

import pytest

from tests.helpers import VALID_CREATE, as_user, create, revise

ANY_ID = uuid.uuid4()
DECISION = {"expected_version": 1, "outcome": "APPROVED", "comment": "Fits policy."}
REVISION = {"expected_version": 1, "discount_bps": 30, "reason": "Second competing offer."}


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", f"/requests/{ANY_ID}", None),
        ("POST", f"/requests/{ANY_ID}/revisions", REVISION),
        ("POST", f"/requests/{ANY_ID}/decisions", DECISION),
        ("GET", "/applications/APP-1004/approved-discount", None),
    ],
    ids=["detail", "revise", "decide", "approved-discount"],
)
@pytest.mark.parametrize(
    "headers",
    [{}, {"X-User-Id": ""}, {"X-User-Id": "mallory"}],
    ids=["missing", "empty", "unknown"],
)
def test_every_endpoint_needs_a_known_user(client, method, path, body, headers):
    response = client.request(method, path, json=body, headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "UNKNOWN_USER"


@pytest.mark.parametrize("call", ["create", "revise"])
def test_unknown_user_is_reported_before_an_invalid_body(client, call):
    if call == "create":
        response = create(client, VALID_CREATE | {"discount_bps": "twenty"}, user="mallory")
    else:
        response = revise(
            client, str(ANY_ID), user="mallory", **REVISION | {"discount_bps": "twenty"}
        )

    assert response.status_code == 401
    assert response.json()["code"] == "UNKNOWN_USER"


@pytest.mark.parametrize(
    ("user", "path", "body"),
    [
        ("alice", f"/requests/{ANY_ID}/revisions", REVISION | {"discount_bps": "thirty"}),
        ("carol", f"/requests/{ANY_ID}/decisions", DECISION | {"expected_version": "one"}),
    ],
    ids=["revise", "decide"],
)
def test_body_is_validated_before_the_request_is_looked_up(client, user, path, body):
    response = client.post(path, json=body, headers=as_user(user))

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_validation_error_lists_the_fields_without_echoing_input(client):
    response = create(client, VALID_CREATE | {"discount_bps": "secret-20"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert [error["field"] for error in body["details"]["errors"]] == ["discount_bps"]
    assert all(error["message"] for error in body["details"]["errors"])
    assert "secret-20" not in response.text


@pytest.mark.parametrize(
    "content", [b"{not json", b'{"reason": "\xff"}'], ids=["not-json", "not-utf8"]
)
def test_malformed_body_is_a_validation_error(client, content):
    response = client.post(
        "/requests",
        headers=as_user("alice", key="key-1") | {"Content-Type": "application/json"},
        content=content,
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert [error["field"] for error in body["details"]["errors"]] == ["body"]
