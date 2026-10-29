"""Turns one `generation.requested` message into a `generation.completed` or `generation.failed` message."""
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

from .catalog import ModelSpec
from .evaluator_client import EvaluatorUnavailable
from .llm import GenerationFailed, LLMClient, Usage
from .providers import ModelUnavailable, ProviderError, build_provider
from .resilience import CircuitBreaker, RateLimiter, RetryPolicy
from .strategies import STRATEGIES, Job

logger = logging.getLogger(__name__)

REQUESTED, COMPLETED, FAILED = "generation.requested", "generation.completed", "generation.failed"


class PoisonMessage(ValueError):
    """The message cannot be understood; it goes to the dead-letter queue instead of being retried."""


def make_envelope(type_: str, payload: dict, *, correlation_id: Optional[str] = None,
                  causation_id: Optional[str] = None) -> dict:
    return {"message_id": str(uuid.uuid4()), "type": type_, "version": 1,
            "occurred_at": datetime.now(timezone.utc).isoformat(), "producer": "generator",
            "correlation_id": correlation_id, "causation_id": causation_id, "payload": payload}


def parse_job(envelope: dict) -> Job:
    if not isinstance(envelope, dict) or envelope.get("type") != REQUESTED:
        raise PoisonMessage(f"Not a {REQUESTED} message")
    p = envelope.get("payload") or {}
    try:
        topic = p["topic"]
        job = Job(job_id=str(p["job_id"]), experiment_id=str(p["experiment_id"]), topic_id=str(topic["topic_id"]),
                  topic_title=str(topic.get("title", "")), domain=str(topic.get("domain", "")),
                  source_text=str(topic["source_text"]), model=str(p["model"]), strategy=str(p["strategy"]),
                  num_questions=int(p["num_questions"]))
    except (KeyError, TypeError, ValueError) as e:
        raise PoisonMessage(f"Malformed job payload: {e!r}") from None
    if not 1 <= job.num_questions <= 10 or not job.source_text.strip():
        raise PoisonMessage("Job asks for 1-10 questions from a non-empty topic text")
    return job


class Runtime:
    """Per-process state: one LLM client per model alias, each with its own rate limiter and circuit breaker."""

    def __init__(self, catalog: dict[str, ModelSpec], evaluator, *, max_attempts: int = 4,
                 simulator_delay: float = 0.0, llm_timeout: float = 120.0,
                 provider_factory: Callable = build_provider, sleep: Callable[[float], None] = time.sleep):
        self.catalog, self.evaluator = catalog, evaluator
        self.max_attempts, self.simulator_delay, self.llm_timeout = max_attempts, simulator_delay, llm_timeout
        self.provider_factory, self.sleep = provider_factory, sleep
        self._clients: dict[str, LLMClient] = {}
        self._lock = threading.Lock()

    def llm(self, spec: ModelSpec) -> LLMClient:
        with self._lock:
            if spec.alias not in self._clients:
                provider = self.provider_factory(spec, simulator_delay=self.simulator_delay, timeout=self.llm_timeout)
                self._clients[spec.alias] = LLMClient(spec, provider, RateLimiter(spec.rpm, sleep=self.sleep),
                                                      CircuitBreaker(), RetryPolicy(), self.max_attempts, self.sleep)
            return self._clients[spec.alias]


class JobHandler:
    def __init__(self, runtime: Runtime):
        self.runtime = runtime

    def __call__(self, envelope: dict) -> dict:
        job = parse_job(envelope)
        started = time.monotonic()
        spec = self.runtime.catalog.get(job.model)
        base = {"job_id": job.job_id, "experiment_id": job.experiment_id, "model": job.model, "strategy": job.strategy}

        def reply(type_: str, payload: dict) -> dict:
            payload["latency_seconds"] = round(time.monotonic() - started, 3)
            return make_envelope(type_, {**base, **payload}, correlation_id=job.experiment_id,
                                 causation_id=envelope.get("message_id"))

        def failed(kind: str, message: str, *, status=None, attempts: int = 0, usage: Optional[Usage] = None) -> dict:
            usage = usage or Usage()
            logger.warning("Job %s (%s/%s) failed: %s: %s", job.job_id, job.model, job.strategy, kind, message)
            payload = {"error_kind": kind, "error": message[:500], "status_code": status,
                       "attempts": attempts, "prompt_tokens": usage.prompt_tokens,
                       "completion_tokens": usage.completion_tokens,
                       "cost_usd": round(spec.cost(usage.prompt_tokens, usage.completion_tokens), 6) if spec else 0.0}
            if spec is not None:  # failed jobs record the route and the settings too
                payload.update(provider=spec.provider, requested_model_id=spec.model_id,
                               trace={"settings": spec.request_settings()})
            return reply(FAILED, payload)

        if spec is None:
            return failed("invalid_job", f"Unknown model '{job.model}'")
        strategy = STRATEGIES.get(job.strategy)
        if strategy is None:
            return failed("invalid_job", f"Unknown strategy '{job.strategy}'")

        logger.info("Job %s: %s with %s on %s", job.job_id, job.strategy, job.model, job.topic_id)
        try:
            outcome = strategy(job, self.runtime.llm(spec), self.runtime.evaluator)
        except ModelUnavailable as e:
            return failed("model_unavailable", str(e))
        except ProviderError as e:
            return failed("provider_rejected", str(e), status=e.status, attempts=1)
        except GenerationFailed as e:
            return failed(e.kind, str(e), attempts=e.attempts, usage=e.usage)
        except EvaluatorUnavailable as e:
            return failed("evaluator_unavailable", str(e))
        except Exception as e:  # a bug must not leave the job hanging
            logger.exception("Job %s crashed", job.job_id)
            return failed("internal_error", f"{type(e).__name__}: {e}")

        usage = outcome.usage
        logger.info("Job %s done: %d questions, %d calls, status %s", job.job_id, len(outcome.items), usage.calls, outcome.status)
        return reply(COMPLETED, {
            "provider": spec.provider, "requested_model_id": spec.model_id,
            "returned_model_id": outcome.returned_model_id, "simulated": spec.provider == "simulator",
            "attempts": outcome.attempts, "calls": usage.calls, "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cost_usd": round(spec.cost(usage.prompt_tokens, usage.completion_tokens), 6),
            "strategy_status": outcome.status, "trace": {**outcome.trace, "settings": spec.request_settings()},
            "items": outcome.items,
        })
