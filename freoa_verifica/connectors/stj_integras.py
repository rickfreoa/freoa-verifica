"""Íntegras do STJ (CKAN: integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica).

Recurso diário aos pares: metadadosAAAAMMDD.json e textosAAAAMMDD.zip, este com um arquivo
`<SeqDocumento>.txt` por documento. Os metadados não trazem órgão julgador; o recorte se faz
pelo vínculo com espelho já presente no acervo (decisão 0044). Inteiro teor por declaração da
coleção oficial, nunca por comprimento (decisão 0038).
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
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
    import unicodedata

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


@dataclass(frozen=True)
class _RegistroCentral:
    """Campos de 32/16 bits de um registro do diretório central, como estão no arquivo (com as sentinelas)."""

    flags: int
    usize: int
    csize: int
    disco: int
    deslocamento: int
    nome: bytes
    extra: bytes


_EOCD = b"PK\x05\x06"
_CENTRAL = b"PK\x01\x02"


def _percorrer_diretorio_central(raw: bytes) -> list[_RegistroCentral]:
    """Percorre o diretório central efetivo antes de `ZipFile` (que aloca um ZipInfo por registro).

    Reproduz a localização do `zipfile` (EOCD no fim ou por busca nos últimos 64 KiB; EOCD64 imediatamente
    antes do localizador, que fica imediatamente antes do EOCD) e o seu laço, que anda por `size_cd` bytes e
    ignora a contagem declarada. O laço aqui é limitado a MAX_ENTRADAS+1 registros e a MAX_DIRETORIO_CENTRAL
    bytes. Contagem e tamanho declarados são reconciliados com os percorridos; divergência recusa o recurso.
    """
    import struct

    n = len(raw)
    if n >= 22 and raw[n - 22:n - 18] == _EOCD and raw[n - 2:] == b"\x00\x00":
        pos = n - 22
    else:
        ini = max(n - 0xFFFF - 22, 0)
        achado = raw[ini:].rfind(_EOCD)
        if achado < 0 or ini + achado + 22 > n:
            raise IntegrasInvalidas("zip_invalido")
        pos = ini + achado
    _, _, _, _, total_decl, tam_cd, desloc_cd, _ = struct.unpack("<4sHHHHIIH", raw[pos:pos + 22])
    zip64 = False
    loc = raw[pos - 20:pos] if pos >= 20 else b""
    if len(loc) == 20 and loc[:4] == b"PK\x06\x07":
        disco, _, discos = struct.unpack("<4xIQI", loc)
        if disco != 0 or discos > 1:
            raise IntegrasInvalidas("zip_invalido")
        e64 = raw[pos - 76:pos - 20] if pos >= 76 else b""
        if len(e64) == 56 and e64[:4] == b"PK\x06\x06":
            _, _, _, _, _, _, _, total_decl, tam_cd, desloc_cd = struct.unpack("<4sQHHIIQQQQ", e64)
            zip64 = True
    if total_decl > MAX_ENTRADAS:
        raise IntegrasInvalidas("zip_entradas_excedidas")
    if tam_cd > MAX_DIRETORIO_CENTRAL:
        raise IntegrasInvalidas("zip_diretorio_excedido")
    concat = pos - tam_cd - desloc_cd - (76 if zip64 else 0)
    inicio = desloc_cd + concat
    if inicio < 0:
        raise IntegrasInvalidas("zip_invalido")
    dados = raw[inicio:inicio + tam_cd]
    registros: list[_RegistroCentral] = []
    total = 0
    while total < tam_cd:
        if len(registros) >= MAX_ENTRADAS:
            raise IntegrasInvalidas("zip_entradas_excedidas")
        cab = dados[total:total + 46]
        if len(cab) != 46 or cab[:4] != _CENTRAL:
            raise IntegrasInvalidas("zip_invalido")
        (_, _, _, flags, _, _, _, _, csize, usize, n_nome, n_extra, n_com, disco, _, _, desloc) = \
            struct.unpack("<4sHHHHHHIIIHHHHHII", cab)
        fim = total + 46 + n_nome + n_extra + n_com
        if fim > len(dados):
            raise IntegrasInvalidas("zip_invalido")
        registros.append(_RegistroCentral(
            flags, usize, csize, disco, desloc, dados[total + 46:total + 46 + n_nome],
            dados[total + 46 + n_nome:total + 46 + n_nome + n_extra]))
        total = fim
    if total != tam_cd or len(registros) != total_decl:
        raise IntegrasInvalidas("zip_diretorio_divergente")
    return registros


def ler_textos_detalhado(raw: bytes) -> tuple[dict[str, tuple[str | None, str]], dict[str, str]]:
    """(textos, recusadas). textos: SeqDocumento -> (texto ou None se não UTF-8, sha256 dos bytes);
    recusadas: SeqDocumento -> motivo, para entrada cujo cabeçalho local, data descriptor ou extra ZIP64
    diverge do diretório central. Limites de entradas, tamanho, razão e nomes recusam o recurso inteiro."""
    registros = _percorrer_diretorio_central(raw)  # antes de ZipFile: ele aloca um ZipInfo por registro
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise IntegrasInvalidas("zip_invalido") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) != len(registros):
            raise IntegrasInvalidas("zip_diretorio_divergente")
        total = lidos = 0
        out: dict[str, tuple[str | None, str]] = {}
        recusadas: dict[str, str] = {}
        for info, registro in zip(infos, registros):
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
                _conferir_zip64_central(registro)
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


_ZIP64_SENTINELA = 0xFFFFFFFF
_ASSINATURA_DESCRITOR = b"PK\x07\x08"


def _extra_local(extra: bytes, motivo: str = "zip_local_extra_invalido") -> dict[int, bytes]:
    """Campos de um extra (id -> dados); extra malformado ou com id repetido recusa a entrada."""
    import struct

    campos: dict[int, bytes] = {}
    i = 0
    while i < len(extra):
        if i + 4 > len(extra):
            raise EntradaRecusada(motivo)
        ident, tam = struct.unpack("<HH", extra[i:i + 4])
        if i + 4 + tam > len(extra) or ident in campos:
            raise EntradaRecusada(motivo)
        campos[ident] = extra[i + 4:i + 4 + tam]
        i += 4 + tam
    return campos


def _conferir_zip64_central(reg: _RegistroCentral) -> None:
    """Extra ZIP64 do diretório central exatamente como a APPNOTE 4.5.3 manda.

    O extra contém só os campos cujo valor comum é a sentinela (0xFFFFFFFF; 0xFFFF para disco), na ordem
    fixa: tamanho descompactado (8 bytes), compactado (8), deslocamento (8) e disco (4). O comprimento tem
    de ser exatamente o das sentinelas presentes; extra ZIP64 sem sentinela, curto, longo ou repetido
    recusa a entrada. `zipfile` consome o extra só quando há sentinela e ignora o que sobra.
    """
    z64 = _extra_local(reg.extra, "zip_zip64_divergente").get(0x0001)
    esperado = 8 * sum(v == _ZIP64_SENTINELA for v in (reg.usize, reg.csize, reg.deslocamento))
    esperado += 4 * (reg.disco == 0xFFFF)
    if z64 is None:
        return  # sentinela sem extra, ou extra curto: o `zipfile` recusa o arquivo (zip_invalido) antes de chegar aqui
    if esperado == 0 or len(z64) != esperado:  # extra ZIP64 sem nenhuma sentinela também diverge
        raise EntradaRecusada("zip_zip64_divergente")


def _conferir_local(info: zipfile.ZipInfo, local: bytes, extra: bytes) -> tuple[bool, bool]:
    """Confronta método, flags, CRC, tamanhos e extra ZIP64 do cabeçalho local com o diretório central.

    Devolve (tem_descritor, zip64). Divergência levanta EntradaRecusada com o motivo.
    """
    import struct

    flags, metodo, crc, comp, tam = struct.unpack("<HH4xIII", local[6:26])
    if flags != info.flag_bits:
        raise EntradaRecusada("zip_local_flags_divergente")
    if metodo != info.compress_type:
        raise EntradaRecusada("zip_local_metodo_divergente")
    descritor = bool(flags & 0x8)  # com descritor, CRC e tamanhos do local podem vir zerados

    def igual(valor: int, central: int) -> bool:
        return valor == central or (descritor and valor == 0)

    z64 = _extra_local(extra).get(0x0001)
    if z64 is not None:  # no local o extra ZIP64 traz tamanho original e comprimido, nesta ordem
        if len(z64) != 16:
            raise EntradaRecusada("zip_zip64_divergente")
        z_tam, z_comp = struct.unpack("<QQ", z64)
        if not (igual(z_tam, info.file_size) and igual(z_comp, info.compress_size)):
            raise EntradaRecusada("zip_zip64_divergente")
        # com extra, os campos de 32 bits trazem a sentinela (ou o valor real, igual ao central)
        if not all(v == _ZIP64_SENTINELA or igual(v, c) for v, c in ((comp, info.compress_size), (tam, info.file_size))):
            raise EntradaRecusada("zip_local_tamanho_divergente")
    elif not (igual(comp, info.compress_size) and igual(tam, info.file_size)):
        # inclui a sentinela sem extra: o tamanho real seria desconhecido
        raise EntradaRecusada("zip_zip64_divergente" if _ZIP64_SENTINELA in (comp, tam) else "zip_local_tamanho_divergente")
    if not igual(crc, info.CRC):
        raise EntradaRecusada("zip_local_crc_divergente")
    return descritor, z64 is not None


def _conferir_descritor(info: zipfile.ZipInfo, depois: bytes, zip64: bool) -> None:
    """O data descriptor (com ou sem assinatura, 4 ou 8 bytes por tamanho) deve repetir o diretório central."""
    import struct

    largura = 8 if zip64 else 4
    formato = "<I" + ("QQ" if largura == 8 else "II")
    tamanho = struct.calcsize(formato)
    alvo = (info.CRC, info.compress_size, info.file_size)
    candidatos = [depois[4:4 + tamanho]] if depois[:4] == _ASSINATURA_DESCRITOR else []
    candidatos.append(depois[:tamanho])
    for c in candidatos:
        if len(c) == tamanho and struct.unpack(formato, c) == alvo:
            return
    raise EntradaRecusada("zip_descriptor_divergente")


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
    extra = fp.read(n_extra)
    if len(extra) != n_extra:
        raise IntegrasInvalidas("zip_truncado")
    descritor, zip64 = _conferir_local(info, local, extra)
    if info.compress_size > MAX_POR_ENTRADA:
        raise IntegrasInvalidas("zip_entrada_grande")
    comp = fp.read(info.compress_size)
    if len(comp) != info.compress_size:
        raise IntegrasInvalidas("zip_truncado")
    if descritor:
        _conferir_descritor(info, fp.read(24), zip64)
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


_FORMULA = re.compile(r"acordam os Ministros d[ao] (.{3,40}?) do Superior Tribunal de Justi.a,\s+em Sess.o"
                      r"(?: Virtual)? de (\d{2}/\d{2}/\d{4})(?!\d)", re.I)
_FIM_DO_INTERVALO = re.compile(r"\s+a\s+(\d{2}/\d{2}/\d{4})(?!\d)", re.I)
_INTERVALO_ABERTO = re.compile(r"\s*(?:a|à|até)\b|[\s,;.)]*(?:a|à|até)\s*\d", re.I)
_TERMINADOR = re.compile(r"[ ]*(?:\Z|[.,;)\n])")
_ABERTURA_MAX = 3000
_BLOCO = re.compile(r"</?(?:br|p|div|li|tr|h[1-6])\b[^<>]*>", re.I)
_MARCACAO = re.compile(r"<!--.*?-->|</?[A-Za-z][^<>]*>|<[!?][^<>]*>", re.S)
_INVISIVEIS = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))


def visao_textual(texto: str) -> str:
    """Texto sem a marcação da fonte, só para ler a estrutura; o hash da prova é sempre dos bytes brutos.

    Só tags de bloco (`br`, `p`, `div`, `li`, `tr`, `h1` a `h6`) viram quebra de linha. Qualquer outra tag
    (`span`, `b`, `i`, `em`, `font`, `a`... e as não listadas) é removida SEM inserir espaço, de modo que
    `RELAT<span>Ó</span>RIO` seja uma palavra só. Entidades são decodificadas DEPOIS da remoção das tags e o
    resultado é texto: um `&lt;br&gt;` vira os caracteres `<br>` e nunca é reinterpretado como marcação.
    Espaços Unicode e invisíveis são normalizados.
    """
    t = _MARCACAO.sub("", texto) if "<!--" in texto else texto
    t = _BLOCO.sub("\n", t)
    t = _MARCACAO.sub("", t)
    t = html.unescape(t).translate(_INVISIVEIS)
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[^\S\n]+", " ", t)
    t = re.sub(r" ?\n[ \n]*", "\n", t)
    return t.strip()


_MARCA_EMENTA = re.compile(r"EMENTA[ ]*[:.]?")
_TITULO_DE_FECHO = re.compile(r"(?:RELATORIO|VOTO|ACORDAO|DECISAO|PARECER)[ ]*[:.]?")
_TITULO_COM_TEXTO = re.compile(r"(?:RELATORIO|VOTO|ACORDAO|DECISAO|PARECER)\b")


def _estrutura(texto: str) -> tuple[str, str | None] | None:
    """(abertura, ementa própria) na visão textual; None sem marcador EMENTA dentro do limite da abertura.

    Método de prova positiva: a ementa própria só existe se (1) há um marcador EMENTA sozinho na linha dentro
    dos primeiros 3.000 caracteres; (2) o bloco que o segue termina num título canônico (RELATÓRIO, VOTO,
    ACÓRDÃO, DECISÃO, PARECER) sozinho na sua linha; (3) no bloco não há outro marcador EMENTA nem linha que
    comece por título canônico seguido de texto; (4) não resta `<` nem `>` no bloco. Qualquer outra
    configuração devolve a abertura com ementa None (`sem_prova_do_julgamento`).
    """
    linhas = visao_textual(texto).split("\n")
    pos = 0
    ini = None
    for i, linha in enumerate(linhas):
        if _MARCA_EMENTA.fullmatch(_sem_acento(linha)):
            ini = i
            break
        pos += len(linha) + 1
    if ini is None or pos > _ABERTURA_MAX:
        return None
    abertura = "\n".join(linhas[:ini])
    bloco: list[str] = []
    for linha in linhas[ini + 1:]:
        d = _sem_acento(linha)
        if _TITULO_DE_FECHO.fullmatch(d):
            corpo = "\n".join(bloco)
            return abertura, (None if "<" in corpo or ">" in corpo else corpo)
        if _MARCA_EMENTA.fullmatch(d) or _TITULO_COM_TEXTO.match(d):
            return abertura, None
        bloco.append(linha)
    return abertura, None


def abertura_do_texto(texto: str) -> str | None:
    """Trecho (visão textual) que antecede o marcador EMENTA; None sem marcador ou além do limite.

    A fórmula só vale se estiver nesse trecho: citação de outro acórdão no corpo não é a abertura.
    """
    est = _estrutura(texto)
    return est[0] if est else None


def ementa_propria(texto: str) -> str | None:
    """Bloco da ementa do próprio acórdão (visão textual), ou None se a prova positiva não se completa."""
    est = _estrutura(texto)
    return est[1] if est else None


def _data_br(d: str) -> str | None:
    """dd/mm/aaaa pelo calendário (31/02 e 00/00 não existem) -> ISO."""
    try:
        return date(int(d[6:]), int(d[3:5]), int(d[:2])).isoformat()
    except ValueError:
        return None


def julgamento_no_texto(texto: str) -> tuple[str, str, str] | None:
    """(órgão, início, fim ISO) da fórmula de abertura do acórdão, lida na visão textual.

    Prova positiva: a data da sessão (ou o intervalo "de X a Y" completo) é seguida, após espaços, de um
    terminador explícito (vírgula, ponto, ponto e vírgula, parêntese, quebra de linha ou fim da fórmula).
    Resíduo de marcação, conectivo parcial ("a", "até" sem data), data inexistente no calendário, fim anterior
    ao início ou qualquer texto não reconhecido entre a data e o terminador devolve None.
    """
    abertura = abertura_do_texto(texto)
    if abertura is None:
        return None
    achados = list(_FORMULA.finditer(abertura))
    if len(achados) != 1:
        return None
    m = achados[0]
    ini = _data_br(m.group(2))
    if ini is None:
        return None
    resto = abertura[m.end():]
    fim_m = _FIM_DO_INTERVALO.match(resto)
    if fim_m:
        fim = _data_br(fim_m.group(1))
        if fim is None or fim < ini:
            return None
        resto = resto[fim_m.end():]
    elif _INTERVALO_ABERTO.match(resto):  # "de X a" sem data final válida: não recua para o dia X
        return None
    else:
        fim = ini
    if not _TERMINADOR.match(resto):
        return None
    return _sem_acento(m.group(1)), ini, fim


_ORGAOS = {"CE": "CORTE ESPECIAL", "S1": "PRIMEIRA SECAO", "S2": "SEGUNDA SECAO", "S3": "TERCEIRA SECAO"}


def _orgao(v: Any) -> str:
    o = _sem_acento(str(v or ""))
    return _ORGAOS.get(o, o)


def _data_iso(v: Any) -> str | None:
    d = re.sub(r"[^0-9]", "", str(v or ""))
    if len(d) != 8 or d[:2] not in ("19", "20"):
        return None
    return _data_br(f"{d[6:8]}/{d[4:6]}/{d[:4]}")


def _alfanumerico(visao: str) -> str:
    return re.sub(r"[^0-9A-Z]+", " ", _sem_acento(visao)).strip()


def _normal(t: str) -> str:
    return _alfanumerico(visao_textual(t))


_EMENTA_MIN = 120


def _ementa_no_texto(ementa: Any, ementa_propria_normal: str | None) -> bool:
    """O bloco da ementa do próprio acórdão reproduz a do espelho (trecho inicial, ao menos 120 caracteres).

    Só o bloco delimitado vale: a ementa do espelho citada como precedente em outro ponto do texto não prova
    o julgamento. Sem bloco delimitado (None) não há prova.
    """
    e = _normal(str(ementa or ""))
    return ementa_propria_normal is not None and len(e) >= _EMENTA_MIN and e[:400] in ementa_propria_normal


def _cadeia_compativel(meta: tuple[str, ...], espelho: tuple[str, ...]) -> bool:
    """Metadados trazem recurso externo e classe base; graus intermediários podem faltar."""
    if not meta or not espelho:
        return False
    if len(meta) == 1:
        return espelho == meta
    return espelho[-1] == meta[-1] and espelho[:len(meta) - 1] == meta[:-1]


def combinar(metadados_body: bytes, zip_body: bytes,
             espelhos_por_registro: Mapping[str, Iterable[tuple[str, str, str, str, str, str]]],
             metadados_content_type: str | None = None) -> Resultado:
    """Une metadados e textos e vincula cada acórdão a um espelho do acervo.

    `espelhos_por_registro`: numeroRegistro -> (chave, siglaClasse, numeroProcesso,
    nomeOrgaoJulgador, dataDecisao, ementa) dos espelhos. Classe dos metadados é parcial: o vínculo
    exige ainda órgão e data de julgamento do espelho dentro da sessão declarada no texto e a
    ementa do espelho reproduzida no texto (prova positiva do julgamento individual).
    O registro abriga vários acórdãos (REsp, AgInt no REsp, EDcl...): o vínculo exige registro,
    classe composta e número iguais. Um candidato: vínculo. Vários: ambíguo. Nenhum: descarte.
    """
    textos, recusadas = ler_textos_detalhado(zip_body)
    res = Resultado()
    metas = ler_metadados(metadados_body, metadados_content_type)
    por_seq: dict[str, list[dict[str, Any]]] = {}
    for md in metas:
        por_seq.setdefault(str(md.get("SeqDocumento") or "").strip(), []).append(md)
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
        integra = Integra(
            seq=seq, numero_registro=registro, processo=str(md.get("processo") or "").strip(),
            tipo="acordao", data_publicacao=md.get("dataPublicacao"), ministro=md.get("NM_MINISTRO"),
            texto=texto, sha256_texto=sha_bytes, metadados=dict(md))
        candidatos.append((integra, (registro, *classe)))
    for seq in sorted(set(recusadas) & set(por_seq) - zip_contado):
        res.orfao(recusadas[seq])  # saída antecipada por metadado (tipo, registro...) não esconde a recusa do ZIP
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
            res.orfao("texto_sem_espelho")
            continue
        if prova is None:  # sem órgão e sessão no texto não há prova do julgamento individual
            res.descartar("sem_prova_do_julgamento")
            continue
        orgao, ini, fim = prova
        bloco = ementa_propria(integra.texto)
        if bloco is None:  # ementa própria não delimitada (sem título seguinte): não há como confrontar
            res.descartar("sem_prova_do_julgamento")
            continue
        texto_n = _alfanumerico(bloco)  # o bloco já é visão textual: não se lê duas vezes
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
