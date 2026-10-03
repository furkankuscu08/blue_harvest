"""Application factory.

Run with: uvicorn app.main:create_app --factory
"""

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import create_db_engine, get_session

router = APIRouter()


@router.get("/health")
def health(session: Annotated[Session, Depends(get_session)]):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "code": "DATABASE_UNAVAILABLE",
                "message": "The database cannot be reached.",
            },
        )
    return {"status": "ok"}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title="Pricing exception requests")
    app.state.session_factory = sessionmaker(create_db_engine(settings.database_path))
    app.include_router(router)
    return app
