"""Schema Registry subject listing and detail retrieval."""
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def fetch_schemas(schema_url: str) -> list[dict[str, Any]]:
    """List all subjects with latest version metadata."""
    schemas: list[dict[str, Any]] = []
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{schema_url}/subjects")
        r.raise_for_status()
        subjects = r.json()

        for subject in subjects:
            try:
                r2 = client.get(f"{schema_url}/subjects/{subject}/versions/latest")
                r2.raise_for_status()
                ver = r2.json()
                topic_name = subject.replace("-value", "").replace("-key", "")
                schemas.append({
                    "subject": subject,
                    "version": ver.get("version", 0),
                    "id": ver.get("id"),
                    "type": ver.get("schemaType", "AVRO"),
                    "topicName": topic_name,
                })
            except Exception as e:
                logger.debug("subject %s: %s", subject, e)
    return schemas


def fetch_schema_details(
    schema_url: str, subject: str, version: str | None = None,
) -> dict[str, Any]:
    """Fetch full schema content for a subject and version (default: latest)."""
    try:
        with httpx.Client(timeout=10.0) as client:
            versions_response = client.get(f"{schema_url}/subjects/{subject}/versions")
            versions_response.raise_for_status()
            all_versions = versions_response.json()

            version_path = version if version else "latest"
            r = client.get(f"{schema_url}/subjects/{subject}/versions/{version_path}")
            r.raise_for_status()
            data = r.json()

            return {
                "subject": subject,
                "version": data.get("version", 0),
                "id": data.get("id"),
                "schema": data.get("schema"),
                "schemaType": data.get("schemaType", "AVRO"),
                "allVersions": all_versions,
            }
    except Exception as e:
        logger.error("Failed to fetch schema for %s: %s", subject, e)
        raise RuntimeError(f"Schema not found: {subject}") from e
