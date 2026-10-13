import random
from typing import List
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .models import Exam, ExamQuestion, StudentAttempt, StudentAnswer
from .database import init_db, get_db
from .schemas import (
    CreateExamRequest,
    TakeExamResponse,
    TakeExamQuestion,
    ExamOption,
    SubmitExamRequest,
    SubmitExamResponse,
    QuestionReviewItem,
    ExamAnalyticsResponse,
    ItemPsychometrics
)

init_db()

app = FastAPI(
    title="EduGen Quiz & Psychometrics Service",
    description="Assessment Delivery & Empirical Psychometric Analysis Microservice",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "edugen-quiz",
        "version": "1.0.0"
    }

@app.post("/exams")
def create_exam_endpoint(req: CreateExamRequest, db: Session = Depends(get_db)):
    if not req.questions:
        raise HTTPException(status_code=400, detail="An exam must have at least one question.")

    exam = Exam(
        title=req.title,
        domain=req.domain or "SYSTEM",
        duration_minutes=req.duration_minutes,
        passing_percentage=req.passing_percentage
    )
    db.add(exam)
    db.flush()

    for q_input in req.questions:
        question = ExamQuestion(
            exam_id=exam.id,
            question_stem=q_input.question_stem,
            option_a=q_input.option_a,
            option_b=q_input.option_b,
            option_c=q_input.option_c,
            option_d=q_input.option_d,
            correct_option=q_input.correct_option.upper(),
            explanation=q_input.explanation
        )
        db.add(question)

    db.commit()
    return {
        "message": "Exam created successfully",
        "exam_id": exam.id,
        "question_count": len(req.questions)
    }

@app.get("/exams")
def list_exams_endpoint(db: Session = Depends(get_db)):
    exams = db.query(Exam).order_by(Exam.created_at.desc()).all()
    return [
        {
            "id": e.id,
            "title": e.title,
            "domain": e.domain,
            "duration_minutes": e.duration_minutes,
            "passing_percentage": e.passing_percentage,
            "question_count": len(e.questions),
            "attempt_count": len(e.attempts),
            "created_at": e.created_at.isoformat()
        }
        for e in exams
    ]

@app.get("/exams/{exam_id}/take", response_model=TakeExamResponse)
def take_exam_endpoint(exam_id: str, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions_payload = []
    for q in exam.questions:
        options = [
            ExamOption(key="A", text=q.option_a),
            ExamOption(key="B", text=q.option_b),
            ExamOption(key="C", text=q.option_c),
            ExamOption(key="D", text=q.option_d),
        ]
        questions_payload.append(TakeExamQuestion(
            id=q.id,
            question_stem=q.question_stem,
            options=options
        ))

    return TakeExamResponse(
        exam_id=exam.id,
        title=exam.title,
        domain=exam.domain,
        duration_minutes=exam.duration_minutes,
        total_questions=len(questions_payload),
        questions=questions_payload
    )

@app.post("/exams/{exam_id}/submit", response_model=SubmitExamResponse)
def submit_exam_endpoint(exam_id: str, req: SubmitExamRequest, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    correct_count = 0
    total = len(exam.questions)
    review_items = []

    # Map question_id -> Question
    q_map = {q.id: q for q in exam.questions}

    # Evaluate each answer
    student_answers_to_save = []
    for q_id, q in q_map.items():
        selected = req.answers.get(q_id, "").upper()
        is_corr = (selected == q.correct_option)
        if is_corr:
            correct_count += 1

        review_items.append(QuestionReviewItem(
            question_id=q.id,
            question_stem=q.question_stem,
            selected_option=selected or "UNANSWERED",
            correct_option=q.correct_option,
            is_correct=is_corr,
            explanation=q.explanation
        ))

        student_answers_to_save.append((q_id, selected or "NONE", is_corr))

    score_pct = round((correct_count / max(1, total)) * 100.0, 1)
    passed = score_pct >= exam.passing_percentage

    # Save StudentAttempt
    attempt = StudentAttempt(
        exam_id=exam.id,
        student_name=req.student_name,
        score_percentage=score_pct,
        passed=passed
    )
    db.add(attempt)
    db.flush()

    for q_id, sel, is_corr in student_answers_to_save:
        sa = StudentAnswer(
            attempt_id=attempt.id,
            question_id=q_id,
            selected_option=sel,
            is_correct=is_corr
        )
        db.add(sa)

    db.commit()

    return SubmitExamResponse(
        attempt_id=attempt.id,
        student_name=req.student_name,
        score_percentage=score_pct,
        total_questions=total,
        correct_count=correct_count,
        passed=passed,
        review=review_items
    )

@app.get("/exams/{exam_id}/analytics", response_model=ExamAnalyticsResponse)
def exam_analytics_endpoint(exam_id: str, db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    attempts = exam.attempts
    total_attempts = len(attempts)

    avg_score = round(sum(a.score_percentage for a in attempts) / max(1, total_attempts), 2) if total_attempts > 0 else 0.0
    passed_count = sum(1 for a in attempts if a.passed)
    pass_rate = round((passed_count / max(1, total_attempts)) * 100.0, 1) if total_attempts > 0 else 0.0

    item_metrics = []
    for q in exam.questions:
        q_answers = db.query(StudentAnswer).filter(StudentAnswer.question_id == q.id).all()
        q_attempts = len(q_answers)
        q_correct = sum(1 for a in q_answers if a.is_correct)

        p_value = round(q_correct / max(1, q_attempts), 3) if q_attempts > 0 else 0.0

        counts = {"A": 0, "B": 0, "C": 0, "D": 0}
        for a in q_answers:
            opt = a.selected_option.upper()
            if opt in counts:
                counts[opt] += 1

        # Check dead distractors (foils chosen 0 times when attempts > 3)
        dead_foils = [opt for opt in ["A", "B", "C", "D"] if opt != q.correct_option and counts[opt] == 0]

        # Pedagogical status
        if q_attempts < 2:
            status = "INSUFFICIENT_DATA"
        elif p_value < 0.25:
            status = "DIFFICULT_FLAG (p < 0.25)"
        elif p_value > 0.90:
            status = "TRIVIAL_FLAG (p > 0.90)"
        elif len(dead_foils) >= 2:
            status = "INEFFECTIVE_DISTRACTORS"
        else:
            status = "OPTIMAL"

        item_metrics.append(ItemPsychometrics(
            question_id=q.id,
            question_stem=q.question_stem,
            total_attempts=q_attempts,
            correct_count=q_correct,
            difficulty_index_p=p_value,
            option_selection_counts=counts,
            dead_distractors=dead_foils if q_attempts >= 3 else [],
            pedagogical_status=status
        ))

    return ExamAnalyticsResponse(
        exam_id=exam.id,
        title=exam.title,
        total_attempts=total_attempts,
        average_score=avg_score,
        pass_rate=pass_rate,
        items=item_metrics
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("project.services.quiz.src.main:app", host="0.0.0.0", port=8003, reload=True)
