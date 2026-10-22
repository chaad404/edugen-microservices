"""One model behind rate limiting, a circuit breaker and retries: the only retry layer for LLM calls."""
import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

from .catalog import ModelSpec
from .providers.base import ChatResult, ProviderError
from .resilience import CircuitBreaker, CircuitOpen, RateLimiter, RetryPolicy
from .validation import InvalidOutput, parse_json_object

T = TypeVar("T")


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    def add(self, result: ChatResult) -> None:
        self.prompt_tokens += result.prompt_tokens
        self.completion_tokens += result.completion_tokens
        self.calls += 1

    def merge(self, other: "Usage") -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.calls += other.calls


class GenerationFailed(Exception):
    """Every attempt failed. `usage` still counts the tokens of the failed attempts: they were paid for."""

    def __init__(self, kind: str, message: str, attempts: int, usage: Usage):
        super().__init__(message)
        self.kind, self.attempts, self.usage = kind, attempts, usage


class LLMClient:
    def __init__(self, spec: ModelSpec, provider, limiter: RateLimiter, breaker: CircuitBreaker,
                 policy: RetryPolicy, max_attempts: int = 4, sleep: Callable[[float], None] = time.sleep):
        self.spec, self.provider = spec, provider
        self.limiter, self.breaker, self.policy = limiter, breaker, policy
        self.max_attempts = max_attempts
        self.sleep = sleep

    def complete_json(self, messages: list[dict], parse: Callable[[dict], T]) -> tuple[T, Usage, int, Optional[str]]:
        """
        Calls the model until `parse` accepts its JSON output. Returns (parsed value, usage, attempts, returned
        model ID). A non-retryable provider error (bad key, no credit, retired model) is raised at once.
        """
        usage, last = Usage(), None
        for attempt in range(1, self.max_attempts + 1):
            try:
                self.breaker.before_call()
                self.limiter.wait()
                result = self.provider.chat(messages, json_mode=True)
            except CircuitOpen as e:
                last = e
            except ProviderError as e:
                if not e.retryable:
                    raise
                self.breaker.record_failure()
                last = e
            else:
                self.breaker.record_success()
                usage.add(result)
                try:
                    return parse(parse_json_object(result.text)), usage, attempt, result.returned_model_id
                except InvalidOutput as e:  # the host works; the answer was unusable
                    last = e
            if attempt < self.max_attempts:
                self.sleep(self.policy.delay(attempt, last))
        kind = "invalid_output" if isinstance(last, InvalidOutput) else "provider_error"
        raise GenerationFailed(kind, f"{self.spec.alias}: all {self.max_attempts} attempts failed ({last})",
                               self.max_attempts, usage)
