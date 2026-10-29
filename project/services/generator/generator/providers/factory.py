"""Builds the provider adapter for a model alias."""
from typing import Optional

import httpx

from ..catalog import ModelSpec
from .cohere import CohereProvider
from .mistral import MistralProvider
from .openrouter import OpenRouterProvider
from .simulator import SimulatorProvider


class ModelUnavailable(RuntimeError):
    """The model needs an API key that is not configured."""


def build_provider(spec: ModelSpec, *, client: Optional[httpx.Client] = None, simulator_delay: float = 0.0,
                   timeout: float = 120.0):
    if spec.provider == "simulator":
        return SimulatorProvider(spec, delay=simulator_delay)
    key = spec.api_key()
    if not key:
        raise ModelUnavailable(f"{spec.label} needs the environment variable {spec.api_key_env}")
    if spec.provider == "openrouter":
        return OpenRouterProvider(spec, key, client, timeout)
    if spec.provider == "mistral":
        return MistralProvider(spec, key, client, timeout)
    if spec.provider == "cohere":
        return CohereProvider(spec, key, client, timeout)
    raise ValueError(f"Unknown provider '{spec.provider}' for model '{spec.alias}'")
