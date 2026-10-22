"""Chat providers: one adapter per API, all returning the same ChatResult."""
from .base import ChatResult, ProviderError
from .factory import ModelUnavailable, build_provider

__all__ = ["ChatResult", "ProviderError", "ModelUnavailable", "build_provider"]
