"""
Request bodies of the Review API. The study contract forbids unknown fields: if the Lab ever sent a model
name or a score with an item, the request would be rejected instead of silently storing it (blindness by contract).
"""
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

Likert = Annotated[int, Field(ge=1, le=5)]
LABELS = ("A", "B", "C", "D")


class StudyItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_ref: str = Field(min_length=8, max_length=36)
    topic_label: str = Field(max_length=300)
    domain: str = Field(max_length=32)
    question: str = Field(max_length=4000)
    options: dict[str, str]
    answer: Literal["A", "B", "C", "D"]

    @field_validator("options")
    @classmethod
    def four_labelled_options(cls, value: dict[str, str]) -> dict[str, str]:
        if sorted(value) != list(LABELS) or any(not text.strip() or len(text) > 1000 for text in value.values()):
            raise ValueError("options must have the labels A, B, C and D with non-empty text")
        return value


class StudyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_id: str = Field(min_length=8, max_length=36)
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["expert", "student", "both"]
    seed: int
    student_items: int = Field(ge=1, le=40)
    items: list[StudyItemIn] = Field(min_length=1, max_length=500)


class JoinRequest(BaseModel):
    code: str = Field(min_length=4, max_length=32)
    rater_name: Optional[str] = Field(default=None, pattern=r"^[\w .-]{2,60}$",
                                      description="Experts: a pseudonym, used to resume the review")
    consent: bool = Field(default=False, description="Students: the participation and data-use notice was accepted")


class RatingIn(BaseModel):
    relevance: Likert
    clarity: Likert
    difficulty: Likert
    distractors: Likert
    key_correct: Literal["yes", "no", "unsure"]
    unusable: bool = False
    unusable_reason: Optional[str] = Field(default=None, max_length=1000)
    comment: Optional[str] = Field(default=None, max_length=2000)


class AnswerIn(BaseModel):
    item_ref: str = Field(max_length=36)
    choice: Literal["A", "B", "C", "D"] = Field(description="The shown position the student picked")


class FeedbackIn(BaseModel):
    item_ref: str = Field(max_length=36)
    clarity: Likert
    helpfulness: Likert
    difficulty: Likert
