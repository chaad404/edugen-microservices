"""Synchronous calls to the Evaluator, used by the verify -> repair -> select strategy."""
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import httpx


class EvaluatorUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Verdict:
    flags: tuple
    repairable: bool
    serious: bool
    quality: Optional[int]

    @property
    def passed(self) -> bool:
        return not self.flags


class EvaluatorClient:
    def __init__(self, base_url: str, timeout: float = 30.0, attempts: int = 3,
                 client: Optional[httpx.Client] = None, sleep: Callable[[float], None] = time.sleep):
        self.url = base_url.rstrip("/") + "/v1/evaluations"
        self.attempts = attempts
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0))
        self.sleep = sleep

    def check(self, source_text: str, items: Sequence[dict]) -> list[Verdict]:
        body = {"source_text": source_text, "context": source_text, "items": [
            {"id": str(i), **{k: item[k] for k in ("question", "options", "answer", "evidence") if k in item}}
            for i, item in enumerate(items)]}
        last = None
        for attempt in range(1, self.attempts + 1):
            try:
                response = self.client.post(self.url, json=body)
                if response.status_code < 500:
                    response.raise_for_status()  # a 4xx is a bug in this request, not an outage
                    results = response.json()["items"]
                    return [Verdict(tuple(r["flags"]), r["repairable"], r["serious"], r["quality"]) for r in results]
                last = f"HTTP {response.status_code}"
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = type(e).__name__
            if attempt < self.attempts:
                self.sleep(0.5 * 2 ** attempt)
        raise EvaluatorUnavailable(f"Evaluator unavailable after {self.attempts} attempts ({last})")
