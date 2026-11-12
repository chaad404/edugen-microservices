"""
Start-up data: the demo topics (written for this project, free to publish), the public sample of the
thesis prototype's results, and live runs recorded on another deployment. Every import is idempotent, so
every start of the service may run them.
"""
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import Experiment, Item, Job, Topic

logger = logging.getLogger(__name__)
THESIS_EXPERIMENT_ID = "2026a5e0-0000-4000-8000-000000000001"
_NAMESPACE = uuid.UUID("2026a5e0-0000-4000-8000-000000000000")
RECORDED_FORMAT = "edugen-recorded-run/1"  # written by scripts/export_run.py
_METRICS = ("alignment", "alignment_lexical", "grade", "plausibility", "plausibility_lexical", "diversity")
_JOB_TEXT = ("model", "strategy", "status", "provider", "requested_model_id", "returned_model_id", "strategy_status",
             "error_kind", "error", "trace", "latency_seconds")
_JOB_COUNTS = ("attempts", "calls", "prompt_tokens", "completion_tokens")
_JOB_TIMES = ("created_at", "dispatched_at", "generated_at", "finished_at")


def seed_demo_topics(session: Session, path: Path) -> int:
    if not path.exists():
        return 0
    existing = set(session.scalars(select(Topic.topic_id)))
    added = 0
    for t in json.loads(path.read_text(encoding="utf-8"))["topics"]:
        if t["topic_id"] not in existing:
            session.add(Topic(topic_id=t["topic_id"], domain=t["domain"], title=t["title"],
                              source_text=t["source_text"], origin="demo"))
            added += 1
    return added


def import_thesis_sample(session: Session, path: Path) -> bool:
    """
    Imports the prototype sample as one completed experiment with the scores the prototype recorded. Its jobs
    and questions are imported once; on later starts only the title and description follow the seed file, so a
    reworded label also reaches a database that already holds the sample.
    """
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    existing = session.get(Experiment, THESIS_EXPERIMENT_ID)
    if existing is not None:
        existing.name, existing.description = data["name"], data.get("description")
        return False
    topics = {}
    for t in data["topics"]:
        topic = session.scalar(select(Topic).where(Topic.topic_id == t["topic_id"]))
        if topic is None:
            # The prototype's topic texts were drafted from other students' notes: they stay out of this project
            topic = Topic(topic_id=t["topic_id"], domain=t["domain"], title=t["title"], source_text=None, origin="thesis")
            session.add(topic)
        topics[t["topic_id"]] = topic

    batches = data["batches"]
    experiment = Experiment(
        id=THESIS_EXPERIMENT_ID, name=data["name"], origin="thesis_import", status="completed",
        questions_per_job=data.get("questions_per_job", 5), models=sorted({b["model"] for b in batches}),
        strategies=sorted({b["condition"] for b in batches}), description=data.get("description"),
        created_by="thesis import", finished_at=utcnow())
    session.add(experiment)
    for b in batches:
        job = Job(id=str(uuid.uuid5(_NAMESPACE, f"{b['batch_id']}|{b['topic_id']}|{b['model']}|{b['condition']}")),
                  experiment_id=experiment.id, topic=topics[b["topic_id"]], model=b["model"], strategy=b["condition"],
                  status="succeeded", provider=b.get("provider"), requested_model_id=b.get("requested_model_id"),
                  returned_model_id=b.get("returned_model_id"), simulated=False, attempts=1, calls=b.get("calls", 1),
                  prompt_tokens=b.get("prompt_tokens") or 0, completion_tokens=b.get("completion_tokens") or 0,
                  cost_usd=b.get("cost_usd") or 0.0, latency_seconds=b.get("latency_seconds"),
                  strategy_status=b.get("status"), finished_at=utcnow())
        session.add(job)
        for position, it in enumerate(b["items"]):
            session.add(Item(job=job, position=position, question=it["question"], options=it["options"],
                             answer=it["answer"], metrics_source="thesis", thesis_ref=str(it["thesis_question_id"]),
                             **{k: it["metrics"].get(k) for k in ("alignment", "alignment_lexical", "grade",
                                                                   "plausibility", "plausibility_lexical", "diversity")}))
    logger.info("Imported the thesis sample: %d batches", len(batches))
    return True


def _time(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def import_recorded_runs(session: Session, directory: Path) -> int:
    """
    Imports live runs that were made on another deployment and shipped as files (scripts/export_run.py writes
    them), so a fresh deployment shows real-model results without API keys or cost. A run is imported once, with
    its jobs, their traces, the generated questions and the scores they had. It is marked `recorded`: it is never
    passed off as a run of this deployment. Where the run already exists (imported earlier, or made here), its
    record is kept and only the title and description follow the file.
    """
    if not directory.is_dir():
        return 0
    imported = 0
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != RECORDED_FORMAT:
            logger.warning("Skipped %s: not a %s file", path.name, RECORDED_FORMAT)
            continue
        run = data["experiment"]
        existing = session.get(Experiment, run["id"])
        if existing is not None:  # as for the sample: a reworded title reaches existing databases
            existing.name, existing.description = run["name"], run.get("description")
            continue

        topics = {}
        for t in data["topics"]:
            topic = session.scalar(select(Topic).where(Topic.topic_id == t["topic_id"]))
            if topic is None:  # unknown here: listed for its recorded results, without a text to generate from
                topic = Topic(topic_id=t["topic_id"], domain=t["domain"], title=t["title"], source_text=None,
                              origin="recorded")
                session.add(topic)
            topics[t["topic_id"]] = topic

        times = {name: _time(run.get(name)) for name in ("created_at", "finished_at") if run.get(name)}
        experiment = Experiment(
            id=run["id"], name=run["name"], origin="recorded", status=run["status"],
            questions_per_job=run["questions_per_job"], models=run["models"], strategies=run["strategies"],
            description=run.get("description"), created_by=run.get("created_by") or "recorded run", **times)
        session.add(experiment)
        for j in data["jobs"]:
            times = {name: _time(j.get(name)) for name in _JOB_TIMES if j.get(name)}
            job = Job(id=j["id"], experiment_id=experiment.id, topic=topics[j["topic_id"]],
                      simulated=bool(j.get("simulated")), cost_usd=float(j.get("cost_usd") or 0.0),
                      **{name: j.get(name) for name in _JOB_TEXT}, **{name: int(j.get(name) or 0) for name in _JOB_COUNTS},
                      **times)
            session.add(job)
            for it in j.get("items", []):
                session.add(Item(job=job, position=it["position"], question=it["question"], options=it["options"],
                                 answer=it["answer"], evidence=it.get("evidence"), metrics_source="evaluator",
                                 valid=it.get("valid"), flags=it.get("flags"), quality=it.get("quality"),
                                 checked_at=times.get("finished_at"),
                                 **{name: (it.get("metrics") or {}).get(name) for name in _METRICS}))
        imported += 1
        logger.info("Imported the recorded run %s: %d jobs", path.name, len(data["jobs"]))
    return imported
