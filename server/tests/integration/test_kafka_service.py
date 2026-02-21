"""Integration tests for KafkaService against real Kafka + Schema Registry."""
import os
import time

import pytest
from confluent_kafka import Producer

from src.kafka import KafkaService

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
SCHEMA_REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://localhost:8081")


@pytest.fixture()
def kafka_service():
    return KafkaService()


class TestFetchTopics:
    def test_discovers_test_topics(self, kafka_service, test_topics, cluster_config):
        state = kafka_service.fetch_system_state(cluster_config)
        topic_names = {t["name"] for t in state["topics"]}
        for t in test_topics:
            assert t in topic_names, f"Expected topic '{t}' in discovered topics"

    def test_topic_has_partitions(self, kafka_service, test_topics, cluster_config):
        state = kafka_service.fetch_system_state(cluster_config)
        for t in state["topics"]:
            if t["name"] in test_topics:
                assert t["partitions"] == 2


class TestFetchSchemas:
    def test_discovers_schemas(self, kafka_service, test_topics, test_schemas, cluster_config):
        state = kafka_service.fetch_system_state(cluster_config)
        subjects = {s["subject"] for s in state["schemas"]}
        for subject in test_schemas:
            assert subject in subjects, f"Expected subject '{subject}' in discovered schemas"

    def test_schema_has_id(self, kafka_service, test_topics, test_schemas, cluster_config):
        state = kafka_service.fetch_system_state(cluster_config)
        for s in state["schemas"]:
            if s["subject"] in test_schemas:
                assert s["id"] is not None, f"Schema for {s['subject']} should have an id"

    def test_shared_schemas_have_same_id(self, kafka_service, test_topics, test_schemas, cluster_config):
        """orders-value and payments-value use the same schema content, so they should share an ID."""
        assert test_schemas["inttest-orders-value"] == test_schemas["inttest-payments-value"]

        state = kafka_service.fetch_system_state(cluster_config)
        schema_map = {s["subject"]: s["id"] for s in state["schemas"]}
        assert schema_map.get("inttest-orders-value") == schema_map.get("inttest-payments-value")

    def test_different_schema_has_different_id(self, kafka_service, test_topics, test_schemas, cluster_config):
        """users-value has a different schema, so it should have a different ID."""
        assert test_schemas["inttest-users-value"] != test_schemas["inttest-orders-value"]


class TestFetchSchemaDetails:
    def test_fetch_latest_version(self, kafka_service, test_topics, test_schemas):
        details = kafka_service.fetch_schema_details(SCHEMA_REGISTRY_URL, "inttest-orders-value")
        assert details["subject"] == "inttest-orders-value"
        assert details["version"] >= 1
        assert details["id"] is not None
        assert details["schema"] is not None
        assert isinstance(details["allVersions"], list)

    def test_fetch_specific_version(self, kafka_service, test_topics, test_schemas):
        details = kafka_service.fetch_schema_details(SCHEMA_REGISTRY_URL, "inttest-orders-value", version="1")
        assert details["version"] == 1


class TestProduceAndConsume:
    def test_produce_message(self, kafka_service, test_topics, cluster_config):
        result = kafka_service.produce_message(cluster_config, "inttest-orders", '{"id":1,"amount":99.99}')
        assert result["ok"] is True
        assert result["partition"] is not None
        assert result["offset"] is not None

    def test_produce_with_key(self, kafka_service, test_topics, cluster_config):
        result = kafka_service.produce_message(cluster_config, "inttest-orders", '{"id":2}', key="key-1")
        assert result["ok"] is True

    def test_produce_rejects_internal_topic(self, kafka_service, cluster_config):
        with pytest.raises(RuntimeError, match="internal topics"):
            kafka_service.produce_message(cluster_config, "__consumer_offsets", "test")

    def test_topic_details_include_messages(self, kafka_service, test_topics, cluster_config):
        # Produce a message first
        kafka_service.produce_message(cluster_config, "inttest-orders", '{"test":"message"}')
        time.sleep(1)

        details = kafka_service.fetch_topic_details(cluster_config, "inttest-orders", include_messages=True)
        assert details["name"] == "inttest-orders"
        assert details["partitions"] == 2
        assert isinstance(details["recentMessages"], list)
        assert len(details["recentMessages"]) > 0


class TestTopicDetails:
    def test_fetch_topic_config(self, kafka_service, test_topics, cluster_config):
        details = kafka_service.fetch_topic_details(cluster_config, "inttest-orders")
        assert details["name"] == "inttest-orders"
        assert details["partitions"] == 2
        assert "config" in details
        assert "retentionMs" in details["config"]

    def test_nonexistent_topic_returns_empty_config(self, kafka_service, cluster_config):
        details = kafka_service.fetch_topic_details(cluster_config, "nonexistent-topic-xyz")
        assert details["partitions"] == 0
        assert details["replicationFactor"] == 0


class TestClusterHealth:
    def test_healthy_cluster(self, kafka_service, cluster_config):
        health = kafka_service.check_cluster_health(cluster_config)
        assert health["online"] is True
        assert health["error"] is None

    def test_unreachable_cluster(self, kafka_service):
        health = kafka_service.check_cluster_health({"bootstrapServers": "localhost:19999"})
        assert health["online"] is False
        assert health["error"] is not None
