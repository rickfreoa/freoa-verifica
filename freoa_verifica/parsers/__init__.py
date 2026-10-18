"""Parsers normativos por perfil, com sentinela."""

from freoa_verifica.parsers.isolated import parse_isolated
from freoa_verifica.parsers.model import (
    AmbiguousProvision,
    Annotation,
    Issue,
    ParsedDocument,
    Provision,
    QuarantinedDocument,
    QuotedAmendment,
    Redaction,
    RevokedProvision,
)

__all__ = [
    "AmbiguousProvision",
    "Annotation",
    "Issue",
    "ParsedDocument",
    "Provision",
    "QuarantinedDocument",
    "QuotedAmendment",
    "Redaction",
    "RevokedProvision",
    "parse_isolated",
]
