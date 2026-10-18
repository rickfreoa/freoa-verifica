"""Modelo comum de saída dos parsers normativos."""

from __future__ import annotations

from dataclasses import dataclass, field

DOCUMENT_BLOCKING_CODES = frozenset({"TRUNCATED"})
PROVISION_BLOCKING_CODES = frozenset(
    {"DUPLICATE_CURRENT", "ORDER", "UNCERTAIN_CONTINUATION", "SCOPE_COLLISION"}
)


class AmbiguousProvision(Exception):
    """Mais de uma redação vigente sem cadeia editorial resolvida."""

    def __init__(self, path: str, detail: str = "") -> None:
        self.path = path
        super().__init__(detail or f"dispositivo ambíguo: {path}")


class RevokedProvision(Exception):
    """Última anotação indica revogação; não há texto vigente."""

    def __init__(self, path: str, detail: str = "") -> None:
        self.path = path
        super().__init__(detail or f"dispositivo revogado: {path}")


class QuarantinedDocument(Exception):
    """Documento em quarentena; accessors de texto recusam."""

    def __init__(self, detail: str = "documento em quarentena") -> None:
        super().__init__(detail)


@dataclass
class Annotation:
    kind: str  # redacao_dada|incluido|revogado|vide|vigencia|producao_efeitos|veto|renumerado|outro
    raw: str
    act_ref: str | None = None
    act_href: str | None = None
    act_date: str | None = None  # ISO quando o texto traz data completa


@dataclass
class Redaction:
    text: str
    struck: bool
    order: int
    annotations: list[Annotation] = field(default_factory=list)
    span: tuple[int, int] = (0, 0)  # offsets no texto extraído
    superseded_without_strike: bool = False
    scope: str = ""


@dataclass
class Provision:
    path: str
    label: str
    scope: str
    headings: list[str] = field(default_factory=list)
    redactions: list[Redaction] = field(default_factory=list)
    ambiguous: bool = False
    concurrent_redactions: list[Redaction] = field(default_factory=list)

    def current_redaction(self) -> Redaction:
        if self.ambiguous:
            raise AmbiguousProvision(self.path)
        for red in reversed(self.redactions):
            if red.struck or red.superseded_without_strike:
                continue
            if any(a.kind == "revogado" for a in red.annotations):
                raise RevokedProvision(self.path)
            # Stub (VETADO) vazio: não é texto vigente
            if any(a.kind == "veto" for a in red.annotations) and not red.text.strip():
                continue
            return red
        if self.redactions:
            last = self.redactions[-1]
            if any(a.kind == "revogado" for a in last.annotations):
                raise RevokedProvision(self.path)
            if any(a.kind == "veto" for a in last.annotations) and not last.text.strip():
                raise RevokedProvision(self.path, f"dispositivo vetado: {self.path}")
        raise RevokedProvision(self.path, f"sem redação vigente: {self.path}")

    def current_text(self) -> str:
        return self.current_redaction().text


@dataclass
class QuotedAmendment:
    """Texto citado de outra lei dentro de lei alteradora (não é dispositivo próprio)."""

    host_path: str
    target_ref_text: str
    target_label: str
    text: str


@dataclass
class EditorialBlock:
    """Bloco editorial (nota, obs., glossário) separado da redação normativa."""

    text: str
    span: tuple[int, int]
    kind: str = "editorial"  # editorial|uncertain


@dataclass
class Issue:
    code: str
    path: str | None
    detail: str
    blocking_scope: str | None = None  # 'document' | 'provision' | None


@dataclass
class ParsedDocument:
    profile: str
    parser_version: str
    title: str
    ementa: str | None
    text: str
    provisions: list[Provision] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    amendments: list[QuotedAmendment] = field(default_factory=list)
    editorial_blocks: list[EditorialBlock] = field(default_factory=list)

    @property
    def quarantined(self) -> bool:
        return any(
            i.blocking_scope == "document" or i.code in DOCUMENT_BLOCKING_CODES
            for i in self.issues
        )

    @property
    def ambiguous_paths(self) -> list[str]:
        return [p.path for p in self.provisions if p.ambiguous]

    def provision(self, path: str) -> Provision | None:
        for p in self.provisions:
            if p.path == path:
                return p
        return None

    def current_text(self, path: str) -> str | None:
        if self.quarantined:
            raise QuarantinedDocument()
        prov = self.provision(path)
        if prov is None:
            return None
        return prov.current_text()

    def current_redaction(self, path: str) -> Redaction | None:
        if self.quarantined:
            raise QuarantinedDocument()
        prov = self.provision(path)
        if prov is None:
            return None
        return prov.current_redaction()


def document_from_dict(raw: dict) -> ParsedDocument:
    """Reconstitui o modelo persistido sem inferir campos ausentes."""
    from dataclasses import fields

    def exact(cls, values):
        if set(values) != {f.name for f in fields(cls)}:
            raise ValueError("modelo incompleto")
        return cls(**values)

    def red(values):
        values = dict(values)
        values["annotations"] = [exact(Annotation, a) for a in values["annotations"]]
        values["span"] = tuple(values["span"])
        return exact(Redaction, values)

    def prov(values):
        values = dict(values)
        values["redactions"] = [red(r) for r in values["redactions"]]
        values["concurrent_redactions"] = [red(r) for r in values["concurrent_redactions"]]
        return exact(Provision, values)

    values = dict(raw)
    values["provisions"] = [prov(p) for p in values["provisions"]]
    values["issues"] = [exact(Issue, i) for i in values["issues"]]
    values["amendments"] = [exact(QuotedAmendment, a) for a in values["amendments"]]
    values["editorial_blocks"] = [
        exact(EditorialBlock, {**b, "span": tuple(b["span"])})
        for b in values["editorial_blocks"]
    ]
    return exact(ParsedDocument, values)
