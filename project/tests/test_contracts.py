"""
Cross-service contract test: the four real services in one process, connected through their real HTTP
APIs (Starlette test clients) and their real message handlers (the broker is replaced by direct hand-over).
It fails if any request, response or message between the services stops matching.

    python -m pytest project/tests -p no:cacheprovider
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

SERVICES = Path(__file__).resolve().parents[1] / "services"
for name in ("evaluator", "generator", "lab", "review"):
    sys.path.insert(0, str(SERVICES / name))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

import evaluator.main as evaluator_main  # noqa: E402
import generator.main as generator_main  # noqa: E402
from generator import config as generator_config  # noqa: E402
import lab.main as lab_main  # noqa: E402
import review.main as review_main  # noqa: E402
from evaluator.embedder import normalize  # noqa: E402
from generator.catalog import load_catalog  # noqa: E402
from generator.evaluator_client import EvaluatorClient as GeneratorsEvaluatorClient  # noqa: E402
from generator.jobs import JobHandler, Runtime  # noqa: E402
from generator.strategies import REPAIR_ROUNDS, WRITER_CALLS  # noqa: E402
from lab.clients import EvaluatorClient, GeneratorClient, ReviewClient  # noqa: E402
from lab.db import make_engine as lab_engine, make_session_factory as lab_sessions  # noqa: E402
from lab.models import Base as LabBase, OutboxMessage as LabOutbox  # noqa: E402
from lab.orchestration import MAX_CALLS_PER_JOB, evaluate_pending, handle_generation_result, mark_dispatched  # noqa: E402
from lab.outbox import OutboxRelay  # noqa: E402
from lab.seed import THESIS_EXPERIMENT_ID, import_thesis_sample, seed_demo_topics  # noqa: E402
from lab.studies import handle_review_event  # noqa: E402
from review.db import make_engine as review_engine, make_session_factory as review_sessions  # noqa: E402
from review.models import Base as ReviewBase, OutboxMessage as ReviewOutbox  # noqa: E402

SEED = SERVICES / "lab" / "seed"


class BagOfWordsEmbedder:
    """Offline stand-in for the embedding model (the real one is verified against the thesis separately)."""
    model_name = "bag-of-words"

    def embed(self, texts):
        out = np.zeros((len(texts), 256), dtype=np.float32)
        for i, text in enumerate(texts):
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                out[i, int(hashlib.md5(word.encode()).hexdigest(), 16) % 256] += 1.0
        return normalize(out)


class CollectingPublisher:
    def __init__(self):
        self.messages = []

    def publish(self, exchange, routing_key, body, **kwargs):
        self.messages.append(json.loads(body))

    def reset(self):
        pass


@pytest.fixture
def system():
    evaluator_http = TestClient(evaluator_main.create_app(BagOfWordsEmbedder()))
    catalog = load_catalog(str(SERVICES / "generator" / "generator" / "models.yaml"))
    runtime = Runtime(catalog, GeneratorsEvaluatorClient("http://evaluator", client=evaluator_http), sleep=lambda s: None)
    generator_http = TestClient(generator_main.create_app(runtime, start_worker=False))

    review_db = review_sessions(review_engine("sqlite://"))
    ReviewBase.metadata.create_all(review_db.kw["bind"])
    review_http = TestClient(review_main.create_app(session_factory=review_db, start_workers=False))

    lab_db = lab_sessions(lab_engine("sqlite://"))
    LabBase.metadata.create_all(lab_db.kw["bind"])
    with lab_db() as session:
        seed_demo_topics(session, SEED / "demo_topics.json")
        import_thesis_sample(session, SEED / "thesis_sample.json")
        session.commit()
    lab_app = lab_main.create_app(
        session_factory=lab_db, start_workers=False, run_seed=False,
        evaluator=EvaluatorClient("http://evaluator", client=evaluator_http),
        generator=GeneratorClient("http://generator", client=generator_http),
        review=ReviewClient("http://review", client=review_http))
    lab_http = TestClient(lab_app)
    token = lab_http.post("/auth/login", json={"username": "operator", "password": "edugen-demo"}).json()["access_token"]
    return {"lab": lab_http, "lab_db": lab_db, "review": review_http, "review_db": review_db,
            "jobs": JobHandler(runtime), "evaluator": lab_app.state.evaluator,
            "auth": {"Authorization": f"Bearer {token}"}}


def deliver_jobs(system) -> int:
    """Outbox -> 'broker' -> Generator -> result message -> Lab, as RabbitMQ would carry them."""
    publisher = CollectingPublisher()
    OutboxRelay(system["lab_db"], publisher, on_published=mark_dispatched).run_once()
    for command in publisher.messages:
        assert command["type"] == "generation.requested"
        result = system["jobs"](command)
        with system["lab_db"]() as session:
            handle_generation_result(session, result)
            session.commit()
    return len(publisher.messages)


def test_an_experiment_runs_through_generator_and_evaluator(system):
    lab, auth = system["lab"], system["auth"]
    models = {m["alias"]: m for m in lab.get("/models", headers=auth).json()}
    assert models["simulator"]["available"]
    body = {"name": "Contract test", "topic_ids": ["NETCOMP-DEMO-1", "SYSTEM-DEMO-1"], "models": ["simulator"],
            "strategies": ["baseline", "prompt_v2", "verify_repair"], "questions_per_job": 3}
    experiment = lab.post("/experiments", json=body, headers=auth)
    assert experiment.status_code == 202
    experiment_id = experiment.json()["id"]

    assert deliver_jobs(system) == 6
    with system["lab_db"]() as session:
        assert evaluate_pending(session, system["evaluator"]) == 6
        session.commit()

    detail = lab.get(f"/experiments/{experiment_id}", headers=auth).json()
    assert detail["status"] == "completed", [j["error"] for j in detail["jobs"]]
    assert all(j["simulated"] and j["items"] == 3 for j in detail["jobs"])
    verify = [j for j in detail["jobs"] if j["strategy"] == "verify_repair"]
    assert all(j["strategy_status"] in ("all_passed", "best_effort") and j["calls"] >= 3 for j in verify)

    summary = lab.get(f"/experiments/{experiment_id}/summary", headers=auth).json()
    assert summary["bands_available"] and {g["strategy"] for g in summary["groups"]} == {"baseline", "prompt_v2", "verify_repair"}
    for group in summary["groups"]:
        assert group["pillars"]["P1"]["band_of_mean"] is not None and group["valid"] == 6
    # The key-balancing strategies spread the keys over all four letters
    balanced = next(g for g in summary["groups"] if g["strategy"] == "prompt_v2")
    assert max(balanced["key_positions"].values()) - min(balanced["key_positions"].values()) <= 2
    # ... while the letters the model wrote before the balancing reach the Lab too
    assert balanced["raw_keys_known"] == 6 and sum(balanced["raw_key_positions"].values()) == 6

    items = lab.get(f"/experiments/{experiment_id}/items", headers=auth).json()
    assert items["total"] == 18 and all(i["flags"] is not None for i in items["items"])


def test_a_blind_study_runs_through_the_review_service_and_back(system):
    lab, review, auth = system["lab"], system["review"], system["auth"]
    study = lab.post("/studies", headers=auth, json={"title": "Contract study", "kind": "both", "per_cell": 1,
                                                     "student_items": 3, "experiment_ids": [THESIS_EXPERIMENT_ID]})
    assert study.status_code == 201 and study.json()["status"] == "open", study.json()
    codes = study.json()

    expert = {"Authorization": "Bearer " + review.post("/v1/sessions", json={"code": codes["expert_code"], "rater_name": "Rater 1"}).json()["token"]}
    for _ in range(3):
        item = review.get("/v1/expert/next", headers=expert).json()["item"]
        assert set(item) == {"item_ref", "topic_label", "domain", "question", "options", "answer"}  # still blind
        saved = review.put(f"/v1/expert/ratings/{item['item_ref']}", headers=expert, json={
            "relevance": 4, "clarity": 4, "difficulty": 3, "distractors": 3, "key_correct": "yes"})
        assert saved.status_code == 200

    student = {"Authorization": "Bearer " + review.post("/v1/sessions", json={"code": codes["student_code"], "consent": True}).json()["token"]}
    for _ in range(3):
        question = review.get("/v1/quiz/current", headers=student).json()
        ref = question["item"]["item_ref"]
        review.post("/v1/quiz/answers", headers=student, json={"item_ref": ref, "choice": "B"})
        state = review.post("/v1/quiz/feedback", headers=student, json={"item_ref": ref, "clarity": 4, "helpfulness": 4, "difficulty": 2}).json()
    assert state["state"] == "completed"

    # Review outbox -> 'broker' -> Lab inbox
    with system["review_db"]() as session:
        events = [json.loads(m.body) for m in session.scalars(select(ReviewOutbox).order_by(ReviewOutbox.id))]
    assert {e["type"] for e in events} == {"review.rating.submitted", "review.answer.submitted", "review.feedback.submitted"}
    with system["lab_db"]() as session:
        outcomes = [handle_review_event(session, e) for e in events]
        session.commit()
    assert outcomes == ["stored"] * 9

    analytics = lab.get(f"/studies/{codes['id']}/analytics", headers=auth).json()
    assert analytics["progress"] == {"raters": 1, "ratings": 3, "participants": 1, "answers": 3, "feedback": 3}
    rated = [i for i in analytics["items"] if i["expert"]["ratings"]]
    assert len(rated) == 3 and all(i["model"] in {"cohere", "gpt-oss", "llama33", "mistral-small"} for i in rated)


def test_the_labs_cost_bound_uses_the_generators_call_limits():
    attempts = generator_config.MAX_ATTEMPTS
    assert MAX_CALLS_PER_JOB == {"baseline": attempts, "prompt_v2": attempts,
                                 "verify_repair": (WRITER_CALLS + REPAIR_ROUNDS) * attempts}


def test_jobs_are_not_lost_when_published_before_any_consumer(system):
    """The outbox keeps unpublished jobs: nothing is marked sent until the broker accepted it."""
    lab, auth = system["lab"], system["auth"]
    lab.post("/experiments", headers=auth, json={"name": "Queued", "topic_ids": ["SPECALK-DEMO-1"],
                                                 "models": ["simulator"], "strategies": ["baseline"], "questions_per_job": 2})
    with system["lab_db"]() as session:
        pending = list(session.scalars(select(LabOutbox).where(LabOutbox.published_at.is_(None))))
    assert len(pending) == 1 and pending[0].message_type == "generation.requested"
