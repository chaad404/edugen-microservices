import os
from .base import BaseLLMProvider
from .mock_provider import MockLLMProvider
from .openai_provider import OpenAIProvider

def get_llm_provider(model_name: str) -> BaseLLMProvider:
    """
    Factory resolving provider by model alias.
    Defaults to MockLLMProvider if offline or unspecified.
    """
    name = (model_name or "mock").lower()
    
    if name in ["gpt-4o", "gpt-4o-mini", "openai"]:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return OpenAIProvider(api_key=api_key)
        # Graceful fallback to Mock if key is missing
        return MockLLMProvider()

    return MockLLMProvider()
