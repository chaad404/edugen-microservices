"""The events this service publishes. Same envelope as every EduGen message (course chapters 4.4 and 8.1)."""
import json
import uuid

from .db import utcnow
from .models import OutboxMessage

EVENTS = "edugen.events"
REVIEW_RATING = "review.rating.submitted"
REVIEW_ANSWER = "review.answer.submitted"
REVIEW_FEEDBACK = "review.feedback.submitted"


def outbox_event(type_: str, payload: dict, study_id: str) -> OutboxMessage:
    env = {"message_id": str(uuid.uuid4()), "type": type_, "version": 1, "occurred_at": utcnow().isoformat(),
           "producer": "review", "correlation_id": study_id, "causation_id": None, "payload": payload}
    return OutboxMessage(message_id=env["message_id"], message_type=type_, exchange=EVENTS, routing_key=type_,
                         body=json.dumps(env), correlation_id=study_id)
