import json

import httpx
import pytest

from generator.providers import ModelUnavailable, build_provider
from generator.providers.base import ProviderError
from generator.providers.cohere import CohereProvider
from generator.providers.mistral import MistralProvider
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


def test_mistral_is_called_directly_with_the_versioned_model_id(catalog):
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"model": "mistral-small-2603",
                                         "choices": [{"message": {"content": '{"questions": []}'}}],
                                         "usage": {"prompt_tokens": 95, "completion_tokens": 25}})

    result = MistralProvider(catalog["mistral-small"], "key-2", client_returning(handler)).chat(MESSAGES, json_mode=True)
    assert seen["url"] == "https://api.mistral.ai/v1/chat/completions" and seen["auth"] == "Bearer key-2"
    assert seen["body"]["model"] == "mistral-small-2603" and "provider" not in seen["body"]
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert (result.text, result.prompt_tokens, result.completion_tokens) == ('{"questions": []}', 95, 25)
    assert result.returned_model_id == "mistral-small-2603"


def test_mistral_content_parts_keep_the_text_and_drop_the_thinking(catalog):
    content = [{"type": "thinking", "thinking": [{"type": "text", "text": "Let me plan."}]},
               {"type": "text", "text": '{"questions": '}, {"type": "text", "text": "[]}"}]
    provider = MistralProvider(catalog["mistral-small"], "k", client_returning(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": content}}], "usage": {}})))
    assert provider.chat(MESSAGES, json_mode=True).text == '{"questions": []}'


def test_the_factory_needs_the_mistral_key(catalog, monkeypatch):
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    with pytest.raises(ModelUnavailable, match="MISTRAL_API_KEY"):
        build_provider(catalog["mistral-small"])
    monkeypatch.setenv("MISTRAL_API_KEY", "k")
    assert isinstance(build_provider(catalog["mistral-small"]), MistralProvider)


def _body_sent(provider_class, spec):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        if provider_class is CohereProvider:
            return httpx.Response(200, json={"message": {"content": [{"type": "text", "text": "{}"}]}, "usage": {}})
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}], "usage": {}})

    provider_class(spec, "k", client_returning(handler)).chat(MESSAGES, json_mode=True)
    return seen["body"]


def test_the_fixed_settings_are_sent_in_each_apis_own_names(catalog):
    for provider_class, alias in ((OpenRouterProvider, "llama33"), (MistralProvider, "mistral-small")):
        body = _body_sent(provider_class, catalog[alias])
        assert (body["temperature"], body["top_p"], body["max_tokens"]) == (0.7, 1.0, 8192), alias
    cohere = _body_sent(CohereProvider, catalog["cohere"])
    assert (cohere["temperature"], cohere["p"], cohere["max_tokens"]) == (0.7, 1.0, 8192) and "top_p" not in cohere
    gpt_oss = _body_sent(OpenRouterProvider, catalog["gpt-oss"])
    assert gpt_oss["reasoning"] == {"effort": "medium"} and gpt_oss["provider"]["order"] == ["groq"]
