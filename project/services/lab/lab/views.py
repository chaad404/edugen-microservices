"""JSON representations returned by the API (never the ORM objects themselves)."""
from typing import Optional

from .clients import Framework
from .models import Experiment, Item, Job, Study, Topic

PILLAR_METRICS = (("P1", "alignment"), ("P2", "grade"), ("P3a", "plausibility"), ("P3b", "diversity"))


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def topic_view(topic: Topic, with_text: bool = False) -> dict:
    view = {"topic_id": topic.topic_id, "domain": topic.domain, "title": topic.title, "origin": topic.origin,
            "has_source_text": bool(topic.source_text),
            "source_length": len(topic.source_text) if topic.source_text else 0}
    if with_text:
        view["source_text"] = topic.source_text
    return view


def job_view(job: Job) -> dict:
    return {
        "id": job.id, "topic_id": job.topic.topic_id, "domain": job.topic.domain, "model": job.model,
        "strategy": job.strategy, "status": job.status, "provider": job.provider,
        "requested_model_id": job.requested_model_id, "returned_model_id": job.returned_model_id,
        # Sampling settings sent with the requests; None for jobs run before they were recorded
        "settings": (job.trace or {}).get("settings"),
        "simulated": job.simulated, "attempts": job.attempts, "calls": job.calls,
        "prompt_tokens": job.prompt_tokens, "completion_tokens": job.completion_tokens,
        "cost_usd": round(job.cost_usd, 6), "latency_seconds": job.latency_seconds,
        "strategy_status": job.strategy_status, "error_kind": job.error_kind, "error": job.error,
        "evaluation_attempts": job.evaluation_attempts, "items": len(job.items),
        "created_at": _iso(job.created_at), "dispatched_at": _iso(job.dispatched_at),
        "generated_at": _iso(job.generated_at), "finished_at": _iso(job.finished_at),
    }


def experiment_view(experiment: Experiment, with_jobs: bool = False) -> dict:
    counts: dict[str, int] = {}
    for job in experiment.jobs:
        counts[job.status] = counts.get(job.status, 0) + 1
    view = {
        "id": experiment.id, "name": experiment.name, "origin": experiment.origin, "status": experiment.status,
        "description": experiment.description, "models": experiment.models, "strategies": experiment.strategies,
        "questions_per_job": experiment.questions_per_job, "created_by": experiment.created_by,
        "created_at": _iso(experiment.created_at), "finished_at": _iso(experiment.finished_at),
        "job_counts": counts, "jobs_total": len(experiment.jobs),
        "cost_usd": round(sum(j.cost_usd for j in experiment.jobs), 6),
        "links": {"self": f"/experiments/{experiment.id}", "items": f"/experiments/{experiment.id}/items",
                  "summary": f"/experiments/{experiment.id}/summary",
                  "events": f"/events/stream?channel=experiment:{experiment.id}"},
    }
    if with_jobs:
        view["jobs"] = [job_view(j) for j in experiment.jobs]
    return view


def item_view(item: Item, framework: Optional[Framework]) -> dict:
    metrics = {m: getattr(item, m) for m in
               ("alignment", "alignment_lexical", "grade", "plausibility", "plausibility_lexical", "diversity")}
    bands = ({key: framework.band(key, metrics[metric]) for key, metric in PILLAR_METRICS} if framework else None)
    job = item.job
    return {
        "id": item.id, "job_id": item.job_id, "position": item.position, "topic_id": job.topic.topic_id,
        "domain": job.topic.domain, "model": job.model, "strategy": job.strategy, "question": item.question,
        "options": item.options, "answer": item.answer, "evidence": item.evidence,
        "metrics_source": item.metrics_source, "valid": item.valid, "metrics": metrics, "bands": bands,
        "flags": item.flags, "quality": item.quality,
    }


def study_view(study: Study) -> dict:
    return {
        "id": study.id, "title": study.title, "kind": study.kind, "status": study.status, "seed": study.seed,
        "per_cell": study.per_cell, "student_items": study.student_items, "items": len(study.items),
        "source_experiments": study.source_experiments, "expert_code": study.expert_code,
        "student_code": study.student_code, "publish_error": study.publish_error,
        "created_at": _iso(study.created_at), "published_at": _iso(study.published_at),
        "links": {"analytics": f"/studies/{study.id}/analytics",
                  "events": f"/events/stream?channel=study:{study.id}"},
    }
