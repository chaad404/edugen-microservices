from typing import List, Optional
from pydantic import BaseModel, Field

class MCQItem(BaseModel):
    id: Optional[str] = None
    question_stem: str = Field(..., description="The main question text")
    option_a: str = Field(..., description="Option A")
    option_b: str = Field(..., description="Option B")
    option_c: str = Field(..., description="Option C")
    option_d: str = Field(..., description="Option D")
    correct_option: str = Field(..., pattern="^[A-Da-d]$", description="Correct option key (A, B, C, or D)")
    explanation: Optional[str] = Field(None, description="Pedagogical rationale for the key")

    def get_correct_text(self) -> str:
        key = self.correct_option.upper()
        mapping = {"A": self.option_a, "B": self.option_b, "C": self.option_c, "D": self.option_d}
        return mapping.get(key, "")

    def get_distractors(self) -> List[str]:
        key = self.correct_option.upper()
        mapping = {"A": self.option_a, "B": self.option_b, "C": self.option_c, "D": self.option_d}
        return [text for opt, text in mapping.items() if opt != key]

class EvaluateItemRequest(BaseModel):
    source_text: str = Field(..., description="Authorized syllabus/reference text")
    question: MCQItem

class ItemEvaluationResult(BaseModel):
    semantic_alignment: float = Field(..., description="Pillar 1: Lexical TF Cosine similarity with syllabus")
    linguistic_complexity: float = Field(..., description="Pillar 2: Flesch-Kincaid Grade Level")
    reading_ease: float = Field(..., description="Flesch Reading Ease score")
    distractor_plausibility: float = Field(..., description="Pillar 3: Average foil-to-key Jaccard similarity")
    distractor_diversity: float = Field(..., description="Pairwise inter-foil divergence")
    quality_gate_passed: bool = Field(..., description="Passes automated sanity and quality criteria")
    flags: List[str] = Field(default_factory=list, description="Quality warnings or anomaly flags")

class EvaluateBatchRequest(BaseModel):
    source_text: str = Field(..., description="Curriculum reference text")
    questions: List[MCQItem]

class EvaluateBatchResponse(BaseModel):
    total_questions: int
    mean_semantic_alignment: float
    mean_linguistic_complexity: float
    mean_distractor_plausibility: float
    passed_quality_gate_count: int
    results: List[ItemEvaluationResult]
