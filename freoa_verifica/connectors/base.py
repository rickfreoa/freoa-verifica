"""Interface comum dos conectores oficiais."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from freoa_verifica.parsers.model import ParsedDocument
from freoa_verifica.transport import Response

UserAgentMode = Literal["identified", "navegador_1_2_0"]


CATEGORIAS_INDISPONIBILIDADE = (
    "ambiental_desafio",
    "fonte_fora",
    "recusa_identificado",
    "resposta_inesperada",
    "regressao",
)
_REASONS_RESPOSTA_INESPERADA = frozenset({"resposta_invalida", "resposta_inesperada"})


class Unavailable(Exception):
    """Fonte inacessível ou resposta não interpretável — nunca trate como zero resultados.

    `reason` é o código estável. `categoria` (decisão 0045) só existe por prova positiva;
    `evidencia` traz status, marcador, cabecalho, sha256 e url quando conhecidos.
    """

    def __init__(self, reason: str, categoria: str | None = None, evidencia: dict | None = None):
        self.reason = reason
        if categoria is None and reason in _REASONS_RESPOSTA_INESPERADA:
            categoria = "resposta_inesperada"
        if categoria is not None and categoria not in CATEGORIAS_INDISPONIBILIDADE:
            raise ValueError(f"categoria inválida: {categoria}")
        self.categoria = categoria
        self.evidencia = dict(evidencia or {})
        super().__init__(reason)

    def classificacao(self) -> dict:
        """Campos aditivos para a saída JSON; vazio quando não há categoria provada."""
        if self.categoria is None:
            return {}
        out: dict = {"categoria": self.categoria}
        if self.evidencia:
            out["evidencia_indisponibilidade"] = self.evidencia
        return out


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
    """Contrato A9: candidatos lidos + `total` informado pela fonte.

    `total` é `None` quando a fonte não informa (desconhecido, nunca o tamanho lido). `total_exato`: `True`
    exato, `False` cota inferior, `None` a fonte não diz. `truncado` = a fonte tem mais do que foi lido.
    """

    def __init__(self, items=(), total: int | None = None, total_exato: bool | None = None):
        super().__init__(items)
        self.total = None if total is None else max(total, len(self))
        self.total_exato = total_exato if self.total is not None else None

    @property
    def truncado(self) -> bool:
        return self.total is not None and self.total > len(self)


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
    user_agent: ClassVar[UserAgentMode] = "identified"
    coverage: ClassVar[dict[str, Any]] = {}
    # Filtros públicos que a busca ao vivo aplica na origem: "remoto" (parâmetro da fonte) ou "local"
    # (no próprio conector, sobre o recuperado). Ausente = não aplicado (docs/FILTROS.md).
    filtros: ClassVar[dict[str, str]] = {}

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
        tjdft,
        tjsp,
    )

    return dict(_REGISTRY)


def get_connector(connector_id: str) -> Connector:
    classes = registry()
    if connector_id not in classes:
        raise KeyError(connector_id)
    return classes[connector_id]()
