"""Errors as RFC 9457 problem details (application/problem+json), never as stack traces."""
import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

PROBLEM_JSON = "application/problem+json"
logger = logging.getLogger(__name__)


def problem(status: int, title: str, detail: str = "", type_: str = "about:blank", **extra) -> JSONResponse:
    body = {"type": type_, "title": title, "status": status, **({"detail": detail} if detail else {}), **extra}
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def install_problem_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        title = HTTPStatus(exc.status_code).phrase
        detail = exc.detail if isinstance(exc.detail, str) else ""
        return problem(exc.status_code, title, detail, instance=request.url.path)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", "")} for e in exc.errors()]
        return problem(422, "Invalid request", "The request body does not match the contract.",
                       instance=request.url.path, errors=errors)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s", request.url.path)
        return problem(500, "Internal Server Error", "An unexpected error occurred.", instance=request.url.path)
