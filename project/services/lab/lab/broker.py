"""
RabbitMQ for the Lab: topology, the publisher used by the outbox relay, and the consumer of the
Generator's results and the Review service's events (course chapter 8).
"""
import functools
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

import pika
from pika.exceptions import AMQPError

from .messages import COMMANDS, DLX, EVENTS

logger = logging.getLogger(__name__)

JOBS_QUEUE, JOBS_DEAD = "generator.jobs", "generator.jobs.dead"
RESULTS_QUEUE, REVIEW_QUEUE, LAB_DEAD = "lab.generation-results", "lab.review-events", "lab.dead"


def declare_topology(channel) -> None:
    """Idempotent. The job queue is declared here too, so jobs sent before any Generator started are kept."""
    channel.exchange_declare(COMMANDS, exchange_type="direct", durable=True)
    channel.exchange_declare(EVENTS, exchange_type="topic", durable=True)
    channel.exchange_declare(DLX, exchange_type="direct", durable=True)
    channel.queue_declare(JOBS_QUEUE, durable=True, arguments={
        "x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": JOBS_QUEUE})
    channel.queue_bind(JOBS_QUEUE, COMMANDS, routing_key="generation.requested")
    channel.queue_declare(JOBS_DEAD, durable=True)
    channel.queue_bind(JOBS_DEAD, DLX, routing_key=JOBS_QUEUE)
    for queue, pattern in ((RESULTS_QUEUE, "generation.*"), (REVIEW_QUEUE, "review.#")):
        channel.queue_declare(queue, durable=True, arguments={
            "x-dead-letter-exchange": DLX, "x-dead-letter-routing-key": LAB_DEAD})
        channel.queue_bind(queue, EVENTS, routing_key=pattern)
    channel.queue_declare(LAB_DEAD, durable=True)
    channel.queue_bind(LAB_DEAD, DLX, routing_key=LAB_DEAD)


class RabbitPublisher:
    """Publishes with confirms and `mandatory`: an unroutable or unconfirmed message raises, so it stays in the outbox."""

    def __init__(self, url: str):
        self.url = url
        self._connection = None
        self._channel = None

    def _ensure(self):
        if self._channel is None or self._channel.is_closed:
            self.reset()
            self._connection = pika.BlockingConnection(pika.URLParameters(self.url))
            self._channel = self._connection.channel()
            declare_topology(self._channel)
            self._channel.confirm_delivery()
        return self._channel

    def publish(self, exchange: str, routing_key: str, body: str, *, message_id: str, message_type: str,
                correlation_id: Optional[str] = None) -> None:
        self._ensure().basic_publish(
            exchange, routing_key, body.encode("utf-8"), mandatory=True,
            properties=pika.BasicProperties(content_type="application/json", delivery_mode=2, message_id=message_id,
                                            type=message_type, correlation_id=correlation_id or ""))

    def reset(self) -> None:
        try:
            if self._connection is not None and self._connection.is_open:
                self._connection.close()
        except AMQPError:
            pass
        self._connection = self._channel = None


class RabbitConsumer:
    """
    One channel per queue with prefetch 1 and one worker thread per queue: the messages of a queue are applied
    in order while the connection keeps its heartbeats. A message is acknowledged after the handler committed;
    if the handler fails (e.g. the database is unreachable) it is returned to the queue after a pause.
    A message that is not JSON goes to the dead-letter queue.
    """

    def __init__(self, url: str, handlers: dict[str, Callable[[dict], None]]):
        self.url, self.handlers = url, handlers
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
        executors = {queue: ThreadPoolExecutor(max_workers=1, thread_name_prefix=queue) for queue in self.handlers}
        try:
            for i, (queue, handler) in enumerate(self.handlers.items()):
                channel = connection.channel()
                if i == 0:
                    declare_topology(channel)
                channel.basic_qos(prefetch_count=1)
                channel.basic_consume(queue, functools.partial(self._on_message, connection, executors[queue], handler))
            self.connected.set()
            logger.info("Consuming %s", ", ".join(self.handlers))
            while not self._stop.is_set():
                connection.process_data_events(time_limit=1)
        finally:
            self.connected.clear()
            for executor in executors.values():
                executor.shutdown(wait=False)
            if connection.is_open:
                connection.close()

    def _on_message(self, connection, executor, handler, channel, method, properties, body) -> None:
        try:
            env = json.loads(body)
            if not isinstance(env, dict):
                raise ValueError("not an object")
        except ValueError as e:
            logger.error("Unreadable message moved to %s: %s", LAB_DEAD, e)
            channel.basic_reject(method.delivery_tag, requeue=False)
            return

        def work():
            try:
                handler(env)
                ok = True
            except Exception:
                logger.exception("Handling %s failed; it will be redelivered", env.get("type"))
                ok = False
            connection.add_callback_threadsafe(functools.partial(self._settle, connection, channel, method.delivery_tag, ok))

        executor.submit(work)

    @staticmethod
    def _settle(connection, channel, tag, ok: bool) -> None:
        if ok:
            channel.basic_ack(tag)
        else:
            connection.call_later(2.0, functools.partial(channel.basic_nack, tag, requeue=True))
