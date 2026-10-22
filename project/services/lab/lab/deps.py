"""Request-scoped dependencies."""
from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def location(request: Request, path: str) -> str:
    """Absolute path as the client sees it (behind the gateway the service runs under /api/lab)."""
    return f"{request.scope.get('root_path', '')}{path}"
