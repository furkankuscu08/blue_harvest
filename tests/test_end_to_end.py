"""The main story through the API: request, approve, read downstream."""

from tests.helpers import create, decide, read_discount


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
