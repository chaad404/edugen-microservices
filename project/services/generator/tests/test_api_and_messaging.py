import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pika.exceptions import UnroutableError

from conftest import FakeEvaluator, request_envelope
from generator.jobs import Runtime
from generator.main import create_app
from generator.messaging import COMMANDS, DLX, JOBS_DEAD, JOBS_QUEUE, JobConsumer, declare_topology


def test_catalog_endpoints(catalog, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    client = TestClient(create_app(Runtime(catalog, FakeEvaluator()), start_worker=False))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200
    models = {m["alias"]: m for m in client.get("/v1/models").json()}
    assert models["simulator"]["available"] is True
    assert models["gpt-oss"]["available"] is False and models["gpt-oss"]["requires"] == "OPENROUTER_API_KEY"
    assert [s["key"] for s in client.get("/v1/strategies").json()] == ["baseline", "prompt_v2", "verify_repair"]


class RecordingChannel:
    def __init__(self, unroutable=False):
        self.calls = []
        self.unroutable = unroutable

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            if name == "basic_publish" and self.unroutable:
                raise UnroutableError([])
        return record

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


class FakeConnection:
    def __init__(self):
        self.later = []

    def call_later(self, delay, callback):
        self.later.append(delay)


def test_topology_dead_letters_the_job_queue():
    channel = RecordingChannel()
    declare_topology(channel)
    queue = next(c for c in channel.named("queue_declare") if c[1][0] == JOBS_QUEUE)
    assert queue[2]["arguments"] == {"x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": JOBS_QUEUE}
    assert ("queue_bind", (JOBS_QUEUE, COMMANDS), {"routing_key": "generation.requested"}) in channel.calls
    assert ("queue_bind", (JOBS_DEAD, DLX), {"routing_key": JOBS_QUEUE}) in channel.calls


def test_unreadable_messages_go_to_the_dead_letter_queue():
    channel = RecordingChannel()
    consumer = JobConsumer("amqp://unused", handler=lambda env: env)
    consumer._on_message(FakeConnection(), channel, SimpleNamespace(delivery_tag=7), None, b"{not json")
    assert channel.calls == [("basic_reject", (7,), {"requeue": False})]
    consumer._on_message(FakeConnection(), channel, SimpleNamespace(delivery_tag=8), None,
                         json.dumps({"type": "generation.requested", "payload": {}}).encode())
    assert channel.calls[-1] == ("basic_reject", (8,), {"requeue": False})


def test_the_job_is_acknowledged_only_after_the_result_is_published():
    result = {"type": "generation.completed", "message_id": "m-2", "correlation_id": "exp-1",
              "payload": {"job_id": "job-1"}}
    channel = RecordingChannel()
    JobConsumer("amqp://unused", handler=None)._finish(FakeConnection(), channel, 9, result, 0)
    assert [c[0] for c in channel.calls] == ["basic_publish", "basic_ack"]
    assert channel.named("basic_publish")[0][2]["mandatory"] is True

    unroutable, connection = RecordingChannel(unroutable=True), FakeConnection()
    JobConsumer("amqp://unused", handler=None, retry_interval=5)._finish(connection, unroutable, 9, result, 0)
    assert not unroutable.named("basic_ack") and connection.later == [5]


def test_request_envelope_fixture_is_a_valid_job_message():
    assert request_envelope()["payload"]["topic"]["source_text"]
