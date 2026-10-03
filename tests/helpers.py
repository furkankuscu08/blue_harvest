"""API calls the tests make often. Defaults follow the seed data."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from httpx import Response

from app.models import Application

VALID_CREATE = {"application_id": "APP-1001", "discount_bps": 20, "reason": "Competing offer."}


def as_user(user_id: str, key: str | None = None) -> dict[str, str]:
    headers = {"X-User-Id": user_id}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def is_utc(timestamp: str) -> bool:
    return datetime.fromisoformat(timestamp).utcoffset() == timedelta(0)


def add_application(client: TestClient, application_id: str) -> None:
    """An application with no request, beyond the one the seed provides."""
    with client.app.state.write_sessions() as session:
        session.add(Application(id=application_id, customer_name="Added by a test"))
        session.commit()


def request_id_for(client: TestClient, application_id: str) -> str | None:
    applications = client.get("/applications", headers=as_user("alice")).json()
    return next(a["request_id"] for a in applications if a["id"] == application_id)


def create(
    client: TestClient, body: dict | None = None, *, user: str = "alice", key: str | None = "key-1"
) -> Response:
    return client.post(
        "/requests", headers=as_user(user, key), json=VALID_CREATE if body is None else body
    )


def get(client: TestClient, request_id: str, *, user: str = "alice") -> Response:
    return client.get(f"/requests/{request_id}", headers=as_user(user))


def decide(client: TestClient, request_id: str, *, user: str = "carol", **body) -> Response:
    return client.post(f"/requests/{request_id}/decisions", headers=as_user(user), json=body)


def revise(client: TestClient, request_id: str, *, user: str = "alice", **body) -> Response:
    return client.post(f"/requests/{request_id}/revisions", headers=as_user(user), json=body)


def read_discount(
    client: TestClient, application_id: str, *, user: str = "mortgage-process"
) -> Response:
    return client.get(f"/applications/{application_id}/approved-discount", headers=as_user(user))
