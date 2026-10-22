"""
Transactional outbox relay (course chapter 5.3). Messages are published in order; a message is marked
sent only after the broker confirmed it. A crash between the confirm and the commit sends it again, so
delivery is at-least-once and every consumer is idempotent.
"""
import logging
import threading
from typing import Callable, Optional

from pika.exceptions import UnroutableError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .db import utcnow
from .models import OutboxMessage

logger = logging.getLogger(__name__)


class OutboxRelay:
    def __init__(self, session_factory: sessionmaker, publisher, *,
                 on_published: Optional[Callable[[Session, OutboxMessage], None]] = None,
                 batch: int = 50, interval: float = 0.5):
        self.session_factory, self.publisher, self.on_published = session_factory, publisher, on_published
        self.batch, self.interval = batch, interval

    def run_once(self) -> int:
        with self.session_factory() as session:
            rows = list(session.scalars(
                select(OutboxMessage).where(OutboxMessage.published_at.is_(None)).order_by(OutboxMessage.id)
                .limit(self.batch).with_for_update(skip_locked=True)))  # several relays never send the same row
            published = 0
            for row in rows:
                try:
                    self.publisher.publish(row.exchange, row.routing_key, row.body, message_id=row.message_id,
                                           message_type=row.message_type, correlation_id=row.correlation_id)
                except UnroutableError:
                    row.attempts, row.last_error = row.attempts + 1, "unroutable: no queue is bound yet"
                    break  # keep the order: retry this row first next time
                except Exception as e:
                    row.attempts, row.last_error = row.attempts + 1, f"{type(e).__name__}: {e}"[:300]
                    self.publisher.reset()
                    break
                row.published_at = utcnow()
                published += 1
                if self.on_published is not None:
                    self.on_published(session, row)
            session.commit()
            return published

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                sent = self.run_once()
            except Exception:
                logger.exception("Outbox relay iteration failed")
                sent = 0
            if sent < self.batch:
                stop.wait(self.interval)
