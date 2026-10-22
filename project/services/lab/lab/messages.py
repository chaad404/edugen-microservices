"""Message contract: one envelope for every command and event on the broker (course chapters 4.4 and 8.1)."""
import json
import uuid
from typing import Optional

from .db import utcnow
from .models import OutboxMessage

COMMANDS, EVENTS, DLX = "edugen.commands", "edugen.events", "edugen.dlx"

GENERATION_REQUESTED = "generation.requested"   # command: Lab -> Generator (work queue)
GENERATION_COMPLETED = "generation.completed"   # event: Generator -> Lab
GENERATION_FAILED = "generation.failed"         # event: Generator -> Lab
REVIEW_RATING = "review.rating.submitted"       # events: Review -> Lab
REVIEW_ANSWER = "review.answer.submitted"
REVIEW_FEEDBACK = "review.feedback.submitted"


def envelope(type_: str, payload: dict, *, correlation_id: Optional[str] = None,
             causation_id: Optional[str] = None) -> dict:
    """Stable type, unique ID, schema version and a business payload: never a copy of internal tables."""
    return {"message_id": str(uuid.uuid4()), "type": type_, "version": 1, "occurred_at": utcnow().isoformat(),
            "producer": "lab", "correlation_id": correlation_id, "causation_id": causation_id, "payload": payload}


def outbox_message(env: dict, exchange: str, routing_key: str, aggregate_id: Optional[str] = None) -> OutboxMessage:
    return OutboxMessage(message_id=env["message_id"], message_type=env["type"], exchange=exchange,
                         routing_key=routing_key, body=json.dumps(env), aggregate_id=aggregate_id,
                         correlation_id=env.get("correlation_id"))
