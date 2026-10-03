"""The error body from docs/api-contract.md, section "Errors".

Every error defined in the contract is answered with {code, message, details}.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


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


def install_error_handlers(app: FastAPI) -> None:
    async def handle_api_error(_request: Request, error: ApiError) -> JSONResponse:
        return error_response(error)

    app.add_exception_handler(ApiError, handle_api_error)
