from types import SimpleNamespace

from sqlalchemy import func, select

from conftest import outbox_payloads
from lab.models import Experiment, Job
from lab.orchestration import estimate
from lab.seed import import_thesis_sample
from conftest import SEED

BODY = {"name": "Demo run", "topic_ids": ["NETCOMP-DEMO-1"], "models": ["simulator"],
        "strategies": ["baseline", "prompt_v2"], "questions_per_job": 3}


def test_an_experiment_is_accepted_with_one_job_and_one_outbox_message_per_cell(client, auth, session_factory):
    response = client.post("/experiments", json=BODY, headers=auth)
    assert response.status_code == 202
    body = response.json()
    assert response.headers["location"] == f"/experiments/{body['id']}"
    assert body["status"] == "running" and body["jobs_total"] == 2 and body["job_counts"] == {"queued": 2}

    with session_factory() as session:
        messages = outbox_payloads(session)
    assert [m["type"] for m in messages] == ["generation.requested"] * 2
    payload = messages[0]["payload"]
    assert payload["topic"]["source_text"].startswith("## The congestion window")  # event-carried state
    assert payload["num_questions"] == 3 and messages[0]["correlation_id"] == body["id"]

    detail = client.get(f"/experiments/{body['id']}", headers=auth).json()
    assert {j["strategy"] for j in detail["jobs"]} == {"baseline", "prompt_v2"}


def test_paid_models_need_an_explicit_confirmation(client, auth):
    body = {**BODY, "models": ["simulator", "llama33"]}
    response = client.post("/experiments", json=body, headers=auth)
    assert response.status_code == 422
    problem = response.json()
    assert problem["type"] == "urn:edugen:problem:paid-models-not-confirmed"
    assert problem["estimate"]["jobs"] == 4 and problem["estimate"]["estimated_cost_usd"] > 0
    assert "expected about $" in problem["detail"] and "at most $" in problem["detail"]
    assert client.post("/experiments", json={**body, "confirm_paid": True}, headers=auth).status_code == 202


def test_requests_that_cannot_run_are_rejected_with_a_stable_problem_type(client, auth, session_factory):
    with session_factory() as session:
        import_thesis_sample(session, SEED / "thesis_sample.json")
        session.commit()
    cases = {
        "model-unavailable": {**BODY, "models": ["cohere"], "confirm_paid": True},
        "unknown-model": {**BODY, "models": ["gpt-7"]},
        "unknown-strategy": {**BODY, "strategies": ["magic"]},
        "unknown-topic": {**BODY, "topic_ids": ["NOPE-1"]},
        "topic-without-source-text": {**BODY, "topic_ids": ["NETCOMP-2022-1"]},
    }
    for code, body in cases.items():
        response = client.post("/experiments", json=body, headers=auth)
        assert response.status_code == 422, code
        assert response.json()["type"] == f"urn:edugen:problem:{code}"
    assert client.post("/experiments", json={**BODY, "models": ["simulator", "simulator"]}, headers=auth).status_code == 422


def test_the_same_idempotency_key_never_starts_a_second_experiment(client, auth, session_factory):
    headers = {**auth, "Idempotency-Key": "run-42"}
    first = client.post("/experiments", json=BODY, headers=headers)
    second = client.post("/experiments", json=BODY, headers=headers)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Experiment)) == 1
        assert session.scalar(select(func.count()).select_from(Job)) == 2

    reused = client.post("/experiments", json={**BODY, "name": "Other"}, headers=headers)
    assert reused.status_code == 409
    assert reused.json()["type"] == "urn:edugen:problem:idempotency-key-reused"


def test_without_the_model_catalog_no_experiment_starts(client, auth, fakes):
    fakes.generator.down = True
    response = client.post("/experiments", json=BODY, headers=auth)
    assert response.status_code == 503
    assert response.json()["type"] == "urn:edugen:problem:model-catalog-unavailable"


def test_estimate_reports_jobs_and_cost(client, auth):
    body = client.post("/experiments/estimate", json={**BODY, "models": ["llama33"]}, headers=auth).json()
    assert body["jobs"] == 2 and body["paid_models"] == ["llama33"] and body["estimated_cost_usd"] > 0
    assert body["max_cost_usd"] > body["estimated_cost_usd"] and body["max_per_model"]["llama33"] == body["max_cost_usd"]


def test_the_estimate_uses_measured_output_and_bounds_every_attempt():
    topic = SimpleNamespace(source_text="x" * 400)  # prompt: 400 / 4 + 900 = 1,000 tokens expected
    model = {"alias": "m", "paid": True, "price_per_m": {"input": 1.0, "output": 2.0},
             "settings": {"max_tokens": 8192}, "output_tokens_per_question": 100}
    cost = estimate([topic], [model], ["baseline"], 5)
    assert cost["estimated_cost_usd"] == round((1000 * 1.0 + 500 * 2.0) / 1e6, 4)
    # At most: 4 attempts, each with the generous prompt (400 / 2 + 3,000) and the full max_tokens
    assert cost["max_cost_usd"] == round(4 * (3200 * 1.0 + 8192 * 2.0) / 1e6, 4)

    unbounded = {**model, "alias": "u", "settings": {}}
    cost = estimate([topic], [model, unbounded], ["baseline"], 5)
    assert cost["max_per_model"] == {"m": 0.0783, "u": None} and cost["max_cost_usd"] is None
    free = {"alias": "simulator", "paid": False, "price_per_m": {"input": 0, "output": 0}}
    assert estimate([topic], [free], ["verify_repair"], 5)["max_cost_usd"] == 0


def test_catalog_routes(client, auth, fakes):
    topics = client.get("/topics", headers=auth).json()
    assert {t["topic_id"] for t in topics} == {"NETCOMP-DEMO-1", "SPECALK-DEMO-1", "SYSTEM-DEMO-1"}
    assert client.get("/topics/SYSTEM-DEMO-1", headers=auth).json()["source_text"].startswith("## Linearity")
    assert client.get("/topics/NOPE", headers=auth).status_code == 404
    assert client.get("/framework", headers=auth).json()["version"] == "thesis-2026-10"
    assert [m["alias"] for m in client.get("/models", headers=auth).json()][0] == "simulator"

    new = {"topic_id": "OTHER-CUSTOM-1", "domain": "OTHER", "title": "Custom topic", "source_text": "x " * 150}
    created = client.post("/topics", json=new, headers=auth)
    assert created.status_code == 201 and created.headers["location"] == "/topics/OTHER-CUSTOM-1"
    assert client.post("/topics", json=new, headers=auth).status_code == 409
