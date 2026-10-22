"""
Synchronous calls to the other services, each with a time limit. A failure becomes ServiceUnavailable,
which callers turn into a bounded, visible state (retry later, 503, or data marked as incomplete).
"""
import threading
import time
from bisect import bisect_right
from typing import Callable, Optional, Sequence

import httpx


class ServiceUnavailable(RuntimeError):
    pass


class ServiceError(RuntimeError):
    """The other service answered with a 4xx: this request was wrong, retrying will not help."""

    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail}")
        self.status, self.detail = status, detail


def _call(send: Callable[[], httpx.Response], service: str) -> httpx.Response:
    try:
        response = send()
    except (httpx.TimeoutException, httpx.TransportError) as e:
        raise ServiceUnavailable(f"{service} unreachable ({type(e).__name__})") from None
    if response.status_code >= 500:
        raise ServiceUnavailable(f"{service} answered HTTP {response.status_code}")
    if response.status_code >= 400:
        raise ServiceError(response.status_code, response.text[:300])
    return response


class EvaluatorClient:
    BATCH = 100  # the Evaluator's limit per request

    def __init__(self, base_url: str, timeout: float = 30.0, client: Optional[httpx.Client] = None):
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0))

    def evaluate(self, source_text: Optional[str], items: Sequence[dict]) -> list[dict]:
        """Scores of each item, in order. Without a source text the Evaluator skips alignment."""
        results = []
        for start in range(0, len(items), self.BATCH):
            body = {"source_text": source_text, "items": list(items[start:start + self.BATCH])}
            response = _call(lambda: self.client.post(f"{self.base}/v1/evaluations", json=body), "Evaluator")
            data = response.json()
            if not data.get("dense_available"):
                # The framework bands are defined on the dense metrics: wait rather than store lexical-only scores
                raise ServiceUnavailable("Evaluator is running without its embedding model")
            results += data["items"]
        return results

    def framework(self) -> dict:
        return _call(lambda: self.client.get(f"{self.base}/v1/framework"), "Evaluator").json()


class GeneratorClient:
    """The model catalog, cached briefly; the last known catalog is used while the Generator is down."""

    def __init__(self, base_url: str, timeout: float = 5.0, ttl: float = 30.0, client: Optional[httpx.Client] = None):
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=3.0))
        self.ttl = ttl
        self._cache: Optional[list] = None
        self._fetched = 0.0
        self._lock = threading.Lock()

    def models(self) -> list[dict]:
        with self._lock:
            if self._cache is not None and time.monotonic() - self._fetched < self.ttl:
                return self._cache
            try:
                self._cache = _call(lambda: self.client.get(f"{self.base}/v1/models"), "Generator").json()
                self._fetched = time.monotonic()
            except ServiceUnavailable:
                if self._cache is None:
                    raise
            return self._cache


class ReviewClient:
    def __init__(self, base_url: str, timeout: float = 10.0, client: Optional[httpx.Client] = None):
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=3.0))

    def create_study(self, payload: dict, token: str, idempotency_key: str) -> dict:
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": idempotency_key}
        return _call(lambda: self.client.post(f"{self.base}/internal/v1/studies", json=payload, headers=headers),
                     "Review").json()


class Framework:
    """The Evaluator's pillar definitions; bands are always computed from its published cut points."""

    def __init__(self, data: dict):
        self.version = data["version"]
        self.pillars = {p["key"]: p for p in data["pillars"]}

    def band(self, key: str, value: Optional[float]) -> Optional[str]:
        if value is None:
            return None
        pillar = self.pillars[key]
        return pillar["labels"][bisect_right(pillar["cuts"], value)]

    def in_zone(self, key: str, value: Optional[float]) -> Optional[bool]:
        zone = self.pillars[key].get("zone")
        return None if value is None or not zone else zone[0] <= value < zone[1]


class FrameworkCache:
    def __init__(self, evaluator: EvaluatorClient, ttl: float = 600.0):
        self.evaluator, self.ttl = evaluator, ttl
        self._value: Optional[Framework] = None
        self._fetched = 0.0
        self._lock = threading.Lock()

    def get(self) -> Optional[Framework]:
        with self._lock:
            if self._value is None or time.monotonic() - self._fetched > self.ttl:
                try:
                    self._value, self._fetched = Framework(self.evaluator.framework()), time.monotonic()
                except (ServiceUnavailable, ServiceError, KeyError):
                    pass  # keep the last known definition; None only if it was never available
            return self._value
