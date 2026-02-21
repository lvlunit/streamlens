"""Kafka Streams application configuration loading."""
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_streams_config() -> list[dict[str, Any]]:
    """Load Kafka Streams applications from server/streams.yaml."""
    streams: list[dict[str, Any]] = []
    config_path = Path(__file__).parent.parent.parent / "streams.yaml"

    if not config_path.exists():
        logger.debug("No streams.yaml found, skipping streams configuration")
        return streams

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)

        if not config or "streams" not in config:
            logger.warning("streams.yaml exists but has no 'streams' key")
            return streams

        for entry in config.get("streams", []):
            name = entry.get("name")
            consumer_group = entry.get("consumerGroup")
            if not name or not consumer_group:
                logger.warning("Skipping invalid stream config: %s", entry)
                continue

            streams.append({
                "id": f"streams:{name}",
                "label": name,
                "name": name,
                "consumerGroup": consumer_group,
                "consumesFrom": entry.get("inputTopics", []),
                "producesTo": entry.get("outputTopics", []),
                "source": "config",
            })
            logger.info("Loaded streams app '%s': %s → %s", name, entry.get("inputTopics", []), entry.get("outputTopics", []))

    except Exception as e:
        logger.error("Failed to load streams.yaml: %s", e)

    return streams
