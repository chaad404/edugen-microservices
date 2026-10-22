"""The model registry: which alias means which model, where it is hosted, what it costs, whether it is usable."""
import os
from dataclasses import dataclass, field
from typing import Optional

import yaml


@dataclass(frozen=True)
class ModelSpec:
    alias: str
    label: str
    provider: str
    model_id: str
    rpm: float
    price_input: float
    price_output: float
    api_key_env: Optional[str] = None
    routing: dict = field(default_factory=dict)
    settings: dict = field(default_factory=dict)
    params: Optional[str] = None
    notes: Optional[str] = None

    @property
    def paid(self) -> bool:
        return self.price_input > 0 or self.price_output > 0

    def api_key(self) -> Optional[str]:
        return os.getenv(self.api_key_env) if self.api_key_env else None

    @property
    def available(self) -> bool:
        return self.provider == "simulator" or bool(self.api_key())

    def cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return prompt_tokens / 1e6 * self.price_input + completion_tokens / 1e6 * self.price_output

    def public(self) -> dict:
        """What other services may see: never the key itself, only whether one is configured."""
        return {
            "alias": self.alias, "label": self.label, "provider": self.provider, "model_id": self.model_id,
            "params": self.params, "rpm": self.rpm, "paid": self.paid, "available": self.available,
            "requires": None if self.available else self.api_key_env,
            "price_per_m": {"input": self.price_input, "output": self.price_output}, "notes": self.notes,
        }


def load_catalog(path: str) -> dict[str, ModelSpec]:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    catalog = {}
    for alias, spec in data["models"].items():
        prices = spec.get("price_per_m", {})
        catalog[alias] = ModelSpec(
            alias=alias, label=spec.get("label", alias), provider=spec["provider"], model_id=spec["model_id"],
            rpm=float(spec.get("rpm", 30)), price_input=float(prices.get("input", 0)),
            price_output=float(prices.get("output", 0)), api_key_env=spec.get("api_key_env"),
            routing=spec.get("routing") or {}, settings=spec.get("settings") or {},
            params=spec.get("params"), notes=spec.get("notes"),
        )
    return catalog
