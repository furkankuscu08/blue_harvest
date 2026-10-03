"""The main stories through the API, from docs/state-model.md, "Example"."""

from tests.helpers import create, decide, get, read_discount, revise


def test_request_is_approved_and_read_downstream(client):
    created = create(client, user="alice")
    assert created.status_code == 201
    request_id = created.json()["id"]

    pending = read_discount(client, "APP-1001")
    assert pending.status_code == 404
    assert pending.json()["code"] == "NO_APPROVED_DISCOUNT"

    approved = decide(
        client,
        request_id,
        user="carol",
        expected_version=1,
        outcome="APPROVED",
        comment="Matches a documented competing offer.",
    )
    assert approved.status_code == 201

    discount = read_discount(client, "APP-1001")
    assert discount.status_code == 200
    assert discount.json() == {
        "application_id": "APP-1001",
        "request_id": request_id,
        "revision_number": 1,
        "approved_discount_bps": 20,
        "decided_by": "carol",
        "decided_at": approved.json()["revisions"][0]["decision"]["decided_at"],
    }


def test_declined_request_is_revised_approved_and_read_downstream(client):
    # Expected values are written out, not read from another response, so the
    # detail and the downstream read cannot agree on the wrong revision.
    created = create(
        client,
        {"application_id": "APP-1001", "discount_bps": 35, "reason": "Competing offer."},
    )
    assert created.status_code == 201
    request_id = created.json()["id"]

    declined = decide(
        client,
        request_id,
        user="dave",
        expected_version=1,
        outcome="DECLINED",
        comment="Above what the competing offer justifies.",
    )
    assert (declined.status_code, declined.json()["status"]) == (201, "DECLINED")
    assert read_discount(client, "APP-1001").json()["code"] == "NO_APPROVED_DISCOUNT"

    revised = revise(
        client, request_id, expected_version=2, discount_bps=20, reason="Matches the offer."
    )
    assert (revised.status_code, revised.json()["status"]) == (201, "PENDING")
    assert read_discount(client, "APP-1001").json()["code"] == "NO_APPROVED_DISCOUNT"

    approved = decide(
        client,
        request_id,
        user="carol",
        expected_version=3,
        outcome="APPROVED",
        comment="Matches a documented competing offer.",
    )
    assert (approved.status_code, approved.json()["version"]) == (201, 4)

    discount = read_discount(client, "APP-1001")
    assert discount.status_code == 200
    body = discount.json()
    assert (body["revision_number"], body["approved_discount_bps"], body["decided_by"]) == (
        2,
        20,
        "carol",
    )

    history = get(client, request_id).json()["revisions"]
    assert [(r["number"], r["discount_bps"], r["decision"]["outcome"]) for r in history] == [
        (1, 35, "DECLINED"),
        (2, 20, "APPROVED"),
    ]
    assert body["decided_at"] == history[1]["decision"]["decided_at"]
