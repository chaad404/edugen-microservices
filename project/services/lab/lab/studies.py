"""
Blind human evaluation (thesis use cases UC-200 expert review and UC-300 student quiz), run by the Review service.

Blindness is enforced by data ownership: the Lab sends the Review service an opaque item_ref, the topic
label, the question and its options, nothing else. Model, strategy, provider and scores never leave the Lab,
so the Review service cannot reveal them, not even by mistake.
"""
import random
import uuid
from collections import defaultdict
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .clients import ReviewClient, ServiceError, ServiceUnavailable
from .db import utcnow
from .events import record_event
from .messages import REVIEW_ANSWER, REVIEW_FEEDBACK, REVIEW_RATING
from .models import Experiment, HumanRating, Item, Job, QuizAnswer, QuizFeedback, Study, StudyItem
from .orchestration import _claim
from .problems import Problem


MAX_STUDY_ITEMS = 500  # the Review service's contract limit


def channel(study_id: str) -> str:
    return f"study:{study_id}"


def stratified_sample(items: Sequence[Item], per_cell: int, seed: int) -> list[Item]:
    """Equal numbers of questions from every model x strategy x domain cell, reproducible by seed."""
    cells = defaultdict(list)
    for item in items:
        cells[(item.job.model, item.job.strategy, item.job.topic.domain)].append(item)
    rng = random.Random(seed)
    chosen = []
    for key in sorted(cells):
        pool = sorted(cells[key], key=lambda i: i.id)
        chosen += rng.sample(pool, min(per_cell, len(pool)))
    return sorted(chosen, key=lambda i: i.id)


def create_study(session: Session, *, title: str, kind: str, experiment_ids: Sequence[str], per_cell: int,
                 seed: int, student_items: int, operator: str) -> Study:
    found = set(session.scalars(select(Experiment.id).where(Experiment.id.in_(experiment_ids))))
    missing = sorted(set(experiment_ids) - found)
    if missing:
        raise Problem(422, "unknown-experiment", "Unknown experiment", ", ".join(missing))
    pool = list(session.scalars(
        select(Item).join(Job).where(Job.experiment_id.in_(experiment_ids),
                                     or_(Item.valid.is_(None), Item.valid.is_(True)),
                                     or_(Item.alignment.is_not(None), Item.plausibility.is_not(None)))
        .order_by(Item.id)))
    items = stratified_sample(pool, per_cell, seed)
    if not items:
        raise Problem(422, "no-items", "Nothing to review", "The experiments have no scored questions yet.")
    if len(items) > MAX_STUDY_ITEMS:
        raise Problem(422, "study-too-large", "Study too large",
                      f"{len(items)} questions sampled; a study holds at most {MAX_STUDY_ITEMS}. Lower per_cell.")

    study = Study(id=str(uuid.uuid4()), title=title, kind=kind, status="draft", seed=seed, per_cell=per_cell,
                  student_items=min(student_items, len(items)), source_experiments=list(experiment_ids),
                  created_by=operator)
    session.add(study)
    for position, item in enumerate(items):
        study.items.append(StudyItem(item_ref=str(uuid.uuid4()), item=item, position=position))
    record_event(session, channel(study.id), "study.created", {"study_id": study.id, "items": len(items)})
    session.flush()
    return study


def blinded_payload(study: Study) -> dict:
    return {
        "study_id": study.id, "title": study.title, "kind": study.kind, "seed": study.seed,
        "student_items": study.student_items,
        "items": [{"item_ref": si.item_ref, "topic_label": si.item.job.topic.title, "domain": si.item.job.topic.domain,
                   "question": si.item.question, "options": si.item.options, "answer": si.item.answer}
                  for si in study.items],
    }


def publish_study(session: Session, study: Study, review: ReviewClient, token: str) -> None:
    """Hands the blinded study to the Review service. Safe to repeat: the study ID is the idempotency key."""
    try:
        result = review.create_study(blinded_payload(study), token, idempotency_key=study.id)
    except ServiceUnavailable as e:
        study.publish_error = str(e)
        return
    except ServiceError as e:
        study.publish_error = f"Rejected by the Review service: {e.detail[:200]}"
        return
    study.expert_code, study.student_code = result.get("expert_code"), result.get("student_code")
    study.status, study.published_at, study.publish_error = "open", utcnow(), None
    record_event(session, channel(study.id), "study.published",
                 {"expert_code": study.expert_code, "student_code": study.student_code})


def _score(value) -> int:
    score = int(value)
    if not 1 <= score <= 5:
        raise ValueError(f"Likert score out of range: {score}")
    return score


def handle_review_event(session: Session, env: dict) -> str:
    """Idempotent consumer of the Review service's events."""
    if not _claim(session, env):
        return "duplicate"
    p = env.get("payload") or {}
    study_item = session.get(StudyItem, p.get("item_ref"))
    if study_item is None or study_item.study_id != p.get("study_id"):
        return "unknown_item"
    kind, key = env.get("type"), {"study_id": study_item.study_id, "item_ref": study_item.item_ref}
    try:
        if kind == REVIEW_RATING:
            values = {d: _score(p[d]) for d in ("relevance", "clarity", "difficulty", "distractors")}
            values.update(key_correct=str(p.get("key_correct", "unsure")), unusable=bool(p.get("unusable")),
                          comment=p.get("comment"), revision=int(p.get("revision", 1)))
            rating = session.scalar(select(HumanRating).filter_by(**key, rater=str(p["rater"])))
            if rating is None:
                session.add(HumanRating(**key, rater=str(p["rater"]), **values))
            elif values["revision"] >= rating.revision:  # an older revision arriving late must not win
                for field, value in values.items():
                    setattr(rating, field, value)
            who = {"rater": str(p["rater"])}
        elif kind == REVIEW_ANSWER:
            if session.scalar(select(QuizAnswer).filter_by(**key, participant=str(p["participant"]))) is None:
                session.add(QuizAnswer(**key, participant=str(p["participant"]), chosen=str(p["chosen"]),
                                       correct=bool(p["correct"]), time_ms=p.get("time_ms")))
            who = {"participant": str(p["participant"])}
        elif kind == REVIEW_FEEDBACK:
            if session.scalar(select(QuizFeedback).filter_by(**key, participant=str(p["participant"]))) is None:
                session.add(QuizFeedback(**key, participant=str(p["participant"]), clarity=_score(p["clarity"]),
                                         helpfulness=_score(p["helpfulness"]), difficulty=_score(p["difficulty"])))
            who = {"participant": str(p["participant"])}
        else:
            return "ignored"
    except (KeyError, TypeError, ValueError):
        return "invalid"
    record_event(session, channel(study_item.study_id), kind, {"item_ref": study_item.item_ref, **who})
    return "stored"
