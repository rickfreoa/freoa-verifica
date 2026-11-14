"""Interface comum dos conectores oficiais."""

from __future__ import annotations

import functools
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from freoa_verifica.parsers.model import ParsedDocument
from freoa_verifica.transport import Response

UserAgentMode = Literal["identified"]


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


class LocalParserFailure(Unavailable):
    """Processo isolado sem resultado; não constitui evidência de perfil remoto."""


# Causas tipadas e distintas da falha local do parser isolado (códigos, nunca texto livre). Cada
# código identifica um mecanismo; a sanitização N2 não pode fundi-los (regressão da r2, CI de ad89d58).
CAUSAS_PARSER = frozenset({
    "importacao", "criacao_processo", "exit_nao_zero", "protocolo", "perfil_desconhecido",
    "timeout", "orcamento_esgotado", "entrada_excedida", "memoria_excedida", "limites_nao_instalados",
    "stdout_excedido", "stderr_excedido", "leitura_falhou", "escrita_falhou", "fechamento_falhou",
    "descendente_reteve_pipes", "erro_so", "pdf_paginas_excedidas", "pdf_texto_excedido",
    "pdf_folha_sem_extracao", "pdf_sem_biblioteca",
})
# Tipo da exceção de sistema no filho (ex.: criação de descendente negada pelo limite de processos).
TIPOS_ERRO_SO = frozenset({"OSError", "BlockingIOError", "PermissionError"})


def sanitizar_falha_parser(exc: Unavailable, *, perfil=None, url=None, sha256=None) -> Unavailable:
    """Lista permitida para falha local, inclusive exceções legadas de terceiros."""
    if not isinstance(exc, LocalParserFailure) and exc.reason != "falha_parser_camara":
        return exc
    evidence = exc.evidencia
    safe = {"fase": "interpretacao", "causa": evidence.get("causa")
            if isinstance(evidence.get("causa"), str) and evidence["causa"] in CAUSAS_PARSER else "protocolo"}
    profile = perfil or evidence.get("perfil")
    if isinstance(profile, str) and profile in {"planalto", "cvm_docx", "bcb_json", "cvm_pdf", "pdf_texto", "camara_legin", "camara_anexo", "normas_leg"}:
        safe["perfil"] = profile
    if type(evidence.get("exit_code")) is int:
        safe["exit_code"] = evidence["exit_code"]
    address = url or evidence.get("url")
    if address:
        from freoa_verifica.connectors.camara_policy import validar_url
        try:
            validar_url(address)
        except (ValueError, TypeError):
            pass
        else:
            safe["url"] = address
    digest = sha256 or evidence.get("sha256")
    if isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest):
        safe["sha256"] = digest
    if isinstance(exc, LocalParserFailure):
        return LocalParserFailure(f"{profile}_nao_processado" if "perfil" in safe else "parser_nao_processado", None, safe)
    return Unavailable("falha_parser_camara", None, safe)


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


class AmbiguousCandidates(Exception):
    """Alternativas oficiais confirmadas por metadados; nenhuma escolhida como texto."""

    def __init__(self, candidates: list[Candidate]):
        self.candidates = tuple(candidates)
        super().__init__("identidade_ambigua")


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


def sob_guarda(fn):
    """Executa `fn` sob a guarda da chamada (`guarda.da_chamada`)."""
    if getattr(fn, "_sob_guarda", False):
        return fn

    @functools.wraps(fn)
    def interno(*args, **kwargs):
        from freoa_verifica.connectors.guarda import da_chamada  # import tardio: guarda importa este módulo

        with da_chamada():
            return fn(*args, **kwargs)

    interno._sob_guarda = True
    return interno


# Métodos que podem chegar à rede: chamados diretamente (sem a fachada), cada um abre a própria guarda (FIX17/F-23).
ENTRADAS_DE_REDE = ("health", "search", "resolve", "fetch", "fetch_situacao", "sync", "package_show")


class Connector(ABC):
    """Contrato de conector de fonte oficial."""

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for nome in ENTRADAS_DE_REDE:
            fn = cls.__dict__.get(nome)
            if callable(fn):
                setattr(cls, nome, sob_guarda(fn))

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
        camara_legin,
        cvm_colegiado,
        cvm_normas,
        datajud,
        planalto,
        normas_leg,
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
