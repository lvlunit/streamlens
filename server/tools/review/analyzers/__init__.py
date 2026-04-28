"""Analyzer package for the automated code review engine.

Provides the abstract :class:`BaseAnalyzer` interface and concrete
analyzer implementations for various static analysis tools.
"""

from .base import BaseAnalyzer

__all__ = ["BaseAnalyzer"]
