"""HTTP endpoints from docs/api-contract.md.

The caller is identified by the X-User-Id header (assumption A7: this is not
authentication). The identity is resolved as a dependency, so an unknown
caller is rejected before the request body is validated. The role is checked
next, before any business check.

An endpoint that changes data uses only the write session. Its response body
is built inside the transaction and returned only after the commit succeeds.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.db import get_read_session, get_write_session
from app.domain import Actor, create_request, decide, require_role, revise
from app.errors import ApiError
from app.models import (
    Application,
    ExceptionRequest,
    IdempotencyRecord,
    Role,
    Status,
    User,
)
from app.schemas import (
    ApplicationSummary,
    ApprovedDiscount,
    CreateRequestInput,
    DecisionInput,
    RequestDetail,
    RequestSummary,
    RevisionInput,
    UserSummary,
)

MAX_IDEMPOTENCY_KEY_LENGTH = 255

router = APIRouter()

ReadSession = Annotated[Session, Depends(get_read_session)]
WriteSession = Annotated[Session, Depends(get_write_session)]


def _actor(session: Session, user_id: str | None) -> Actor:
    user = session.get(User, user_id) if user_id else None
    if user is None:
        raise ApiError(401, "UNKNOWN_USER", "X-User-Id is missing or is not a known user.")
    return Actor(user.id, frozenset(r.role for r in user.roles))


def read_actor(session: ReadSession, x_user_id: Annotated[str | None, Header()] = None) -> Actor:
    return _actor(session, x_user_id)


def write_actor(session: WriteSession, x_user_id: Annotated[str | None, Header()] = None) -> Actor:
    return _actor(session, x_user_id)


ReadActor = Annotated[Actor, Depends(read_actor)]
WriteActor = Annotated[Actor, Depends(write_actor)]


def _load_request(session: Session, request_id: uuid.UUID) -> ExceptionRequest:
    request = session.get(ExceptionRequest, str(request_id))
    if request is None:
        raise ApiError(404, "REQUEST_NOT_FOUND", "No request with this id.")
    return request


def _require_application(session: Session, application_id: str) -> None:
    if session.get(Application, application_id) is None:
        raise ApiError(404, "APPLICATION_NOT_FOUND", "No application with this id.")


def _respond_after_commit(session: Session, request: ExceptionRequest) -> JSONResponse:
    """Build the detail inside the transaction, then commit, then return it."""
    response_body = RequestDetail.model_validate(request).model_dump(mode="json")
    session.commit()
    return JSONResponse(status_code=201, content=response_body)


@router.get("/health")
def health(session: ReadSession):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise ApiError(503, "DATABASE_UNAVAILABLE", "The database cannot be reached.") from exc
    return {"status": "ok"}


@router.post("/requests", status_code=201, response_model=RequestDetail)
def create_exception_request(
    body: CreateRequestInput,
    session: WriteSession,
    caller: WriteActor,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> JSONResponse:
    require_role(caller, Role.RELATIONSHIP_MANAGER)
    if not idempotency_key or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
        raise ApiError(
            400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key must be 1 to 255 characters."
        )

    # 1. A key this caller used before: replay the stored response, or refuse.
    payload = json.dumps(body.model_dump(mode="json"), sort_keys=True)
    record = session.get(IdempotencyRecord, (caller.id, idempotency_key))
    if record is not None:
        if record.request_payload != payload:
            raise ApiError(
                422, "IDEMPOTENCY_KEY_REUSED", "This key was already used with different fields."
            )
        return JSONResponse(status_code=201, content=json.loads(record.response_body))

    # 2. The application exists. 3. It has no request yet.
    _require_application(session, body.application_id)
    existing_id = session.scalar(
        select(ExceptionRequest.id).where(ExceptionRequest.application_id == body.application_id)
    )
    if existing_id is not None:
        raise ApiError(
            409,
            "REQUEST_ALREADY_EXISTS",
            "An exception request already exists for this application.",
            {"request_id": existing_id},
        )

    now = datetime.now(UTC)
    request = create_request(
        caller,
        application_id=body.application_id,
        discount_bps=body.discount_bps,
        reason=body.reason,
        now=now,
    )
    session.add(request)
    response_body = RequestDetail.model_validate(request).model_dump(mode="json")
    session.add(
        IdempotencyRecord(
            user_id=caller.id,
            key=idempotency_key,
            request_payload=payload,
            response_body=json.dumps(response_body),
            created_at=now,
        )
    )
    session.commit()
    return JSONResponse(status_code=201, content=response_body)


@router.get("/requests")
def list_requests(session: ReadSession, _caller: ReadActor) -> list[RequestSummary]:
    requests = session.scalars(
        select(ExceptionRequest)
        .options(selectinload(ExceptionRequest.revisions))
        .order_by(ExceptionRequest.updated_at.desc(), ExceptionRequest.id)
    )
    return [
        RequestSummary(
            id=request.id,
            application_id=request.application_id,
            status=request.status,
            version=request.version,
            created_by=request.created_by,
            current_discount_bps=request.revisions[-1].discount_bps,
            updated_at=request.updated_at,
        )
        for request in requests
    ]


@router.get("/requests/{request_id}")
def get_exception_request(
    request_id: uuid.UUID, session: ReadSession, _caller: ReadActor
) -> RequestDetail:
    # Built while the read transaction is open, so it comes from one snapshot.
    return RequestDetail.model_validate(_load_request(session, request_id))


@router.post("/requests/{request_id}/revisions", status_code=201, response_model=RequestDetail)
def revise_request(
    request_id: uuid.UUID, body: RevisionInput, session: WriteSession, caller: WriteActor
) -> JSONResponse:
    require_role(caller, Role.RELATIONSHIP_MANAGER)
    request = _load_request(session, request_id)
    revise(
        request,
        caller,
        expected_version=body.expected_version,
        discount_bps=body.discount_bps,
        reason=body.reason,
        now=datetime.now(UTC),
    )
    return _respond_after_commit(session, request)


@router.post("/requests/{request_id}/decisions", status_code=201, response_model=RequestDetail)
def decide_on_request(
    request_id: uuid.UUID, body: DecisionInput, session: WriteSession, caller: WriteActor
) -> JSONResponse:
    require_role(caller, Role.REVIEWER)
    request = _load_request(session, request_id)
    decide(
        request,
        caller,
        expected_version=body.expected_version,
        outcome=body.outcome,
        comment=body.comment,
        now=datetime.now(UTC),
    )
    return _respond_after_commit(session, request)


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


@router.get("/applications/{application_id}/approved-discount")
def get_approved_discount(
    application_id: str, session: ReadSession, caller: ReadActor
) -> ApprovedDiscount:
    require_role(caller, Role.MORTGAGE_PROCESS)
    _require_application(session, application_id)
    request = session.scalar(
        select(ExceptionRequest).where(ExceptionRequest.application_id == application_id)
    )
    if request is None or request.status != Status.APPROVED:
        raise ApiError(404, "NO_APPROVED_DISCOUNT", "The application has no approved request.")

    approved = request.revisions[-1]
    return ApprovedDiscount(
        application_id=application_id,
        request_id=request.id,
        revision_number=approved.number,
        approved_discount_bps=approved.discount_bps,
        decided_by=approved.decision.decided_by,
        decided_at=approved.decision.decided_at,
    )


@router.get("/users")
def list_users(session: ReadSession) -> list[UserSummary]:
    # No caller: the UI reads this list to choose who to act as.
    users = session.scalars(select(User).options(selectinload(User.roles)).order_by(User.id))
    return [
        UserSummary(id=user.id, name=user.name, roles=sorted(r.role for r in user.roles))
        for user in users
    ]
