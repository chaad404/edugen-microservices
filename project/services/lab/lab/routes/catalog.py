from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clients import ServiceUnavailable
from ..deps import get_session, location
from ..models import Topic
from ..orchestration import STRATEGIES
from ..problems import Problem
from ..schemas import TopicCreate
from ..security import Operator, require_operator
from ..views import topic_view

router = APIRouter(tags=["catalog"], dependencies=[Depends(require_operator)])

STRATEGY_INFO = {
    "baseline": "Thesis April 2026 zero-shot template: topic text only, one call.",
    "prompt_v2": "Thesis prompt v2 (evidence quote, item-writing rules), one call, keys balanced over A-D.",
    "verify_repair": "Writer (3 calls) -> Evaluator checks -> targeted LLM repair (max 2 rounds) -> selection.",
}


@router.get("/models", summary="Model registry of the Generator: price and availability")
def models(request: Request):
    try:
        return request.app.state.generator.models()
    except ServiceUnavailable as e:
        raise Problem(503, "model-catalog-unavailable", "Model catalog unavailable", str(e)) from None


@router.get("/strategies", summary="Generation strategies (the thesis conditions)")
def strategies():
    return [{"key": key, "description": STRATEGY_INFO[key]} for key in STRATEGIES]


@router.get("/framework", summary="Pillars and cut points, as published by the Evaluator")
def framework(request: Request):
    current = request.app.state.framework.get()
    if current is None:
        raise Problem(503, "framework-unavailable", "Quality framework unavailable",
                      "The Evaluator has not been reachable since the Lab started.")
    return {"version": current.version, "pillars": list(current.pillars.values())}


@router.get("/topics", summary="Topics: demo topics, thesis topics (results only) and custom topics")
def list_topics(session: Session = Depends(get_session)):
    return [topic_view(t) for t in session.scalars(select(Topic).order_by(Topic.domain, Topic.topic_id))]


@router.get("/topics/{topic_id}")
def get_topic(topic_id: str, session: Session = Depends(get_session)):
    topic = session.scalar(select(Topic).where(Topic.topic_id == topic_id))
    if topic is None:
        raise HTTPException(404, f"Topic {topic_id} not found.")
    return topic_view(topic, with_text=True)


@router.post("/topics", status_code=201, summary="Add a topic with its source text")
def create_topic(body: TopicCreate, request: Request, session: Session = Depends(get_session),
                 operator: Operator = Depends(require_operator)):
    if session.scalar(select(Topic).where(Topic.topic_id == body.topic_id)) is not None:
        raise Problem(409, "topic-exists", "Topic exists", f"{body.topic_id} already exists.")
    topic = Topic(topic_id=body.topic_id, domain=body.domain, title=body.title, source_text=body.source_text,
                  origin="custom")
    session.add(topic)
    session.commit()
    return JSONResponse(topic_view(topic), status_code=201,
                        headers={"Location": location(request, f"/topics/{topic.topic_id}")})
