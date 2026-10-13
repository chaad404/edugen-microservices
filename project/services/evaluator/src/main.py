from typing import List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import (
    EvaluateItemRequest,
    ItemEvaluationResult,
    EvaluateBatchRequest,
    EvaluateBatchResponse,
    MCQItem
)
from .metrics import (
    calculate_semantic_alignment,
    calculate_linguistic_complexity,
    calculate_distractor_plausibility,
    calculate_distractor_diversity
)
from .quality_gate import audit_quality_gate

app = FastAPI(
    title="EduGen Evaluator Service",
    description="Deterministic NLP Evaluation Microservice implementing The Three Pillars of Assessment Quality",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def evaluate_single_item(item: MCQItem, source_text: str) -> ItemEvaluationResult:
    # Pillar 1
    alignment = calculate_semantic_alignment(source_text, item.question_stem)
    # Pillar 2
    grade, ease = calculate_linguistic_complexity(item.question_stem)
    # Pillar 3
    correct_text = item.get_correct_text()
    distractors = item.get_distractors()
    plausibility = calculate_distractor_plausibility(correct_text, distractors)
    diversity = calculate_distractor_diversity(distractors)
    # Quality Gate
    passed, flags = audit_quality_gate(item, alignment)

    return ItemEvaluationResult(
        semantic_alignment=alignment,
        linguistic_complexity=grade,
        reading_ease=ease,
        distractor_plausibility=plausibility,
        distractor_diversity=diversity,
        quality_gate_passed=passed,
        flags=flags
    )

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "edugen-evaluator",
        "version": "1.0.0"
    }

@app.post("/evaluate/item", response_model=ItemEvaluationResult)
def evaluate_item_endpoint(req: EvaluateItemRequest):
    try:
        return evaluate_single_item(req.question, req.source_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {str(e)}")

@app.post("/evaluate/batch", response_model=EvaluateBatchResponse)
def evaluate_batch_endpoint(req: EvaluateBatchRequest):
    if not req.questions:
        raise HTTPException(status_code=400, detail="Question list cannot be empty.")

    results: List[ItemEvaluationResult] = []
    for q in req.questions:
        res = evaluate_single_item(q, req.source_text)
        results.append(res)

    total = len(results)
    avg_align = round(sum(r.semantic_alignment for r in results) / total, 4)
    avg_comp = round(sum(r.linguistic_complexity for r in results) / total, 2)
    avg_plaus = round(sum(r.distractor_plausibility for r in results) / total, 4)
    passed_count = sum(1 for r in results if r.quality_gate_passed)

    return EvaluateBatchResponse(
        total_questions=total,
        mean_semantic_alignment=avg_align,
        mean_linguistic_complexity=avg_comp,
        mean_distractor_plausibility=avg_plaus,
        passed_quality_gate_count=passed_count,
        results=results
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("project.services.evaluator.src.main:app", host="0.0.0.0", port=8002, reload=True)
