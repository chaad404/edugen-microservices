"""Mistral's own chat completions API (Mistral Small 4 in the thesis), called directly with the user's account."""
from typing import Optional

import httpx

from ..catalog import ModelSpec
from .base import ChatResult, ProviderError, post_json, request_fields


def _text(content) -> str:
    """Message content as text: a string, or the text parts of a list (thinking parts are left out)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text") or "" for part in content
                       if isinstance(part, dict) and part.get("type", "text") == "text")
    raise TypeError(f"message content is a {type(content).__name__}")


class MistralProvider:
    name = "mistral"
    url = "https://api.mistral.ai/v1/chat/completions"

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
            text = _text(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError):
            raise ProviderError("Unexpected response shape from Mistral.") from None
        usage = data.get("usage") or {}
        return ChatResult(text, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0),
                          data.get("model"))
