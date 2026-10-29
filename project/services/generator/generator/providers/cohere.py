"""Cohere v2 chat API (Command A in the thesis)."""
from typing import Optional

import httpx

from ..catalog import ModelSpec
from .base import ChatResult, ProviderError, post_json, request_fields


class CohereProvider:
    name = "cohere"
    url = "https://api.cohere.com/v2/chat"

    def __init__(self, spec: ModelSpec, api_key: str, client: Optional[httpx.Client] = None, timeout: float = 120.0):
        self.spec = spec
        self._api_key = api_key
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0))

    def chat(self, messages: list[dict], json_mode: bool) -> ChatResult:
        body = {"model": self.spec.model_id, "messages": messages,
                **request_fields(self.name, self.spec.settings, self.spec.extra)}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        data = post_json(self.client, self.url, {"Authorization": f"Bearer {self._api_key}"}, body)
        try:
            text = data["message"]["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise ProviderError("Unexpected response shape from Cohere.") from None
        tokens = (data.get("usage") or {}).get("tokens") or {}
        # Cohere does not echo the model ID; the requested ID is pinned in the registry
        return ChatResult(text, int(tokens.get("input_tokens") or 0), int(tokens.get("output_tokens") or 0), None)
