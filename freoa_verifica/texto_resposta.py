"""Interpretação textual única do corpo de uma resposta HTTP (decisão 0061).

Detecção de desafio (`connectors.challenge`, `transport._desafio_na_resposta`) e leitura de sucesso pelos
conectores usam esta função. Ordem: BOM → `charset` do Content-Type → `<meta charset>`/`http-equiv` nos
primeiros 1024 bytes (HTML) → UTF-8. Charset desconhecido ou bytes inválidos no charset escolhido são
`RespostaInvalida`: corpo que não foi interpretado nunca equivale a "sem marcador".
"""

from __future__ import annotations

import codecs
import re
import unicodedata

_BOMS: tuple[tuple[bytes, str], ...] = (  # UTF-32 antes de UTF-16: o BOM LE de 32 começa com o de 16
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)
_CHARSET_CABECALHO = re.compile(r'charset\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^;\s]*))', re.I)
_CHARSET_META = re.compile(rb'<meta\b[^>]*?charset\s*=\s*["\']?\s*([A-Za-z0-9_:.\-]+)', re.I)
_MIMES_HTML = {"text/html", "application/xhtml+xml"}
_META_BYTES = 1024


def _mime(content_type: str | None) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def _textual(mime: str) -> bool:
    return (
        not mime or mime.startswith("text/") or mime.endswith(("/json", "+json", "/xml", "+xml", "/javascript"))
    )


def _invalida(motivo: str):
    from freoa_verifica.transport import RespostaInvalida  # import tardio: transport usa esta função

    return RespostaInvalida(motivo)


def _charset(corpo: bytes, content_type: str | None, mime: str) -> str | None:
    """Charset declarado (cabeçalho, depois meta de HTML); None se nada foi declarado."""
    m = _CHARSET_CABECALHO.search(content_type or "")
    if m:
        return next(g for g in m.groups() if g is not None).strip().lower()
    if not mime or mime in _MIMES_HTML:
        m = _CHARSET_META.search(corpo[:_META_BYTES])
        if m:
            return m.group(1).decode("ascii").lower()
    return None


def texto_da_resposta(corpo: bytes | str | None, content_type: str | None = None, *, parcial: bool = False) -> str:
    """Texto do corpo conforme BOM/charset; `RespostaInvalida` se não for interpretável.

    `parcial`: o corpo é só o começo de uma resposta maior; sequência multibyte cortada no fim é aceita.
    Mime não textual (PDF, DOCX…) não tem charset: devolve latin-1, só para busca de marcadores ASCII.
    """
    if corpo is None:
        return ""
    if isinstance(corpo, str):
        return corpo
    mime = _mime(content_type)
    if not _textual(mime):
        return corpo.decode("latin-1")
    nome = next((n for bom, n in _BOMS if corpo.startswith(bom)), None)
    if nome is None:
        nome = _charset(corpo, content_type, mime) or "utf-8"
    try:
        decodificador = codecs.getincrementaldecoder(nome)(errors="strict")
        texto = decodificador.decode(corpo, final=not parcial)
    except LookupError as exc:
        raise _invalida(f"Charset não suportado: {nome}") from exc
    except (UnicodeError, TypeError, ValueError) as exc:
        raise _invalida(f"Corpo inválido para o charset {nome}") from exc
    if not isinstance(texto, str):
        raise _invalida(f"Charset não textual: {nome}")
    return texto


def normalizar_para_busca(texto: str) -> str:
    """NFKC, casefold e sem acentos: forma em que marcadores e texto são comparados."""
    base = unicodedata.normalize("NFKC", texto).casefold()
    return "".join(c for c in unicodedata.normalize("NFKD", base) if not unicodedata.combining(c))
