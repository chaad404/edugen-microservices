"""Request bodies of the Lab API. Limits are part of the contract (course chapter 6.4: operational layer)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

CHANNEL_PATTERN = r"^(experiment|study):[0-9a-f-]{36}$"


def _unique(values: list[str]) -> list[str]:
    if len(set(values)) != len(values):
        raise ValueError("values must be unique")
    return values


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class StreamTicketRequest(BaseModel):
    channel: str = Field(pattern=CHANNEL_PATTERN, examples=["experiment:2026a5e0-0000-4000-8000-000000000001"])


class TopicCreate(BaseModel):
    topic_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,40}$", examples=["NETCOMP-CUSTOM-1"])
    domain: Literal["NETCOMP", "SPECALK", "SYSTEM", "OTHER"]
    title: str = Field(min_length=3, max_length=300)
    source_text: str = Field(min_length=200, max_length=60_000)


class ExperimentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    topic_ids: list[str] = Field(min_length=1, max_length=10)
    models: list[str] = Field(min_length=1, max_length=6)
    strategies: list[str] = Field(min_length=1, max_length=3)
    questions_per_job: int = Field(default=5, ge=1, le=10)
    confirm_paid: bool = Field(default=False, description="Required when a selected model calls a paid API")
    description: Optional[str] = Field(default=None, max_length=1000)

    check_unique = field_validator("topic_ids", "models", "strategies")(_unique)


class StudyCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["expert", "student", "both"] = "both"
    experiment_ids: list[str] = Field(min_length=1, max_length=5)
    per_cell: int = Field(default=2, ge=1, le=20, description="Questions per model x strategy x domain cell")
    seed: int = Field(default=2026, description="Same seed, same sample")
    student_items: int = Field(default=10, ge=1, le=40, description="Questions each student answers")

    check_unique = field_validator("experiment_ids")(_unique)
