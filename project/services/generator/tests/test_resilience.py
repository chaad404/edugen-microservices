import json
import random

import pytest

from conftest import ScriptedProvider, client_for, provider_error
from generator.llm import GenerationFailed
from generator.resilience import CircuitBreaker, CircuitOpen, RateLimiter, RetryPolicy
from generator.validation import normalized_questions

VALID = json.dumps({"questions": [{"question": "Which mechanism retransmits a lost segment early?",
                                   "options": {"A": "Fast retransmit", "B": "Slow start", "C": "Congestion avoidance",
                                               "D": "Delayed acknowledgement"}, "answer": "A"}]})


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_rate_limiter_spaces_requests_by_60_over_rpm():
    clock = FakeClock()
    limiter = RateLimiter(30, clock=clock, sleep=clock.sleep)
    limiter.wait()
    limiter.wait()
    assert clock.slept == [pytest.approx(2.0)]


def test_circuit_breaker_opens_fails_fast_and_recovers():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout=30, clock=clock)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitBreaker.OPEN
    with pytest.raises(CircuitOpen):
        breaker.before_call()
    clock.now += 30
    breaker.before_call()  # trial call allowed
    assert breaker.state == CircuitBreaker.HALF_OPEN
    breaker.record_failure()  # trial failed: open again at once
    assert breaker.state == CircuitBreaker.OPEN
    clock.now += 30
    breaker.before_call()
    breaker.record_success()
    assert breaker.state == CircuitBreaker.CLOSED and breaker.failures == 0


def test_retry_policy():
    policy = RetryPolicy(base=2, cap=60, rng=random.Random(1))
    assert policy.delay(2, provider_error(429)) >= 40              # rate limit: wait out most of a window
    assert policy.delay(1, provider_error(429, retry_after=90)) == 90
    assert policy.delay(1, provider_error(503, retry_after=7)) == 7
    for attempt in range(1, 8):
        assert 0 <= policy.delay(attempt, provider_error(503)) <= min(60, 2 * 2 ** attempt)


def test_invalid_output_is_retried_and_all_tokens_are_counted(catalog):
    provider = ScriptedProvider(["not json", VALID])
    items, usage, attempts, returned = client_for(catalog["simulator"], provider).complete_json(
        [{"role": "user", "content": "x"}], lambda d: normalized_questions(d, 1))
    assert attempts == 2 and usage.calls == 2 and usage.prompt_tokens == 200
    assert items[0]["answer"] == "A" and returned == "scripted-model"


def test_a_rejected_key_is_not_retried(catalog):
    provider = ScriptedProvider([provider_error(401, retryable=False), VALID])
    with pytest.raises(Exception) as info:
        client_for(catalog["simulator"], provider).complete_json([], lambda d: d)
    assert info.value.status == 401 and len(provider.calls) == 1


def test_persistent_outage_ends_after_max_attempts(catalog):
    provider = ScriptedProvider([provider_error(503)] * 3)
    client = client_for(catalog["simulator"], provider, max_attempts=3)
    with pytest.raises(GenerationFailed) as info:
        client.complete_json([], lambda d: d)
    assert info.value.kind == "provider_error" and info.value.attempts == 3
    assert client.breaker.failures == 3


def test_unusable_answers_every_time_end_as_invalid_output(catalog):
    provider = ScriptedProvider(["{}", "{}"])
    with pytest.raises(GenerationFailed) as info:
        client_for(catalog["simulator"], provider, max_attempts=2).complete_json([], lambda d: normalized_questions(d, 1))
    assert info.value.kind == "invalid_output" and info.value.usage.calls == 2
