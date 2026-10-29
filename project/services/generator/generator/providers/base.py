"""What every provider returns, and how HTTP failures are classified for the retry policy."""
from dataclasses import dataclass
from typing import Optional

import httpx

# Client errors that will not fix themselves by retrying: bad key, no credit, no access, unknown or retired model.
# 400 stays retryable: some hosts answer 400 when one sample was not valid JSON (seen in the thesis on Groq).
NON_RETRYABLE_STATUS = frozenset({401, 402, 403, 404, 410})

# Shared setting name -> the parameter name of each provider's API (Cohere calls top_p "p")
SETTING_NAMES = {
    "openrouter": {"temperature": "temperature", "top_p": "top_p", "max_tokens": "max_tokens"},
    "mistral": {"temperature": "temperature", "top_p": "top_p", "max_tokens": "max_tokens"},
    "cohere": {"temperature": "temperature", "top_p": "p", "max_tokens": "max_tokens"},
}


def request_fields(provider: str, settings: dict, extra: dict) -> dict:
    """The settings in the provider's own parameter names, plus the model's provider-specific fields."""
    names = SETTING_NAMES[provider]
    return {**{names[key]: value for key, value in settings.items()}, **extra}


@dataclass(frozen=True)
class ChatResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    returned_model_id: Optional[str]


class ProviderError(Exception):
    def __init__(self, message: str, *, status: Optional[int] = None, retry_after: Optional[float] = None,
                 retryable: bool = True):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.retryable = retryable


def _retry_after(value: Optional[str]) -> Optional[float]:
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:  # the HTTP-date form is not used by these providers
        return None


def post_json(client: httpx.Client, url: str, headers: dict, body: dict) -> dict:
    """POST and return the JSON body; every failure becomes a classified ProviderError."""
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        raise ProviderError("The provider did not answer within the time limit.") from None
    except httpx.TransportError as e:
        raise ProviderError(f"Network error: {type(e).__name__}") from None
    if response.status_code >= 400:
        raise ProviderError(f"HTTP {response.status_code}: {response.text[:300]}", status=response.status_code,
                            retry_after=_retry_after(response.headers.get("Retry-After")),
                            retryable=response.status_code not in NON_RETRYABLE_STATUS)
    try:
        return response.json()
    except ValueError:
        raise ProviderError("The provider answered with a body that is not JSON.", status=response.status_code) from None
