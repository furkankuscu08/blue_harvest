"""The downstream read, from docs/api-contract.md, "Approved discount"."""

import pytest

from tests.helpers import get, read_discount, request_id_for


def test_mortgage_process_reads_the_approved_discount(client):
    # Seed: APP-1004 is APPROVED. The values come from its approved revision.
    request_id = request_id_for(client, "APP-1004")
    approved = get(client, request_id).json()["revisions"][-1]

    response = read_discount(client, "APP-1004")

    assert response.status_code == 200
    assert response.json() == {
        "application_id": "APP-1004",
        "request_id": request_id,
        "revision_number": approved["number"],
        "approved_discount_bps": approved["discount_bps"],
        "decided_by": approved["decision"]["decided_by"],
        "decided_at": approved["decision"]["decided_at"],
    }


@pytest.mark.parametrize("application_id", ["APP-1001", "APP-1002", "APP-1003"])
def test_no_approved_discount_without_an_approved_request(client, application_id):
    # Seed: APP-1001 has no request, APP-1002 is PENDING, APP-1003 is DECLINED.
    response = read_discount(client, application_id)

    assert response.status_code == 404
    assert response.json()["code"] == "NO_APPROVED_DISCOUNT"


def test_unknown_application_is_not_found(client):
    response = read_discount(client, "APP-9999")

    assert response.status_code == 404
    assert response.json()["code"] == "APPLICATION_NOT_FOUND"


@pytest.mark.parametrize("application_id", ["APP-1004", "APP-9999"])
def test_internal_user_cannot_read_the_approved_discount(client, application_id):
    response = read_discount(client, application_id, user="alice")

    assert response.status_code == 403
    assert response.json()["code"] == "ROLE_NOT_ALLOWED"
