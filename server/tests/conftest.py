"""Shared fixtures for server tests."""
import json
import os

import pytest


@pytest.fixture()
def tmp_clusters_file(tmp_path):
    """Create a temporary clusters.json and point CLUSTERS_JSON to it."""
    clusters_file = tmp_path / "clusters.json"
    clusters_file.write_text(json.dumps({"clusters": [
        {
            "id": 1,
            "name": "test-cluster",
            "bootstrapServers": "localhost:9092",
            "schemaRegistryUrl": "http://localhost:8081",
            "connectUrl": "http://localhost:8083",
            "createdAt": "2025-01-01T00:00:00Z",
        }
    ]}, indent=2))
    os.environ["CLUSTERS_JSON"] = str(clusters_file)
    yield clusters_file
    os.environ.pop("CLUSTERS_JSON", None)
