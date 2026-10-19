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
_NOME = re.compile(r"^(\d{1,15})\.txt$")
_REGISTRO = re.compile(r"^\d{12}$")


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
    sha256_texto: str
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


def ler_textos(raw: bytes) -> dict[str, str]:
    """SeqDocumento -> texto, com limites de entradas, tamanho, razão de compressão e nomes."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise IntegrasInvalidas("zip_invalido") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRADAS:
            raise IntegrasInvalidas("zip_entradas_excedidas")
        total = 0
        out: dict[str, str] = {}
        for info in infos:
            if info.is_dir():
                continue
            m = _NOME.match(info.filename)
            if not m:  # recusa caminhos, barras e nomes fora do padrão (inclui zip-slip)
                raise IntegrasInvalidas(f"zip_nome_inesperado: {info.filename[:80]}")
            if info.file_size > MAX_POR_ENTRADA:
                raise IntegrasInvalidas("zip_entrada_grande")
            total += info.file_size
            if total > MAX_DESCOMPACTADO:
                raise IntegrasInvalidas("zip_descompactado_excedido")
            if info.compress_size and info.file_size / info.compress_size > MAX_RAZAO:
                raise IntegrasInvalidas("zip_razao_compressao")
            with zf.open(info) as fh:
                data = fh.read(MAX_POR_ENTRADA + 1)
            if len(data) > MAX_POR_ENTRADA:
                raise IntegrasInvalidas("zip_entrada_grande")
            seq = m.group(1)
            if seq in out:
                raise IntegrasInvalidas("zip_seq_repetido")
            out[seq] = _decodificar(data)
        return out


def _decodificar(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def combinar(metadados_body: bytes, zip_body: bytes,
             espelhos_por_registro: Mapping[str, Iterable[str]]) -> Resultado:
    """Une metadados e textos e vincula cada acórdão ao espelho pelo número de registro.

    `espelhos_por_registro`: numeroRegistro (12 dígitos) -> chaves de espelhos do acervo.
    Um espelho: vínculo. Vários: ambíguo (nunca escolhe). Nenhum: descarte contado.
    """
    textos = ler_textos(zip_body)
    res = Resultado()
    vistos: set[str] = set()
    for md in ler_metadados(metadados_body):
        seq = str(md.get("SeqDocumento") or "").strip()
        if not seq.isdigit():
            res.descartar("sem_seq")
            continue
        if seq in vistos:
            res.descartar("seq_repetido_nos_metadados")
            continue
        vistos.add(seq)
        tipo = _sem_acento(str(md.get("tipoDocumento") or ""))
        if tipo != "ACORDAO":
            res.descartar("monocratica_fora_desta_versao")
            continue
        registro = re.sub(r"\D", "", str(md.get("numeroRegistro") or ""))
        if not _REGISTRO.match(registro):
            res.descartar("registro_invalido")
            continue
        texto = textos.get(seq)
        if texto is None or not texto.strip():
            res.descartar("texto_ausente_no_zip")
            continue
        integra = Integra(
            seq=seq, numero_registro=registro, processo=str(md.get("processo") or "").strip(),
            tipo="acordao", data_publicacao=md.get("dataPublicacao"), ministro=md.get("NM_MINISTRO"),
            texto=texto, sha256_texto=hashlib.sha256(texto.encode("utf-8")).hexdigest(), metadados=dict(md))
        chaves = sorted(set(espelhos_por_registro.get(registro, ())))
        if not chaves:
            res.descartar("fora_do_recorte_ou_sem_espelho")
        elif len(chaves) == 1:
            res.vinculadas.append((integra, chaves[0]))
        else:
            res.ambiguas.append((integra, chaves))
    return res
