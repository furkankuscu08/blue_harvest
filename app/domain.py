"""Business rules for pricing exception requests.

Each function checks its rules in the order of the API contract and changes
the request only when every check passes, so a rejected call changes nothing
(I4). Who acted and when come from the caller's identity and the server clock,
never from the request body (I9).

Checks that need the database (application exists, one request per
application, idempotency) belong to the service layer.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.models import ExceptionRequest, Outcome, Role


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
    raise NotImplementedError


def revise(
    request: ExceptionRequest,
    actor: Actor,
    *,
    expected_version: int,
    discount_bps: int,
    reason: str,
    now: datetime,
) -> None:
    raise NotImplementedError


def decide(
    request: ExceptionRequest,
    actor: Actor,
    *,
    expected_version: int,
    outcome: Outcome,
    comment: str | None,
    now: datetime,
) -> None:
    raise NotImplementedError
