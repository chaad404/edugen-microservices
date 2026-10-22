"""
Start-up data: the demo topics (written for this project, free to publish) and the public sample of the
thesis results. Both imports are idempotent, so every start of the service may run them.
"""
import json
import logging
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import Experiment, Item, Job, Topic

logger = logging.getLogger(__name__)
THESIS_EXPERIMENT_ID = "2026a5e0-0000-4000-8000-000000000001"
_NAMESPACE = uuid.UUID("2026a5e0-0000-4000-8000-000000000000")


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
    """Imports the thesis sample as one completed experiment with the scores recorded by the thesis."""
    if not path.exists() or session.get(Experiment, THESIS_EXPERIMENT_ID) is not None:
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    topics = {}
    for t in data["topics"]:
        topic = session.scalar(select(Topic).where(Topic.topic_id == t["topic_id"]))
        if topic is None:
            # The thesis topic texts were drafted from other students' notes: they stay out of this project
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
