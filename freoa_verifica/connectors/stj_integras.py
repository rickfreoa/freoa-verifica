"""Íntegras do STJ (CKAN: integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica).

Recurso diário aos pares: metadadosAAAAMMDD.json e textosAAAAMMDD.zip, este com um arquivo
`<SeqDocumento>.txt` por documento. Os metadados não trazem órgão julgador; o recorte se faz
pelo vínculo com espelho já presente no acervo (decisão 0044). Inteiro teor por declaração da
coleção oficial, nunca por comprimento (decisão 0038).

O vínculo não interpreta o texto da íntegra: exige identidade de metadados (registro, cadeia de classe,
número, data de publicação), unicidade dupla e, só como filtro negativo, a ementa do espelho no texto.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
import struct
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Mapping

from freoa_verifica.texto_resposta import interpretar
from freoa_verifica.transport import RespostaInvalida

MAX_ENTRADAS = 5000
MAX_DESCOMPACTADO = 200 * 1024 * 1024
MAX_POR_ENTRADA = 5 * 1024 * 1024
MAX_RAZAO = 100.0
MAX_DIRETORIO_CENTRAL = 2 * 1024 * 1024  # bytes; 5.000 nomes de `<seq>.txt` ocupam cerca de 0,4 MB
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
    descartes: dict[str, int] = field(default_factory=dict)  # por documento (item de metadados)
    orfaos: dict[str, int] = field(default_factory=dict)  # por texto que não vincula a documento ou espelho

    def descartar(self, motivo: str) -> None:
        self.descartes[motivo] = self.descartes.get(motivo, 0) + 1

    def orfao(self, motivo: str) -> None:
        self.orfaos[motivo] = self.orfaos.get(motivo, 0) + 1


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn").upper().strip()


def ler_metadados(body: bytes, content_type: str | None = None) -> list[dict[str, Any]]:
    """Metadados do dia. O corpo passa pela interpretação única (decisões 0061 a 0064) e só UTF-8 vale
    (decisão 0044, item 5); o JSON é lido sobre o texto, nunca sobre bytes (que aceitariam UTF-16/32)."""
    try:
        interp = interpretar(body, content_type)
    except RespostaInvalida as exc:
        raise IntegrasInvalidas(f"metadados_invalidos: {exc}") from exc
    if interp.codificacao not in ("utf-8", "utf-8-sig"):
        raise IntegrasInvalidas(f"metadados_nao_utf8: {interp.codificacao}")
    try:
        data = json.loads(interp.texto)
    except json.JSONDecodeError as exc:
        raise IntegrasInvalidas(f"metadados_invalidos: {exc}") from exc
    if not isinstance(data, list):
        raise IntegrasInvalidas("metadados_nao_lista")
    ruins = [i for i, d in enumerate(data) if not isinstance(d, dict)]
    if ruins:  # contrato da fonte mudou: indisponibilidade, nunca resultado vazio regular
        raise IntegrasInvalidas(f"metadados_item_nao_objeto: {ruins[:5]}")
    return data


class EntradaRecusada(Exception):
    """Entrada do ZIP recusada por divergência interna; o recurso segue e o motivo é contado."""


def ler_textos(raw: bytes) -> dict[str, tuple[str | None, str]]:
    """Textos aceitos do ZIP (ver `ler_textos_detalhado`); as entradas recusadas ficam de fora."""
    return ler_textos_detalhado(raw)[0]


_EOCD = b"PK\x05\x06"
_CENTRAL = b"PK\x01\x02"
_LOCAL = b"PK\x03\x04"
_DESCRITOR = b"PK\x07\x08"
_EOCD64 = b"PK\x06\x06"
_LOCALIZADOR64 = b"PK\x06\x07"
_SENTINELA32 = 0xFFFFFFFF
_SENTINELA16 = 0xFFFF


def _nao_suportado(sub: str) -> IntegrasInvalidas:
    return IntegrasInvalidas(f"zip_estrutura_nao_suportada:{sub}")


def _conferir_extra(extra: bytes) -> None:
    """Extra malformado ou com campo ZIP64 (id 0x0001) recusa o recurso: só a disposição estrita é aceita."""
    i = 0
    while i < len(extra):
        if i + 4 > len(extra):
            raise _nao_suportado("extra_invalido")
        ident, tam = struct.unpack("<HH", extra[i:i + 4])
        if i + 4 + tam > len(extra):
            raise _nao_suportado("extra_invalido")
        if ident == 0x0001:
            raise _nao_suportado("zip64")
        i += 4 + tam


def _descritor_conforme(depois: bytes, crc: int, csize: int, usize: int) -> int | None:
    """Comprimento do data descriptor (com assinatura: 16; sem: 12) que repete o diretório central, ou None."""
    alvo = (crc, csize, usize)
    if depois[:4] == _DESCRITOR and len(depois) >= 16 and struct.unpack("<III", depois[4:16]) == alvo:
        return 16
    if len(depois) >= 12 and struct.unpack("<III", depois[:12]) == alvo:
        return 12
    return None


def _validar_estrutura(raw: bytes) -> list[int]:
    """Aceita só a disposição estrita do ZIP e devolve os deslocamentos do diretório central, na ordem dele.

    Tudo é conferido sobre os bytes, antes de `ZipFile` (que aloca um ZipInfo por registro). Fora da disposição
    estrita o recurso inteiro é recusado (`zip_estrutura_nao_suportada:<sub>`), de modo que o percurso feito
    aqui e o do `zipfile` só podem ler o mesmo diretório:

    - EOCD nos últimos 22 bytes, sem comentário; nenhuma assinatura de EOCD64 nem de localizador ZIP64;
    - sem ZIP64: nenhuma sentinela (0xFFFF, 0xFFFFFFFF) nem extra 0x0001 no EOCD, no central ou no local;
    - disco único (campos de disco do EOCD e de cada registro central iguais a 0);
    - diretório central imediatamente antes do EOCD (deslocamento + tamanho == bytes antes do EOCD);
    - primeiro cabeçalho local no byte 0 e cada membro (cabeçalho local, nome, extra, dados, descritor se bit 3)
      começando onde o anterior terminou, o último terminando no diretório.

    Limites: MAX_ENTRADAS registros e MAX_DIRETORIO_CENTRAL bytes de diretório; contagem e tamanho declarados
    são reconciliados com os percorridos.
    """
    n = len(raw)
    if n < 22:
        raise IntegrasInvalidas("zip_invalido")
    if raw[n - 22:n - 18] != _EOCD or raw[n - 2:] != b"\x00\x00":
        if _EOCD in raw[max(n - 0xFFFF - 22, 0):]:  # comentário, rabo ou ZIP concatenado
            raise _nao_suportado("eocd_nao_final")
        raise IntegrasInvalidas("zip_invalido")
    _, disco, disco_cd, no_disco, total, tam_cd, off_cd, _ = struct.unpack("<4sHHHHIIH", raw[n - 22:])
    if _SENTINELA16 in (disco, disco_cd, no_disco, total) or _SENTINELA32 in (tam_cd, off_cd):
        raise _nao_suportado("zip64")
    if n >= 42 and raw[n - 42:n - 38] == _LOCALIZADOR64:
        raise _nao_suportado("zip64")
    if disco or disco_cd or no_disco != total:
        raise _nao_suportado("multidisco")
    if total > MAX_ENTRADAS:
        raise IntegrasInvalidas("zip_entradas_excedidas")
    if tam_cd > MAX_DIRETORIO_CENTRAL:
        raise IntegrasInvalidas("zip_diretorio_excedido")
    if off_cd + tam_cd != n - 22:
        raise _nao_suportado("diretorio_nao_adjacente_ao_eocd")
    dados = raw[off_cd:n - 22]
    if _EOCD64 in raw[off_cd:] or _LOCALIZADOR64 in raw[off_cd:]:
        raise _nao_suportado("zip64")
    registros: list[tuple[int, int, int, int, int]] = []  # (deslocamento, flags, crc, csize, usize)
    pos = 0
    while pos < tam_cd:
        if len(registros) >= MAX_ENTRADAS:
            raise IntegrasInvalidas("zip_entradas_excedidas")
        cab = dados[pos:pos + 46]
        if len(cab) != 46 or cab[:4] != _CENTRAL:
            raise IntegrasInvalidas("zip_invalido")
        (_, _, _, flags, _, _, _, crc, csize, usize, n_nome, n_extra, n_com, disco_ini, _, _, desloc) = \
            struct.unpack("<4sHHHHHHIIIHHHHHII", cab)
        fim = pos + 46 + n_nome + n_extra + n_com
        if fim > tam_cd:
            raise IntegrasInvalidas("zip_invalido")
        if _SENTINELA32 in (csize, usize, desloc) or disco_ini == _SENTINELA16:
            raise _nao_suportado("zip64")
        if disco_ini:
            raise _nao_suportado("multidisco")
        _conferir_extra(dados[pos + 46 + n_nome:pos + 46 + n_nome + n_extra])
        registros.append((desloc, flags, crc, csize, usize))
        pos = fim
    if len(registros) != total:
        raise IntegrasInvalidas("zip_diretorio_divergente")
    pos = 0
    for desloc, flags, crc, csize, usize in sorted(registros):
        if desloc != pos:
            raise _nao_suportado("membros_nao_contiguos")
        cab = raw[pos:pos + 30]
        if len(cab) != 30 or cab[:4] != _LOCAL:
            raise IntegrasInvalidas("zip_cabecalho_local")
        csize_l, usize_l, n_nome, n_extra = struct.unpack("<IIHH", cab[18:30])
        if _SENTINELA32 in (csize_l, usize_l):
            raise _nao_suportado("zip64")
        _conferir_extra(raw[pos + 30 + n_nome:pos + 30 + n_nome + n_extra])
        pos += 30 + n_nome + n_extra + csize
        if flags & 0x8:
            depois = raw[pos:pos + 16]
            pos += _descritor_conforme(depois, crc, csize, usize) or (16 if depois[:4] == _DESCRITOR else 12)
    if pos != off_cd:
        raise _nao_suportado("membros_nao_contiguos")
    return [r[0] for r in registros]


def ler_textos_detalhado(raw: bytes) -> tuple[dict[str, tuple[str | None, str]], dict[str, str]]:
    """(textos, recusadas). textos: SeqDocumento -> (texto ou None se não UTF-8, sha256 dos bytes);
    recusadas: SeqDocumento -> motivo, para entrada cujo cabeçalho local ou data descriptor diverge do
    diretório central. Estrutura fora da disposição estrita, limites de entradas, tamanho, razão e nomes
    recusam o recurso inteiro."""
    deslocamentos = _validar_estrutura(raw)  # antes de ZipFile: ele aloca um ZipInfo por registro
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise IntegrasInvalidas("zip_invalido") from exc
    with zf:
        infos = zf.infolist()
        if [i.header_offset for i in infos] != deslocamentos:
            raise IntegrasInvalidas("zip_diretorio_divergente")
        total = lidos = 0
        out: dict[str, tuple[str | None, str]] = {}
        recusadas: dict[str, str] = {}
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
            seq = m.group(1)
            if seq in out or seq in recusadas:
                raise IntegrasInvalidas("zip_seq_repetido")
            try:
                data = _ler_bruto(zf, info)
            except EntradaRecusada as exc:
                recusadas[seq] = str(exc)
                continue
            if len(data) > MAX_POR_ENTRADA:
                raise IntegrasInvalidas("zip_entrada_grande")
            lidos += len(data)
            if lidos > MAX_DESCOMPACTADO:
                raise IntegrasInvalidas("zip_descompactado_excedido")
            out[seq] = (_decodificar(data), hashlib.sha256(data).hexdigest())
        return out, recusadas


def _conferir_local(info: zipfile.ZipInfo, local: bytes) -> bool:
    """Confronta método, flags, CRC e tamanhos do cabeçalho local com o diretório central.

    Devolve se há data descriptor. Divergência levanta EntradaRecusada com o motivo. Sem ZIP64 (a estrutura
    estrita o exclui), a sentinela já recusou o recurso antes.
    """
    flags, metodo, crc, comp, tam = struct.unpack("<HH4xIII", local[6:26])
    if flags != info.flag_bits:
        raise EntradaRecusada("zip_local_flags_divergente")
    if metodo != info.compress_type:
        raise EntradaRecusada("zip_local_metodo_divergente")
    descritor = bool(flags & 0x8)  # com descritor, CRC e tamanhos do local podem vir zerados

    def igual(valor: int, central: int) -> bool:
        return valor == central or (descritor and valor == 0)

    if not (igual(comp, info.compress_size) and igual(tam, info.file_size)):
        raise EntradaRecusada("zip_local_tamanho_divergente")
    if not igual(crc, info.CRC):
        raise EntradaRecusada("zip_local_crc_divergente")
    return descritor


def _conferir_descritor(info: zipfile.ZipInfo, depois: bytes) -> None:
    """O data descriptor (com ou sem assinatura, 4 bytes por campo) deve repetir o diretório central."""
    if _descritor_conforme(depois, info.CRC, info.compress_size, info.file_size) is None:
        raise EntradaRecusada("zip_descriptor_divergente")


def _ler_bruto(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    """Lê o fluxo comprimido pelo cabeçalho local e o descompacta sem confiar em file_size/CRC declarados."""
    import zlib

    fp = zf.fp
    fp.seek(info.header_offset)
    local = fp.read(30)
    if len(local) != 30 or local[:4] != b"PK\x03\x04":
        raise IntegrasInvalidas("zip_cabecalho_local")
    n_nome, n_extra = struct.unpack("<HH", local[26:30])
    if fp.read(n_nome) != info.orig_filename.encode("cp437" if not info.flag_bits & 0x800 else "utf-8"):
        raise IntegrasInvalidas("zip_nome_divergente")
    if len(fp.read(n_extra)) != n_extra:
        raise IntegrasInvalidas("zip_truncado")
    descritor = _conferir_local(info, local)
    if info.compress_size > MAX_POR_ENTRADA:
        raise IntegrasInvalidas("zip_entrada_grande")
    comp = fp.read(info.compress_size)
    if len(comp) != info.compress_size:
        raise IntegrasInvalidas("zip_truncado")
    if descritor:
        _conferir_descritor(info, fp.read(16))
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
    """UTF-8 estrito, sem BOM alternativo (decisão 0044, item 5); falha não é mascarada: o documento é descartado."""
    try:
        return data.decode("utf-8", errors="strict")
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


_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_DJE = re.compile(r"DJEN?[ ]+DATA:[ ]*([0-9]{2})/([0-9]{2})/([0-9]{4})")


def _calendario(ano: str, mes: str, dia: str) -> str | None:
    """Data pelo calendário (31/02 e 00/00 não existem) -> ISO."""
    try:
        return date(int(ano), int(mes), int(dia)).isoformat()
    except ValueError:
        return None


def _data_iso(v: Any) -> str | None:
    """`dataPublicacao` dos metadados: só AAAA-MM-DD, válida no calendário."""
    m = _ISO.fullmatch(v.strip()) if isinstance(v, str) else None
    return _calendario(m[1], m[2], m[3]) if m else None


def _publicacao_do_espelho(v: Any) -> str | None:
    """`dataPublicacao` do espelho: AAAA-MM-DD ou `DJE`/`DJEN` + `DATA:DD/MM/AAAA` (formato do espelho do STJ,
    com espaços de preenchimento depois da sigla), válidos no calendário. Outro valor é ilegível (None)."""
    if not isinstance(v, str):
        return None
    m = _DJE.fullmatch(v.strip())
    return _calendario(m[3], m[2], m[1]) if m else _data_iso(v)


def _normal(texto: str) -> str:
    """Normalização única, idêntica para o texto e para a ementa do espelho.

    `<...>` sem `<`/`>` internos vira espaço; entidades HTML são decodificadas uma vez; invisíveis (categoria Cf)
    e diacríticos saem (NFKD); casefold; espaços colapsados. É deliberadamente fraca: serve só ao filtro
    negativo da ementa, em que uma diferença de normalização só pode produzir falso negativo (perde vínculo);
    nunca cria vínculo, que depende dos metadados.
    """
    t = html.unescape(re.sub(r"<[^<>]*>", " ", texto))
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if unicodedata.category(c) not in ("Mn", "Cf"))
    return " ".join(t.casefold().split())


_EMENTA_MIN = 120


def _ementa_no_texto(ementa: Any, texto_normal: str) -> bool:
    """Filtro só negativo: a ementa do espelho (ao menos 120 caracteres normalizados; os primeiros 400 são
    conferidos) tem de ocorrer no texto normalizado. Condição necessária, nunca suficiente para vincular."""
    e = _normal(str(ementa or ""))
    return len(e) >= _EMENTA_MIN and e[:400] in texto_normal


_MOTIVOS_SEM_CANDIDATO = ("classe_nao_identica", "numero_divergente", "data_publicacao_espelho_ilegivel",
                          "data_publicacao_divergente")


def _candidatos(espelhos: list[tuple], tokens: tuple[str, ...], numero: str,
                publicacao: str) -> tuple[list[tuple], str]:
    """(espelhos candidatos, motivo se nenhum). Candidato: cadeia de classe idêntica, número igual e data de
    publicação do espelho (normalizada) igual à dos metadados. O motivo é o do espelho que foi mais longe."""
    achados: list[tuple] = []
    fundo = 0
    for esp in espelhos:
        if classe_tokens(esp[1] or "") != tokens:
            continue
        if str(esp[2] or "").strip().lstrip("0") != numero.lstrip("0"):
            fundo = max(fundo, 1)
            continue
        pub = _publicacao_do_espelho(esp[6])
        if pub is None:
            fundo = max(fundo, 2)
        elif pub != publicacao:
            fundo = max(fundo, 3)
        else:
            achados.append(esp)
    return achados, _MOTIVOS_SEM_CANDIDATO[fundo]


def combinar(metadados_body: bytes, zip_body: bytes,
             espelhos_por_registro: Mapping[str, Iterable[tuple[str, str, str, str, str, str, str]]],
             metadados_content_type: str | None = None) -> Resultado:
    """Une metadados e textos e vincula cada acórdão a um espelho do acervo, sem interpretar o texto.

    `espelhos_por_registro`: numeroRegistro -> tuplas (chave, siglaClasse, numeroProcesso, nomeOrgaoJulgador,
    dataDecisao, ementa, dataPublicacao) dos espelhos, `dataPublicacao` como no espelho (`DJEN       DATA:08/10/2026`
    ou ISO). O órgão vem sempre do espelho (carregado pela chave); `dataDecisao` não entra no vínculo.

    Candidato = espelho com o mesmo numeroRegistro, cadeia de classe idêntica (recurso dos metadados + classe de
    `processo` == classe do espelho, na ordem), número igual e data de publicação igual à dos metadados.
    Unicidade dupla: (i) exatamente um candidato no acervo; (ii) exatamente um acórdão nos metadados do dia com
    aquele registro (qualquer classe). Mais de um candidato, ou falha de (ii): `ambiguous`, sem escolha. Sem
    candidato, o motivo é específico. Com um candidato, a ementa do espelho tem de ocorrer no texto
    (filtro negativo); o texto não é lido para mais nada.
    """
    textos, recusadas = ler_textos_detalhado(zip_body)
    res = Resultado()
    metas = ler_metadados(metadados_body, metadados_content_type)
    por_seq: dict[str, list[dict[str, Any]]] = {}
    acordaos_do_registro: dict[str, set[str]] = {}  # itens distintos (duplicata idêntica conta uma vez)
    for md in metas:
        por_seq.setdefault(str(md.get("SeqDocumento") or "").strip(), []).append(md)
        if _sem_acento(str(md.get("tipoDocumento") or "")) == "ACORDAO" and isinstance(md.get("numeroRegistro"), str):
            acordaos_do_registro.setdefault(md["numeroRegistro"].strip(), set()).add(
                json.dumps(md, sort_keys=True, ensure_ascii=False))
    for seq in sorted({*textos, *recusadas} - set(por_seq)):  # texto sem metadado nunca vincula, mas é contado
        res.orfao("texto_sem_metadado" if seq in textos else recusadas[seq])
    zip_contado: set[str] = set()
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
        if seq in recusadas:  # entrada do ZIP recusada por divergência interna: o motivo é o do ZIP
            res.descartar(recusadas[seq])
            zip_contado.add(seq)
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
        publicacao = _data_iso(md.get("dataPublicacao"))
        if publicacao is None:
            res.descartar("data_publicacao_metadado_ilegivel")
            continue
        integra = Integra(
            seq=seq, numero_registro=registro, processo=str(md.get("processo") or "").strip(),
            tipo="acordao", data_publicacao=md.get("dataPublicacao"), ministro=md.get("NM_MINISTRO"),
            texto=texto, sha256_texto=sha_bytes, metadados=dict(md))
        candidatos.append((integra, (registro, *classe, publicacao)))
    for seq in sorted(set(recusadas) & set(por_seq) - zip_contado):
        res.orfao(recusadas[seq])  # saída antecipada por metadado (tipo, registro...) não esconde a recusa do ZIP
    mapa = {r: list(v) for r, v in espelhos_por_registro.items()}  # Iterable consumível: materializa uma vez
    for integra, (registro, tokens, numero, publicacao) in candidatos:
        espelhos = mapa.get(registro, [])
        if not espelhos:
            res.descartar("fora_do_recorte_ou_sem_espelho")
            res.orfao("texto_sem_espelho")
            continue
        achados, motivo = _candidatos(espelhos, tokens, numero, publicacao)
        if len(acordaos_do_registro[registro]) > 1 or len(achados) > 1:  # unicidade dupla: nunca escolhe
            res.ambiguas.append((integra, sorted(e[0] for e in achados)))
        elif not achados:
            res.descartar(motivo)
        elif not _ementa_no_texto(achados[0][5], _normal(integra.texto)):
            res.descartar("ementa_ausente_no_texto")
        else:
            res.vinculadas.append((integra, achados[0][0]))
    return res
