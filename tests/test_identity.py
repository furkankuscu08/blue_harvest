"""Caller identity and the error body, from docs/api-contract.md, "Conventions"."""

import pytest


@pytest.mark.parametrize("headers", [{}, {"X-User-Id": "mallory"}, {"X-User-Id": ""}])
def test_missing_or_unknown_user_is_rejected(client, headers):
    response = client.get("/applications", headers=headers)

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "UNKNOWN_USER"
    assert body["message"]
    assert body["details"] is None


def test_known_user_lists_the_seed_applications(client):
    response = client.get("/applications", headers={"X-User-Id": "alice"})

    assert response.status_code == 200
    applications = response.json()
    assert [a["id"] for a in applications] == [
        "APP-1001",
        "APP-1002",
        "APP-1003",
        "APP-1004",
        "APP-1005",
    ]
    assert all(a["customer_name"] for a in applications)
    request_ids = [a["request_id"] for a in applications]
    assert request_ids[0] is None
    assert all(isinstance(request_id, str) for request_id in request_ids[1:])
