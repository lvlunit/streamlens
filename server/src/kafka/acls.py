"""Topic-level ACL binding retrieval."""
import logging
from typing import Any

from confluent_kafka.admin import AdminClient

logger = logging.getLogger(__name__)


def fetch_topic_acls(admin: AdminClient, topic_names: list[str] | None = None) -> list[dict[str, Any]]:
    """Fetch all ACL bindings for TOPIC resources.

    Tries a wildcard filter first; falls back to per-topic queries.
    """
    acls: list[dict[str, Any]] = []
    topic_names = topic_names or []

    try:
        from confluent_kafka.admin import (
            AclBindingFilter, ResourceType, ResourcePatternType, AclOperation, AclPermissionType,
        )

        try:
            acl_filter = AclBindingFilter(
                restype=ResourceType.TOPIC, name=None,
                resource_pattern_type=ResourcePatternType.ANY,
                principal=None, host=None,
                operation=AclOperation.ANY,
                permission_type=AclPermissionType.ANY,
            )
            result = admin.describe_acls(acl_filter, request_timeout=10)
            for acl in result.result():
                parsed = _parse_binding(acl)
                if parsed:
                    acls.append(parsed)
            if acls:
                logger.info("Found %d topic ACL bindings (match-any filter)", len(acls))
                return acls
        except (TypeError, ValueError) as e:
            logger.debug("Match-any ACL filter not supported (%s), trying per-topic", e)

        if not topic_names:
            try:
                metadata = admin.list_topics(timeout=5)
                if getattr(metadata, "topics", None):
                    topic_names = [n for n in metadata.topics.keys() if n and not n.startswith("__")]
            except Exception as e:
                logger.debug("list_topics for ACL fallback: %s", e)

        seen: set[tuple[str, str, str, str, str]] = set()
        for topic in topic_names:
            if not topic or topic.startswith("__"):
                continue
            try:
                acl_filter = AclBindingFilter(
                    restype=ResourceType.TOPIC, name=topic,
                    resource_pattern_type=ResourcePatternType.LITERAL,
                    principal=None, host=None,
                    operation=AclOperation.ANY,
                    permission_type=AclPermissionType.ANY,
                )
                result = admin.describe_acls(acl_filter, request_timeout=5)
                for acl in result.result():
                    parsed = _parse_binding(acl)
                    if parsed:
                        key = (parsed["topic"], parsed["principal"], parsed["host"], parsed["operation"], parsed["permissionType"])
                        if key not in seen:
                            seen.add(key)
                            acls.append(parsed)
            except Exception as e:
                logger.debug("ACL describe for topic %s: %s", topic, e)

        if acls:
            logger.info("Found %d topic ACL bindings (per-topic)", len(acls))
    except ImportError as e:
        logger.debug("ACL classes not available: %s", e)
    except Exception as e:
        logger.warning("Topic ACL fetch failed: %s", e)
    return acls


def _parse_binding(acl: Any) -> dict[str, Any] | None:
    topic = getattr(acl, "name", None) or getattr(acl, "resource_name", None)
    if not topic or (isinstance(topic, str) and topic.startswith("__")):
        return None
    principal = getattr(acl, "principal", "") or ""
    host = getattr(acl, "host", "") or ""
    op = getattr(acl, "operation", None)
    perm = getattr(acl, "permission_type", None)
    operation = op.name if hasattr(op, "name") else str(op) if op else "UNKNOWN"
    permission_type = perm.name if hasattr(perm, "name") else str(perm) if perm else "UNKNOWN"
    return {
        "topic": topic,
        "principal": principal,
        "host": host,
        "operation": operation,
        "permissionType": permission_type,
    }
