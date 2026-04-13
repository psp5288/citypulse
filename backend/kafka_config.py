"""Kafka topic names (avoid naming package `kafka` — conflicts with PyPI)."""

TOPIC_SOCIAL = "city.social"
TOPIC_TRAFFIC = "city.traffic"
TOPIC_WEATHER = "city.weather"
TOPIC_EVENTS = "city.events"

ALL_TOPICS = [TOPIC_SOCIAL, TOPIC_TRAFFIC, TOPIC_WEATHER, TOPIC_EVENTS]

CONSUMER_GROUP = "city-pulse-processor"
