"""
Publishing to RabbitMQ. This service only publishes events. With `mandatory`, a message that no queue
receives yet (the Lab has not declared its queue) raises and stays in the outbox until it can be delivered.
"""
from typing import Optional

import pika
from pika.exceptions import AMQPError

from .messages import EVENTS


class RabbitPublisher:
    def __init__(self, url: str):
        self.url = url
        self._connection = None
        self._channel = None

    def _ensure(self):
        if self._channel is None or self._channel.is_closed:
            self.reset()
            self._connection = pika.BlockingConnection(pika.URLParameters(self.url))
            self._channel = self._connection.channel()
            self._channel.exchange_declare(EVENTS, exchange_type="topic", durable=True)
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
