from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..deps import get_session
from ..problems import problem

router = APIRouter(tags=["operations"])


@router.get("/health", summary="Liveness: the process is running")
def health():
    return {"status": "ok"}


@router.get("/ready", summary="Readiness: the database answers")
def ready(session: Session = Depends(get_session)):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return problem(503, "Not ready", "The database is not reachable.")
    return {"status": "ready"}
