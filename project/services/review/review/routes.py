"""
HTTP routes. /internal/* is called by the Lab over the internal network only; the gateway does not expose it.
Everything else is reached through the gateway under /api/review.
"""
import hashlib
import json
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import service
from .problems import Problem, problem
from .schemas import AnswerIn, FeedbackIn, JoinRequest, RatingIn, StudyIn
from .security import Caller, issue_participant_token, require_expert, require_operator, require_participant, require_student

INSTRUCTIONS = {
    "expert": ("Rate every question on the four 1-5 scales, decide whether the marked answer is correct, and flag "
               "a question as unusable if it has a factual error. The generating model is hidden on purpose."),
    "student": ("Answer each question, then rate it. Questions come one at a time and an answer cannot be changed. "
                "No personal data is stored; you can stop and resume later on this device."),
}

ops = APIRouter(tags=["operations"])
internal = APIRouter(prefix="/internal/v1", tags=["internal"])
public = APIRouter(prefix="/v1")


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


@ops.get("/health", summary="Liveness")
def health():
    return {"status": "ok"}


@ops.get("/ready", summary="Readiness: the database answers")
def ready(session: Session = Depends(get_session)):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return problem(503, "Not ready", "The database is not reachable.")
    return {"status": "ready"}


@internal.post("/studies", status_code=201, summary="Create a blinded study (called by the Lab)")
def create_study(body: StudyIn, session: Session = Depends(get_session), operator: Caller = Depends(require_operator),
                 idempotency_key: Optional[str] = Header(default=None, max_length=200)):
    if idempotency_key != body.study_id:
        raise Problem(400, "idempotency-key-required", "Idempotency key required",
                      "Send the study ID as the Idempotency-Key header, so a retried request is safe.")
    request_hash = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    study, created = service.create_study(session, body, request_hash)
    session.commit()
    return JSONResponse(service.study_codes(study), status_code=201 if created else 200)


@public.get("/studies/{study_id}/progress", tags=["studies"], summary="Who rated or answered how much (operator)")
def study_progress(study_id: str, session: Session = Depends(get_session), operator: Caller = Depends(require_operator)):
    return service.progress(session, study_id)


@public.post("/sessions", tags=["sessions"], summary="Redeem a study code; returns a session token")
def join(body: JoinRequest, session: Session = Depends(get_session)):
    participant, study = service.join(session, body)
    session.commit()
    return {"token": issue_participant_token(participant.id, participant.role, study.id), "role": participant.role,
            "study_title": study.title, "instructions": INSTRUCTIONS[participant.role]}


@public.get("/sessions/me", tags=["sessions"], summary="Progress of the current session (for resuming)")
def me(session: Session = Depends(get_session), caller: Caller = Depends(require_participant)):
    view = service.session_view(session, caller)
    return {**view, "instructions": INSTRUCTIONS[view["role"]]}  # still shown after a reload


@public.get("/expert/items", tags=["expert review"], summary="All questions of the review, in this rater's order")
def expert_items(session: Session = Depends(get_session), caller: Caller = Depends(require_expert)):
    return service.expert_items(session, caller)


@public.get("/expert/next", tags=["expert review"], summary="The next question without a rating")
def expert_next(session: Session = Depends(get_session), caller: Caller = Depends(require_expert)):
    return service.expert_next(session, caller)


@public.get("/expert/items/{item_ref}", tags=["expert review"], summary="One question with this rater's rating")
def expert_item(item_ref: str, session: Session = Depends(get_session), caller: Caller = Depends(require_expert)):
    return service.expert_item(session, caller, item_ref)


@public.put("/expert/ratings/{item_ref}", tags=["expert review"],
            summary="Create or revise the rating of one question (idempotent PUT)")
def save_rating(item_ref: str, body: RatingIn, session: Session = Depends(get_session),
                caller: Caller = Depends(require_expert)):
    result = service.save_rating(session, caller, item_ref, body)
    session.commit()
    return result


@public.get("/quiz/current", tags=["student quiz"], summary="The current question (starts its timer)")
def quiz_current(session: Session = Depends(get_session), caller: Caller = Depends(require_student)):
    result = service.quiz_current(session, caller)
    session.commit()
    return result


@public.post("/quiz/answers", tags=["student quiz"], summary="Answer the current question (cannot be changed)")
def quiz_answer(body: AnswerIn, session: Session = Depends(get_session), caller: Caller = Depends(require_student)):
    result = service.submit_answer(session, caller, body)
    session.commit()
    return result


@public.post("/quiz/feedback", tags=["student quiz"], summary="Rate the answered question; moves to the next one")
def quiz_feedback(body: FeedbackIn, session: Session = Depends(get_session), caller: Caller = Depends(require_student)):
    result = service.submit_feedback(session, caller, body)
    session.commit()
    return result
