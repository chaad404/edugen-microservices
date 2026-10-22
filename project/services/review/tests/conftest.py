import json
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from review import config
from review.db import make_engine, make_session_factory
from review.main import create_app
from review.models import Base, OutboxMessage


def operator_token(role="operator") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"iss": "edugen-lab", "aud": "edugen", "sub": "operator", "role": role,
                       "iat": int(now.timestamp()), "exp": int((now + timedelta(hours=1)).timestamp())},
                      config.LAB_JWT_SECRET, algorithm="HS256")


def study_body(n=6, kind="both", student_items=4, study_id=None) -> dict:
    return {"study_id": study_id or str(uuid.uuid4()), "title": "Pilot review", "kind": kind, "seed": 2026,
            "student_items": student_items,
            "items": [{"item_ref": str(uuid.uuid4()), "topic_label": "TCP congestion control", "domain": "NETCOMP",
                       "question": f"Which mechanism is described in statement {i}?",
                       "options": {"A": f"key text {i}", "B": f"wrong b {i}", "C": f"wrong c {i}", "D": f"wrong d {i}"},
                       "answer": "A"} for i in range(n)]}


@pytest.fixture
def session_factory():
    factory = make_session_factory(make_engine("sqlite://"))
    Base.metadata.create_all(factory.kw["bind"])
    return factory


@pytest.fixture
def client(session_factory):
    return TestClient(create_app(session_factory=session_factory, start_workers=False))


@pytest.fixture
def operator():
    return {"Authorization": f"Bearer {operator_token()}"}


@pytest.fixture
def study(client, operator):
    body = study_body()
    response = client.post("/internal/v1/studies", json=body, headers={**operator, "Idempotency-Key": body["study_id"]})
    assert response.status_code == 201
    return {"body": body, **response.json()}


def join(client, code, **extra) -> dict:
    response = client.post("/v1/sessions", json={"code": code, **extra})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def outbox(session_factory) -> list[dict]:
    with session_factory() as session:
        return [json.loads(m.body) for m in session.scalars(select(OutboxMessage).order_by(OutboxMessage.id))]


RATING = {"relevance": 4, "clarity": 5, "difficulty": 3, "distractors": 2, "key_correct": "yes"}
