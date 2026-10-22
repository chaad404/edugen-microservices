import json

import httpx
import pytest

from generator.providers.base import ProviderError
from generator.providers.cohere import CohereProvider
from generator.providers.openrouter import OpenRouterProvider

MESSAGES = [{"role": "system", "content": "Output ONLY JSON."}, {"role": "user", "content": "Write 1 question"}]


def client_returning(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_openrouter_request_pins_the_host_and_asks_for_json(catalog):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json={"model": "meta-llama/llama-3.3-70b-instruct",
                                         "choices": [{"message": {"content": '{"questions": []}'}}],
                                         "usage": {"prompt_tokens": 120, "completion_tokens": 30}})

    result = OpenRouterProvider(catalog["llama33"], "key-1", client_returning(handler)).chat(MESSAGES, json_mode=True)
    assert seen["auth"] == "Bearer key-1"
    assert seen["body"]["model"] == "meta-llama/llama-3.3-70b-instruct"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["provider"]["order"] == ["coreweave"]
    assert (result.prompt_tokens, result.completion_tokens) == (120, 30)
    assert result.returned_model_id == "meta-llama/llama-3.3-70b-instruct"


def test_rate_limit_is_retryable_and_carries_retry_after(catalog):
    provider = OpenRouterProvider(catalog["gpt-oss"], "k", client_returning(
        lambda r: httpx.Response(429, headers={"Retry-After": "7"}, text="slow down")))
    with pytest.raises(ProviderError) as info:
        provider.chat(MESSAGES, json_mode=True)
    assert info.value.status == 429 and info.value.retry_after == 7 and info.value.retryable


@pytest.mark.parametrize("status", [401, 402, 403, 404, 410])
def test_key_credit_and_model_errors_are_not_retryable(catalog, status):
    provider = OpenRouterProvider(catalog["gpt-oss"], "k", client_returning(lambda r: httpx.Response(status)))
    with pytest.raises(ProviderError) as info:
        provider.chat(MESSAGES, json_mode=True)
    assert info.value.retryable is False


def test_upstream_errors_inside_http_200_are_detected(catalog):
    provider = OpenRouterProvider(catalog["gpt-oss"], "k", client_returning(
        lambda r: httpx.Response(200, json={"error": {"code": 502, "message": "upstream down"}})))
    with pytest.raises(ProviderError) as info:
        provider.chat(MESSAGES, json_mode=True)
    assert info.value.status == 502 and info.value.retryable


def test_timeouts_become_retryable_provider_errors(catalog):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError) as info:
        OpenRouterProvider(catalog["gpt-oss"], "k", client_returning(handler)).chat(MESSAGES, json_mode=True)
    assert info.value.retryable


def test_cohere_response_is_parsed(catalog):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"content": [{"type": "text", "text": '{"questions": []}'}]},
                                         "usage": {"tokens": {"input_tokens": 80, "output_tokens": 20}}})

    result = CohereProvider(catalog["cohere"], "k", client_returning(handler)).chat(MESSAGES, json_mode=True)
    assert seen["url"] == "https://api.cohere.com/v2/chat"
    assert seen["body"]["model"] == "command-a-03-2025"
    assert result.text == '{"questions": []}' and result.prompt_tokens == 80 and result.returned_model_id is None
