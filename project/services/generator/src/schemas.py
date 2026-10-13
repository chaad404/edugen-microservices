from typing import List, Optional
from pydantic import BaseModel, Field
import uuid

class GeneratedMCQ(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question_stem: str = Field(..., description="The problem statement")
    option_a: str = Field(..., description="Option A")
    option_b: str = Field(..., description="Option B")
    option_c: str = Field(..., description="Option C")
    option_d: str = Field(..., description="Option D")
    correct_option: str = Field(..., pattern="^[A-Da-d]$", description="Correct key: A, B, C, or D")
    explanation: Optional[str] = Field(None, description="Pedagogical rationale for key")
    strategy_used: Optional[str] = Field(None, description="Strategy that created this item")

class GenerateBatchRequest(BaseModel):
    topic_id: str = Field(default="SYSTEM-2022-1", description="Unique topic identifier")
    domain: Optional[str] = Field(default="SYSTEM", description="Curricular domain")
    title: Optional[str] = Field(default="Systems Fundamentals", description="Topic title")
    source_text: str = Field(..., description="Curriculum reference text for grounding")
    model_name: str = Field(default="mock", description="Model alias (mock, gpt-4o, llama33, mistral)")
    strategy: str = Field(default="multi_agent", description="Generation strategy: zero_shot, rag, or multi_agent")
    count: int = Field(default=3, ge=1, le=10, description="Number of questions to generate (1-10)")

class GenerateBatchResponse(BaseModel):
    run_id: str
    topic_id: str
    model_name: str
    strategy: str
    questions: List[GeneratedMCQ]
    latency_seconds: float
    tokens_used: int
    estimated_cost_usd: float
