import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from lab.clients import ServiceUnavailable
from lab.db import make_engine, make_session_factory
from lab.main import create_app
from lab.messages import GENERATION_COMPLETED, GENERATION_FAILED, envelope
from lab.models import Base
from lab.seed import seed_demo_topics

SEED = Path(__file__).parents[1] / "seed"

FRAMEWORK = {"version": "thesis-2026-10", "pillars": [
    {"key": "P1", "metric": "alignment", "cuts": [0.64, 0.70, 0.76], "labels": ["Weak", "Good enough", "Better", "Best"], "zone": None},
    {"key": "P2", "metric": "grade", "cuts": [8.0, 10.0, 14.0, 16.0],
     "labels": ["Too simple", "Good enough", "Best", "Good enough", "Too dense"], "zone": [10.0, 14.0]},
    {"key": "P3a", "metric": "plausibility", "cuts": [0.30, 0.45, 0.60, 0.80],
     "labels": ["Weak", "Good enough", "Better", "Best", "Too close"], "zone": None},
    {"key": "P3b", "metric": "diversity", "cuts": [0.40, 0.55, 0.70], "labels": ["Weak", "Good enough", "Better", "Best"], "zone": None},
]}

CATALOG = [
    {"alias": "simulator", "label": "Offline simulator", "available": True, "paid": False, "requires": None,
     "price_per_m": {"input": 0, "output": 0}},
    {"alias": "llama33", "label": "Llama 3.3 70B", "available": True, "paid": True, "requires": None,
     "price_per_m": {"input": 0.71, "output": 0.71}, "settings": {"max_tokens": 8192}, "output_tokens_per_question": 96},
    {"alias": "cohere", "label": "Command A", "available": False, "paid": True, "requires": "COHERE_API_KEY",
     "price_per_m": {"input": 2.5, "output": 10.0}, "settings": {"max_tokens": 8192}, "output_tokens_per_question": 118},
]


class FakeGenerator:
    def __init__(self):
        self.down = False

    def models(self):
        if self.down:
            raise ServiceUnavailable("Generator unreachable")
        return CATALOG


class FakeEvaluator:
    def __init__(self):
        self.down = False
        self.calls = []

    def framework(self):
        if self.down:
            raise ServiceUnavailable("Evaluator unreachable")
        return FRAMEWORK

    def evaluate(self, source_text, items):
        if self.down:
            raise ServiceUnavailable("Evaluator unreachable")
        self.calls.append((source_text, items))
        return [{"id": item["id"], "valid": True, "validation_notes": "Valid",
                 "metrics": {"alignment": 0.72 if source_text else None, "alignment_lexical": 0.4 if source_text else None,
                             "grade": 12.0, "plausibility": 0.5, "plausibility_lexical": 0.2, "diversity": 0.6},
                 "flags": ["length_cue"] if "longest" in item["question"] else [], "repairable": False, "serious": False,
                 "quality": 9} for item in items]


class FakeReview:
    def __init__(self):
        self.down = False
        self.calls = []

    def create_study(self, payload, token, idempotency_key):
        if self.down:
            raise ServiceUnavailable("Review unreachable")
        self.calls.append({"payload": payload, "token": token, "key": idempotency_key})
        return {"study_id": payload["study_id"], "expert_code": "EXP-ABCD", "student_code": "STU-WXYZ"}


def questions(n=3):
    return [{"question": f"Which statement about slow start number {i} is correct?",
             "options": {"A": f"key {i}", "B": f"wrong b {i}", "C": f"wrong c {i}", "D": f"wrong d {i}"},
             "answer": "ABCD"[i % 4], "evidence": "slow start doubles the window"} for i in range(n)]


def completed(job_id: str, items=None) -> dict:
    return envelope(GENERATION_COMPLETED, {
        "job_id": job_id, "experiment_id": "x", "model": "simulator", "strategy": "baseline", "provider": "simulator",
        "requested_model_id": "edugen-simulator-1", "returned_model_id": "edugen-simulator-1", "simulated": True,
        "attempts": 1, "calls": 1, "prompt_tokens": 900, "completion_tokens": 400, "cost_usd": 0.0,
        "latency_seconds": 1.2, "strategy_status": "valid", "trace": {}, "items": items if items is not None else questions()})


def failed(job_id: str) -> dict:
    return envelope(GENERATION_FAILED, {"job_id": job_id, "experiment_id": "x", "model": "simulator",
                                        "strategy": "baseline", "error_kind": "provider_error", "error": "HTTP 503",
                                        "attempts": 4, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0})


@pytest.fixture
def session_factory():
    factory = make_session_factory(make_engine("sqlite://"))
    Base.metadata.create_all(factory.kw["bind"])
    with factory() as session:
        seed_demo_topics(session, SEED / "demo_topics.json")
        session.commit()
    return factory


@pytest.fixture
def fakes():
    return SimpleNamespace(generator=FakeGenerator(), evaluator=FakeEvaluator(), review=FakeReview())


@pytest.fixture
def app(session_factory, fakes):
    application = create_app(session_factory=session_factory, evaluator=fakes.evaluator, generator=fakes.generator,
                             review=fakes.review, start_workers=False, run_seed=False)
    application.state.stream_max_seconds = 1.5
    return application


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth(client):
    token = client.post("/auth/login", json={"username": "operator", "password": "edugen-demo"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def outbox_payloads(session) -> list[dict]:
    from sqlalchemy import select

    from lab.models import OutboxMessage
    return [json.loads(row.body) for row in session.scalars(select(OutboxMessage).order_by(OutboxMessage.id))]
