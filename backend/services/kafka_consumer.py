import asyncio
import json
import logging

from backend.config import settings

logger = logging.getLogger(__name__)


async def start_kafka_consumer():
    """
    Optional: consume city.* topics. If Kafka is unavailable, logs once and exits.
    Extend to merge into scoring context per district.
    """
    if not settings.kafka_enabled:
        logger.info("Kafka consumer disabled (KAFKA_ENABLED=false)")
        return

    try:
        from aiokafka import AIOKafkaConsumer
    except ImportError:
        logger.warning("aiokafka not installed — skipping Kafka consumer")
        return

    from backend.kafka_config import ALL_TOPICS, CONSUMER_GROUP

    consumer = AIOKafkaConsumer(
        *ALL_TOPICS,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=CONSUMER_GROUP,
        auto_offset_reset="latest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")) if v else None,
    )

    try:
        await consumer.start()
        logger.info("Kafka consumer started on %s", settings.kafka_bootstrap_servers)
        async for msg in consumer:
            _ = msg.value  # placeholder: merge into Redis context buffer
            await asyncio.sleep(0)
    except Exception as e:
        logger.warning("Kafka consumer stopped: %s", e)
    finally:
        try:
            await consumer.stop()
        except Exception:
            pass
