"""
Domain logic of the Review service (thesis use cases UC-200 and UC-300):

- Studies arrive from the Lab, idempotent by study ID, and get one expert code and one student code.
- Experts rate every question in their own stable random order and may revise a rating (revision number).
- Students answer a random subset in a strictly linear flow (thesis UI.3.1): answer, then feedback, then the
  next question. An answer cannot be changed. Time per question is measured on the server. The options are
  shuffled per student, and answers are stored in the original labels.
- Every stored rating, answer and feedback also writes an outbox event for the Lab in the same transaction.
"""
import hashlib
import random
import secrets
import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .db import utcnow
from .messages import REVIEW_ANSWER, REVIEW_FEEDBACK, REVIEW_RATING, outbox_event
from .models import ExpertRating, Participant, QuizStep, Study, StudyItem
from .problems import Problem
from .schemas import AnswerIn, FeedbackIn, JoinRequest, RatingIn, StudyIn
from .security import Caller

LABELS = ("A", "B", "C", "D")
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I to misread
ROLES_BY_KIND = {"expert": {"expert"}, "student": {"student"}, "both": {"expert", "student"}}


def _rng(*parts) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16))


def _new_code(session: Session, prefix: str) -> str:
    while True:
        code = f"{prefix}-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))
        if session.scalar(select(Study.id).where(or_(Study.expert_code == code, Study.student_code == code))) is None:
            return code


def create_study(session: Session, body: StudyIn, request_hash: str) -> tuple[Study, bool]:
    existing = session.get(Study, body.study_id)
    if existing is not None:
        if existing.request_hash != request_hash:
            raise Problem(409, "study-conflict", "Study exists", "A different study was already created with this ID.")
        return existing, False
    refs = [item.item_ref for item in body.items]
    if len(set(refs)) != len(refs):
        raise Problem(422, "duplicate-item-ref", "Duplicate item reference", "Every item_ref must be unique.")
    study = Study(id=body.study_id, title=body.title, kind=body.kind, seed=body.seed,
                  student_items=min(body.student_items, len(body.items)), expert_code=_new_code(session, "EXP"),
                  student_code=_new_code(session, "STU"), request_hash=request_hash)
    for position, item in enumerate(body.items):
        study.items.append(StudyItem(item_ref=item.item_ref, position=position, topic_label=item.topic_label,
                                     domain=item.domain, question=item.question, options=item.options,
                                     answer=item.answer))
    session.add(study)
    session.flush()
    return study, True


def study_codes(study: Study) -> dict:
    roles = ROLES_BY_KIND[study.kind]
    return {"study_id": study.id, "items": len(study.items),
            "expert_code": study.expert_code if "expert" in roles else None,
            "student_code": study.student_code if "student" in roles else None}


def join(session: Session, body: JoinRequest) -> tuple[Participant, Study]:
    code = body.code.strip().upper()
    study = session.scalar(select(Study).where(or_(Study.expert_code == code, Study.student_code == code)))
    if study is None:
        raise Problem(404, "unknown-code", "Unknown code", "Check the code you received.")
    role = "expert" if code == study.expert_code else "student"
    if role not in ROLES_BY_KIND[study.kind]:
        raise Problem(404, "unknown-code", "Unknown code", "Check the code you received.")

    if role == "expert":
        name = (body.rater_name or "").strip()
        if not name:
            raise Problem(422, "rater-name-required", "Pseudonym required",
                          "Experts choose a pseudonym, which lets them resume their review later.")
        participant = session.scalar(select(Participant).where(Participant.study_id == study.id,
                                                               Participant.rater_name == name))
        if participant is None:
            participant = Participant(id=str(uuid.uuid4()), study_id=study.id, role="expert", rater_name=name)
            session.add(participant)
        return participant, study

    if not body.consent:
        raise Problem(422, "consent-required", "Consent required",
                      "Please accept the participation notice before starting the quiz.")
    participant = Participant(id=str(uuid.uuid4()), study_id=study.id, role="student")
    session.add(participant)
    rng = _rng(study.seed, participant.id)
    chosen = sorted(study.items, key=lambda i: i.position)
    rng.shuffle(chosen)
    for position, item in enumerate(chosen[:study.student_items]):
        permutation = list(LABELS)
        rng.shuffle(permutation)  # against position bias: the key is not always where the model put it
        session.add(QuizStep(participant_id=participant.id, item_id=item.id, position=position,
                             permutation="".join(permutation)))
    session.flush()
    return participant, study


def _participant(session: Session, caller: Caller) -> tuple[Participant, Study]:
    participant = session.get(Participant, caller.subject)
    if participant is None or participant.study_id != caller.study_id or participant.role != caller.role:
        raise Problem(401, "unknown-session", "Unknown session", "Join the study again with your code.")
    return participant, participant.study


def session_view(session: Session, caller: Caller) -> dict:
    participant, study = _participant(session, caller)
    if participant.role == "expert":
        rated = len(list(session.scalars(select(ExpertRating.id).where(ExpertRating.participant_id == participant.id))))
        total = len(study.items)
    else:
        steps = _steps(session, participant)
        rated, total = sum(1 for s in steps if s.feedback_at is not None), len(steps)
    return {"role": participant.role, "study_title": study.title, "rater_name": participant.rater_name,
            "done": rated, "total": total, "completed": participant.completed_at is not None,
            "completion_code": participant.completion_code}


# --- Expert review (UC-200) ---

def expert_order(study: Study, rater_name: str) -> list[StudyItem]:
    """A different but stable order per rater, so order effects average out (ported from the thesis)."""
    items = sorted(study.items, key=lambda i: i.id)
    _rng(rater_name.strip().lower()).shuffle(items)
    return items


def _item_view(item: StudyItem) -> dict:
    return {"item_ref": item.item_ref, "topic_label": item.topic_label, "domain": item.domain,
            "question": item.question, "options": item.options, "answer": item.answer}


def _rating_view(rating: ExpertRating) -> dict:
    return {"relevance": rating.relevance, "clarity": rating.clarity, "difficulty": rating.difficulty,
            "distractors": rating.distractors, "key_correct": rating.key_correct, "unusable": rating.unusable,
            "unusable_reason": rating.unusable_reason, "comment": rating.comment, "revision": rating.revision}


def _ratings(session: Session, participant: Participant) -> dict[int, ExpertRating]:
    return {r.item_id: r for r in session.scalars(select(ExpertRating).where(ExpertRating.participant_id == participant.id))}


def expert_items(session: Session, caller: Caller) -> dict:
    participant, study = _participant(session, caller)
    rated = _ratings(session, participant)
    order = expert_order(study, participant.rater_name)
    return {"total": len(order), "rated": len(rated),
            "items": [{"position": n, "item_ref": item.item_ref, "rated": item.id in rated} for n, item in enumerate(order, 1)]}


def expert_next(session: Session, caller: Caller) -> dict:
    participant, study = _participant(session, caller)
    rated = _ratings(session, participant)
    order = expert_order(study, participant.rater_name)
    for position, item in enumerate(order, 1):
        if item.id not in rated:
            return {"done": False, "position": position, "total": len(order), "rated": len(rated),
                    "item": _item_view(item), "rating": None}
    return {"done": True, "total": len(order), "rated": len(rated)}


def _study_item(study: Study, item_ref: str) -> StudyItem:
    """Record-level authorization: only items of the caller's own study exist for the caller."""
    item = next((i for i in study.items if i.item_ref == item_ref), None)
    if item is None:
        raise Problem(404, "unknown-item", "Unknown item", "This question is not part of your study.")
    return item


def expert_item(session: Session, caller: Caller, item_ref: str) -> dict:
    participant, study = _participant(session, caller)
    item = _study_item(study, item_ref)
    rating = _ratings(session, participant).get(item.id)
    order = [i.item_ref for i in expert_order(study, participant.rater_name)]
    return {"position": order.index(item.item_ref) + 1, "total": len(order), "item": _item_view(item),
            "rating": _rating_view(rating) if rating else None}


def save_rating(session: Session, caller: Caller, item_ref: str, body: RatingIn) -> dict:
    participant, study = _participant(session, caller)
    item = _study_item(study, item_ref)
    rating = session.scalar(select(ExpertRating).where(ExpertRating.participant_id == participant.id,
                                                       ExpertRating.item_id == item.id))
    fields = body.model_dump()
    if rating is None:
        rating = ExpertRating(participant_id=participant.id, item_id=item.id, revision=1, **fields)
        session.add(rating)
    else:
        for name, value in fields.items():
            setattr(rating, name, value)
        rating.revision += 1
        rating.updated_at = utcnow()
    session.flush()
    session.add(outbox_event(REVIEW_RATING, {
        "study_id": study.id, "item_ref": item.item_ref, "rater": participant.rater_name,
        "relevance": rating.relevance, "clarity": rating.clarity, "difficulty": rating.difficulty,
        "distractors": rating.distractors, "key_correct": rating.key_correct, "unusable": rating.unusable,
        "comment": rating.comment, "revision": rating.revision}, study.id))
    rated = len(_ratings(session, participant))
    if rated == len(study.items) and participant.completed_at is None:
        participant.completed_at = utcnow()
    return {"saved": True, "revision": rating.revision, "rated": rated, "total": len(study.items)}


# --- Student quiz (UC-300) ---

def _steps(session: Session, participant: Participant) -> list[QuizStep]:
    return list(session.scalars(select(QuizStep).where(QuizStep.participant_id == participant.id).order_by(QuizStep.position)))


def _current(steps: list[QuizStep]):
    return next((s for s in steps if s.feedback_at is None), None)


def _completed_view(participant: Participant, steps: list[QuizStep]) -> dict:
    return {"state": "completed", "total": len(steps), "correct": sum(1 for s in steps if s.correct),
            "completion_code": participant.completion_code}


def quiz_current(session: Session, caller: Caller) -> dict:
    participant, study = _participant(session, caller)
    steps = _steps(session, participant)
    step = _current(steps)
    if step is None:
        return _completed_view(participant, steps)
    if step.served_at is None:
        step.served_at = utcnow()  # the time per question starts when it is first shown
    item = step.item
    return {"state": "question" if step.answered_at is None else "feedback", "position": step.position + 1,
            "total": len(steps), "chosen": step.chosen_shown,
            "item": {"item_ref": item.item_ref, "topic_label": item.topic_label, "domain": item.domain,
                     "question": item.question,
                     "options": [{"label": shown, "text": item.options[original]}
                                 for shown, original in zip(LABELS, step.permutation)]}}


def _step_for(steps: list[QuizStep], item_ref: str) -> QuizStep:
    step = _current(steps)
    if step is None:
        raise Problem(409, "quiz-completed", "Quiz completed", "There are no more questions.")
    if step.item.item_ref != item_ref:
        raise Problem(409, "not-current-question", "Not the current question",
                      "Questions are answered in order; an earlier question cannot be changed.")
    return step


def submit_answer(session: Session, caller: Caller, body: AnswerIn) -> dict:
    participant, study = _participant(session, caller)
    step = _step_for(_steps(session, participant), body.item_ref)
    if step.answered_at is not None:
        if step.chosen_shown == body.choice:
            return {"state": "feedback"}  # the same request repeated (e.g. after a timeout): no second effect
        raise Problem(409, "answer-locked", "Answer already given", "An answer cannot be changed.")
    if step.served_at is None:
        raise Problem(409, "question-not-shown", "Question not shown yet", "Load the current question first.")
    now = utcnow()
    step.answered_at, step.chosen_shown = now, body.choice
    step.chosen_original = step.permutation[LABELS.index(body.choice)]
    step.correct = step.chosen_original == step.item.answer
    step.time_ms = int((now - step.served_at).total_seconds() * 1000)
    session.add(outbox_event(REVIEW_ANSWER, {
        "study_id": study.id, "item_ref": step.item.item_ref, "participant": participant.id,
        "chosen": step.chosen_original, "correct": step.correct, "time_ms": step.time_ms,
        "position": step.position + 1}, study.id))
    return {"state": "feedback"}


def submit_feedback(session: Session, caller: Caller, body: FeedbackIn) -> dict:
    participant, study = _participant(session, caller)
    steps = _steps(session, participant)
    step = _step_for(steps, body.item_ref)
    if step.answered_at is None:
        raise Problem(409, "answer-first", "Answer first", "Rate the question after answering it.")
    step.clarity, step.helpfulness, step.difficulty = body.clarity, body.helpfulness, body.difficulty
    step.feedback_at = utcnow()
    session.add(outbox_event(REVIEW_FEEDBACK, {
        "study_id": study.id, "item_ref": step.item.item_ref, "participant": participant.id,
        "clarity": body.clarity, "helpfulness": body.helpfulness, "difficulty": body.difficulty}, study.id))
    if _current(steps) is None:
        participant.completed_at = utcnow()
        participant.completion_code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
        return _completed_view(participant, steps)
    return {"state": "question"}


def progress(session: Session, study_id: str) -> dict:
    study = session.get(Study, study_id)
    if study is None:
        raise Problem(404, "unknown-study", "Unknown study", study_id)
    participants = list(session.scalars(select(Participant).where(Participant.study_id == study.id)))
    experts = [p for p in participants if p.role == "expert"]
    students = [p for p in participants if p.role == "student"]
    rated = {p.id: len(list(session.scalars(select(ExpertRating.id).where(ExpertRating.participant_id == p.id))))
             for p in experts}
    answers = sum(1 for p in students for s in _steps(session, p) if s.answered_at is not None)
    return {"study_id": study.id, "items": len(study.items),
            "experts": [{"rater": p.rater_name, "rated": rated[p.id], "completed": p.completed_at is not None}
                        for p in experts],
            "students": len(students), "students_completed": sum(1 for p in students if p.completed_at),
            "answers": answers}
