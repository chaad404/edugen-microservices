"""
The experiment pipeline, orchestrated by the Lab:

1. create_experiment: the experiment, one job per topic x model x strategy and one outbox message per job
   are written in ONE local transaction, so a job can never exist without its message or the reverse.
2. The outbox relay publishes the jobs (generation.requested) and marks them dispatched.
3. handle_generation_result: idempotent consumer of generation.completed / generation.failed (inbox).
4. evaluate_pending: scores generated jobs through the Evaluator. While the Evaluator is down the job waits
   in "generated" and is retried with growing delays; the generated questions are never lost.
5. When every job has finished, the experiment is completed.
"""
import uuid
from datetime import timedelta
from typing import Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .clients import EvaluatorClient, ServiceUnavailable
from .db import utcnow
from .events import record_event
from .messages import COMMANDS, GENERATION_COMPLETED, GENERATION_FAILED, GENERATION_REQUESTED, envelope, outbox_message
from .models import Experiment, InboxMessage, Item, Job, OutboxMessage, Topic
from .problems import Problem

STRATEGIES = ("baseline", "prompt_v2", "verify_repair")
TERMINAL = {"succeeded", "failed"}
# Calls per job for the expected cost; verify_repair = 3 Writer calls + up to 2 repairs, plus a retry margin
CALLS_PER_JOB = {"baseline": 1, "prompt_v2": 1, "verify_repair": 6}
# The most calls a job can make: every planned call uses all 4 attempts of the Generator (3 Writer + 2 repair
# calls for verify_repair). A contract test keeps these equal to the Generator's limits.
MAX_CALLS_PER_JOB = {"baseline": 4, "prompt_v2": 4, "verify_repair": 20}
OUTPUT_TOKENS_PER_QUESTION = 130  # for a model whose registry entry has no measured figure


def channel(experiment_id: str) -> str:
    return f"experiment:{experiment_id}"


def estimate(topics: Sequence[Topic], models: Sequence[dict], strategies: Sequence[str], n: int) -> dict:
    """
    API cost of a planned run at list prices.
    - Expected: prompt ~ text/4 + 900 template tokens, and the output per question the model wrote in earlier
      runs (gpt-oss writes reasoning tokens as well), for the usual number of calls.
    - At most: every call takes all its attempts and writes max_tokens, and the prompt is counted generously
      (text/2 + 3,000 tokens for the template and repair items). A paid model without max_tokens has no bound.
    """
    expected_total, max_total = 0.0, 0.0
    per_model, max_per_model = {}, {}
    for model in models:
        price = model["price_per_m"]
        per_question = model.get("output_tokens_per_question") or OUTPUT_TOKENS_PER_QUESTION
        max_tokens = (model.get("settings") or {}).get("max_tokens")
        expected = maximum = 0.0
        for topic in topics:
            text = len(topic.source_text or "")
            for strategy in strategies:
                expected += CALLS_PER_JOB[strategy] * (
                    (text / 4 + 900) * price["input"] + per_question * n * price["output"]) / 1e6
                if max_tokens:
                    maximum += MAX_CALLS_PER_JOB[strategy] * (
                        (text / 2 + 3000) * price["input"] + max_tokens * price["output"]) / 1e6
        bounded = bool(max_tokens) or not model["paid"]
        per_model[model["alias"]] = round(expected, 4)
        max_per_model[model["alias"]] = round(maximum, 4) if bounded else None
        expected_total += expected
        max_total = max_total + maximum if bounded and max_total is not None else None
    return {"jobs": len(topics) * len(models) * len(strategies), "estimated_cost_usd": round(expected_total, 4),
            "max_cost_usd": round(max_total, 4) if max_total is not None else None,
            "per_model": per_model, "max_per_model": max_per_model}


def describe_cost(cost: dict) -> str:
    bound = f"at most ${cost['max_cost_usd']}" if cost["max_cost_usd"] is not None else "no upper bound"
    return f"expected about ${cost['estimated_cost_usd']}, {bound}"


def validate_request(session: Session, topic_ids: Sequence[str], model_aliases: Sequence[str],
                     strategies: Sequence[str], catalog: Sequence[dict]) -> tuple[list[Topic], list[dict]]:
    known = {m["alias"]: m for m in catalog}
    unknown = [m for m in model_aliases if m not in known]
    if unknown:
        raise Problem(422, "unknown-model", "Unknown model", f"Not in the model registry: {', '.join(unknown)}")
    unavailable = [m for m in model_aliases if not known[m]["available"]]
    if unavailable:
        needs = ", ".join(f"{m} needs {known[m]['requires']}" for m in unavailable)
        raise Problem(422, "model-unavailable", "Model not configured", needs)
    bad = [s for s in strategies if s not in STRATEGIES]
    if bad:
        raise Problem(422, "unknown-strategy", "Unknown strategy", f"Use one of {', '.join(STRATEGIES)}")
    topics = list(session.scalars(select(Topic).where(Topic.topic_id.in_(topic_ids)).order_by(Topic.topic_id)))
    missing = sorted(set(topic_ids) - {t.topic_id for t in topics})
    if missing:
        raise Problem(422, "unknown-topic", "Unknown topic", ", ".join(missing))
    no_text = [t.topic_id for t in topics if not t.source_text]
    if no_text:
        raise Problem(422, "topic-without-source-text", "Topic has no source text",
                      f"{', '.join(no_text)}: thesis topics are listed for their recorded results only.")
    return topics, [known[m] for m in model_aliases]


def create_experiment(session: Session, *, name: str, topic_ids: Sequence[str], models: Sequence[str],
                      strategies: Sequence[str], questions_per_job: int, confirm_paid: bool,
                      catalog: Sequence[dict], operator: str, description: Optional[str] = None) -> Experiment:
    topics, specs = validate_request(session, topic_ids, models, strategies, catalog)
    cost = estimate(topics, specs, strategies, questions_per_job)
    paid = [s["alias"] for s in specs if s["paid"]]
    if paid and not confirm_paid:
        raise Problem(422, "paid-models-not-confirmed", "Paid models need confirmation",
                      f"{', '.join(paid)} call paid APIs ({describe_cost(cost)}). "
                      "Repeat the request with confirm_paid=true.", estimate=cost)

    experiment = Experiment(id=str(uuid.uuid4()), name=name, origin="live", status="running",
                            questions_per_job=questions_per_job, models=list(models), strategies=list(strategies),
                            description=description, created_by=operator)
    session.add(experiment)
    for topic in topics:
        for model in models:
            for strategy in strategies:
                job = Job(id=str(uuid.uuid4()), topic=topic, model=model, strategy=strategy, status="queued")
                experiment.jobs.append(job)
                command = envelope(GENERATION_REQUESTED, {
                    "job_id": job.id, "experiment_id": experiment.id, "model": model, "strategy": strategy,
                    "num_questions": questions_per_job,
                    # Event-carried state: the Generator needs no call back to the Lab to do the job
                    "topic": {"topic_id": topic.topic_id, "title": topic.title, "domain": topic.domain,
                              "source_text": topic.source_text},
                }, correlation_id=experiment.id)
                session.add(outbox_message(command, COMMANDS, GENERATION_REQUESTED, aggregate_id=job.id))
    record_event(session, channel(experiment.id), "experiment.created",
                 {"experiment_id": experiment.id, "jobs": cost["jobs"], "estimated_cost_usd": cost["estimated_cost_usd"],
                  "max_cost_usd": cost["max_cost_usd"]})
    session.flush()  # applies the column defaults, so the response shows what will be stored
    return experiment


def mark_dispatched(session: Session, message: OutboxMessage) -> None:
    """Outbox relay hook: a published job is now waiting in the broker for a Generator."""
    if message.message_type != GENERATION_REQUESTED:
        return
    job = session.get(Job, message.aggregate_id)
    if job is not None and job.status == "queued":
        job.status, job.dispatched_at = "dispatched", utcnow()
        record_event(session, channel(job.experiment_id), "job.dispatched", {"job_id": job.id})


def _claim(session: Session, env: dict) -> bool:
    """Inbox: records the message ID; False if this message was already processed."""
    message_id = env.get("message_id")
    if not message_id or session.get(InboxMessage, message_id) is not None:
        return False
    session.add(InboxMessage(message_id=message_id, message_type=env.get("type", "")))
    try:
        session.flush()  # the primary key is the guard against a parallel duplicate
    except IntegrityError:
        session.rollback()
        return False
    return True


def handle_generation_result(session: Session, env: dict) -> str:
    if not _claim(session, env):
        return "duplicate"
    payload = env.get("payload") or {}
    job = session.get(Job, payload.get("job_id"))
    if job is None:
        return "unknown_job"
    if job.status not in ("queued", "dispatched"):
        return "already_processed"  # a repeated job (at-least-once): the first result counts

    for field in ("provider", "requested_model_id", "returned_model_id", "strategy_status", "trace"):
        if payload.get(field) is not None:
            setattr(job, field, payload[field])
    job.simulated = bool(payload.get("simulated", False))
    job.attempts = int(payload.get("attempts") or 0)
    job.calls = int(payload.get("calls") or 0)
    job.prompt_tokens = int(payload.get("prompt_tokens") or 0)
    job.completion_tokens = int(payload.get("completion_tokens") or 0)
    job.cost_usd = float(payload.get("cost_usd") or 0.0)
    job.latency_seconds = payload.get("latency_seconds")
    now = utcnow()

    if env.get("type") == GENERATION_FAILED:
        job.status, job.finished_at = "failed", now
        job.error_kind, job.error = payload.get("error_kind"), payload.get("error")
        record_event(session, channel(job.experiment_id), "job.failed",
                     {"job_id": job.id, "model": job.model, "strategy": job.strategy,
                      "error_kind": job.error_kind, "error": job.error})
        _maybe_complete(session, job.experiment)
        return "failed"
    if env.get("type") != GENERATION_COMPLETED:
        return "ignored"

    for position, item in enumerate(payload.get("items") or []):
        session.add(Item(job_id=job.id, position=position, question=item["question"], options=item["options"],
                         answer=item["answer"], evidence=item.get("evidence")))
    job.status, job.generated_at, job.next_evaluation_at = "generated", now, now
    record_event(session, channel(job.experiment_id), "job.generated",
                 {"job_id": job.id, "model": job.model, "strategy": job.strategy,
                  "items": len(payload.get("items") or []), "cost_usd": job.cost_usd})
    return "generated"


def _item_payload(item: Item) -> dict:
    body = {"id": str(item.id), "question": item.question, "options": item.options, "answer": item.answer}
    if item.evidence:
        body["evidence"] = item.evidence
    return body


def _apply(item: Item, result: dict, now, metrics: bool = True) -> None:
    item.valid, item.validation_notes = result["valid"], result["validation_notes"]
    item.flags, item.quality, item.checked_at = result["flags"], result["quality"], now
    if metrics:
        m = result["metrics"]
        item.metrics_source = "evaluator"
        item.alignment, item.alignment_lexical, item.grade = m["alignment"], m["alignment_lexical"], m["grade"]
        item.plausibility, item.plausibility_lexical = m["plausibility"], m["plausibility_lexical"]
        item.diversity = m["diversity"]


def _mean(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 4) if values else None


def evaluate_pending(session: Session, evaluator: EvaluatorClient, limit: int = 10) -> int:
    now = utcnow()
    jobs = list(session.scalars(
        select(Job).where(Job.status == "generated",
                          or_(Job.next_evaluation_at.is_(None), Job.next_evaluation_at <= now))
        .order_by(Job.generated_at).limit(limit)))
    done = 0
    for job in jobs:
        try:
            results = evaluator.evaluate(job.topic.source_text, [_item_payload(i) for i in job.items])
        except ServiceUnavailable as e:
            job.evaluation_attempts += 1
            job.next_evaluation_at = now + timedelta(seconds=min(60, 2 ** job.evaluation_attempts))
            if job.evaluation_attempts == 1:
                record_event(session, channel(job.experiment_id), "job.evaluation_delayed",
                             {"job_id": job.id, "reason": str(e)})
            continue
        for item, result in zip(job.items, results):
            _apply(item, result, now)
        job.status, job.finished_at = "succeeded", now
        record_event(session, channel(job.experiment_id), "job.succeeded", {
            "job_id": job.id, "model": job.model, "strategy": job.strategy, "topic_id": job.topic.topic_id,
            "items": len(job.items), "valid": sum(1 for i in job.items if i.valid),
            "flags": sum(len(i.flags or []) for i in job.items), "strategy_status": job.strategy_status,
            "cost_usd": job.cost_usd,
            "mean": {m: _mean(getattr(i, m) for i in job.items) for m in ("alignment", "grade", "plausibility", "diversity")},
        })
        _maybe_complete(session, job.experiment)
        done += 1
    return done


def backfill_thesis_flags(session: Session, evaluator: EvaluatorClient, limit: int = 100) -> int:
    """
    Imported thesis questions come with their recorded metrics but without per-question flags. The option
    checks need no source text, so the Evaluator adds them; the recorded metrics are kept.
    """
    items = list(session.scalars(select(Item).where(Item.metrics_source == "thesis", Item.checked_at.is_(None))
                                 .order_by(Item.id).limit(limit)))
    if not items:
        return 0
    try:
        results = evaluator.evaluate(None, [_item_payload(i) for i in items])
    except ServiceUnavailable:
        return 0
    now = utcnow()
    for item, result in zip(items, results):
        _apply(item, result, now, metrics=False)
    return len(items)


def _maybe_complete(session: Session, experiment: Experiment) -> None:
    session.flush()
    if experiment.status != "running" or any(j.status not in TERMINAL for j in experiment.jobs):
        return
    failed = sum(1 for j in experiment.jobs if j.status == "failed")
    experiment.status = "completed_with_failures" if failed else "completed"
    experiment.finished_at = utcnow()
    record_event(session, channel(experiment.id), "experiment.completed", {
        "experiment_id": experiment.id, "status": experiment.status, "jobs": len(experiment.jobs), "failed": failed,
        "cost_usd": round(sum(j.cost_usd for j in experiment.jobs), 6)})
