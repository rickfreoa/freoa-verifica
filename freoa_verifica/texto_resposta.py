"""Interpretação textual única do corpo de uma resposta HTTP (decisões 0061 a 0064).

Detecção de desafio (`connectors.challenge`, `transport._desafio_na_resposta`) e leitura de sucesso pelos
conectores usam esta função. Antes de tudo, a validação do Content-Type (0064). Ordem: BOM → parâmetro `charset`
do Content-Type (media type, RFC 9110 §8.3.1)
→ HTML: "prescan a byte stream to determine its encoding" (WHATWG HTML §13.2.3.2); XML: declaração
`encoding` (RFC 7303) → UTF-8. Rótulos pela tabela de encodings do WHATWG. Charset desconhecido ou bytes
inválidos no charset escolhido são `RespostaInvalida`: corpo que não foi interpretado nunca equivale a "sem
marcador".
"""

from __future__ import annotations

import codecs
import re
import unicodedata
from dataclasses import dataclass

_BOMS: tuple[tuple[bytes, str], ...] = (  # UTF-32 antes de UTF-16: o BOM LE de 32 começa com o de 16
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
_META_BYTES = 1024
_ESPACOS = b"\t\n\x0c\r "
_LETRAS = b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Tabela de encodings do WHATWG: nome -> (codec do Python, rótulos). "-" = sem codec (recusado).
_TABELA = (
    ("utf-8", "utf-8", "unicode-1-1-utf-8 unicode11utf8 unicode20utf8 utf-8 utf8 x-unicode20utf8"),
    ("ibm866", "cp866", "866 cp866 csibm866 ibm866"),
    ("iso-8859-2", "iso8859-2", "csisolatin2 iso-8859-2 iso-ir-101 iso8859-2 iso88592 iso_8859-2 iso_8859-2:1987 l2 latin2"),
    ("iso-8859-3", "iso8859-3", "csisolatin3 iso-8859-3 iso-ir-109 iso8859-3 iso88593 iso_8859-3 iso_8859-3:1988 l3 latin3"),
    ("iso-8859-4", "iso8859-4", "csisolatin4 iso-8859-4 iso-ir-110 iso8859-4 iso88594 iso_8859-4 iso_8859-4:1988 l4 latin4"),
    ("iso-8859-5", "iso8859-5", "csisolatincyrillic cyrillic iso-8859-5 iso-ir-144 iso8859-5 iso88595 iso_8859-5 iso_8859-5:1988"),
    (
        "iso-8859-6",
        "iso8859-6",
        "arabic asmo-708 csiso88596e csiso88596i csisolatinarabic ecma-114 iso-8859-6 iso-8859-6-e iso-8859-6-i "
        "iso-ir-127 iso8859-6 iso88596 iso_8859-6 iso_8859-6:1987",
    ),
    (
        "iso-8859-7",
        "iso8859-7",
        "csisolatingreek ecma-118 elot_928 greek greek8 iso-8859-7 iso-ir-126 iso8859-7 iso88597 iso_8859-7 "
        "iso_8859-7:1987 sun_eu_greek",
    ),
    (
        "iso-8859-8",
        "iso8859-8",
        "csiso88598e csisolatinhebrew hebrew iso-8859-8 iso-8859-8-e iso-ir-138 iso8859-8 iso88598 iso_8859-8 "
        "iso_8859-8:1988 visual csiso88598i iso-8859-8-i logical",
    ),
    ("iso-8859-10", "iso8859-10", "csisolatin6 iso-8859-10 iso-ir-157 iso8859-10 iso885910 l6 latin6"),
    ("iso-8859-13", "iso8859-13", "iso-8859-13 iso8859-13 iso885913"),
    ("iso-8859-14", "iso8859-14", "iso-8859-14 iso8859-14 iso885914"),
    ("iso-8859-15", "iso8859-15", "csisolatin9 iso-8859-15 iso8859-15 iso885915 iso_8859-15 l9"),
    ("iso-8859-16", "iso8859-16", "iso-8859-16"),
    ("koi8-r", "koi8-r", "cskoi8r koi koi8 koi8-r koi8_r"),
    ("koi8-u", "koi8-u", "koi8-ru koi8-u"),
    ("macintosh", "mac_roman", "csmacintosh mac macintosh x-mac-roman"),
    ("windows-874", "cp874", "dos-874 iso-8859-11 iso8859-11 iso885911 tis-620 windows-874"),
    ("windows-1250", "cp1250", "cp1250 windows-1250 x-cp1250"),
    ("windows-1251", "cp1251", "cp1251 windows-1251 x-cp1251"),
    (
        "windows-1252",
        "cp1252",
        "ansi_x3.4-1968 ascii cp1252 cp819 csisolatin1 ibm819 iso-8859-1 iso-ir-100 iso8859-1 iso88591 "
        "iso_8859-1 iso_8859-1:1987 l1 latin1 us-ascii windows-1252 x-cp1252",
    ),
    ("windows-1253", "cp1253", "cp1253 windows-1253 x-cp1253"),
    (
        "windows-1254",
        "cp1254",
        "cp1254 csisolatin5 iso-8859-9 iso-ir-148 iso8859-9 iso88599 iso_8859-9 iso_8859-9:1989 l5 windows-1254 "
        "x-cp1254",
    ),
    ("windows-1255", "cp1255", "cp1255 windows-1255 x-cp1255"),
    ("windows-1256", "cp1256", "cp1256 windows-1256 x-cp1256"),
    ("windows-1257", "cp1257", "cp1257 windows-1257 x-cp1257"),
    ("windows-1258", "cp1258", "cp1258 windows-1258 x-cp1258"),
    ("x-mac-cyrillic", "mac_cyrillic", "x-mac-cyrillic x-mac-ukrainian"),
    (
        "gbk",
        "gbk",
        "chinese csgb2312 csiso58gb231280 gb2312 gb_2312 gb_2312-80 gbk iso-ir-58 x-gbk",
    ),
    ("gb18030", "gb18030", "gb18030"),
    ("big5", "big5hkscs", "big5 big5-hkscs cn-big5 csbig5 x-x-big5"),
    ("euc-jp", "euc_jp", "cseucpkdfmtjapanese euc-jp x-euc-jp"),
    ("iso-2022-jp", "iso2022_jp", "csiso2022jp iso-2022-jp"),
    ("shift_jis", "cp932", "csshiftjis ms932 ms_kanji shift-jis shift_jis sjis windows-31j x-sjis"),
    (
        "euc-kr",
        "cp949",
        "cseuckr csksc56011987 euc-kr iso-ir-149 korean ks_c_5601-1987 ks_c_5601-1989 ksc5601 ksc_5601 windows-949",
    ),
    ("replacement", "-", "csiso2022kr hz-gb-2312 iso-2022-cn iso-2022-cn-ext iso-2022-kr replacement"),
    ("utf-16be", "utf-16-be", "unicodefffe utf-16be"),
    ("utf-16le", "utf-16-le", "csunicode iso-10646-ucs-2 ucs-2 unicode unicodefeff utf-16 utf-16le"),
    ("x-user-defined", "-", "x-user-defined"),
)
_ROTULOS: dict[str, tuple[str, str]] = {
    rotulo: (nome, codec) for nome, codec, rotulos in _TABELA for rotulo in rotulos.split()
}


def _c1(exc: UnicodeError):
    """windows-1252 do WHATWG: byte indefinido vira o ponto de código de mesmo valor."""
    if isinstance(exc, UnicodeDecodeError):
        return "".join(chr(b) for b in exc.object[exc.start : exc.end]), exc.end
    raise exc


codecs.register_error("fv_whatwg_c1", _c1)


def _encoding(rotulo: str | None) -> tuple[str, str] | None:
    """"Get an encoding" (WHATWG Encoding): (nome, codec) do rótulo, sem espaços ASCII nas pontas."""
    return _ROTULOS.get((rotulo or "").strip(" \t\n\x0c\r").lower())


# --- prescan HTML (WHATWG HTML §13.2.3.2) ------------------------------------------------------------------


def _atributo(dados: bytes, pos: int) -> tuple[tuple[str, str] | None, int]:
    """"Get an attribute": (nome, valor) ou None se acabou a tag; e a nova posição."""
    n = len(dados)
    while pos < n and dados[pos] in _ESPACOS + b"/":
        pos += 1
    if pos >= n or dados[pos] == 0x3E:  # '>'
        return None, pos
    nome = bytearray()
    valor = bytearray()
    while True:
        if pos >= n:
            return (nome.decode("latin-1"), ""), pos
        c = dados[pos]
        if c == 0x3D and nome:  # '='
            pos += 1
            break
        if c in _ESPACOS:
            while pos < n and dados[pos] in _ESPACOS:
                pos += 1
            if pos >= n or dados[pos] != 0x3D:
                return (nome.decode("latin-1"), ""), pos
            pos += 1
            break
        if c in b"/>":
            return (nome.decode("latin-1"), ""), pos
        nome.append(c | 0x20 if 0x41 <= c <= 0x5A else c)
        pos += 1
    while pos < n and dados[pos] in _ESPACOS:
        pos += 1
    if pos >= n:
        return (nome.decode("latin-1"), ""), pos
    c = dados[pos]
    if c in b"\"'":
        pos += 1
        while pos < n and dados[pos] != c:
            valor.append(dados[pos] | 0x20 if 0x41 <= dados[pos] <= 0x5A else dados[pos])
            pos += 1
        return (nome.decode("latin-1"), valor.decode("latin-1")), pos + 1
    if c == 0x3E:
        return (nome.decode("latin-1"), ""), pos
    while pos < n and dados[pos] not in _ESPACOS + b">":
        valor.append(dados[pos] | 0x20 if 0x41 <= dados[pos] <= 0x5A else dados[pos])
        pos += 1
    return (nome.decode("latin-1"), valor.decode("latin-1")), pos


def _charset_do_content(content: str) -> str | None:
    """"Algorithm for extracting a character encoding from a meta element"."""
    pos = 0
    while True:
        i = content.find("charset", pos)
        if i < 0:
            return None
        pos = i + len("charset")
        while pos < len(content) and content[pos] in " \t\n\x0c\r":
            pos += 1
        if pos < len(content) and content[pos] == "=":
            break
    pos += 1
    while pos < len(content) and content[pos] in " \t\n\x0c\r":
        pos += 1
    if pos >= len(content):
        return None
    if content[pos] in "\"'":
        fim = content.find(content[pos], pos + 1)
        return None if fim < 0 else content[pos + 1 : fim]
    fim = pos
    while fim < len(content) and content[fim] not in " \t\n\x0c\r;":
        fim += 1
    return content[pos:fim]


def _meta(dados: bytes, pos: int) -> tuple[tuple[str, str] | None, int]:
    """Encoding efetivo de um `<meta>` (posição logo após o nome), ou None; e a posição ao fim da tag."""
    vistos: set[str] = set()
    pragma, precisa, charset = False, None, None
    while True:
        attr, pos = _atributo(dados, pos)
        if attr is None:
            break
        nome, valor = attr
        if nome in vistos:
            continue
        vistos.add(nome)
        if nome == "http-equiv":
            pragma = pragma or valor == "content-type"
        elif nome == "content":
            if charset is None:
                achado = _charset_do_content(valor)
                if achado is not None:
                    charset, precisa = _encoding(achado), True
        elif nome == "charset":
            charset, precisa = _encoding(valor), False
    if precisa is None or (precisa and not pragma) or charset is None:
        return None, pos
    if charset[0] in ("utf-16le", "utf-16be"):
        return _ROTULOS["utf-8"], pos
    if charset[0] == "x-user-defined":
        return _ROTULOS["windows-1252"], pos
    return charset, pos


def _prescan_html(corpo: bytes) -> tuple[str, str] | None:
    dados = corpo[:_META_BYTES]
    n = len(dados)
    pos = 0
    while pos < n:
        if dados.startswith(b"<!--", pos):
            fim = dados.find(b"-->", pos + 2)
            if fim < 0:
                return None
            pos = fim + 3
        elif dados[pos : pos + 5].lower() == b"<meta" and pos + 5 < n and dados[pos + 5] in _ESPACOS + b"/":
            achado, pos = _meta(dados, pos + 5)
            if achado is not None:
                return achado
            pos += 1
        elif dados[pos] == 0x3C and pos + 1 < n and (
            dados[pos + 1] in _LETRAS or (dados[pos + 1] == 0x2F and pos + 2 < n and dados[pos + 2] in _LETRAS)
        ):
            pos += 2
            while pos < n and dados[pos] not in _ESPACOS + b">":
                pos += 1
            while True:
                attr, pos = _atributo(dados, pos)
                if attr is None:
                    break
            pos += 1
        elif dados[pos : pos + 2] in (b"<!", b"</", b"<?"):
            fim = dados.find(b">", pos)
            if fim < 0:
                return None
            pos = fim + 1
        else:
            pos += 1
    return None


# --- declaração XML (RFC 7303) -----------------------------------------------------------------------------

_DECL_XML = re.compile(rb'^<\?xml\s[^>]*?\bencoding\s*=\s*(?:"([^"]*)"|\'([^\']*)\')', re.S)


def _declaracao_xml(corpo: bytes) -> tuple[str, str] | None:
    m = _DECL_XML.match(corpo[:_META_BYTES])
    if m is None:
        return None
    achado = _encoding(next(g for g in m.groups() if g is not None).decode("latin-1"))
    # Sem BOM, a declaração só foi lida porque o corpo é ASCII-compatível: UTF-16 declarado vale UTF-8.
    return _ROTULOS["utf-8"] if achado and achado[0].startswith("utf-16") else achado


def _mime(content_type: str | None) -> str:
    """Media type validado, para TODA resposta e antes de qualquer desvio por BOM, MIME binário ou status (FIX18/F-19):
    sintaxe estrita, `charset*`/continuações e `charset` duplicado divergente são `RespostaInvalida`."""
    if not (content_type or "").strip(_OWS):
        return ""
    _charset_cabecalho(content_type)
    return content_type.split(";", 1)[0].strip(_OWS).lower()


def _textual(mime: str) -> bool:
    return (
        not mime or mime.startswith("text/") or mime.endswith(("/json", "+json", "/xml", "+xml", "/javascript"))
    )


def _xml(mime: str) -> bool:
    return mime.endswith(("/xml", "+xml"))


def _invalida(motivo: str):
    from freoa_verifica.transport import RespostaInvalida  # import tardio: transport usa esta função

    return RespostaInvalida(motivo)


_TCHAR = frozenset("!#$%&'*+-.^_`|~0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
_OWS = " \t"


def _token(texto: str, pos: int) -> tuple[str, int]:
    fim = pos
    while fim < len(texto) and texto[fim] in _TCHAR:
        fim += 1
    return texto[pos:fim], fim


def _aspas(texto: str, pos: int) -> tuple[str, int]:
    """quoted-string (RFC 9110 §5.6.4) a partir da aspa de abertura: (valor sem escapes, posição após o fecho)."""
    saida: list[str] = []
    pos += 1
    while pos < len(texto):
        c = texto[pos]
        if c == '"':
            return "".join(saida), pos + 1
        if c == "\\":
            pos += 1
            if pos >= len(texto):
                break
            c = texto[pos]
        if not (c in "\t " or "!" <= c <= "~" or "\x80" <= c <= "\xff"):  # qdtext / quoted-pair
            raise _invalida("Content-Type malformado: caractere inválido em quoted-string")
        saida.append(c)
        pos += 1
    raise _invalida("Content-Type malformado: quoted-string sem fecho")


def parametros_media_type(content_type: str) -> list[tuple[str, str]]:
    """Parâmetros de `type "/" subtype *( OWS ";" OWS [ parameter ] )` (RFC 9110 §5.6.6, §8.3.1).

    Gramática estrita, sem RFC 2231: `charset*` é outro nome de parâmetro, nunca `charset`. Nomes em minúsculas.
    Malformado é `RespostaInvalida`.
    """
    texto = content_type.strip(_OWS)
    tipo, pos = _token(texto, 0)
    if not tipo or texto[pos : pos + 1] != "/":
        raise _invalida("Content-Type malformado: media type sem barra")
    subtipo, pos = _token(texto, pos + 1)
    if not subtipo:
        raise _invalida("Content-Type malformado: subtipo vazio")
    achados: list[tuple[str, str]] = []
    while pos < len(texto):
        while pos < len(texto) and texto[pos] in _OWS:
            pos += 1
        if texto[pos : pos + 1] != ";":
            raise _invalida("Content-Type malformado: esperado ';' entre parâmetros")
        pos += 1
        while pos < len(texto) and texto[pos] in _OWS:
            pos += 1
        if pos >= len(texto) or texto[pos] == ";":  # parâmetro vazio é permitido pela gramática
            continue
        nome, pos = _token(texto, pos)
        if not nome or texto[pos : pos + 1] != "=":
            raise _invalida("Content-Type malformado: parâmetro sem nome ou sem valor")
        pos += 1
        if texto[pos : pos + 1] == '"':
            valor, pos = _aspas(texto, pos)
        else:
            valor, pos = _token(texto, pos)
            if not valor:
                raise _invalida("Content-Type malformado: parâmetro sem valor")
        achados.append((nome.lower(), valor))
    return achados


def _charset_cabecalho(content_type: str | None) -> str | None:
    """Valor do parâmetro `charset` (e só dele) do Content-Type; extensão RFC 2231 e duplicata divergente são inválidas."""
    if not content_type:
        return None
    valores: list[str] = []
    for nome, valor in parametros_media_type(content_type):
        if nome.startswith("charset*"):
            raise _invalida("Content-Type com charset estendido ou em continuação (RFC 2231) não é aceito")
        if nome == "charset":
            valores.append(valor)
    if len({v.lower() for v in valores}) > 1:
        raise _invalida("Content-Type com charset duplicado e divergente")
    return valores[0] if valores else None


def _declarado(corpo: bytes, content_type: str | None, mime: str) -> tuple[str, str, str]:
    """(nome, codec, origem) declarado: cabeçalho, depois prescan de HTML ou declaração XML; senão UTF-8."""
    rotulo = _charset_cabecalho(content_type)
    if rotulo is not None:
        achado = _encoding(rotulo)
        if achado is None:
            raise _invalida(f"Charset não suportado: {rotulo}")
        return (*achado, "header")
    if not mime or mime == "text/html":
        achado = _prescan_html(corpo)
        if achado is not None:
            return (*achado, "meta")
    if _xml(mime) or not mime:
        achado = _declaracao_xml(corpo)
        if achado is not None:
            return (*achado, "declaracao_xml")
    return (*_ROTULOS["utf-8"], "padrao")


ORIGENS = ("bom", "header", "meta", "declaracao_xml", "padrao", "binario")


@dataclass(frozen=True)
class Interpretacao:
    """Texto e a decisão que o produziu: `codificacao` (codec usado; None se binário) e `origem` (`ORIGENS`)."""

    texto: str
    codificacao: str | None
    origem: str


def _parece_html(corpo: bytes, content_type: str | None) -> bool:
    """Marcador HTML no início, nos bytes ou na vista do `charset` declarado (UTF-16 sem BOM não tem `<html` ASCII)."""
    vistas = [corpo[:_META_BYTES].lower()]
    achado = _encoding(_charset_cabecalho(content_type))
    if achado is not None and achado[1] != "-":
        vistas.append(codecs.decode(corpo[: _META_BYTES * 4], achado[1], "ignore").lower().encode("utf-8"))
    return any(b"<html" in v or b"<!doctype" in v for v in vistas)


def interpretar(corpo: bytes, content_type: str | None = None, *, parcial: bool = False) -> Interpretacao:
    """Interpretação única do corpo (decisões 0061 a 0064); `RespostaInvalida` se não for interpretável.

    O Content-Type é validado PRIMEIRO, para todo corpo: BOM, MIME binário ou status nunca dispensam a validação
    (FIX18/F-19). `parcial`: o corpo é só o começo de uma resposta maior; multibyte cortado no fim é aceito.
    Mime não textual (PDF, DOCX…) não tem charset: vista latin-1, só para marcadores ASCII; mas corpo com BOM ou
    marcador HTML sob mime binário é lido como texto (um desafio HTML servido como PDF continua desafio).
    """
    mime = _mime(content_type)
    bom = next((n for b, n in _BOMS if corpo.startswith(b)), None)
    if not _textual(mime):
        if bom is None and not _parece_html(corpo, content_type):
            return Interpretacao(corpo.decode("latin-1"), None, "binario")
        mime = ""
    nome, enc, origem, erros = bom, None, "bom", "strict"
    if nome is None:
        enc, nome, origem = _declarado(corpo, content_type, mime)
        if enc == "windows-1252":
            erros = "fv_whatwg_c1"
    if nome == "-":
        raise _invalida(f"Charset não suportado: {enc}")
    try:
        decodificador = codecs.getincrementaldecoder(nome)(errors=erros)
        texto = decodificador.decode(corpo, final=not parcial)
    except LookupError as exc:
        raise _invalida(f"Charset não suportado: {nome}") from exc
    except (UnicodeError, TypeError, ValueError) as exc:
        raise _invalida(f"Corpo inválido para o charset {nome}") from exc
    if not isinstance(texto, str):
        raise _invalida(f"Charset não textual: {nome}")
    return Interpretacao(texto, nome, origem)


def texto_da_resposta(corpo: bytes | str | None, content_type: str | None = None, *, parcial: bool = False) -> str:
    """Texto de `interpretar`; `str` já é texto, `None` é vazio."""
    if corpo is None:
        return ""
    if isinstance(corpo, str):
        return corpo
    return interpretar(corpo, content_type, parcial=parcial).texto


def vista_bytes(corpo: bytes | str | None) -> str:
    """Bytes crus como latin-1, só para procurar marcadores ASCII (FIX17): nunca é o texto do documento."""
    return corpo.decode("latin-1") if isinstance(corpo, (bytes, bytearray)) else ""


def texto_para_exibicao(corpo: bytes, content_type: str | None) -> str:
    """Exibição de captura guardada, que nunca falha: a interpretação única ou, se inválida, UTF-8/latin-1 declarados
    pelo chamador como exibição (nunca alimentam parser nem verificação)."""
    from freoa_verifica.transport import RespostaInvalida  # import tardio: transport usa este módulo

    try:
        return interpretar(corpo, content_type).texto
    except (RespostaInvalida, ValueError):
        pass
    try:
        return corpo.decode("utf-8")
    except UnicodeDecodeError:
        return corpo.decode("latin-1")


def codec_html_declarado(corpo: bytes) -> str | None:
    """Codec do `<meta>` efetivo de um HTML sem Content-Type (parsers que releem bytes capturados), ou None."""
    achado = _prescan_html(corpo)
    return achado[1] if achado and achado[1] != "-" else None


def content_type_do_response(resp) -> str | None:
    """Content-Type cru que o transporte guardou (ou o do recibo, em captura relida)."""
    return getattr(resp, "content_type", "") or (getattr(resp, "headers", None) or {}).get("content-type") or None


def texto_do_response(resp, *, parcial: bool = False) -> str:
    """Texto do corpo de um `Response`, com o Content-Type cru que o transporte guardou."""
    return texto_da_resposta(resp.body, content_type_do_response(resp), parcial=parcial)


def corpo_binario(resp) -> bytes:
    """Bytes de um `Response` para parser de formato binário (PDF, DOCX), com o Content-Type validado como no texto.

    Único caminho pelo qual um parser recebe bytes de resposta (garantia estrutural 4, FIX18).
    """
    _mime(content_type_do_response(resp))
    return resp.body


def arvore_html(corpo: bytes | str, content_type: str | None = None):
    """Árvore lxml do TEXTO da interpretação única: o parser nunca recebe bytes (FIX16/F-22).

    Declaração `<?xml ... encoding?>` é retirada: lxml recusa str com ela, e a codificação já foi decidida.
    """
    from lxml import html as lxml_html

    return lxml_html.fromstring(re.sub(r"^\s*<\?xml[^>]*\?>", "", texto_da_resposta(corpo, content_type)))


def normalizar_para_busca(texto: str) -> str:
    """NFKC, casefold e sem acentos: forma em que marcadores e texto são comparados."""
    base = unicodedata.normalize("NFKC", texto).casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", base) if not unicodedata.combining(c))
