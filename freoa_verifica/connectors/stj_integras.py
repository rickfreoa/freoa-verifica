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
_NOME = re.compile(r"([0-9]{1,15})\.txt")  # fullmatch: sem \n final nem dígitos Unicode
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
    ruins = [i for i, d in enumerate(data) if not isinstance(d, dict)]
    if ruins:  # contrato da fonte mudou: indisponibilidade, nunca resultado vazio regular
        raise IntegrasInvalidas(f"metadados_item_nao_objeto: {ruins[:5]}")
    return data


def ler_textos(raw: bytes) -> dict[str, tuple[str | None, str]]:
    """SeqDocumento -> (texto ou None se não UTF-8, sha256 dos bytes), com limites de entradas, tamanho, razão de compressão e nomes."""
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
            if info.orig_filename != info.filename or "\x00" in info.orig_filename:
                raise IntegrasInvalidas("zip_nome_inesperado")
            m = _NOME.fullmatch(info.filename)  # diretórios também caem aqui: não pertencem ao formato
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
            data = _ler_bruto(zf, info)
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


def _ler_bruto(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    """Lê o fluxo comprimido pelo cabeçalho local e o descompacta sem confiar em file_size/CRC declarados."""
    import struct
    import zlib

    fp = zf.fp
    fp.seek(info.header_offset)
    local = fp.read(30)
    if len(local) != 30 or local[:4] != b"PK\x03\x04":
        raise IntegrasInvalidas("zip_cabecalho_local")
    n_nome, n_extra = struct.unpack("<HH", local[26:30])
    if fp.read(n_nome) != info.orig_filename.encode("cp437" if not info.flag_bits & 0x800 else "utf-8"):
        raise IntegrasInvalidas("zip_nome_divergente")
    fp.read(n_extra)
    if info.compress_size > MAX_POR_ENTRADA:
        raise IntegrasInvalidas("zip_entrada_grande")
    comp = fp.read(info.compress_size)
    if len(comp) != info.compress_size:
        raise IntegrasInvalidas("zip_truncado")
    if info.compress_type == zipfile.ZIP_STORED:
        if info.compress_size != info.file_size:
            raise IntegrasInvalidas("zip_tamanho_divergente")
        data = comp
    elif info.compress_type == zipfile.ZIP_DEFLATED:
        d = zlib.decompressobj(-15)
        try:
            data = d.decompress(comp, MAX_POR_ENTRADA + 1)
        except zlib.error as exc:
            raise IntegrasInvalidas("zip_fluxo_invalido") from exc
        if len(data) > MAX_POR_ENTRADA:
            raise IntegrasInvalidas("zip_entrada_grande")
        if not d.eof or d.unconsumed_tail or d.unused_data:
            raise IntegrasInvalidas("zip_fluxo_inconsistente")
    else:
        raise IntegrasInvalidas("zip_metodo_nao_suportado")
    if len(data) != info.file_size or (zlib.crc32(data) & 0xFFFFFFFF) != info.CRC:
        raise IntegrasInvalidas("zip_tamanho_ou_crc_divergente")
    return data


def _decodificar(data: bytes) -> str | None:
    """UTF-8 estrito (formato observado); falha não ? mascarada: o documento ? descartado."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


_CONECTIVOS = frozenset({"NO", "NA", "NOS", "NAS", "EM", "DO", "DA", "DOS", "DAS"})


def classe_tokens(sigla: str) -> tuple[str, ...]:
    """'AgInt no REsp' -> ('AGINT','RESP'); conectivos variam entre fontes e não distinguem graus."""
    return tuple(t for t in _sem_acento(sigla).split() if t not in _CONECTIVOS)


def _classe_da_integra(md: Mapping[str, Any]) -> tuple[tuple[str, ...], str] | None:
    """(tokens da classe composta, número) a partir de `recurso` + `processo` ('REsp 2066740')."""
    m = re.match(r"^\s*(.+?)\s+(\d+)\s*$", str(md.get("processo") or ""))
    if not m:
        return None
    return classe_tokens(f"{md.get('recurso') or ''} {m.group(1)}"), m.group(2)


_SESSAO = re.compile(r"acordam os Ministros d[ao] (.{3,40}?) do Superior Tribunal de Justi.a,\s+em Sess.o"
                     r"(?: Virtual)? de (\d{2}/\d{2}/\d{4})(?: a (\d{2}/\d{2}/\d{4}))?", re.I)


def julgamento_no_texto(texto: str) -> tuple[str, str, str] | None:
    """(órgão, início, fim ISO) da fórmula de abertura do acórdão; None se ausente ou repetida."""
    achados = _SESSAO.findall(texto[:3000])
    if len(achados) != 1:
        return None
    orgao, ini, fim = achados[0]
    iso = lambda d: f"{d[6:]}-{d[3:5]}-{d[:2]}"
    return _sem_acento(orgao), iso(ini), iso(fim or ini)


_ORGAOS = {"CE": "CORTE ESPECIAL", "S1": "PRIMEIRA SECAO", "S2": "SEGUNDA SECAO", "S3": "TERCEIRA SECAO"}


def _orgao(v: Any) -> str:
    o = _sem_acento(str(v or ""))
    return _ORGAOS.get(o, o)


def _data_iso(v: Any) -> str | None:
    d = re.sub(r"[^0-9]", "", str(v or ""))
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d[:2] in ("19", "20") else None


def _normal(t: str) -> str:
    t = re.sub(r"(?i)<br\s*/?>", " ", t)
    return re.sub(r"[^0-9A-Z]+", " ", _sem_acento(t)).strip()


_EMENTA_MIN = 120


def _ementa_no_texto(ementa: Any, texto_normal: str) -> bool:
    """O acórdão reproduz a própria ementa: o trecho inicial dela individualiza o julgamento."""
    e = _normal(str(ementa or ""))
    return len(e) >= _EMENTA_MIN and e[:400] in texto_normal


def _cadeia_compativel(meta: tuple[str, ...], espelho: tuple[str, ...]) -> bool:
    """Metadados trazem recurso externo e classe base; graus intermediários podem faltar."""
    if not meta or not espelho:
        return False
    if len(meta) == 1:
        return espelho == meta
    return espelho[-1] == meta[-1] and espelho[:len(meta) - 1] == meta[:-1]


def combinar(metadados_body: bytes, zip_body: bytes,
             espelhos_por_registro: Mapping[str, Iterable[tuple[str, str, str, str, str, str]]]) -> Resultado:
    """Une metadados e textos e vincula cada acórdão a um espelho do acervo.

    `espelhos_por_registro`: numeroRegistro -> (chave, siglaClasse, numeroProcesso,
    nomeOrgaoJulgador, dataDecisao, ementa) dos espelhos. Classe dos metadados ? parcial: o vínculo
    exige ainda órgão e data de julgamento do espelho dentro da sessão declarada no texto e a
    ementa do espelho reproduzida no texto (prova positiva do julgamento individual).
    O registro abriga vários acórdãos (REsp, AgInt no REsp, EDcl...): o vínculo exige registro,
    classe composta e número iguais. Um candidato: vínculo. Vários: ambíguo. Nenhum: descarte.
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
        if len(grupo) > 1 and all(g == grupo[0] for g in grupo):
            for _ in grupo[1:]:
                res.descartar("seq_duplicado_identico")
        if any(g != grupo[0] for g in grupo):  # mesmo Seq com dados diferentes: nenhum vale
            for _ in grupo:
                res.descartar("seq_repetido_divergente")
            continue
        md = grupo[0]
        tipo = _sem_acento(str(md.get("tipoDocumento") or ""))
        if tipo == "DECISAO":
            res.descartar("monocratica_fora_desta_versao")
            continue
        if tipo != "ACORDAO":
            res.descartar("tipo_documento_desconhecido")
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
    mapa = {r: list(v) for r, v in espelhos_por_registro.items()}  # Iterable consumível: materializa uma vez
    repetidas: dict[tuple, int] = {}
    for _, ident in candidatos:
        repetidas[ident] = repetidas.get(ident, 0) + 1
    for integra, ident in candidatos:
        registro, tokens, numero = ident
        prova = julgamento_no_texto(integra.texto)
        compat = [e for e in mapa.get(registro, ())
                  if _cadeia_compativel(tokens, classe_tokens(e[1] or ""))
                  and str(e[2] or "").strip().lstrip("0") == numero.lstrip("0")]
        if repetidas[ident] > 1:  # duas íntegras para a mesma identidade no dia: não escolhe
            res.ambiguas.append((integra, sorted({e[0] for e in compat})))
            continue
        if not compat:
            res.descartar("fora_do_recorte_ou_sem_espelho")
            continue
        if prova is None:  # sem órgão e sessão no texto não há prova do julgamento individual
            res.descartar("sem_prova_do_julgamento")
            continue
        orgao, ini, fim = prova
        texto_n = _normal(integra.texto)
        chaves = sorted({e[0] for e in compat
                         if _orgao(e[3]) == orgao and _data_iso(e[4]) and ini <= _data_iso(e[4]) <= fim
                         and _ementa_no_texto(e[5] if len(e) > 5 else None, texto_n)})
        if not chaves:
            res.descartar("julgamento_divergente_do_espelho")
        elif len(chaves) == 1:
            res.vinculadas.append((integra, chaves[0]))
        else:
            res.ambiguas.append((integra, chaves))
    return res
