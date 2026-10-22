from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..analytics import study_analytics
from ..deps import get_session, location
from ..models import Study
from ..problems import Problem
from ..schemas import StudyCreate
from ..security import Operator, require_operator
from ..studies import create_study, publish_study
from ..views import study_view

router = APIRouter(tags=["studies"], dependencies=[Depends(require_operator)])


def _study(session: Session, study_id: str) -> Study:
    study = session.get(Study, study_id)
    if study is None:
        raise HTTPException(404, f"Study {study_id} not found.")
    return study


@router.post("/studies", status_code=201, summary="Sample questions and open a blind review study")
def start_study(body: StudyCreate, request: Request, session: Session = Depends(get_session),
                operator: Operator = Depends(require_operator)):
    study = create_study(session, title=body.title, kind=body.kind, experiment_ids=body.experiment_ids,
                         per_cell=body.per_cell, seed=body.seed, student_items=body.student_items,
                         operator=operator.username)
    session.commit()  # the sample is kept even if the Review service is down; publishing can be retried
    publish_study(session, study, request.app.state.review, operator.token)
    session.commit()
    return JSONResponse(study_view(study), status_code=201, headers={"Location": location(request, f"/studies/{study.id}")})


@router.get("/studies")
def list_studies(session: Session = Depends(get_session)):
    return [study_view(s) for s in session.scalars(select(Study).order_by(Study.created_at.desc()))]


@router.get("/studies/{study_id}")
def get_study(study_id: str, session: Session = Depends(get_session)):
    return study_view(_study(session, study_id))


@router.post("/studies/{study_id}/publish", summary="Retry handing a draft study to the Review service")
def republish(study_id: str, request: Request, session: Session = Depends(get_session),
              operator: Operator = Depends(require_operator)):
    study = _study(session, study_id)
    if study.status != "open":
        publish_study(session, study, request.app.state.review, operator.token)
        session.commit()
    if study.status != "open":
        raise Problem(503, "review-unavailable", "Review service unavailable", study.publish_error or "")
    return study_view(study)


@router.get("/studies/{study_id}/analytics", summary="Human versus automatic evaluation (unblinded, operator only)")
def analytics(study_id: str, session: Session = Depends(get_session)):
    return study_analytics(session, _study(session, study_id))
