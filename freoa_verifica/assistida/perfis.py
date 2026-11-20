"""Perfis públicos fechados e resolução final do grafo (0089 §2.11)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from freoa_verifica import transport as t

URN = r"urn:lex:br:federal:[a-z]+(?:\.[a-z]+)*:\d{4}-\d{2}-\d{2};[0-9a-z]+(?:[.\-][0-9a-z]+)*"
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
OPERACOES = frozenset(
    {"buscar_legislacao", "verificar_citacao", "verificar_texto", "obter_dispositivo"}
)


@dataclass(frozen=True)
class PerfilSessaoAssistida:
    fonte: str
    porta: t.PerfilPortaAssistida
    vinculos: str
    limpeza_texto: str | None
    operacoes: frozenset[str] = OPERACOES
    validade_barreira_dias: int = 30

    def recurso(self, url: str, tipo: str | None = None) -> t.RecursoAssistido | None:
        try:
            url = url.split("#", 1)[0]
            t.validate_reference(url, self.porta.origens)
            p = urlsplit(url)
            if "//" in p.path:
                return None
            encontrados = [
                r
                for r in self.porta.recursos
                if (tipo is None or r.tipo == tipo)
                and re.fullmatch(r.caminho, p.path)
                and re.fullmatch(r.query, p.query)
            ]
            return encontrados[0] if len(encontrados) == 1 else None
        except (ValueError, t.TransportError, AttributeError):
            return None

    def sanitizar(self, url: str | None) -> str | None:
        # Um caminho pode admitir Document, XHR e Fetch. A ambiguidade entre
        # tipos não torna sua URL pública inválida; cada tipo ainda deve casar
        # uma única gramática completa, inclusive query.
        return (
            url.split("#", 1)[0]
            if url and any(self.recurso(url, r.tipo) for r in self.porta.recursos)
            else None
        )


PERFIS = {
    "planalto": PerfilSessaoAssistida(
        "planalto",
        t.PerfilPortaAssistida(
            frozenset({"www.planalto.gov.br"}),
            (
                t.RecursoAssistido(
                    "Document",
                    r"^/ccivil_03/[A-Za-z0-9_\-/]+\.htm[l]?$",
                    "^$",
                    frozenset({"text/html"}),
                ),
            ),
            (
                r"^TS[0-9a-f]{6,}$",
                r"^BIGipServer[\w.\-]+$",
                r"^f5avr\w+$",
                r"^f5_cspm$",
            ),
            "Compilação oficial publicada sem autenticação.",
        ),
        "documento",
        "planalto_cauda_0089.bin",
    ),
    "normas_leg": PerfilSessaoAssistida(
        "normas_leg",
        t.PerfilPortaAssistida(
            frozenset({"normas.leg.br"}),
            (
                t.RecursoAssistido(
                    "XHR",
                    r"^/api/public/normas$",
                    rf"^urn={URN}&&?tipo_documento=maior-detalhe$",
                    frozenset({"application/json"}),
                ),
                t.RecursoAssistido(
                    "XHR",
                    rf"^/api/public/binario/{UUID}/texto$",
                    "^$",
                    frozenset({"text/html"}),
                ),
            ),
            (r"^_ga$", r"^_ga_[A-Z0-9]+$", r"^_gid$", r"^_gat\w*$"),
            "API pública sem autenticação; licença CC BY 4.0 declarada no JSON.",
        ),
        "uuid_json_ld",
        None,
    ),
}


@dataclass(frozen=True)
class DocumentoSelecionavel:
    captura: t.CapturaAssistida
    identidade: str
    dependentes: tuple[t.CapturaAssistida, ...] = ()
    vinculo: dict = field(default_factory=dict)


class GrafoResolvido(list):
    """Mantém a reserva dos metadados exibidos até o descarte da seleção."""

    def __init__(self, documentos, orcamento):
        self.orcamento = orcamento
        self.reserva = len(documentos) * 8192 + 128
        orcamento.reservar(self.reserva)
        super().__init__(documentos)

    def fechar(self):
        self.clear()
        self.orcamento.liberar(self.reserva)
        self.reserva = 0


def _metadados(captura):
    p = urlsplit(captura.resposta.final_url)
    urn = p.query.split("&", 1)[0].removeprefix("urn=")

    # Duplicatas de chaves JSON não podem esconder conflito.
    def pares(itens):
        obj = {}
        for k, v in itens:
            if k in obj:
                raise ValueError
            obj[k] = v
        return obj

    data = json.loads(captura.resposta.body, object_pairs_hook=pares)
    if data.get("legislationIdentifier") != urn or not re.fullmatch(URN, urn):
        raise ValueError
    enc = data["encoding"]
    if not isinstance(enc, list) or not enc:
        raise ValueError
    encontrados = []
    for e in enc:
        if not isinstance(e, dict) or e.get("@type") != "LegislationObject":
            raise ValueError
        m = re.fullmatch(
            rf"https://normas\.leg\.br/api/binario/({UUID})/texto",
            e.get("contentUrl", ""),
        )
        version = e.get("version")
        sufixo = (
            r"versao\.atualizada"
            if version == "Current"
            else r"\d{4}-\d{2}-\d{2}"
            if version == "Original"
            else None
        )
        if (
            not m
            or sufixo is None
            or not re.fullmatch(re.escape(urn) + "@" + sufixo, e.get("@id", ""))
        ):
            raise ValueError
        encontrados.append((m[1], urn, version, e["@id"]))
    return encontrados


def resolver_grafo(perfil, capturas, *, orcamento):
    """Só recebe exemplares admitidos pela porta. Nenhuma gravação ou estado jurídico."""
    if any(not isinstance(c, t.CapturaAssistida) for c in capturas):
        raise ValueError("EXEMPLAR_NAO_ADMITIDO")
    if perfil.fonte == "planalto":
        reserva = len(capturas) * 8192 + 128
        orcamento.reservar(reserva)
        try:
            documentos = [
                DocumentoSelecionavel(c, urlsplit(c.resposta.final_url).path)
                for c in capturas
            ]
            return GrafoResolvido(documentos, orcamento)
        finally:
            orcamento.liberar(reserva)
    reserva = sum(len(c.resposta.body) * 64 + 4096 for c in capturas)
    orcamento.reservar(reserva)
    try:
        por_uuid, textos, urn_hashes = {}, {}, {}
        for c in capturas:
            p = urlsplit(c.resposta.final_url)
            if p.path == "/api/public/normas":
                try:
                    itens = _metadados(c)
                except (
                    ValueError,
                    KeyError,
                    TypeError,
                    AttributeError,
                    UnicodeError,
                    RecursionError,
                ):
                    continue
                for uid, urn, versao, eid in itens:
                    urn_hashes.setdefault(urn, set()).add(c.resposta.sha256)
                    por_uuid.setdefault(uid, []).append((c, urn, versao, eid))
            elif re.fullmatch(rf"/api/public/binario/{UUID}/texto", p.path):
                textos.setdefault(p.path.split("/")[4], []).append(c)
        saida = []
        for uid, bs in textos.items():
            refs = por_uuid.get(uid, [])
            # A repetida idêntica é uma obtenção distinta, mas não cria ambiguidade semântica.
            unicas = {(a.resposta.sha256, urn, v, eid) for a, urn, v, eid in refs}
            if len(unicas) != 1 or len({b.resposta.sha256 for b in bs}) != 1:
                continue
            a, urn, versao, eid = refs[0]
            if len(urn_hashes[urn]) != 1:
                continue
            # UUID em dois elementos da mesma A é conflito, mesmo com atributos idênticos.
            if any(
                sum(x[0].obtencao_id == ref.obtencao_id for x in refs) != 1
                for ref, *_ in refs
            ):
                continue
            vinculo = {
                "metadados_obtencao_id": a.obtencao_id,
                "metadados_sha256": a.resposta.sha256,
                "urn": urn,
                "uuid": uid,
                "version": versao,
                "@id": eid,
                "legislationLegalValue": "UnofficialLegalValue",
            }
            saida.append(DocumentoSelecionavel(bs[0], f"{urn} {versao}", (a,), vinculo))
        return GrafoResolvido(saida, orcamento)
    finally:
        orcamento.liberar(reserva)
