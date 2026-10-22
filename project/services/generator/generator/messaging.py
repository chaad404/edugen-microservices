"""
RabbitMQ topology and the job consumer (course chapter 8).

- generator.jobs is a work queue: every job goes to exactly one Generator instance (competing consumers).
- prefetch = 1: an instance holds at most one unacknowledged job, so a slow model slows down only the
  instance working on it, and more instances share the load.
- The job runs in a worker thread while this thread keeps serving the connection (heartbeats).
- The result is published with publisher confirms and `mandatory` before the job is acknowledged, so a
  crash in between leads to a repeated job, never a lost one (at-least-once; the Lab ignores duplicates).
- A message that cannot be parsed is rejected to the dead-letter queue instead of being retried forever.
"""
import functools
import json
import logging
import threading

import pika
from pika.exceptions import AMQPError, UnroutableError

from .jobs import FAILED, PoisonMessage, make_envelope, parse_job

logger = logging.getLogger(__name__)

COMMANDS, EVENTS, DLX = "edugen.commands", "edugen.events", "edugen.dlx"
JOBS_QUEUE, JOBS_DEAD = "generator.jobs", "generator.jobs.dead"


def declare_topology(channel) -> None:
    """Idempotent: every service declares what it uses, so start-up order does not matter."""
    channel.exchange_declare(COMMANDS, exchange_type="direct", durable=True)
    channel.exchange_declare(EVENTS, exchange_type="topic", durable=True)
    channel.exchange_declare(DLX, exchange_type="direct", durable=True)
    channel.queue_declare(JOBS_QUEUE, durable=True, arguments={
        "x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": JOBS_QUEUE})
    channel.queue_bind(JOBS_QUEUE, COMMANDS, routing_key="generation.requested")
    channel.queue_declare(JOBS_DEAD, durable=True)
    channel.queue_bind(JOBS_DEAD, DLX, routing_key=JOBS_QUEUE)


class JobConsumer:
    def __init__(self, url: str, handler, publish_retries: int = 60, retry_interval: float = 5.0):
        self.url, self.handler = url, handler
        self.publish_retries, self.retry_interval = publish_retries, retry_interval
        self.connected = threading.Event()
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run_forever(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                self._consume()
                delay = 1.0
            except (AMQPError, OSError) as e:
                self.connected.clear()
                logger.warning("Broker connection lost (%s); reconnecting in %.0f s", type(e).__name__, delay)
                self._stop.wait(delay)
                delay = min(30.0, delay * 2)

    def _consume(self) -> None:
        connection = pika.BlockingConnection(pika.URLParameters(self.url))
        try:
            channel = connection.channel()
            declare_topology(channel)
            channel.confirm_delivery()
            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(JOBS_QUEUE, functools.partial(self._on_message, connection))
            self.connected.set()
            logger.info("Consuming %s", JOBS_QUEUE)
            while not self._stop.is_set():
                connection.process_data_events(time_limit=1)
        finally:
            self.connected.clear()
            if connection.is_open:
                connection.close()

    def _on_message(self, connection, channel, method, properties, body) -> None:
        try:
            envelope = json.loads(body)
            parse_job(envelope)  # check the shape before any work starts
        except (ValueError, PoisonMessage) as e:
            logger.error("Unreadable job message moved to %s: %s", JOBS_DEAD, e)
            channel.basic_reject(method.delivery_tag, requeue=False)
            return

        def work():
            try:
                result = self.handler(envelope)
            except Exception as e:  # the handler should not raise; never leave a job without an answer
                logger.exception("Handler crashed")
                p = envelope["payload"]
                result = make_envelope(FAILED, {"job_id": p.get("job_id"), "experiment_id": p.get("experiment_id"),
                                                "model": p.get("model"), "strategy": p.get("strategy"),
                                                "error_kind": "internal_error", "error": str(e)[:500]},
                                       correlation_id=p.get("experiment_id"), causation_id=envelope.get("message_id"))
            connection.add_callback_threadsafe(
                functools.partial(self._finish, connection, channel, method.delivery_tag, result, 0))

        threading.Thread(target=work, name="job-worker", daemon=True).start()

    def _finish(self, connection, channel, tag, result: dict, attempt: int) -> None:
        try:
            channel.basic_publish(
                EVENTS, result["type"], json.dumps(result).encode("utf-8"),
                properties=pika.BasicProperties(content_type="application/json", delivery_mode=2,
                                                message_id=result["message_id"], type=result["type"],
                                                correlation_id=result.get("correlation_id") or ""),
                mandatory=True)
        except UnroutableError:
            # No queue is bound for results yet (the Lab has not started): keep the job and retry later
            if attempt < self.publish_retries:
                connection.call_later(self.retry_interval, functools.partial(
                    self._finish, connection, channel, tag, result, attempt + 1))
                return
            logger.error("Result of job %s unroutable; returning the job to the queue", result["payload"].get("job_id"))
            channel.basic_nack(tag, requeue=True)
            return
        channel.basic_ack(tag)
