from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import get_read_session


def test_health_returns_ok_when_database_is_reachable(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_returns_503_when_database_is_unavailable(client, tmp_path):
    # A file inside a directory that does not exist cannot be opened by SQLite.
    broken_engine = create_engine(f"sqlite:///{tmp_path / 'missing' / 'test.db'}")

    def broken_session():
        with Session(broken_engine) as session:
            yield session

    client.app.dependency_overrides[get_read_session] = broken_session

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["code"] == "DATABASE_UNAVAILABLE"
