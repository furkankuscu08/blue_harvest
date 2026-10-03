"""The error body from docs/api-contract.md, section "Errors".

Every error defined in the contract is answered with {code, message, details}.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain import DomainError, ErrorCode

DOMAIN_ERRORS = {
    ErrorCode.ROLE_NOT_ALLOWED: (403, "Your roles do not allow this action."),
    ErrorCode.NOT_REQUEST_OWNER: (403, "Only the manager who created the request can revise it."),
    ErrorCode.FOUR_EYES_VIOLATION: (403, "You cannot decide on a request you created."),
    ErrorCode.STALE_VERSION: (409, "The request changed since you loaded it. Reload it first."),
    ErrorCode.INVALID_STATE: (409, "The request's current status does not allow this action."),
}


class ApiError(Exception):
    def __init__(
        self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None
    ):
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def error_response(error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"code": error.code, "message": error.message, "details": error.details},
    )


def _field(error: dict) -> str:
    location = error["loc"]
    if error["type"] == "json_invalid" or len(location) < 2:
        return "body"
    return ".".join(str(part) for part in location[1:])


def install_error_handlers(app: FastAPI) -> None:
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        return error_response(error)

    async def handle_domain_error(_request: Request, error: DomainError) -> JSONResponse:
        status_code, message = DOMAIN_ERRORS[error.code]
        return error_response(ApiError(status_code, error.code, message))

    async def handle_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        # Only the field and the reason: the rejected input is never echoed back.
        errors = [{"field": _field(e), "message": e["msg"]} for e in error.errors()]
        return error_response(
            ApiError(422, "VALIDATION_ERROR", "The request is not valid.", {"errors": errors})
        )

    app.add_exception_handler(ApiError, handle_api_error)
    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
