import os
import json
import time
import structlog

logger = structlog.get_logger()


class _InMemoryChannel:
    def __init__(self):
        self._queue: list = []

    def queue_declare(self, queue, durable=False):
        pass

    def basic_publish(self, exchange, routing_key, body):
        self._queue.append({"routing_key": routing_key, "body": json.loads(body)})
        logger.info("broker_enqueued", routing_key=routing_key, depth=len(self._queue))

    def queue_depth(self):
        return len(self._queue)


BROKER_URL = os.getenv("BROKER_URL", "memory://localhost/")
broker_channel = None

for attempt in range(5):
    try:
        broker_channel = _InMemoryChannel()
        broker_channel.queue_declare(queue="run_queue", durable=True)
        logger.info("broker_connected", broker=BROKER_URL, attempt=attempt)
        break
    except Exception as e:
        logger.warning("broker_connection_failed", attempt=attempt, error=str(e))
        time.sleep(1)

if broker_channel is None:
    logger.error("broker_unavailable", msg="Could not connect after 5 attempts")
