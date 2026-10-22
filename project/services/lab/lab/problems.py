"""Errors as RFC 9457 problem details (application/problem+json), never as stack traces."""
import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

PROBLEM_JSON = "application/problem+json"
logger = logging.getLogger(__name__)


class Problem(Exception):
    """A domain error with a stable type that clients can handle in code (the title may change)."""

    def __init__(self, status: int, code: str, title: str, detail: str = "", **extra):
        super().__init__(detail or title)
        self.status, self.code, self.title, self.detail, self.extra = status, code, title, detail, extra


def problem(status: int, title: str, detail: str = "", type_: str = "about:blank", **extra) -> JSONResponse:
    body = {"type": type_, "title": title, "status": status, **({"detail": detail} if detail else {}), **extra}
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def domain_error(request: Request, exc: Problem):
        return problem(exc.status, exc.title, exc.detail, f"urn:edugen:problem:{exc.code}",
                       instance=request.url.path, **exc.extra)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else ""
        return problem(exc.status_code, HTTPStatus(exc.status_code).phrase, detail, instance=request.url.path)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
        return problem(422, "Invalid request", "The request does not match the contract.",
                       instance=request.url.path, errors=errors)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s", request.url.path)
        return problem(500, "Internal Server Error", "An unexpected error occurred.", instance=request.url.path)
