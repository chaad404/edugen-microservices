import pytest

from conftest import FakeEvaluator, ScriptedProvider, no_sleep, provider_error, request_envelope
from generator.evaluator_client import EvaluatorUnavailable
from generator.jobs import COMPLETED, FAILED, JobHandler, PoisonMessage, Runtime, parse_job
from generator.providers import build_provider


def handler(catalog, evaluator=None, provider_factory=build_provider) -> JobHandler:
    return JobHandler(Runtime(catalog, evaluator or FakeEvaluator(), max_attempts=2,
                              provider_factory=provider_factory, sleep=no_sleep))


def test_parse_job_rejects_messages_it_cannot_understand():
    assert parse_job(request_envelope()).num_questions == 3
    with pytest.raises(PoisonMessage):
        parse_job({**request_envelope(), "type": "something.else"})
    with pytest.raises(PoisonMessage):
        parse_job(request_envelope(topic={"title": "no id and no text"}))
    with pytest.raises(PoisonMessage):
        parse_job(request_envelope(num_questions=0))


def test_a_completed_job_reports_items_provenance_and_cost(catalog):
    result = handler(catalog)(request_envelope())
    assert result["type"] == COMPLETED
    assert result["correlation_id"] == "exp-1" and result["causation_id"] == "msg-1"
    payload = result["payload"]
    assert payload["job_id"] == "job-1" and len(payload["items"]) == 3
    assert payload["simulated"] is True and payload["provider"] == "simulator" and payload["cost_usd"] == 0
    assert payload["requested_model_id"] == "edugen-simulator-1" and payload["calls"] == 1


def test_unknown_models_and_strategies_fail_the_job(catalog):
    assert handler(catalog)(request_envelope(model="gpt-5"))["payload"]["error_kind"] == "invalid_job"
    assert handler(catalog)(request_envelope(strategy="magic"))["payload"]["error_kind"] == "invalid_job"


def test_a_model_without_its_key_fails_with_model_unavailable(catalog, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    result = handler(catalog)(request_envelope(model="gpt-oss"))
    assert result["type"] == FAILED and result["payload"]["error_kind"] == "model_unavailable"
    assert "OPENROUTER_API_KEY" in result["payload"]["error"]


def test_a_rejected_request_fails_without_retrying(catalog):
    provider = ScriptedProvider([provider_error(402, retryable=False)])
    result = handler(catalog, provider_factory=lambda spec, **kw: provider)(request_envelope())
    assert result["payload"]["error_kind"] == "provider_rejected" and result["payload"]["status_code"] == 402
    assert len(provider.calls) == 1


def test_exhausted_retries_report_the_tokens_already_spent(catalog):
    provider = ScriptedProvider(["no json", "still no json"])
    result = handler(catalog, provider_factory=lambda spec, **kw: provider)(request_envelope())
    payload = result["payload"]
    assert payload["error_kind"] == "invalid_output" and payload["attempts"] == 2
    assert payload["prompt_tokens"] == 200


def test_verify_repair_needs_the_evaluator(catalog):
    class DownEvaluator:
        def check(self, *args):
            raise EvaluatorUnavailable("connection refused")

    result = handler(catalog, evaluator=DownEvaluator())(request_envelope(strategy="verify_repair"))
    assert result["payload"]["error_kind"] == "evaluator_unavailable"
