"""Consumer group discovery and lag calculation."""
import logging
import os
from typing import Any

from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient
from confluent_kafka._model import ConsumerGroupTopicPartitions

from .config import client_config

logger = logging.getLogger(__name__)


def fetch_consumer_groups(admin: AdminClient, client_cfg: dict) -> list[dict[str, Any]]:
    """Discover consumer groups and the topics they consume from."""
    consumers: list[dict[str, Any]] = []
    try:
        groups = admin.list_groups(timeout=10)
        if not groups:
            return consumers

        consumer_group_metadata = {
            group.id: group
            for group in groups
            if getattr(group, "protocol_type", "") == "consumer"
        }
        group_ids = list(consumer_group_metadata.keys())
        logger.info("Found %d consumer groups: %s", len(group_ids), group_ids)
        if not group_ids:
            return consumers

        for group_id in group_ids:
            topics_consumed = _discover_topics_from_members(
                admin, consumer_group_metadata.get(group_id),
            )
            if not topics_consumed:
                topics_consumed = _discover_topics_from_offsets(client_cfg, group_id, admin)

            is_streams = _is_likely_streams_app(group_id)
            consumers.append({
                "id": f"group:{group_id}",
                "consumesFrom": sorted(topics_consumed),
                "source": "auto-discovered",
                "isStreams": is_streams,
            })

    except Exception as e:
        logger.warning("consumer groups fetch failed: %s", e)
        import traceback
        logger.warning(traceback.format_exc())

    return consumers


def fetch_consumer_lag(cluster: dict[str, Any], group_id: str) -> dict[str, Any]:
    """Fetch per-partition consumer lag for a consumer group."""
    try:
        cfg = client_config(cluster)
        admin = AdminClient(cfg)
        logger.info("Fetching consumer lag for group: %s", group_id)

        group_request = ConsumerGroupTopicPartitions(group_id)
        group_metadata = admin.list_consumer_group_offsets([group_request], request_timeout=10)
        result: dict[str, Any] = {"topics": {}}

        if not group_metadata:
            return result

        for group_id_key, future in group_metadata.items():
            try:
                group_topic_partitions = future.result(timeout=10)
                partitions_metadata = group_topic_partitions.topic_partitions
                if not partitions_metadata:
                    return result

                tp_list = [(tp.topic, tp.partition, tp.offset) for tp in partitions_metadata]
                topics_data = _query_watermarks_for_lag(cfg, tp_list)
                result = {"topics": topics_data}
                logger.info("Successfully fetched lag for %d topics", len(topics_data))
            except Exception as e:
                logger.error("Failed to get lag for group %s: %s", group_id_key, e, exc_info=True)
                raise

        return result
    except Exception as e:
        logger.error("Failed to fetch consumer lag for %s: %s", group_id, e, exc_info=True)
        raise RuntimeError(f"Could not fetch consumer lag for {group_id}: {e}") from e


def _discover_topics_from_members(admin: AdminClient, group_metadata) -> set[str]:
    """Extract consumed topics from consumer group member metadata/assignment."""
    topics: set[str] = set()
    if not group_metadata or not hasattr(group_metadata, "members") or not group_metadata.members:
        return topics

    all_topics = admin.list_topics(timeout=5).topics.keys()
    for member in group_metadata.members:
        for attr in ("metadata", "assignment"):
            raw = getattr(member, attr, None)
            if not raw:
                continue
            try:
                decoded = raw.decode("utf-8", errors="ignore")
                for topic in all_topics:
                    if not topic.startswith("__") and topic in decoded:
                        topics.add(topic)
            except Exception:
                pass
    return topics


def _discover_topics_from_offsets(
    client_cfg: dict, group_id: str, admin: AdminClient,
) -> set[str]:
    """Fall back to checking committed offsets to find consumed topics."""
    topics: set[str] = set()
    try:
        temp_consumer = Consumer({
            **client_cfg,
            "group.id": f"_temp_query_{group_id}",
            "enable.auto.commit": False,
        })
        cluster_metadata = temp_consumer.list_topics(timeout=5)

        for topic_name in cluster_metadata.topics.keys():
            if topic_name.startswith("__"):
                continue
            topic_metadata = cluster_metadata.topics[topic_name]
            partitions = list(topic_metadata.partitions.keys())
            if not partitions:
                continue
            tps = [TopicPartition(topic_name, p) for p in partitions]
            committed = temp_consumer.committed(tps, timeout=2)
            if any(tp.offset >= 0 for tp in committed):
                topics.add(topic_name)

        temp_consumer.close()
    except Exception as e:
        logger.debug("Could not query offsets for group %s: %s", group_id, e)
    return topics


def _query_watermarks_for_lag(
    client_cfg: dict, tp_list: list[tuple[str, int, int]],
) -> dict[str, Any]:
    """Query high-watermarks and compute lag for a list of topic-partitions."""
    topics_data: dict[str, Any] = {}
    if not tp_list:
        return topics_data

    temp_consumer = None
    try:
        temp_consumer = Consumer({
            **client_cfg,
            "group.id": f"streamlens-lag-{os.getpid()}",
            "enable.auto.commit": False,
            "socket.timeout.ms": 5000,
            "api.version.request": False,
        })

        for topic, partition, committed_offset in tp_list:
            try:
                tp = TopicPartition(topic, partition)
                _low, high = temp_consumer.get_watermark_offsets(tp, cached=False, timeout=2.0)
                lag = max(0, high - committed_offset) if committed_offset >= 0 else high
            except Exception as e:
                logger.warning("Watermark query failed for %s:%d: %s", topic, partition, e)
                high = committed_offset if committed_offset >= 0 else 0
                lag = 0

            if topic not in topics_data:
                topics_data[topic] = {"partitions": []}
            topics_data[topic]["partitions"].append({
                "partition": partition,
                "currentOffset": committed_offset,
                "logEndOffset": high,
                "lag": lag,
            })
    finally:
        if temp_consumer:
            temp_consumer.close()

    return topics_data


def _is_likely_streams_app(group_id: str) -> bool:
    """Heuristic to detect if a consumer group is likely a Kafka Streams application."""
    group_lower = group_id.lower()
    patterns = ["stream", "streams", "kstream", "processor", "transformer", "aggregator", "enricher", "-application"]
    return any(p in group_lower for p in patterns)
