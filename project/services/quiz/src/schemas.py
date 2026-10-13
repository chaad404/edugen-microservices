from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class CreateExamQuestionInput(BaseModel):
    question_stem: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str = Field(..., pattern="^[A-Da-d]$")
    explanation: Optional[str] = None

class CreateExamRequest(BaseModel):
    title: str = Field(..., description="Exam title")
    domain: Optional[str] = Field("SYSTEM", description="Curricular domain")
    duration_minutes: int = Field(20, ge=1, le=180)
    passing_percentage: float = Field(60.0, ge=0.0, le=100.0)
    questions: List[CreateExamQuestionInput]

class ExamOption(BaseModel):
    key: str
    text: str

class TakeExamQuestion(BaseModel):
    id: str
    question_stem: str
    options: List[ExamOption]

class TakeExamResponse(BaseModel):
    exam_id: str
    title: str
    domain: str
    duration_minutes: int
    total_questions: int
    questions: List[TakeExamQuestion]

class SubmitExamRequest(BaseModel):
    student_name: str = Field("Student", description="Name or student ID")
    answers: Dict[str, str] = Field(..., description="Mapping of question_id -> selected_option (A/B/C/D)")

class QuestionReviewItem(BaseModel):
    question_id: str
    question_stem: str
    selected_option: str
    correct_option: str
    is_correct: bool
    explanation: Optional[str] = None

class SubmitExamResponse(BaseModel):
    attempt_id: str
    student_name: str
    score_percentage: float
    total_questions: int
    correct_count: int
    passed: bool
    review: List[QuestionReviewItem]

class ItemPsychometrics(BaseModel):
    question_id: str
    question_stem: str
    total_attempts: int
    correct_count: int
    difficulty_index_p: float = Field(..., description="Item Difficulty Index (p = correct/attempts)")
    option_selection_counts: Dict[str, int]
    dead_distractors: List[str]
    pedagogical_status: str

class ExamAnalyticsResponse(BaseModel):
    exam_id: str
    title: str
    total_attempts: int
    average_score: float
    pass_rate: float
    items: List[ItemPsychometrics]
