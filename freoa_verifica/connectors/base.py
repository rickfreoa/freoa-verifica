"""Interface comum dos conectores oficiais."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from freoa_verifica.parsers.model import ParsedDocument
from freoa_verifica.transport import Response

UserAgentMode = Literal["browser", "identified"]

IDENTIFIED_USER_AGENT = (
    "FREOA-Verifica/1.0 (+https://github.com/rickfreoa/freoa-verifica; "
    "uso-identificado; contato via FV_CONTACT)"
)


class Unavailable(Exception):
    """Fonte inacessível ou resposta não interpretável — nunca trate como zero resultados."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class Candidate:
    """Candidato de busca/resolve — metadados apenas; nunca 'verified'."""

    source_id: str
    key: str
    title: str
    url: str | None = None
    snippet: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CandidateList(list):
    """Contrato A9: candidatos lidos + `total` informado pela fonte; `truncado` = fonte tem mais do que foi lido."""

    def __init__(self, items=(), total: int | None = None):
        super().__init__(items)
        self.total = max(total or 0, len(self))

    @property
    def truncado(self) -> bool:
        return self.total > len(self)


@dataclass(frozen=True)
class HealthProbe:
    name: str  # positivo | negativo | documento
    status: str  # ok | unavailable | failed | zero
    detail: str | None = None


@dataclass(frozen=True)
class HealthReport:
    connector_id: str
    probes: tuple[HealthProbe, ...]
    checked_at: str | None = None

    @property
    def healthy(self) -> bool:
        return all(p.status in {"ok", "zero"} for p in self.probes)


@dataclass
class ParsedDecision:
    """Decisão/jurisprudência parseada a partir de resposta de conector."""

    profile: str
    kind: str
    court: str
    official_id: str
    ementa: str | None = None
    text: str = ""
    judgment_date: str | None = None
    publication_date: str | None = None
    rapporteur: str | None = None
    organ: str | None = None
    class_name: str | None = None
    cnj_number: str | None = None
    documents: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class Connector(ABC):
    """Contrato de conector de fonte oficial."""

    id: ClassVar[str]
    authority: ClassVar[str]
    hosts: ClassVar[frozenset[str]]
    path_prefixes: ClassVar[dict[str, tuple[str, ...]]]
    mimes: ClassVar[frozenset[str]]
    user_agent: ClassVar[UserAgentMode] = "browser"
    coverage: ClassVar[dict[str, Any]] = {}

    @abstractmethod
    def health(self) -> HealthReport:
        """Probes: positivo conhecido, negativo conhecido, documento."""

    @abstractmethod
    def search(self, q: str, **filtros: Any) -> list[Candidate]:
        """Busca candidatos (metadados). Lista vazia só com marcador estrutural de zero."""

    @abstractmethod
    def resolve(self, key: Any) -> Candidate | None:
        """Resolve chave estável (WorkKey, número, etc.) em candidato."""

    @abstractmethod
    def fetch(self, candidate: Candidate) -> Response:
        """Baixa o recurso via transport com hosts/prefixos/mimes do conector."""

    @abstractmethod
    def parse(self, resp: Response) -> ParsedDocument | ParsedDecision:
        """Interpreta o corpo baixado."""


_REGISTRY: dict[str, type[Connector]] = {}


def register(cls: type[Connector]) -> type[Connector]:
    _REGISTRY[cls.id] = cls
    return cls


def registry() -> dict[str, type[Connector]]:
    # Importação tardia para popular o registro.
    from freoa_verifica.connectors import (  # noqa: F401
        bcb,
        cvm_colegiado,
        cvm_normas,
        datajud,
        planalto,
        senado,
        stf,
        stj,
        tcu,
        tjsp,
    )

    return dict(_REGISTRY)


def get_connector(connector_id: str) -> Connector:
    classes = registry()
    if connector_id not in classes:
        raise KeyError(connector_id)
    return classes[connector_id]()
