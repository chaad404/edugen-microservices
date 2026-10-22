"""Request and response contract of the Evaluator API."""
from typing import Annotated, Optional

from pydantic import BaseModel, Field

OptionText = Annotated[str, Field(max_length=1000)]


class ItemIn(BaseModel):
    id: Optional[str] = Field(default=None, max_length=100, description="Caller's identifier, echoed back")
    question: str = Field(max_length=4000)
    options: dict[str, OptionText] = Field(max_length=8, description="Option labels A-D mapped to their text")
    answer: str = Field(max_length=300, description="Label of the correct option")
    evidence: Optional[str] = Field(default=None, max_length=4000,
                                    description="Quote that proves the key; enables the evidence checks")


class EvaluationRequest(BaseModel):
    source_text: Optional[str] = Field(default=None, max_length=200_000,
                                       description="Topic source text; without it alignment is not measured")
    context: Optional[str] = Field(default=None, max_length=400_000,
                                   description="Text the evidence must come from; defaults to source_text")
    items: list[ItemIn] = Field(min_length=1, max_length=100)


class Metrics(BaseModel):
    alignment: Optional[float] = Field(default=None, description="P1, dense: max cosine stem vs source passages")
    alignment_lexical: Optional[float] = Field(default=None, description="P1, lexical: TF cosine")
    grade: Optional[float] = Field(default=None, description="P2: Flesch-Kincaid grade of the stem")
    plausibility: Optional[float] = Field(default=None, description="P3a, dense: mean cosine key vs distractors")
    plausibility_lexical: Optional[float] = Field(default=None, description="P3a, lexical: mean Jaccard")
    diversity: Optional[float] = Field(default=None, description="P3b, dense: 1 - mean cosine among distractors")


class Bands(BaseModel):
    P1: Optional[str] = None
    P2: Optional[str] = None
    P3a: Optional[str] = None
    P3b: Optional[str] = None


class ItemResult(BaseModel):
    id: Optional[str] = None
    valid: bool
    validation_notes: str
    metrics: Metrics
    bands: Bands
    flags: list[str]
    repairable: bool = Field(description="Has flags, and all of them can be fixed by rewriting options or the stem")
    serious: bool = Field(description="Has a flag that needs a different question")
    quality: Optional[int] = Field(default=None, description="Band points over the four pillars (0-12)")


class BatchResult(BaseModel):
    n: int
    key_positions: dict[str, int]
    key_position_chi2: Optional[float] = None
    key_position_p: Optional[float] = Field(default=None, description="Chi-square test against 25% per letter")
    key_longest_rate: Optional[float] = Field(default=None, description="Share of keys that are strictly the longest option")
    duplicate_stems: int


class EvaluationResponse(BaseModel):
    framework_version: str
    dense_available: bool
    embedding_model: Optional[str] = None
    items: list[ItemResult]
    batch: BatchResult
