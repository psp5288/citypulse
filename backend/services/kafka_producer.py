import json
import logging

from backend.config import settings

logger = logging.getLogger(__name__)


async def send_test_event(topic: str, payload: dict) -> bool:
    """Dev helper: publish one JSON message."""
    if not settings.kafka_enabled:
        return False
    try:
        from aiokafka import AIOKafkaProducer
    except ImportError:
        return False

    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    )
    try:
        await producer.start()
        await producer.send_and_wait(topic, payload)
        return True
    except Exception as e:
        logger.debug("Kafka producer: %s", e)
        return False
    finally:
        await producer.stop()
