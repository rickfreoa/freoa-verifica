"""Conectores de fontes oficiais."""

from freoa_verifica.connectors.base import (
    Candidate,
    Connector,
    HealthProbe,
    HealthReport,
    ParsedDecision,
    Unavailable,
    registry,
)

__all__ = [
    "Candidate",
    "Connector",
    "HealthProbe",
    "HealthReport",
    "ParsedDecision",
    "Unavailable",
    "registry",
]
