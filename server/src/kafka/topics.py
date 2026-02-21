"""Topic listing, details, and message production."""
import logging
import os
import time
from typing import Any

from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient

from .config import client_config

logger = logging.getLogger(__name__)


def fetch_topics(admin: AdminClient) -> list[dict[str, Any]]:
    topics = []
    try:
        metadata = admin.list_topics(timeout=10)
        for name, t in metadata.topics.items():
            if name.startswith("__"):
                continue
            partitions = len(t.partitions) if t.partitions else 0
            replication = 0
            if t.partitions:
                for p in t.partitions.values():
                    if hasattr(p, "replicas") and p.replicas:
                        replication = len(p.replicas)
                        break
            topics.append({"name": name, "partitions": partitions, "replication": replication})
    except Exception as e:
        logger.exception("list_topics failed: %s", e)
        raise
    return topics


def fetch_topic_details(
    cluster: dict[str, Any], topic_name: str, include_messages: bool = False,
) -> dict[str, Any]:
    """Fetch config, metadata, and optionally recent messages for a topic."""
    try:
        cfg = client_config(cluster)
        admin = AdminClient(cfg)

        logger.info("Fetching details for topic: %s", topic_name)

        from confluent_kafka.admin import ConfigResource, ResourceType
        config_resource = ConfigResource(ResourceType.TOPIC, topic_name)
        configs = admin.describe_configs([config_resource], request_timeout=10)

        topic_config: dict[str, str] = {}
        for _res, future in configs.items():
            try:
                config_result = future.result()
                topic_config = {
                    entry.name: entry.value
                    for entry in config_result.values()
                    if entry.value is not None
                }
            except Exception as e:
                logger.warning("Could not fetch config for %s: %s", topic_name, e)

        metadata = admin.list_topics(timeout=10)
        topic_metadata = metadata.topics.get(topic_name)

        partitions_count = 0
        replication_factor = 0
        if topic_metadata and topic_metadata.partitions:
            partitions_count = len(topic_metadata.partitions)
            for partition in topic_metadata.partitions.values():
                if hasattr(partition, "replicas") and partition.replicas:
                    replication_factor = len(partition.replicas)
                    break

        retention_ms = topic_config.get("retention.ms", "N/A")
        retention_ms_display = _format_retention(retention_ms)

        messages: list[dict] = []
        if include_messages:
            messages = _fetch_recent_messages(cfg, topic_name, partitions_count)

        return {
            "name": topic_name,
            "partitions": partitions_count,
            "replicationFactor": replication_factor,
            "config": {
                "retentionMs": retention_ms,
                "retentionMsDisplay": retention_ms_display,
                "retentionBytes": topic_config.get("retention.bytes", "N/A"),
                "cleanupPolicy": topic_config.get("cleanup.policy", "delete"),
                "maxMessageBytes": topic_config.get("max.message.bytes", "N/A"),
            },
            "recentMessages": messages,
        }
    except Exception as e:
        logger.error("Failed to fetch topic details for %s: %s", topic_name, e, exc_info=True)
        raise RuntimeError(f"Could not fetch topic details: {e}") from e


def produce_message(
    cluster: dict[str, Any], topic_name: str, value: str, key: str | None = None,
) -> dict[str, Any]:
    """Produce a single message. Rejects internal topics (starting with _)."""
    name = (topic_name or "").strip()
    if not name or name.startswith("_"):
        raise RuntimeError("Cannot produce to internal topics (names starting with _)")

    bootstrap_list = [s.strip() for s in (cluster.get("bootstrapServers") or "").split(",") if s.strip()]
    if not bootstrap_list:
        raise RuntimeError("No bootstrap servers configured")

    try:
        producer = Producer({**client_config(cluster), "client.id": "streamlens-ui-producer"})
        value_bytes = value.encode("utf-8")
        key_bytes = key.encode("utf-8") if key else None
        delivered: dict[str, Any] = {"partition": None, "offset": None, "err": None}

        def delivery_callback(err, msg):
            if err:
                delivered["err"] = err
            else:
                delivered["partition"] = msg.partition()
                delivered["offset"] = msg.offset()

        producer.produce(topic_name, value=value_bytes, key=key_bytes, callback=delivery_callback)
        producer.flush(timeout=10)

        if delivered["err"]:
            raise RuntimeError(str(delivered["err"]))
        return {"ok": True, "partition": delivered["partition"], "offset": delivered["offset"]}
    except Exception as e:
        logger.exception("Produce failed for topic %s: %s", topic_name, e)
        raise RuntimeError(f"Produce failed: {e}") from e


def _format_retention(retention_ms: str) -> str:
    if retention_ms == "N/A":
        return "N/A"
    try:
        ms = int(retention_ms)
        if ms == -1:
            return "Unlimited"
        days = ms // (1000 * 60 * 60 * 24)
        hours = (ms % (1000 * 60 * 60 * 24)) // (1000 * 60 * 60)
        return f"{days}d {hours}h" if days > 0 else f"{hours}h"
    except (ValueError, TypeError):
        return str(retention_ms)


def _fetch_recent_messages(
    cfg: dict, topic_name: str, partitions_count: int, max_messages: int = 5,
) -> list[dict]:
    messages: list[dict] = []
    try:
        temp_consumer = Consumer({
            **cfg,
            "group.id": f"streamlens-viewer-{os.getpid()}",
            "enable.auto.commit": False,
            "auto.offset.reset": "latest",
        })

        partitions = [TopicPartition(topic_name, p) for p in range(partitions_count)]
        for tp in partitions:
            _low, high = temp_consumer.get_watermark_offsets(tp, cached=False, timeout=2.0)
            tp.offset = max(0, high - max_messages)

        temp_consumer.assign(partitions)
        start_time = time.time()

        while len(messages) < max_messages and (time.time() - start_time) < 3:
            msg = temp_consumer.poll(timeout=0.5)
            if msg is None or msg.error():
                continue
            try:
                key_str = msg.key().decode("utf-8") if msg.key() else None
            except Exception:
                key_str = str(msg.key()) if msg.key() else None
            try:
                value_str = msg.value().decode("utf-8") if msg.value() else None
            except Exception:
                value_str = "<binary data>"

            messages.append({
                "partition": msg.partition(),
                "offset": msg.offset(),
                "timestamp": msg.timestamp()[1] if msg.timestamp()[0] else None,
                "key": key_str,
                "value": value_str,
            })

        temp_consumer.close()
    except Exception as e:
        logger.warning("Could not fetch messages for %s: %s", topic_name, e)
    return messages
