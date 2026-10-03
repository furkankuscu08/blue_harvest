"""HTTP endpoints from docs/api-contract.md.

The caller is identified by the X-User-Id header (assumption A7: this is not
authentication). The identity is resolved as a dependency, so an unknown
caller is rejected before the request body is validated.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_read_session
from app.domain import Actor
from app.errors import ApiError
from app.models import Application, ExceptionRequest, User
from app.schemas import ApplicationSummary

router = APIRouter()

ReadSession = Annotated[Session, Depends(get_read_session)]


def _actor(session: Session, user_id: str | None) -> Actor:
    user = session.get(User, user_id) if user_id else None
    if user is None:
        raise ApiError(401, "UNKNOWN_USER", "X-User-Id is missing or is not a known user.")
    return Actor(user.id, frozenset(r.role for r in user.roles))


def read_actor(session: ReadSession, x_user_id: Annotated[str | None, Header()] = None) -> Actor:
    return _actor(session, x_user_id)


ReadActor = Annotated[Actor, Depends(read_actor)]


@router.get("/health")
def health(session: ReadSession):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise ApiError(503, "DATABASE_UNAVAILABLE", "The database cannot be reached.") from exc
    return {"status": "ok"}


@router.get("/applications")
def list_applications(session: ReadSession, _caller: ReadActor) -> list[ApplicationSummary]:
    rows = session.execute(
        select(Application.id, Application.customer_name, ExceptionRequest.id)
        .outerjoin(ExceptionRequest, ExceptionRequest.application_id == Application.id)
        .order_by(Application.id)
    )
    return [
        ApplicationSummary(id=app_id, customer_name=name, request_id=request_id)
        for app_id, name, request_id in rows
    ]
