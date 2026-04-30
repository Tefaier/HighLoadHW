from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import pika

logger = logging.getLogger(__name__)


@dataclass
class RabbitPublisher:
    amqp_url: str

    def publish(self, routing_key: str, payload: dict, exchange: str = '', retries: int = 3) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        last_error: Exception | None = None

        for attempt in range(1, retries + 1):
            connection = None
            try:
                params = pika.URLParameters(self.amqp_url)
                params.socket_timeout = 3
                connection = pika.BlockingConnection(params)
                channel = connection.channel()
                channel.queue_declare(queue=routing_key, durable=True)
                channel.basic_publish(
                    exchange=exchange,
                    routing_key=routing_key,
                    body=body,
                    properties=pika.BasicProperties(content_type='application/json', delivery_mode=2),
                )
                return
            except Exception as exc:  # pragma: no cover
                last_error = exc
                logger.warning('Rabbit publish failed (attempt %s/%s): %s', attempt, retries, exc)
                time.sleep(min(2 ** attempt, 5))
            finally:
                if connection and not connection.is_closed:
                    try:
                        connection.close()
                    except Exception:
                        pass

        if last_error:
            raise last_error
