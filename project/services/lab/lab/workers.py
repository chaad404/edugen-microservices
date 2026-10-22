"""Background work of the Lab: outbox relay, message consumer and the evaluation loop, one thread each."""
import logging
import threading

from sqlalchemy.orm import sessionmaker

from .broker import RESULTS_QUEUE, REVIEW_QUEUE, RabbitConsumer, RabbitPublisher
from .clients import EvaluatorClient
from .orchestration import backfill_thesis_flags, evaluate_pending, handle_generation_result, mark_dispatched
from .outbox import OutboxRelay
from .studies import handle_review_event

logger = logging.getLogger(__name__)


class Workers:
    def __init__(self, session_factory: sessionmaker, evaluator: EvaluatorClient, rabbitmq_url: str):
        self.session_factory, self.evaluator = session_factory, evaluator
        self.stop_event = threading.Event()
        self.relay = OutboxRelay(session_factory, RabbitPublisher(rabbitmq_url), on_published=mark_dispatched)
        self.consumer = RabbitConsumer(rabbitmq_url, {RESULTS_QUEUE: self._on_result, REVIEW_QUEUE: self._on_review})

    def start(self) -> None:
        for name, target in (("outbox-relay", lambda: self.relay.run_forever(self.stop_event)),
                             ("consumer", self.consumer.run_forever),
                             ("evaluation-loop", self._evaluation_loop)):
            threading.Thread(target=target, name=name, daemon=True).start()

    def shutdown(self) -> None:
        self.stop_event.set()
        self.consumer.stop()

    def _on_result(self, env: dict) -> None:
        with self.session_factory() as session:
            outcome = handle_generation_result(session, env)
            session.commit()
        logger.info("%s for job %s: %s", env.get("type"), (env.get("payload") or {}).get("job_id"), outcome)

    def _on_review(self, env: dict) -> None:
        with self.session_factory() as session:
            outcome = handle_review_event(session, env)
            session.commit()
        logger.info("%s: %s", env.get("type"), outcome)

    def _evaluation_loop(self) -> None:
        while not self.stop_event.is_set():
            busy = 0
            try:
                with self.session_factory() as session:
                    busy = evaluate_pending(session, self.evaluator)
                    session.commit()
                with self.session_factory() as session:
                    busy += backfill_thesis_flags(session, self.evaluator)
                    session.commit()
            except Exception:
                logger.exception("Evaluation loop iteration failed")
            self.stop_event.wait(0.2 if busy else 1.0)
