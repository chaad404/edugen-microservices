"""OpenRouter chat completions (OpenAI-compatible). `routing` pins the host, as in the thesis."""
from typing import Optional

import httpx

from ..catalog import ModelSpec
from .base import NON_RETRYABLE_STATUS, ChatResult, ProviderError, post_json


class OpenRouterProvider:
    name = "openrouter"
    url = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, spec: ModelSpec, api_key: str, client: Optional[httpx.Client] = None, timeout: float = 120.0):
        self.spec = spec
        self._api_key = api_key
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0))

    def chat(self, messages: list[dict], json_mode: bool) -> ChatResult:
        body = {"model": self.spec.model_id, "messages": messages, **self.spec.settings}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.spec.routing:
            body["provider"] = self.spec.routing
        data = post_json(self.client, self.url, {"Authorization": f"Bearer {self._api_key}", "X-Title": "EduGen"}, body)

        # OpenRouter reports some upstream failures inside an HTTP 200 body
        if data.get("error"):
            error = data["error"]
            code = error.get("code") if isinstance(error.get("code"), int) else None
            raise ProviderError(f"Upstream error: {str(error.get('message'))[:200]}", status=code,
                                retryable=code not in NON_RETRYABLE_STATUS)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderError("Unexpected response shape from OpenRouter.") from None
        usage = data.get("usage") or {}
        return ChatResult(text, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0),
                          data.get("model"))
