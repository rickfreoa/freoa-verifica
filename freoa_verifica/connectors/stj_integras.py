"""Íntegras do STJ (CKAN: integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica).

Recurso diário aos pares: metadadosAAAAMMDD.json e textosAAAAMMDD.zip, este com um arquivo
`<SeqDocumento>.txt` por documento. Os metadados não trazem órgão julgador; o recorte se faz
pelo vínculo com espelho já presente no acervo (decisão 0044). Inteiro teor por declaração da
coleção oficial, nunca por comprimento (decisão 0038).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

MAX_ENTRADAS = 5000
MAX_DESCOMPACTADO = 200 * 1024 * 1024
MAX_POR_ENTRADA = 5 * 1024 * 1024
MAX_RAZAO = 100.0
_NOME = re.compile(r"([0-9]{1,15})\.txt")  # fullmatch: sem \n final nem d?gitos Unicode
_REGISTRO = re.compile(r"[0-9]{12}")


class IntegrasInvalidas(ValueError):
    """Recurso de íntegras recusado (formato ou limites)."""


@dataclass(frozen=True)
class Integra:
    seq: str
    numero_registro: str
    processo: str
    tipo: str
    data_publicacao: str | None
    ministro: str | None
    texto: str
    sha256_texto: str  # dos bytes brutos do arquivo no ZIP oficial
    metadados: dict[str, Any]

    @property
    def texto_limpo(self) -> str:
        """Quebras <br> viram linhas; o hash da prova é sempre do texto bruto."""
        return re.sub(r"(?i)<br\s*/?>", "\n", self.texto).strip()


@dataclass
class Resultado:
    vinculadas: list[tuple[Integra, str]] = field(default_factory=list)  # (íntegra, chave do espelho)
    ambiguas: list[tuple[Integra, list[str]]] = field(default_factory=list)
    descartes: dict[str, int] = field(default_factory=dict)

    def descartar(self, motivo: str) -> None:
        self.descartes[motivo] = self.descartes.get(motivo, 0) + 1


def _sem_acento(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").upper().strip()


def ler_metadados(body: bytes) -> list[dict[str, Any]]:
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrasInvalidas(f"metadados_invalidos: {exc}") from exc
    if not isinstance(data, list):
        raise IntegrasInvalidas("metadados_nao_lista")
    return [d for d in data if isinstance(d, dict)]


def ler_textos(raw: bytes) -> dict[str, tuple[str | None, str]]:
    """SeqDocumento -> (texto ou None se n?o UTF-8, sha256 dos bytes), com limites de entradas, tamanho, razão de compressão e nomes."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise IntegrasInvalidas("zip_invalido") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRADAS:
            raise IntegrasInvalidas("zip_entradas_excedidas")
        total = lidos = 0
        out: dict[str, tuple[str | None, str]] = {}
        for info in infos:
            if info.is_dir():
                continue
            m = _NOME.fullmatch(info.filename)
            if not m:  # recusa caminhos, barras e nomes fora do padrão (inclui zip-slip)
                raise IntegrasInvalidas(f"zip_nome_inesperado: {info.filename[:80]}")
            if info.file_size > MAX_POR_ENTRADA:
                raise IntegrasInvalidas("zip_entrada_grande")
            total += info.file_size
            if total > MAX_DESCOMPACTADO:
                raise IntegrasInvalidas("zip_descompactado_excedido")
            if info.file_size and (not info.compress_size or info.file_size / info.compress_size > MAX_RAZAO):
                raise IntegrasInvalidas("zip_razao_compressao")
            if info.flag_bits & 0x1:
                raise IntegrasInvalidas("zip_criptografado")
            try:
                with zf.open(info) as fh:  # cabe?alho pode mentir: conta os bytes lidos
                    data = fh.read(MAX_POR_ENTRADA + 1)
            except (zipfile.BadZipFile, EOFError, NotImplementedError, RuntimeError, OSError) as exc:
                raise IntegrasInvalidas(f"zip_leitura: {type(exc).__name__}") from exc
            except Exception as exc:  # zlib.error e afins
                raise IntegrasInvalidas(f"zip_leitura: {type(exc).__name__}") from exc
            if len(data) > MAX_POR_ENTRADA:
                raise IntegrasInvalidas("zip_entrada_grande")
            lidos += len(data)
            if lidos > MAX_DESCOMPACTADO:
                raise IntegrasInvalidas("zip_descompactado_excedido")
            seq = m.group(1)
            if seq in out:
                raise IntegrasInvalidas("zip_seq_repetido")
            out[seq] = (_decodificar(data), hashlib.sha256(data).hexdigest())
        return out


def _decodificar(data: bytes) -> str | None:
    """UTF-8 estrito (formato observado); falha n?o ? mascarada: o documento ? descartado."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


_CONECTIVOS = frozenset({"NO", "NA", "NOS", "NAS", "EM", "DO", "DA", "DOS", "DAS"})


def classe_tokens(sigla: str) -> tuple[str, ...]:
    """'AgInt no REsp' -> ('AGINT','RESP'); conectivos variam entre fontes e n?o distinguem graus."""
    return tuple(t for t in _sem_acento(sigla).split() if t not in _CONECTIVOS)


def _classe_da_integra(md: Mapping[str, Any]) -> tuple[tuple[str, ...], str] | None:
    """(tokens da classe composta, n?mero) a partir de `recurso` + `processo` ('REsp 2066740')."""
    m = re.match(r"^\s*(.+?)\s+(\d+)\s*$", str(md.get("processo") or ""))
    if not m:
        return None
    return classe_tokens(f"{md.get('recurso') or ''} {m.group(1)}"), m.group(2)


def combinar(metadados_body: bytes, zip_body: bytes,
             espelhos_por_registro: Mapping[str, Iterable[tuple[str, str, str]]]) -> Resultado:
    """Une metadados e textos e vincula cada ac?rd?o a um espelho do acervo.

    `espelhos_por_registro`: numeroRegistro -> (chave, siglaClasse, numeroProcesso) dos espelhos.
    O registro abriga v?rios ac?rd?os (REsp, AgInt no REsp, EDcl...): o v?nculo exige registro,
    classe composta e n?mero iguais. Um candidato: v?nculo. V?rios: amb?guo. Nenhum: descarte.
    """
    textos = ler_textos(zip_body)
    res = Resultado()
    metas = ler_metadados(metadados_body)
    por_seq: dict[str, list[dict[str, Any]]] = {}
    for md in metas:
        por_seq.setdefault(str(md.get("SeqDocumento") or "").strip(), []).append(md)
    candidatos: list[tuple[Integra, tuple]] = []
    for seq, grupo in por_seq.items():
        if not (seq.isascii() and seq.isdecimal()):
            for _ in grupo:
                res.descartar("sem_seq")
            continue
        if any(g != grupo[0] for g in grupo):  # mesmo Seq com dados diferentes: nenhum vale
            for _ in grupo:
                res.descartar("seq_repetido_divergente")
            continue
        md = grupo[0]
        if _sem_acento(str(md.get("tipoDocumento") or "")) != "ACORDAO":
            res.descartar("monocratica_fora_desta_versao")
            continue
        registro = str(md.get("numeroRegistro") or "").strip()
        if not isinstance(md.get("numeroRegistro"), str) or not _REGISTRO.fullmatch(registro):
            res.descartar("registro_invalido")
            continue
        classe = _classe_da_integra(md)
        if classe is None:
            res.descartar("processo_invalido")
            continue
        if seq not in textos:
            res.descartar("texto_ausente_no_zip")
            continue
        texto, sha_bytes = textos[seq]
        if texto is None:
            res.descartar("texto_nao_utf8")
            continue
        if not texto.strip():
            res.descartar("texto_vazio")
            continue
        integra = Integra(
            seq=seq, numero_registro=registro, processo=str(md.get("processo") or "").strip(),
            tipo="acordao", data_publicacao=md.get("dataPublicacao"), ministro=md.get("NM_MINISTRO"),
            texto=texto, sha256_texto=sha_bytes, metadados=dict(md))
        candidatos.append((integra, (registro, *classe)))
    repetidas: dict[tuple, int] = {}
    for _, ident in candidatos:
        repetidas[ident] = repetidas.get(ident, 0) + 1
    for integra, ident in candidatos:
        registro, tokens, numero = ident
        chaves = sorted({k for k, sigla, num in espelhos_por_registro.get(registro, ())
                         if classe_tokens(sigla or "") == tokens
                         and str(num or "").strip().lstrip("0") == numero.lstrip("0")})
        if repetidas[ident] > 1:  # duas ?ntegras para o mesmo ac?rd?o no dia: n?o escolhe
            res.ambiguas.append((integra, chaves))
        elif not chaves:
            res.descartar("fora_do_recorte_ou_sem_espelho")
        elif len(chaves) == 1:
            res.vinculadas.append((integra, chaves[0]))
        else:
            res.ambiguas.append((integra, chaves))
    return res
