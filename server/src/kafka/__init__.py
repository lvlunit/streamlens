"""kafka subpackage — drop-in replacement for the monolithic kafka.py module."""
from .service import KafkaService

kafka_service = KafkaService()

__all__ = ["KafkaService", "kafka_service"]
