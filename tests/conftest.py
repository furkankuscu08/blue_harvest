import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "test.db")))
    with TestClient(app) as client:
        yield client
