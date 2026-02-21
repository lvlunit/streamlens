"""Integration tests for topology building against real Kafka + Schema Registry."""
import os

import pytest

from src.topology import build_topology


KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
SCHEMA_REGISTRY_URL = os.environ.get("SCHEMA_REGISTRY_URL", "http://localhost:8081")


class TestBuildTopologyIntegration:
    def test_topology_contains_test_topics(self, test_topics, cluster_config):
        result = build_topology(99, cluster_config)
        topic_ids = {n["id"] for n in result["nodes"] if n["type"] == "topic"}
        for t in test_topics:
            assert f"topic:{t}" in topic_ids

    def test_topology_contains_schema_nodes(self, test_topics, test_schemas, cluster_config):
        result = build_topology(99, cluster_config)
        schema_nodes = [n for n in result["nodes"] if n["type"] == "schema"]
        assert len(schema_nodes) > 0

    def test_shared_schemas_produce_single_node(self, test_topics, test_schemas, cluster_config):
        """orders-value and payments-value share the same schema ID -> one schema node with two edges."""
        result = build_topology(99, cluster_config)

        shared_id = test_schemas["inttest-orders-value"]
        matching_nodes = [
            n for n in result["nodes"]
            if n["type"] == "schema" and n["id"] == f"schema:{shared_id}"
        ]
        assert len(matching_nodes) == 1, f"Expected 1 node for schema ID {shared_id}"

        node = matching_nodes[0]
        assert "inttest-orders-value" in node["data"]["subjects"]
        assert "inttest-payments-value" in node["data"]["subjects"]
        assert node["data"]["label"] == "Multiple subjects"

        # Edges from both topics to the shared schema node
        schema_edges = [
            e for e in result["edges"]
            if e["type"] == "schema_link" and e["target"] == f"schema:{shared_id}"
        ]
        edge_sources = {e["source"] for e in schema_edges}
        assert "topic:inttest-orders" in edge_sources
        assert "topic:inttest-payments" in edge_sources

    def test_unique_schema_has_subject_as_label(self, test_topics, test_schemas, cluster_config):
        """users-value has a unique schema ID -> node label is the subject name."""
        result = build_topology(99, cluster_config)

        users_id = test_schemas["inttest-users-value"]
        matching_nodes = [
            n for n in result["nodes"]
            if n["type"] == "schema" and n["id"] == f"schema:{users_id}"
        ]
        assert len(matching_nodes) == 1
        assert matching_nodes[0]["data"]["label"] == "inttest-users-value"

    def test_schema_edges_link_to_topics(self, test_topics, test_schemas, cluster_config):
        result = build_topology(99, cluster_config)
        schema_edges = [e for e in result["edges"] if e["type"] == "schema_link"]
        for edge in schema_edges:
            assert edge["source"].startswith("topic:")
            assert edge["target"].startswith("schema:")
