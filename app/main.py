"""Application factory.

Run with: uvicorn app.main:create_app --factory
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import router
from app.config import Settings
from app.db import create_db_engine, read_session_factory, write_session_factory
from app.errors import install_error_handlers
from app.models import Base
from app.seed import seed_if_empty

STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Pricing exception requests")
    engine = create_db_engine(settings.database_path)
    app.state.read_sessions = read_session_factory(engine)
    app.state.write_sessions = write_session_factory(engine)

    Base.metadata.create_all(engine)
    with app.state.write_sessions() as session:
        seed_if_empty(session)
        session.commit()

    install_error_handlers(app)
    app.include_router(router)

    # The UI: one page and its files. Mounted under /static, not at the root,
    # so that unknown routes keep the framework's answer.
    @app.get("/", include_in_schema=False)
    def ui() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
