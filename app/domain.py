"""Business rules for pricing exception requests.

Each function checks its rules in the order of the API contract and changes
the request only when every check passes, so a rejected call changes nothing
(I4). Who acted and when come from the caller's identity and the server clock,
never from the request body (I9).

Checks that need the database (application exists, one request per
application, idempotency) belong to the service layer.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.models import Decision, ExceptionRequest, Outcome, Revision, Role, Status

# Assumption A5: the largest discount a request may ask for, in basis points.
MAX_DISCOUNT_BPS = 200


class ErrorCode(StrEnum):
    ROLE_NOT_ALLOWED = "ROLE_NOT_ALLOWED"
    NOT_REQUEST_OWNER = "NOT_REQUEST_OWNER"
    FOUR_EYES_VIOLATION = "FOUR_EYES_VIOLATION"
    STALE_VERSION = "STALE_VERSION"
    INVALID_STATE = "INVALID_STATE"


class DomainError(Exception):
    def __init__(self, code: ErrorCode):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Actor:
    id: str
    roles: frozenset[Role]


def create_request(
    actor: Actor, *, application_id: str, discount_bps: int, reason: str, now: datetime
) -> ExceptionRequest:
    require_role(actor, Role.RELATIONSHIP_MANAGER)

    request = ExceptionRequest(
        id=str(uuid.uuid4()),
        application_id=application_id,
        status=Status.PENDING,
        version=1,
        created_by=actor.id,
        created_at=now,
        updated_at=now,
    )
    request.revisions.append(
        Revision(number=1, discount_bps=discount_bps, reason=reason, created_at=now)
    )
    return request


def revise(
    request: ExceptionRequest,
    actor: Actor,
    *,
    expected_version: int,
    discount_bps: int,
    reason: str,
    now: datetime,
) -> None:
    require_role(actor, Role.RELATIONSHIP_MANAGER)
    if actor.id != request.created_by:
        raise DomainError(ErrorCode.NOT_REQUEST_OWNER)
    _require_version(request, expected_version)
    if request.status not in (Status.PENDING, Status.DECLINED):
        raise DomainError(ErrorCode.INVALID_STATE)

    number = request.revisions[-1].number + 1
    request.revisions.append(
        Revision(number=number, discount_bps=discount_bps, reason=reason, created_at=now)
    )
    request.status = Status.PENDING
    request.version += 1
    request.updated_at = now


def decide(
    request: ExceptionRequest,
    actor: Actor,
    *,
    expected_version: int,
    outcome: Outcome,
    comment: str,
    now: datetime,
) -> None:
    require_role(actor, Role.REVIEWER)
    if actor.id == request.created_by:
        raise DomainError(ErrorCode.FOUR_EYES_VIOLATION)
    _require_version(request, expected_version)
    if request.status != Status.PENDING:
        raise DomainError(ErrorCode.INVALID_STATE)

    # I5: the decision always applies to the latest revision.
    request.revisions[-1].decision = Decision(
        outcome=outcome, decided_by=actor.id, decided_at=now, comment=comment
    )
    request.status = Status(outcome)
    request.version += 1
    request.updated_at = now


def require_role(actor: Actor, role: Role) -> None:
    if role not in actor.roles:
        raise DomainError(ErrorCode.ROLE_NOT_ALLOWED)


def _require_version(request: ExceptionRequest, expected_version: int) -> None:
    if expected_version != request.version:
        raise DomainError(ErrorCode.STALE_VERSION)
