from pika.exceptions import UnroutableError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from conftest import completed, failed, questions
from lab.models import Experiment, Job, OutboxMessage
from lab.orchestration import evaluate_pending, handle_generation_result, mark_dispatched
from lab.outbox import OutboxRelay

BODY = {"name": "Pipeline", "topic_ids": ["NETCOMP-DEMO-1"], "models": ["simulator"],
        "strategies": ["baseline", "prompt_v2"], "questions_per_job": 3}


class FakePublisher:
    def __init__(self, fail_with=None):
        self.sent, self.fail_with, self.resets = [], fail_with, 0

    def publish(self, exchange, routing_key, body, **kwargs):
        if self.fail_with:
            raise self.fail_with
        self.sent.append((exchange, routing_key, kwargs["message_type"]))

    def reset(self):
        self.resets += 1


def start(client, auth) -> str:
    return client.post("/experiments", json=BODY, headers=auth).json()["id"]


def jobs_of(session_factory, experiment_id):
    with session_factory() as session:
        return list(session.scalars(select(Job).options(selectinload(Job.items))
                                    .where(Job.experiment_id == experiment_id).order_by(Job.strategy)))


def test_the_relay_publishes_in_order_and_marks_jobs_dispatched(client, auth, session_factory):
    experiment_id = start(client, auth)
    publisher = FakePublisher()
    assert OutboxRelay(session_factory, publisher, on_published=mark_dispatched).run_once() == 2
    assert publisher.sent == [("edugen.commands", "generation.requested", "generation.requested")] * 2
    assert {j.status for j in jobs_of(session_factory, experiment_id)} == {"dispatched"}
    assert OutboxRelay(session_factory, publisher).run_once() == 0  # nothing is sent twice


def test_an_unroutable_message_stays_in_the_outbox(client, auth, session_factory):
    start(client, auth)
    assert OutboxRelay(session_factory, FakePublisher(UnroutableError([]))).run_once() == 0
    with session_factory() as session:
        rows = list(session.scalars(select(OutboxMessage)))
    assert all(r.published_at is None for r in rows)
    assert rows[0].attempts == 1 and "unroutable" in rows[0].last_error


def test_results_are_consumed_idempotently(client, auth, session_factory):
    experiment_id = start(client, auth)
    first, second = jobs_of(session_factory, experiment_id)
    message = completed(first.id)
    with session_factory() as session:
        assert handle_generation_result(session, message) == "generated"
        session.commit()
    with session_factory() as session:
        assert handle_generation_result(session, message) == "duplicate"           # redelivered message
        assert handle_generation_result(session, completed(first.id)) == "already_processed"  # repeated job
        assert handle_generation_result(session, completed("no-such-job")) == "unknown_job"
        session.commit()
    job = jobs_of(session_factory, experiment_id)[0]
    assert job.status == "generated" and len(job.items) == 3 and job.simulated and job.prompt_tokens == 900


def test_the_job_view_shows_the_recorded_settings(client, auth, session_factory):
    experiment_id = start(client, auth)
    first, second = jobs_of(session_factory, experiment_id)
    message = completed(first.id)
    message["payload"]["trace"] = {"settings": {"temperature": 0.7, "top_p": 1.0, "max_tokens": 8192}}
    with session_factory() as session:
        handle_generation_result(session, message)
        session.commit()
    jobs = {j["id"]: j for j in client.get(f"/experiments/{experiment_id}", headers=auth).json()["jobs"]}
    assert jobs[first.id]["settings"] == {"temperature": 0.7, "top_p": 1.0, "max_tokens": 8192}
    assert jobs[second.id]["settings"] is None  # not run yet, or run before settings were recorded


def test_evaluation_scores_the_items_and_completes_the_experiment(client, auth, session_factory, fakes):
    experiment_id = start(client, auth)
    first, second = jobs_of(session_factory, experiment_id)
    with session_factory() as session:
        handle_generation_result(session, completed(first.id))
        handle_generation_result(session, failed(second.id))
        session.commit()
    with session_factory() as session:
        assert evaluate_pending(session, fakes.evaluator) == 1
        session.commit()
    source_text, sent = fakes.evaluator.calls[0]
    assert source_text.startswith("## The congestion window") and sent[0]["evidence"]

    detail = client.get(f"/experiments/{experiment_id}", headers=auth).json()
    assert detail["status"] == "completed_with_failures"
    assert {j["status"] for j in detail["jobs"]} == {"succeeded", "failed"}
    items = client.get(f"/experiments/{experiment_id}/items", headers=auth).json()
    assert items["total"] == 3 and items["items"][0]["bands"] == {
        "P1": "Better", "P2": "Best", "P3a": "Better", "P3b": "Better"}


def test_while_the_evaluator_is_down_the_job_waits_and_is_retried(client, auth, session_factory, fakes):
    experiment_id = start(client, auth)
    first = jobs_of(session_factory, experiment_id)[0]
    with session_factory() as session:
        handle_generation_result(session, completed(first.id))
        session.commit()
    fakes.evaluator.down = True
    with session_factory() as session:
        assert evaluate_pending(session, fakes.evaluator) == 0
        session.commit()
    job = jobs_of(session_factory, experiment_id)[0]
    assert job.status == "generated" and job.evaluation_attempts == 1 and job.next_evaluation_at is not None

    fakes.evaluator.down = False
    with session_factory() as session:
        session.get(Job, first.id).next_evaluation_at = None  # do not wait for the backoff in the test
        session.commit()
    with session_factory() as session:
        assert evaluate_pending(session, fakes.evaluator) == 1
        session.commit()
    events = client.get(f"/events?channel=experiment:{experiment_id}", headers=auth).json()["events"]
    assert "job.evaluation_delayed" in [e["type"] for e in events]


def test_progress_events_can_be_polled_and_streamed_with_resume(client, auth, session_factory, fakes):
    experiment_id = start(client, auth)
    channel = f"experiment:{experiment_id}"
    first = jobs_of(session_factory, experiment_id)[0]
    with session_factory() as session:
        handle_generation_result(session, completed(first.id))
        session.commit()

    polled = client.get(f"/events?channel={channel}", headers=auth).json()
    assert [e["type"] for e in polled["events"]] == ["experiment.created", "job.generated"]
    after_first = polled["events"][0]["id"]

    ticket = client.post("/auth/stream-tickets", json={"channel": channel}, headers=auth).json()["ticket"]
    with client.stream("GET", f"/events/stream?channel={channel}&ticket={ticket}",
                       headers={"Last-Event-ID": str(after_first)}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.read().decode()
    assert body.startswith("retry: 3000")
    assert "event: job.generated" in body and "event: experiment.created" not in body  # resumed after the ID


def test_summary_compares_models_and_strategies_with_bands(client, auth, session_factory, fakes):
    experiment_id = start(client, auth)
    first, second = jobs_of(session_factory, experiment_id)
    items = questions(4)
    items[0]["question"] = "Which option is the longest?"
    with session_factory() as session:
        handle_generation_result(session, completed(first.id, items))
        handle_generation_result(session, completed(second.id))
        evaluate_pending(session, fakes.evaluator)
        session.commit()
    summary = client.get(f"/experiments/{experiment_id}/summary", headers=auth).json()
    assert summary["bands_available"] is True
    groups = {(g["model"], g["strategy"]): g for g in summary["groups"]}
    baseline = groups[("simulator", "baseline")]
    assert baseline["questions"] == 4 and baseline["pillars"]["P1"]["band_of_mean"] == "Better"
    assert baseline["pillars"]["P2"]["share_in_zone"] == 1.0
    assert baseline["key_positions"] == {"A": 1, "B": 1, "C": 1, "D": 1} and baseline["flags"] == {"length_cue": 1}
    assert set(summary["leaders"]) == {"P1", "P2", "P3a", "P3b"}

    fakes.evaluator.down = True
    client.app.state.framework._value = None
    degraded = client.get(f"/experiments/{experiment_id}/summary", headers=auth).json()
    assert degraded["bands_available"] is False and degraded["groups"][0]["means"]["alignment"] == 0.72


def test_the_comparison_shows_the_key_letters_as_the_model_wrote_them(client, auth, session_factory, fakes):
    experiment_id = start(client, auth)
    first, second = jobs_of(session_factory, experiment_id)  # baseline, prompt_v2
    balanced = completed(second.id)  # stored keys A, B, C after balancing; the model wrote A three times
    balanced["payload"]["trace"] = {"key_balance": "shuffled", "raw_answers": ["A", "A", "A"]}
    with session_factory() as session:
        handle_generation_result(session, completed(first.id))
        handle_generation_result(session, balanced)
        session.commit()
    groups = {g["strategy"]: g for g in client.get(f"/experiments/{experiment_id}/summary", headers=auth).json()["groups"]}
    assert groups["prompt_v2"]["key_positions"] == {"A": 1, "B": 1, "C": 1, "D": 0}
    assert groups["prompt_v2"]["raw_key_positions"] == {"A": 3, "B": 0, "C": 0, "D": 0}
    assert groups["prompt_v2"]["raw_keys_known"] == 3 and groups["prompt_v2"]["raw_key_position_p"] < 0.05
    # Nothing re-orders the baseline's options, so its stored keys are the model's own letters
    assert groups["baseline"]["raw_key_positions"] == groups["baseline"]["key_positions"]

    # A balanced job from before the letters were recorded: its own letters are unknown, not guessed
    older = start(client, auth)
    old_balanced = jobs_of(session_factory, older)[1]
    with session_factory() as session:
        handle_generation_result(session, completed(old_balanced.id))
        session.commit()
    groups = {g["strategy"]: g for g in client.get(f"/experiments/{older}/summary", headers=auth).json()["groups"]}
    assert groups["prompt_v2"]["raw_key_positions"] is None and groups["prompt_v2"]["raw_keys_known"] == 0


def test_unknown_experiment_is_404(client, auth):
    assert client.get("/experiments/does-not-exist", headers=auth).status_code == 404
    with client:  # lifespan with run_seed=False still creates nothing new
        pass
    assert Experiment.__tablename__ == "experiments"
