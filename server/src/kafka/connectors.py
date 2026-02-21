"""Kafka Connect connector discovery and detail retrieval."""
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SENSITIVE_KEYWORDS = [
    "password", "passwd", "pwd", "secret", "key", "token",
    "credential", "auth", "ssl.key", "ssl.truststore.password",
    "ssl.keystore.password", "sasl.jaas.config", "connection.password",
    "aws.secret", "azure.client.secret", "api.key", "api.secret",
]


def fetch_connectors(connect_url: str) -> list[dict[str, Any]]:
    """List connectors and their topic associations from Kafka Connect REST API."""
    connectors: list[dict[str, Any]] = []
    with httpx.Client(timeout=10.0) as client:
        r = client.get(f"{connect_url}/connectors")
        r.raise_for_status()
        names = r.json()

        for name in names:
            try:
                r2 = client.get(f"{connect_url}/connectors/{name}")
                r2.raise_for_status()
                info = r2.json()
                config = info.get("config", {})
                connector_class = config.get("connector.class", "")

                topics_conf = (
                    config.get("topics") or config.get("topics.regex")
                    or config.get("topic") or config.get("topic.regex") or ""
                )
                topic_list = [t.strip() for t in topics_conf.split(",") if t.strip()] if isinstance(topics_conf, str) else []
                if not topic_list and "topic" in config:
                    topic_list = [config["topic"].strip()]

                is_sink = "sink" in connector_class.lower() or "Sink" in info.get("type", "")
                connector_type = "sink" if is_sink else "source"

                if topic_list:
                    for topic in topic_list[:5]:
                        connectors.append({"id": f"connect:{name}", "type": connector_type, "topic": topic})
                else:
                    connectors.append({"id": f"connect:{name}", "type": connector_type, "topic": "?"})
            except Exception as e:
                logger.debug("connector %s: %s", name, e)

    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for c in connectors:
        key = (c["id"], c["topic"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def fetch_connector_details(connect_url: str, connector_name: str) -> dict[str, Any]:
    """Fetch and return connector config with sensitive values masked."""
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{connect_url}/connectors/{connector_name}")
            r.raise_for_status()
            info = r.json()

            config = info.get("config", {})
            masked_config = {}
            for k, v in config.items():
                is_sensitive = any(kw in k.lower() for kw in SENSITIVE_KEYWORDS)
                masked_config[k] = "********" if (is_sensitive and v) else v

            return {
                "name": info.get("name"),
                "type": info.get("type", "unknown"),
                "config": masked_config,
                "tasks": info.get("tasks", []),
                "connectorClass": config.get("connector.class", "N/A"),
            }
    except Exception as e:
        logger.error("Failed to fetch connector details for %s: %s", connector_name, e)
        raise RuntimeError(f"Could not fetch connector details: {e}") from e
