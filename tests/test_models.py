from sqlalchemy import inspect

from app.db import create_db_engine
from app.models import Base


def test_schema_can_be_created(tmp_path):
    engine = create_db_engine(str(tmp_path / "test.db"))

    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "applications",
        "users",
        "user_roles",
        "exception_requests",
        "revisions",
        "decisions",
    }
    engine.dispose()
