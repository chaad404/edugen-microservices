from pathlib import Path

import pytest

from generator.catalog import load_catalog
from generator.evaluator_client import Verdict
from generator.llm import LLMClient
from generator.providers.base import ChatResult, ProviderError
from generator.resilience import CircuitBreaker, RateLimiter, RetryPolicy
from generator.strategies import Job

TOPIC_TEXT = """## Slow start
TCP slow start begins with a small congestion window and increases it by one segment for every acknowledgement received.
Because every acknowledgement enlarges the window, the congestion window roughly doubles in each round trip during slow start.
Slow start ends when the congestion window reaches the slow start threshold or when a segment loss is detected.

## Congestion avoidance
In congestion avoidance the sender increases the congestion window by about one segment per round trip time.
This additive increase probes the available bandwidth carefully once the window has passed the threshold.
After a timeout the threshold is set to half of the current window and the window restarts from one segment.

## Fast retransmit and fast recovery
Three duplicate acknowledgements make the sender retransmit the missing segment without waiting for the retransmission timer.
During fast recovery the threshold is halved and the window is set to the new threshold instead of restarting slow start.
Multiplicative decrease after a loss together with additive increase gives the sawtooth pattern of the congestion window.
"""


def make_job(**overrides) -> Job:
    values = dict(job_id="job-1", experiment_id="exp-1", topic_id="NETCOMP-DEMO-1", topic_title="TCP congestion control",
                  domain="NETCOMP", source_text=TOPIC_TEXT, model="simulator", strategy="baseline", num_questions=3)
    values.update(overrides)
    return Job(**values)


def request_envelope(**payload_overrides) -> dict:
    payload = {"job_id": "job-1", "experiment_id": "exp-1", "model": "simulator", "strategy": "baseline",
               "num_questions": 3, "topic": {"topic_id": "NETCOMP-DEMO-1", "title": "TCP congestion control",
                                              "domain": "NETCOMP", "source_text": TOPIC_TEXT}}
    payload.update(payload_overrides)
    return {"message_id": "msg-1", "type": "generation.requested", "version": 1, "payload": payload}


class ScriptedProvider:
    """Returns the scripted results in order; an exception in the script is raised instead."""
    name = "scripted"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, messages, json_mode):
        self.calls.append(messages)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return ChatResult(step, 100, 50, "scripted-model")


class FakeEvaluator:
    """First check flags every candidate; later checks (after repair) pass everything."""

    def __init__(self, first_flags=("weak:B",)):
        self.first_flags = tuple(first_flags)
        self.calls = 0

    def check(self, source_text, items):
        self.calls += 1
        flags = self.first_flags if self.calls == 1 else ()
        return [Verdict(flags, bool(flags), False, 8) for _ in items]


@pytest.fixture
def catalog():
    return load_catalog(str(Path(__file__).parents[1] / "generator" / "models.yaml"))


def no_sleep(_seconds):
    return None


def client_for(spec, provider, max_attempts=3) -> LLMClient:
    return LLMClient(spec, provider, RateLimiter(0), CircuitBreaker(), RetryPolicy(), max_attempts, sleep=no_sleep)


def provider_error(status, retryable=True, retry_after=None) -> ProviderError:
    return ProviderError(f"HTTP {status}", status=status, retryable=retryable, retry_after=retry_after)
