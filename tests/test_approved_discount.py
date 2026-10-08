"""The downstream read, from docs/api-contract.md, "Approved discount"."""

import pytest

from tests.helpers import as_user, decide, get, read_discount, request_id_for, revise


def in_force(client, application_id: str) -> tuple:
    """What the mortgage process is told: revision, discount and who approved it."""
    response = read_discount(client, application_id)
    assert response.status_code == 200
    body = response.json()
    return (body["revision_number"], body["approved_discount_bps"], body["decided_by"])


def in_force_in_detail(client, request_id: str) -> tuple:
    body = get(client, request_id).json()
    return (body["approved_revision_number"], body["approved_discount_bps"])


def in_force_in_list(client, request_id: str) -> int | None:
    rows = client.get("/requests", headers=as_user("alice")).json()
    return next(row["approved_discount_bps"] for row in rows if row["id"] == request_id)


def test_mortgage_process_reads_the_approved_discount(client):
    # Seed: APP-1004 was declined at 35 bps, revised to 20 bps and approved by carol.
    request_id = request_id_for(client, "APP-1004")
    first, approved = get(client, request_id).json()["revisions"]

    response = read_discount(client, "APP-1004")

    assert response.status_code == 200
    assert response.json() == {
        "application_id": "APP-1004",
        "request_id": request_id,
        "revision_number": 2,
        "approved_discount_bps": 20,
        "decided_by": "carol",
        "decided_at": approved["decision"]["decided_at"],
    }
    # Both decisions are carol's, so only the time tells them apart.
    assert first["decision"]["decided_at"] != approved["decision"]["decided_at"]


@pytest.mark.parametrize("application_id", ["APP-1001", "APP-1002", "APP-1003"])
def test_no_approved_discount_without_an_approved_request(client, application_id):
    # Seed: APP-1001 has no request, APP-1002 is PENDING, APP-1003 is DECLINED.
    response = read_discount(client, application_id)

    assert response.status_code == 404
    assert response.json()["code"] == "NO_APPROVED_DISCOUNT"


@pytest.mark.parametrize("declined", [False, True], ids=["pending", "declined"])
def test_approval_stays_in_force_while_a_later_revision_is_not_approved(client, declined):
    # Seed: APP-1004 is APPROVED at 20 bps in revision 2 by carol; version 4.
    request_id = request_id_for(client, "APP-1004")
    before = read_discount(client, "APP-1004").json()
    revised = revise(client, request_id, expected_version=4, discount_bps=30, reason="More.")
    assert revised.status_code == 201
    if declined:
        response = decide(
            client, request_id, user="dave", expected_version=5, outcome="DECLINED", comment="No."
        )
        assert (response.status_code, response.json()["status"]) == (201, "DECLINED")

    # Not the 30 bps nobody approved, and not "no approved discount" either (A10).
    assert read_discount(client, "APP-1004").json() == before
    assert in_force_in_detail(client, request_id) == (2, 20)


def test_later_approval_replaces_the_approval_in_force(client):
    # A lower discount replaces a higher one: the latest approval counts, not the largest.
    request_id = request_id_for(client, "APP-1004")
    replaced = get(client, request_id).json()["revisions"][1]
    revise(client, request_id, expected_version=4, discount_bps=15, reason="Customer accepts less.")

    approved = decide(
        client, request_id, user="dave", expected_version=5, outcome="APPROVED", comment="Fine."
    )

    assert approved.status_code == 201
    second, third = approved.json()["revisions"][1:]
    assert read_discount(client, "APP-1004").json() == {
        "application_id": "APP-1004",
        "request_id": request_id,
        "revision_number": 3,
        "approved_discount_bps": 15,
        "decided_by": "dave",
        "decided_at": third["decision"]["decided_at"],
    }
    assert in_force_in_detail(client, request_id) == (3, 15)
    # Revision 2 keeps its approval as it was written, with who, when and why; it
    # is only no longer the one in force (I7, I8).
    assert second == replaced
    assert second["decision"]["outcome"] == "APPROVED"


@pytest.mark.parametrize("declined", [False, True], ids=["pending", "declined"])
def test_second_approval_stays_in_force_not_the_first_or_the_largest(client, declined):
    # Approved at 20 bps, then at 15 bps, then 40 bps is asked for. Wrong answers
    # once the latest revision is not approved: 20 (the first approval, and the
    # largest), 40 (the latest revision), nothing.
    request_id = request_id_for(client, "APP-1004")
    revise(client, request_id, expected_version=4, discount_bps=15, reason="Second offer.")
    decide(client, request_id, user="dave", expected_version=5, outcome="APPROVED", comment="Fine.")
    assert in_force(client, "APP-1004") == (3, 15, "dave")

    revised = revise(client, request_id, expected_version=6, discount_bps=40, reason="Third offer.")
    assert (revised.status_code, revised.json()["status"]) == (201, "PENDING")
    if declined:
        response = decide(
            client, request_id, user="carol", expected_version=7, outcome="DECLINED", comment="No."
        )
        assert (response.status_code, response.json()["status"]) == (201, "DECLINED")

    assert in_force(client, "APP-1004") == (3, 15, "dave")
    assert in_force_in_detail(client, request_id) == (3, 15)
    assert in_force_in_list(client, request_id) == 15


def test_unknown_application_is_not_found(client):
    response = read_discount(client, "APP-9999")

    assert response.status_code == 404
    assert response.json()["code"] == "APPLICATION_NOT_FOUND"


@pytest.mark.parametrize("application_id", ["APP-1004", "APP-9999"])
def test_internal_user_cannot_read_the_approved_discount(client, application_id):
    response = read_discount(client, application_id, user="alice")

    assert response.status_code == 403
    assert response.json()["code"] == "ROLE_NOT_ALLOWED"
