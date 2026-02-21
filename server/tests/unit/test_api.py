"""Integration tests for FastAPI endpoints in main.py."""
import json
import os
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _setup_env(tmp_clusters_file):
    """All tests in this module use the temporary clusters file."""
    pass


@pytest.fixture()
def client():
    # Import after env is set so storage picks up the temp file
    import importlib
    import src.storage as storage_mod
    importlib.reload(storage_mod)

    from main import app
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"


class TestClusterEndpoints:
    def test_list_clusters(self, client):
        res = client.get("/api/clusters")
        assert res.status_code == 200
        clusters = res.json()
        assert len(clusters) == 1
        assert clusters[0]["name"] == "test-cluster"

    def test_get_cluster(self, client):
        res = client.get("/api/clusters/1")
        assert res.status_code == 200
        assert res.json()["name"] == "test-cluster"

    def test_get_cluster_not_found(self, client):
        res = client.get("/api/clusters/999")
        assert res.status_code == 404

    @patch("main.build_topology", return_value={"nodes": [], "edges": []})
    @patch("main.create_snapshot", return_value={"id": 2, "clusterId": 2, "data": {"nodes": [], "edges": []}, "createdAt": ""})
    def test_create_cluster(self, mock_snap, mock_topo, client):
        res = client.post("/api/clusters", json={
            "name": "new-cluster",
            "bootstrapServers": "localhost:9093",
        })
        assert res.status_code == 200
        assert res.json()["name"] == "new-cluster"

    def test_delete_cluster(self, client):
        res = client.delete("/api/clusters/1")
        assert res.status_code == 204

        res = client.get("/api/clusters/1")
        assert res.status_code == 404

    def test_delete_cluster_not_found(self, client):
        res = client.delete("/api/clusters/999")
        assert res.status_code == 404


class TestTopologyEndpoints:
    @patch("main.build_topology", return_value={"nodes": [{"id": "topic:t1", "type": "topic", "data": {"label": "t1"}}], "edges": []})
    @patch("main.create_snapshot")
    def test_topology_get_creates_snapshot_if_missing(self, mock_snap, mock_topo, client):
        mock_snap.return_value = {
            "id": 1, "clusterId": 1,
            "data": {"nodes": [{"id": "topic:t1", "type": "topic", "data": {"label": "t1"}}], "edges": []},
            "createdAt": "",
        }
        res = client.get("/api/clusters/1/topology")
        assert res.status_code == 200
        assert "data" in res.json()

    def test_topology_cluster_not_found(self, client):
        res = client.get("/api/clusters/999/topology")
        assert res.status_code == 404

    @patch("main.build_topology", return_value={"nodes": [], "edges": []})
    @patch("main.create_snapshot", return_value={"id": 1, "clusterId": 1, "data": {"nodes": [], "edges": []}, "createdAt": ""})
    def test_refresh_topology(self, mock_snap, mock_topo, client):
        res = client.post("/api/clusters/1/refresh")
        assert res.status_code == 200


class TestTopologySearchEndpoint:
    def test_search_no_snapshot(self, client):
        res = client.get("/api/clusters/1/topology/search?q=test")
        assert res.status_code == 404


class TestClusterSanitization:
    def test_sensitive_fields_stripped(self, client, tmp_clusters_file):
        """SSL fields should not appear in the API response."""
        data = json.loads(tmp_clusters_file.read_text())
        data["clusters"][0]["sslKeyPassword"] = "secret"
        data["clusters"][0]["sslTruststorePassword"] = "trustsecret"
        tmp_clusters_file.write_text(json.dumps(data))

        import importlib, src.storage as storage_mod
        importlib.reload(storage_mod)

        res = client.get("/api/clusters/1")
        assert res.status_code == 200
        body = res.json()
        assert "sslKeyPassword" not in body
        assert "sslTruststorePassword" not in body
