"""Listing requests and users, from docs/api-contract.md."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from app.models import ExceptionRequest
from tests.helpers import as_user, create, decide, get, request_id_for, revise

SUMMARY_FIELDS = {
    "id",
    "application_id",
    "status",
    "version",
    "created_by",
    "current_discount_bps",
    "approved_discount_bps",
    "updated_at",
}


def list_requests(client, *, user: str = "alice"):
    return client.get("/requests", headers=as_user(user))


def summary(row: dict) -> tuple:
    return (
        row["application_id"],
        row["status"],
        row["version"],
        row["created_by"],
        row["current_discount_bps"],
        row["approved_discount_bps"],
    )


def test_requests_are_listed_with_the_latest_change_first(client):
    response = list_requests(client)

    assert response.status_code == 200
    rows = response.json()
    # Seed: APP-1005 changed last, APP-1002 first. APP-1001 has no request.
    assert [summary(row) for row in rows] == [
        ("APP-1005", "PENDING", 1, "dave", 15, None),
        ("APP-1004", "APPROVED", 4, "alice", 20, 20),
        ("APP-1003", "DECLINED", 2, "bob", 60, None),
        ("APP-1002", "PENDING", 1, "alice", 25, None),
    ]
    for row in rows:
        assert set(row) == SUMMARY_FIELDS
        detail = get(client, request_id_for(client, row["application_id"])).json()
        assert (row["id"], row["updated_at"]) == (detail["id"], detail["updated_at"])


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ("create", ("APP-1001", "PENDING", 1, "alice", 20, None)),
        ("revise", ("APP-1003", "PENDING", 3, "bob", 40, None)),
        ("decide", ("APP-1002", "DECLINED", 2, "alice", 25, None)),
    ],
    ids=["create", "revise", "decide"],
)
def test_changed_request_moves_to_the_top_of_the_list(client, change, expected):
    if change == "create":
        changed = create(client)
    elif change == "revise":
        changed = revise(
            client,
            request_id_for(client, "APP-1003"),
            user="bob",
            expected_version=2,
            discount_bps=40,
            reason="Second competing offer.",
        )
    else:
        changed = decide(
            client,
            request_id_for(client, "APP-1002"),
            expected_version=1,
            outcome="DECLINED",
            comment="No competing offer on file.",
        )
    assert changed.status_code == 201

    rows = list_requests(client).json()

    assert len(rows) == (5 if change == "create" else 4)
    assert summary(rows[0]) == expected
    assert (rows[0]["id"], rows[0]["updated_at"]) == (
        changed.json()["id"],
        changed.json()["updated_at"],
    )


def test_list_shows_the_latest_proposal_next_to_the_approval_in_force(client):
    # Seed: APP-1004 is APPROVED at 20 bps; version 4. Without the second number
    # the row would read as a request with nothing approved.
    request_id = request_id_for(client, "APP-1004")
    revise(client, request_id, expected_version=4, discount_bps=30, reason="More.")
    assert summary(list_requests(client).json()[0]) == ("APP-1004", "PENDING", 5, "alice", 30, 20)

    declined = decide(
        client, request_id, user="dave", expected_version=5, outcome="DECLINED", comment="No."
    )

    assert declined.status_code == 201
    assert summary(list_requests(client).json()[0]) == ("APP-1004", "DECLINED", 6, "alice", 30, 20)


def test_requests_changed_at_the_same_moment_are_ordered_by_id(client):
    with client.app.state.write_sessions() as session:
        session.execute(update(ExceptionRequest).values(updated_at=datetime.now(UTC)))
        session.commit()

    ids = [row["id"] for row in list_requests(client).json()]

    assert len(ids) == 4
    assert ids == sorted(ids)


@pytest.mark.parametrize("user", ["alice", "carol", "mortgage-process"])
def test_any_known_user_lists_the_requests(client, user):
    response = list_requests(client, user=user)

    assert response.status_code == 200
    assert len(response.json()) == 4


@pytest.mark.parametrize("headers", [{}, {"X-User-Id": "mallory"}], ids=["missing", "unknown"])
def test_users_are_listed_without_a_known_caller(client, headers):
    response = client.get("/users", headers=headers)

    assert response.status_code == 200
    assert response.json() == [
        {"id": "alice", "name": "Alice", "roles": ["RELATIONSHIP_MANAGER"]},
        {"id": "bob", "name": "Bob", "roles": ["RELATIONSHIP_MANAGER"]},
        {"id": "carol", "name": "Carol", "roles": ["REVIEWER"]},
        {"id": "dave", "name": "Dave", "roles": ["RELATIONSHIP_MANAGER", "REVIEWER"]},
        {"id": "mortgage-process", "name": "Mortgage process", "roles": ["MORTGAGE_PROCESS"]},
    ]
