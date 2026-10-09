"""Stories through the API: an approval the mortgage process reads, and what follows it."""

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


def test_negotiation_continues_after_an_approval(client):
    # docs/state-model.md, "The approval in force". The mortgage process reads an
    # approved discount at every step, never the proposal that is still open.
    def in_force() -> tuple:
        body = read_discount(client, "APP-1001").json()
        return (body["revision_number"], body["approved_discount_bps"], body["decided_by"])

    request_id = create(client, user="alice").json()["id"]
    first = decide(
        client, request_id, user="carol", expected_version=1, outcome="APPROVED", comment="Fine."
    )
    assert (first.status_code, in_force()) == (201, (1, 20, "carol"))

    more = revise(client, request_id, expected_version=2, discount_bps=30, reason="Customer asks.")
    assert (more.status_code, more.json()["status"], in_force()) == (
        201,
        "PENDING",
        (1, 20, "carol"),
    )

    declined = decide(
        client,
        request_id,
        user="carol",
        expected_version=3,
        outcome="DECLINED",
        comment="Too much.",
    )
    assert (declined.status_code, declined.json()["status"]) == (201, "DECLINED")
    assert in_force() == (1, 20, "carol")

    middle = revise(client, request_id, expected_version=4, discount_bps=25, reason="Meet halfway.")
    assert (middle.status_code, in_force()) == (201, (1, 20, "carol"))

    second = decide(
        client, request_id, user="dave", expected_version=5, outcome="APPROVED", comment="Agreed."
    )
    assert (second.status_code, second.json()["status"]) == (201, "APPROVED")
    assert in_force() == (3, 25, "dave")

    again = revise(client, request_id, expected_version=6, discount_bps=40, reason="One more try.")
    assert (again.status_code, in_force()) == (201, (3, 25, "dave"))

    detail = get(client, request_id).json()
    assert (detail["status"], detail["version"]) == ("PENDING", 7)
    assert (detail["approved_revision_number"], detail["approved_discount_bps"]) == (3, 25)
    assert [
        (r["number"], r["discount_bps"], r["decision"] and r["decision"]["outcome"])
        for r in detail["revisions"]
    ] == [(1, 20, "APPROVED"), (2, 30, "DECLINED"), (3, 25, "APPROVED"), (4, 40, None)]
    downstream = read_discount(client, "APP-1001").json()
    assert downstream["decided_at"] == detail["revisions"][2]["decision"]["decided_at"]
