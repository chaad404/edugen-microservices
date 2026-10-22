import hashlib
import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..clients import ServiceUnavailable
from ..deps import get_session, location
from ..models import Experiment, IdempotencyRecord, Item, Job, Topic
from ..orchestration import create_experiment, estimate, validate_request
from ..problems import Problem
from ..schemas import ExperimentCreate
from ..security import Operator, require_operator
from ..summaries import experiment_summary
from ..views import experiment_view, item_view

router = APIRouter(tags=["experiments"], dependencies=[Depends(require_operator)])


def _catalog(request: Request) -> list[dict]:
    try:
        return request.app.state.generator.models()
    except ServiceUnavailable as e:
        raise Problem(503, "model-catalog-unavailable", "Model catalog unavailable",
                      f"Cannot check the models right now: {e}") from None


def _experiment(session: Session, experiment_id: str) -> Experiment:
    experiment = session.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(404, f"Experiment {experiment_id} not found.")
    return experiment


@router.post("/experiments/estimate", summary="Jobs and estimated API cost of a planned experiment")
def estimate_experiment(body: ExperimentCreate, request: Request, session: Session = Depends(get_session)):
    topics, specs = validate_request(session, body.topic_ids, body.models, body.strategies, _catalog(request))
    return {**estimate(topics, specs, body.strategies, body.questions_per_job),
            "paid_models": [s["alias"] for s in specs if s["paid"]]}


@router.post("/experiments", status_code=202,
             summary="Start an experiment (accepted, then processed asynchronously)",
             description="Returns 202 Accepted with a status resource; progress is streamed on the events channel. "
                         "Send an Idempotency-Key header to make a retried request safe.")
def start_experiment(body: ExperimentCreate, request: Request, session: Session = Depends(get_session),
                     operator: Operator = Depends(require_operator),
                     idempotency_key: Optional[str] = Header(default=None, max_length=200)):
    key = f"experiments:{operator.username}:{idempotency_key}" if idempotency_key else None
    request_hash = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()

    def replay(record: IdempotencyRecord) -> JSONResponse:
        if record.request_hash != request_hash:
            raise Problem(409, "idempotency-key-reused", "Idempotency key reused",
                          "This key was already used for a different request.")
        return JSONResponse(record.response, status_code=record.status_code,
                            headers={"Location": location(request, record.response["links"]["self"])})

    if key and (record := session.get(IdempotencyRecord, key)) is not None:
        return replay(record)

    experiment = create_experiment(session, name=body.name, topic_ids=body.topic_ids, models=body.models,
                                   strategies=body.strategies, questions_per_job=body.questions_per_job,
                                   confirm_paid=body.confirm_paid, catalog=_catalog(request),
                                   operator=operator.username, description=body.description)
    response = experiment_view(experiment)
    if key:
        session.add(IdempotencyRecord(key=key, scope="experiments", request_hash=request_hash, status_code=202,
                                      response=response))
    try:
        session.commit()
    except IntegrityError:  # a parallel request with the same key won the race: answer like it did
        session.rollback()
        return replay(session.get(IdempotencyRecord, key))
    return JSONResponse(response, status_code=202, headers={"Location": location(request, f"/experiments/{experiment.id}")})


@router.get("/experiments", summary="All experiments, newest first")
def list_experiments(session: Session = Depends(get_session)):
    return [experiment_view(e) for e in session.scalars(select(Experiment).order_by(Experiment.created_at.desc()))]


@router.get("/experiments/{experiment_id}", summary="Status resource of an experiment, with its jobs")
def get_experiment(experiment_id: str, session: Session = Depends(get_session)):
    return experiment_view(_experiment(session, experiment_id), with_jobs=True)


@router.get("/experiments/{experiment_id}/items", summary="Generated questions with scores, bands and flags")
def list_items(experiment_id: str, request: Request, session: Session = Depends(get_session),
               model: Optional[str] = None, strategy: Optional[str] = None, topic_id: Optional[str] = None,
               limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    _experiment(session, experiment_id)
    query = select(Item).join(Job).join(Topic).where(Job.experiment_id == experiment_id)
    if model:
        query = query.where(Job.model == model)
    if strategy:
        query = query.where(Job.strategy == strategy)
    if topic_id:
        query = query.where(Topic.topic_id == topic_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(Topic.topic_id, Job.model, Job.strategy, Item.position).limit(limit).offset(offset))
    framework = request.app.state.framework.get()
    return {"total": total, "limit": limit, "offset": offset, "bands_available": framework is not None,
            "items": [item_view(i, framework) for i in rows]}


@router.get("/experiments/{experiment_id}/summary", summary="Comparison per model x strategy (the framework applied)")
def summary(experiment_id: str, request: Request, session: Session = Depends(get_session)):
    return experiment_summary(_experiment(session, experiment_id), request.app.state.framework.get())
