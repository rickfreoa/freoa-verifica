"""Transporte HTTP com IP fixado, validação por salto e limites.

Portado e adaptado de freoa-verifica (core.py, http_receipts.py).
"""

from __future__ import annotations

import hashlib
import http.client
import io
import ipaddress
import os
import random
import re
import socket
import ssl
import threading
import tempfile
from pathlib import Path
from typing import BinaryIO, Callable
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from http.cookiejar import CookieJar
from queue import Empty, Queue
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request as _UrlLibRequest

from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO

# --- cabeçalhos de recibo HTTP ---
# portado de freoa-verifica/http_receipts.py (HEADER_NAMES / _valid_header)

HEADER_NAMES = frozenset({"date", "last-modified", "content-type", "content-length", "retry-after"})
_MIME = re.compile(
    r"[a-z0-9.+-]{1,64}/[a-z0-9.+-]{1,64}"
    r"(?:;[ ]*charset=(?:utf-8|utf-16|iso-8859-1|windows-1252|us-ascii))?",
    re.I,
)

DNS_TIMEOUT = 10.0
MIN_BYTES_PER_SECOND = 2048
SLOW_WINDOW = 30.0
MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 3
DEFAULT_ALLOWED_MIMES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "application/xml",
        "text/xml",
        "application/pdf",
        "application/rss+xml",
        "text/plain",
    }
)
_RESERVED_REQUEST_HEADERS = frozenset(
    {"host", "content-length", "transfer-encoding", "connection"}
)
_HOP_CREDENTIAL_HEADERS = frozenset(
    {"authorization", "cookie", "proxy-authorization"}
)
_DNS_SLOTS = threading.BoundedSemaphore(4)
_MAX_CONCURRENCY = max(1, int(os.environ.get("FV_MAX_CONCURRENCY", "4")))
_CAPTURE_SLOTS = threading.BoundedSemaphore(_MAX_CONCURRENCY)


class TransportError(Exception):
    """Erro base do transporte."""

    def __init__(self, message: str | None = None, *, http: HTTPMetadata | None = None):
        self.http = http
        self.saltos: list[dict] = []  # cadeia de redirecionamentos já respondida: [{url, status}]
        super().__init__(message)


class BlockedHost(TransportError):
    """Host, porta, caminho ou endereço IP recusado pela política."""


class RespostaInvalida(TransportError):
    """Resposta HTTP recebida, mas inválida (MIME, framing, codificação): não é falha de conexão."""


class TooLarge(RespostaInvalida):
    """Corpo declarado ou baixado acima do limite."""


class Timeout(TransportError):
    """Prazo de captura ou DNS esgotado."""


class EmptyBody(TransportError):
    """GET com corpo vazio."""


class TransporteLento(RespostaInvalida):
    """Leitura abaixo da taxa mínima durante uma janela completa, já iniciada a resposta (FIX5/F-01)."""


class HTTPStatusError(TransportError):
    """Resposta HTTP com status inesperado."""

    def __init__(
        self,
        status: int,
        message: str | None = None,
        *,
        http: HTTPMetadata | None = None,
        desafio: str | None = None,
    ):
        self.status = status
        # Tipo do desafio (CAPTCHA/WAF) provado na resposta de erro; None = sem marcador.
        self.desafio = desafio
        super().__init__(message or f"HTTP {status}", http=http)


class ChallengeDetected(TransportError):
    """Desafio interativo (CAPTCHA/JS) detectado — definida aqui; não lançada neste módulo."""


@dataclass(frozen=True)
class HTTPMetadata:
    """Recibo HTTP validado (status + Date/Last-Modified/Content-Type/Content-Length)."""

    status_code: int
    headers: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if type(self.status_code) is not int or not 100 <= self.status_code <= 599:
            raise ValueError("INVALID_HTTP_METADATA_STATUS")
        if type(self.headers) is not tuple or len(self.headers) > len(HEADER_NAMES):
            raise ValueError("INVALID_HTTP_METADATA_HEADERS")
        seen: set[str] = set()
        for pair in self.headers:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError("INVALID_HTTP_METADATA_HEADERS")
            name, value = pair
            if not _valid_header(name, value) or name in seen:
                raise ValueError("INVALID_HTTP_METADATA_HEADERS")
            seen.add(name)


@dataclass(frozen=True)
class Response:
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    sha256: str
    fetched_at: str
    redirects: list[str]
    mime: str
    http: HTTPMetadata | None = None
    size: int = 0


# portado de freoa-verifica/http_receipts.py:_valid_header
def _valid_header(name: str, value: str) -> bool:
    if type(name) is not str or name not in HEADER_NAMES or type(value) is not str:
        return False
    if not 1 <= len(value) <= 192 or any(ord(c) < 32 or ord(c) > 126 for c in value):
        return False
    if name == "retry-after" and re.fullmatch(r"[0-9]{1,9}", value):
        return True
    if name in {"date", "last-modified", "retry-after"}:
        try:
            parsed = parsedate_to_datetime(value)
            return format_datetime(parsed, usegmt=True) == value
        except (ValueError, TypeError, OverflowError):
            return False
    if name == "content-length":
        return (
            re.fullmatch(r"0|[1-9][0-9]{0,8}", value) is not None
            and int(value) <= 50 * 1024 * 1024
        )
    return _MIME.fullmatch(value) is not None


# portado de freoa-verifica/http_receipts.py:observe_http_response
def observe_http_response(response) -> HTTPMetadata:
    """Seleciona cabeçalhos permitidos e válidos; descarta o restante."""
    getheaders = getattr(response, "getheaders", None)
    if callable(getheaders):
        rows = getheaders()
    else:
        rows = [(name, response.getheader(name)) for name in sorted(HEADER_NAMES)]
    if type(rows) not in (tuple, list) or len(rows) > 100:
        raise ValueError("INVALID_HTTP_METADATA_HEADERS")
    selected: dict[str, str] = {}
    duplicates: set[str] = set()
    for pair in rows:
        if type(pair) not in (tuple, list) or len(pair) != 2:
            raise ValueError("INVALID_HTTP_METADATA_HEADERS")
        name, value = pair
        if type(name) is not str:
            continue
        name = name.lower()
        if name not in HEADER_NAMES:
            continue
        if name in selected:
            duplicates.add(name)
        selected[name] = value
    headers = tuple(
        (name, value)
        for name, value in sorted(selected.items())
        if name not in duplicates and _valid_header(name, value)
    )
    return HTTPMetadata(response.status, headers)


def observe_headers(response) -> dict[str, str]:
    """Compat: devolve dict dos cabeçalhos observados no recibo."""
    try:
        meta = observe_http_response(response)
    except (AttributeError, TypeError, ValueError):
        return {}
    return dict(meta.headers)


def _failure_http(response) -> HTTPMetadata | None:
    if response is None:
        return None
    try:
        return observe_http_response(response)
    except (AttributeError, TypeError, ValueError):
        return None


_TCHAR = rb"[!#$%&'*+\-.^_`|~0-9A-Za-z]"
_BWS = rb"[ \t]*"
# quoted-string (RFC 9110 §5.6.4): DQUOTE *( qdtext / quoted-pair ) DQUOTE
_QUOTED = rb'"(?:[\t \x21\x23-\x5b\x5d-\x7e\x80-\xff]|\\[\t \x21-\x7e\x80-\xff])*"'
_CHUNK_EXT = (
    rb"(?:" + _BWS + rb";" + _BWS + _TCHAR + rb"+(?:" + _BWS + rb"=" + _BWS
    + rb"(?:" + _TCHAR + rb"+|" + _QUOTED + rb"))?)*"
)
_LINHA_CHUNK = re.compile(rb"([0-9A-Fa-f]{1,16})" + _CHUNK_EXT + rb"\r\n")
_MAX_LINHA_CHUNK = 65536


class _RespostaEstrita(http.client.HTTPResponse):
    r"""HTTPResponse que não tolera framing chunked malformado (FIX11/F-13).

    O `http.client` descarta sem conferir os 2 bytes depois dos dados de um chunk, aceita tamanho com
    sinal, sublinhado ou espaço (`int(x, 16)`) e dá o fim do corpo por bom sem o CRLF final. Aqui o
    tamanho é `HEXDIG+` com extensão opcional, o fim de chunk é exatamente CRLF e o corpo termina em
    `0 CRLF [trailer] CRLF`; qualquer outra coisa é `HTTPException`/`IncompleteRead`, que o transporte
    classifica como `RespostaInvalida` (resposta já iniciada), nunca repetível.

    Correspondência produção a produção com a RFC 9112 (FIX13/F-13). Restrição = aceita menos que a RFC.

    | Produção da RFC                                   | Implementação                                   | Relação   |
    |---------------------------------------------------|-------------------------------------------------|-----------|
    | HTTP-version = "HTTP" "/" DIGIT "." DIGIT (§2.3)  | `_LINHA_STATUS`: `HTTP/1.[01]`                  | restrição |
    | status-line = version SP status-code SP [reason]  | `_LINHA_STATUS`: SP, 3DIGIT, SP, reason*        | igual     |
    | reason-phrase = 1*(HTAB/SP/VCHAR/obs-text)        | `[\t \x21-\x7e\x80-\xff]*` (vazia, como errata) | igual     |
    | field-line = field-name ":" OWS value OWS (§5)    | `_CAMPO`                                        | igual     |
    | field-name = token (RFC 9110 §5.6.2)              | `_TCHAR+`                                       | igual     |
    | field-value = *field-content; field-content =     | `_CAMPO`: field-vchar, miolo com SP/HTAB,       | igual     |
    |   field-vchar [1*(SP/HTAB/field-vchar) field-vchar]| sem espaço nas pontas                          |           |
    | obs-fold (§5.2)                                   | recusado (a RFC permite recusar na resposta)    | restrição |
    | chunked-body = *chunk last-chunk trailer CRLF     | `_get_chunk_left` + `_ler_trailer`              | igual     |
    | chunk = chunk-size [chunk-ext] CRLF data CRLF     | `_LINHA_CHUNK`; CRLF exato após os dados        | igual     |
    | chunk-size = 1*HEXDIG                             | `[0-9A-Fa-f]{1,16}`                             | restrição |
    | last-chunk = 1*"0" [chunk-ext] CRLF               | tamanho 0 pela mesma `_LINHA_CHUNK`             | igual     |
    | chunk-ext = *(BWS ";" BWS name [BWS "=" BWS val]) | `_CHUNK_EXT`                                    | igual     |
    | chunk-ext-name = token                            | `_TCHAR+`                                       | igual     |
    | chunk-ext-val = token / quoted-string             | `_TCHAR+` / `_QUOTED`                           | igual     |
    | quoted-string, qdtext, quoted-pair (RFC 9110      | `_QUOTED`: qdtext = HTAB/SP/%x21/%x23-5B/       | igual     |
    |   §5.6.4)                                         | %x5D-7E/obs-text; pair = "\" (HTAB/SP/VCHAR/    |           |
    |                                                   | obs-text); CTL e LF/CR recusados                |           |
    | trailer-section = *(field-line CRLF)              | `_CAMPO`; no máximo 100 linhas                  | restrição |
    | BWS = OWS = *(SP / HTAB)                          | `[ \t]*`                                        | igual     |
    | Content-Length = 1*DIGIT                          | `[0-9]+`, até 20 dígitos, valor único           | restrição |
    | Transfer-Encoding = #transfer-coding              | um único `chunked`                              | restrição |

    Nota: BWS antes de ";" é gramática válida (`5 ;x`); espaço depois do tamanho sem ";" (`5 `, `5\t`) não é.
    """

    def _get_chunk_left(self):
        chunk_left = self.chunk_left
        if not chunk_left:  # 0 (fim do chunk) ou None (nenhum chunk aberto)
            if chunk_left is not None and self._safe_read(2) != b"\r\n":
                self._close_conn()
                raise http.client.HTTPException("Fim de chunk inválido")
            linha = self.fp.readline(_MAX_LINHA_CHUNK + 1)
            if len(linha) > _MAX_LINHA_CHUNK:
                raise http.client.LineTooLong("chunk size")
            m = _LINHA_CHUNK.fullmatch(linha)
            if m is None:
                self._close_conn()
                raise http.client.HTTPException("Tamanho ou extensão de chunk inválido")
            chunk_left = int(m.group(1), 16)
            if chunk_left == 0:
                self._ler_trailer()
                self._close_conn()
                chunk_left = None
            self.chunk_left = chunk_left
        return chunk_left

    def _ler_trailer(self) -> None:
        for _ in range(100):
            linha = self.fp.readline(_MAX_LINHA_CHUNK + 1)
            if len(linha) > _MAX_LINHA_CHUNK:
                raise http.client.LineTooLong("trailer line")
            if not linha.endswith(b"\r\n"):
                self._close_conn()
                raise http.client.IncompleteRead(b"")  # encerramento prematuro
            if linha == b"\r\n":
                return
            if _CAMPO.fullmatch(linha[:-2]) is None:
                self._close_conn()
                raise http.client.HTTPException("Campo de trailer inválido")
        raise http.client.HTTPException("Trailer excessivo")


_CAMPO = re.compile(
    _TCHAR + rb"+:[ \t]*(?:[\x21-\x7e\x80-\xff](?:[ \t\x21-\x7e\x80-\xff]*[\x21-\x7e\x80-\xff])?)?[ \t]*"
)
_LINHA_STATUS = re.compile(rb"HTTP/1\.[01] [0-9]{3} [\t \x21-\x7e\x80-\xff]*")


def _campos_estritos(cru: bytes) -> dict[str, list[str]]:
    """Valida os BYTES da linha de status e dos cabeçalhos pela gramática da RFC 9112 §2–§5 (FIX12/F-13).

    Linha de status `HTTP/1.x SP 3DIGIT SP reason`; campo `token ":" OWS valor OWS`, sem espaço antes de
    `:`, sem obs-fold, sem linha sem `:`; fim de linha só CRLF. Respostas 100 são puladas, como faz o
    `http.client`. Devolve os campos da resposta final (nomes em minúsculas). Levanta `ValueError`.
    """
    pos = 0
    while True:
        fim = cru.find(b"\r\n\r\n", pos)
        if fim < 0:
            raise ValueError("Bloco de cabeçalhos sem CRLF CRLF final")
        linhas = cru[pos:fim + 2].split(b"\r\n")[:-1]
        pos = fim + 4
        if _LINHA_STATUS.fullmatch(linhas[0]) is None:
            raise ValueError("Linha de status inválida")
        campos: dict[str, list[str]] = {}
        for linha in linhas[1:]:
            if _CAMPO.fullmatch(linha) is None:
                raise ValueError("Campo de cabeçalho inválido")
            nome, valor = linha.split(b":", 1)
            campos.setdefault(nome.decode("ascii").lower(), []).append(valor.strip(b" \t").decode("latin-1"))
        if linhas[0][9:12] != b"100":
            return campos


def _validar_framing(response, cru: bytes) -> int | None:
    """Validação de QUALQUER resposta, qualquer status (FIX11/F-13, FIX12/F-13). Devolve o Content-Length.

    A decisão é sobre os bytes brutos (`cru`), não sobre o parser tolerante do `http.client`: sintaxe
    estrita da linha de status e dos cabeçalhos; Transfer-Encoding diferente de um único `chunked`,
    Content-Length duplicado, não numérico ou negativo, e Content-Length junto de Transfer-Encoding são
    `RespostaInvalida`. O fluxo chunked e os trailers são validados por `_RespostaEstrita`.
    """
    def invalida(motivo: str) -> RespostaInvalida:
        return RespostaInvalida(motivo, http=_failure_http(response))

    try:
        campos = _campos_estritos(cru)
    except ValueError as exc:
        raise invalida(str(exc)) from exc
    te = campos.get("transfer-encoding", [])
    cl = campos.get("content-length", [])
    if te and (len(te) > 1 or te[0].lower() != "chunked"):
        raise invalida("Transfer-Encoding não suportado")
    if len(cl) > 1 or (cl and (len(cl[0]) > 20 or not re.fullmatch(r"[0-9]+", cl[0]))):
        raise invalida("Content-Length inválido")
    if cl and te:
        raise invalida("Cabeçalhos de framing conflitantes")
    return int(cl[0]) if cl else None


_AMOSTRA_DESAFIO = 65536


def _desafio_na_resposta(response) -> str | None:
    """Tipo de desafio visto em resposta de erro (cabeçalho de borda ou amostra do corpo).

    Lê em laço até 64 KiB ou o fim do corpo, qualquer que seja a fragmentação, e procura o marcador
    no buffer acumulado. Só "examinado por completo e sem marcador" mantém a classificação por
    status; framing inválido, corpo incompleto ou leitura impossível é `RespostaInvalida`.
    """
    from freoa_verifica.connectors.challenge import detect_challenge  # import tardio: challenge importa este módulo

    try:
        headers = dict(response.getheaders())
        reader = getattr(response, "read1", None) or response.read
        amostra = bytearray()
        while len(amostra) < _AMOSTRA_DESAFIO:
            bloco = reader(_AMOSTRA_DESAFIO - len(amostra))
            if not bloco:
                if getattr(response, "length", None):  # Content-Length não satisfeito: EOF prematuro
                    raise http.client.IncompleteRead(bytes(amostra), response.length)
                break
            amostra += bloco
    except (OSError, http.client.HTTPException, ValueError) as exc:
        # Impossível examinar não é "sem marcador" (FIX10/F-13): erro de framing/protocolo propaga.
        raise RespostaInvalida(
            f"Corpo da resposta de erro ilegível: {exc}", http=_failure_http(response)
        ) from exc
    found = detect_challenge(status=response.status, headers=headers, body=bytes(amostra))
    return str(found.args[0]) if found is not None and found.args else None


def _contact_headers() -> dict[str, str]:
    contact = (os.environ.get("FV_CONTACT") or "").strip()
    headers = {"User-Agent": USER_AGENT_IDENTIFICADO,"Accept-Encoding": "identity"}
    if contact:
        headers["From"] = contact
    return headers


def _normalize_caller_headers(headers: dict[str, str] | None) -> dict[str, str]:
    """Normaliza nomes (case-insensitive) e recusa cabeçalhos reservados."""
    if not headers:
        return {}
    normalized: dict[str, str] = {}
    for name, value in headers.items():
        if type(name) is not str or type(value) is not str:
            raise ValueError("cabeçalho inválido")
        key = name.strip()
        if not key:
            raise ValueError("cabeçalho inválido")
        lower = key.lower()
        if lower in _RESERVED_REQUEST_HEADERS:
            raise ValueError(f"cabeçalho reservado: {key}")
        if lower in normalized:
            raise ValueError(f"cabeçalho duplicado: {key}")
        # Preserva a forma canônica Title-Case simples para envio.
        canonical = "-".join(part.capitalize() for part in lower.split("-"))
        normalized[canonical] = value
    return normalized


def _host_canonico(parsed) -> str:
    """Host como o transporte o valida: minúsculo, IDNA, sem ponto final."""
    host = (parsed.hostname or "").lower().rstrip(".")
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


_PERCENT = re.compile(r"%([0-9A-Fa-f]{2})")
_NAO_RESERVADO = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _percent_canonico(texto: str) -> str:
    """`%7E` e `~` são o mesmo octeto: decodifica não reservados, maiusculiza o resto."""

    def troca(m):
        c = chr(int(m.group(1), 16))
        return c if c in _NAO_RESERVADO else "%" + m.group(1).upper()

    return _PERCENT.sub(troca, texto)


def identidade_requisicao(
    metodo: str, url: str, corpo: bytes | None = None, cabecalhos: dict[str, str] | None = None,
) -> tuple:
    """Identidade efetiva de uma requisição, pela mesma canonicalização que valida o destino.

    Esquema minúsculo, host IDNA minúsculo sem ponto final, porta padrão removida, caminho com
    percent-encoding canônico, fragmento descartado. A query vai EXATAMENTE como enviada (a ordem e a
    codificação dos parâmetros são do servidor, não do cliente; FIX13/F-16). Entram também o método, o
    corpo e os cabeçalhos definidos pelo chamador (nomes em minúsculas, ordenados): o servidor pode
    variar a representação por eles. Cache e bloqueio da guarda de execução usam só esta função.
    """
    parsed = urlsplit(url)
    esquema = parsed.scheme.lower()
    try:
        porta = parsed.port
    except ValueError:
        porta = None
    if porta == {"https": 443, "http": 80}.get(esquema):
        porta = None
    host = _host_canonico(parsed)
    if porta is not None:
        host = f"{host}:{porta}"
    campos = tuple(sorted((str(n).strip().lower(), str(v)) for n, v in (cabecalhos or {}).items()))
    return (metodo.upper(), esquema, host, _percent_canonico(parsed.path) or "/", parsed.query, corpo or b"", campos)


def _origin(url: str) -> tuple[str, str, int]:
    parsed = urlsplit(url)
    host = _host_canonico(parsed)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.scheme.lower(), host, port


def _path_allowed(
    host: str,
    target: str,
    decoded_path: str,
    allowed_path_prefixes: dict[str, tuple[str, ...]] | None,
) -> bool:
    if not allowed_path_prefixes or host not in allowed_path_prefixes:
        return True
    prefixes = allowed_path_prefixes[host]
    if type(prefixes) is not tuple or not prefixes:
        raise ValueError("allowed_path_prefixes inválido")
    for prefix in prefixes:
        if (
            not isinstance(prefix, str)
            or not prefix.startswith("/")
            or prefix == "/"
        ):
            raise ValueError("allowed_path_prefixes inválido")
    return any(
        decoded_path.lower().startswith(prefix.lower())
        and target.lower().startswith(prefix.lower())
        for prefix in prefixes
    )


def _mime_allowed(mime: str, allowed_mimes: frozenset[str]) -> bool:
    """Aceita apenas igualdade do tipo base (ex.: application/json ≠ application/json-unexpected)."""
    return mime in allowed_mimes


@dataclass
class Session:
    """Sessão efêmera com CookieJar em memória (escopo de uma consulta).

    Cookies nunca entram em recibos HTTP (`Response.headers` / `HTTPMetadata`).
    """

    _jar: CookieJar = field(default_factory=CookieJar, repr=False, init=False)

    def cookie_header(self, url: str) -> str | None:
        req = _UrlLibRequest(url)
        self._jar.add_cookie_header(req)
        return req.get_header("Cookie") or None

    def absorb_response(self, url: str, response) -> None:
        """Incorpora Set-Cookie da resposta bruta; não altera metadados de recibo."""
        from http.cookiejar import Cookie

        host = (urlsplit(url).hostname or "").lower()
        path = urlsplit(url).path or "/"
        rows = []
        getheaders = getattr(response, "getheaders", None)
        if callable(getheaders):
            rows = getheaders()
        for name, value in rows:
            if str(name).lower() != "set-cookie" or not value:
                continue
            parts = [p.strip() for p in str(value).split(";")]
            if not parts or "=" not in parts[0]:
                continue
            cname, cvalue = parts[0].split("=", 1)
            cname, cvalue = cname.strip(), cvalue.strip()
            if not cname:
                continue
            cpath = path.rsplit("/", 1)[0] or "/"
            for attr in parts[1:]:
                if "=" in attr and attr.split("=", 1)[0].strip().lower() == "path":
                    cpath = attr.split("=", 1)[1].strip() or "/"
            try:
                cookie = Cookie(
                    version=0,
                    name=cname,
                    value=cvalue,
                    port=None,
                    port_specified=False,
                    domain=host,
                    domain_specified=bool(host),
                    domain_initial_dot=False,
                    path=cpath,
                    path_specified=True,
                    secure=urlsplit(url).scheme == "https",
                    expires=None,
                    discard=True,
                    comment=None,
                    comment_url=None,
                    rest={},
                    rfc2109=False,
                )
                self._jar.set_cookie(cookie)
            except Exception:
                continue

    def has_cookie(self, name: str) -> bool:
        target = name.upper()
        return any(c.name.upper() == target for c in self._jar)


# portado de freoa-verifica/core.py:validate_reference
def validate_reference(
    url: str,
    allowed_hosts: frozenset[str],
    *,
    allowed_path_prefixes: dict[str, tuple[str, ...]] | None = None,
) -> tuple[str, str]:
    """Valida sintaxe e política de host/caminho sem acesso à rede."""
    if any(not 33 <= ord(char) <= 126 for char in url):
        raise BlockedHost("URL deve usar ASCII imprimível; percent-encode UTF-8")
    try:
        parsed = urlsplit(url)
        host = _host_canonico(parsed)
        port = parsed.port
    except ValueError as exc:
        raise BlockedHost(str(exc)) from exc
    if parsed.scheme != "https" or host not in allowed_hosts or port not in (None, 443):
        raise BlockedHost("HTTPS em host permitido e porta 443 obrigatórios")
    if parsed.username or parsed.password or parsed.fragment or "\\" in url:
        raise BlockedHost("Componente de URL não suportado")
    target = parsed.path or "/"
    decoded_path = unquote(target)
    if any(part in (".", "..") for part in decoded_path.split("/")) or "\\" in decoded_path:
        raise BlockedHost("Caminho ambíguo")
    if not _path_allowed(host, target, decoded_path, allowed_path_prefixes):
        raise BlockedHost("caminho fora do escopo permitido para o host")
    if parsed.query:
        target += "?" + parsed.query
    return host, target


def revalidar_captura(
    resp: "Response",
    *,
    allowed_hosts: frozenset[str],
    allowed_path_prefixes: dict[str, tuple[str, ...]] | None = None,
    allowed_mimes: frozenset[str] | None = None,
    max_bytes: int = MAX_BYTES,
    max_redirects: int = MAX_REDIRECTS,
) -> None:
    """Confere uma captura já feita contra a política da chamada ATUAL, sem rede (FIX11/F-16).

    Mesmas verificações que `fetch` aplica ao vivo, com as mesmas exceções: host e caminho da URL pedida
    e de cada redirecionamento, número de redirecionamentos, MIME e tamanho (declarado e recebido).
    Levanta a exceção que a chamada receberia sem cache.
    """
    mimes = DEFAULT_ALLOWED_MIMES if allowed_mimes is None else allowed_mimes
    for alvo in (resp.url, *resp.redirects):
        validate_reference(alvo, allowed_hosts, allowed_path_prefixes=allowed_path_prefixes)
    if len(resp.redirects) > max_redirects:
        raise BlockedHost("Limite de redirecionamentos excedido")
    if not _mime_allowed(resp.mime, mimes):
        raise RespostaInvalida(f"MIME não permitido: {resp.mime or '(ausente)'}", http=resp.http)
    declarado = resp.headers.get("content-length")
    if declarado is not None and declarado.isdigit() and int(declarado) > max_bytes:
        raise TooLarge("Corpo declarado acima do limite", http=resp.http)
    if resp.size > max_bytes:
        raise TooLarge("Corpo baixado acima do limite", http=resp.http)


# portado de freoa-verifica/core.py:_public_unicast
def _public_unicast(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if not ip.is_global or ip.is_multicast:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        return (
            ip in ipaddress.ip_network("2000::/3")
            and ip not in ipaddress.ip_network("2002::/16")
            and ip not in ipaddress.ip_network("2001::/32")
            and ip.ipv4_mapped is None
        )
    return True


# portado de freoa-verifica/core.py:validate_url
def validate_url(
    url: str,
    allowed_hosts: frozenset[str],
    *,
    timeout: float = DNS_TIMEOUT,
    allowed_path_prefixes: dict[str, tuple[str, ...]] | None = None,
) -> tuple[str, str, str]:
    """Valida referência e resolve DNS; recusa endereços privados/não unicast."""
    host, target = validate_reference(
        url, allowed_hosts, allowed_path_prefixes=allowed_path_prefixes
    )
    slots = _DNS_SLOTS
    if not slots.acquire(blocking=False):
        raise Timeout("Limite de concorrência DNS atingido")
    resolved: Queue = Queue(maxsize=1)

    def resolve() -> None:
        try:
            resolved.put((socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM), None))
        except Exception as exc:
            resolved.put((None, exc))
        finally:
            slots.release()

    try:
        threading.Thread(target=resolve, daemon=True).start()
    except Exception:
        slots.release()
        raise
    try:
        records, error = resolved.get(timeout=max(0.0, min(timeout, DNS_TIMEOUT)))
    except Empty as exc:
        raise Timeout("Prazo de DNS esgotado") from exc
    if error is not None:
        # Falha de infraestrutura, não de política: fonte_fora, repetível enquanto nada foi recebido.
        raise TransportError(f"Falha de DNS: {error}") from error
    addresses = sorted({record[4][0] for record in records})
    if not addresses or any(not _public_unicast(ip) for ip in addresses):
        raise BlockedHost("DNS retornou endereço inseguro ou não suportado")
    return host, target, addresses[0]


# portado de freoa-verifica/core.py:PinnedHTTPSConnection
class _LeitorObservado(io.RawIOBase):
    """Leitura crua do soquete que sinaliza `iniciada` no primeiro byte recebido (FIX7/F-06).

    Observa `recv_into`, abaixo do buffer do `http.client`: linha de status ou cabeçalho incompletos
    já contam como resposta iniciada.
    """

    def __init__(self, soquete, estado: "_EstadoChamada") -> None:
        super().__init__()
        # `makefile` sem buffer mantém a contagem de referências que adia o fechamento do soquete.
        self._cru = soquete.makefile("rb", buffering=0)
        self._estado = estado

    def readable(self) -> bool:
        return True

    def readinto(self, b):
        n = self._cru.readinto(b)
        if n:
            self._estado.resposta_iniciada = True
            self._estado.bytes_recebidos += n
            if self._estado.cru is not None:
                self._estado.cru += b[:n]
        return n

    def close(self) -> None:
        try:
            self._cru.close()
        finally:
            super().close()


class _SoqueteObservado:
    """Delega ao soquete real; só `makefile` muda, para observar o primeiro byte da resposta."""

    def __init__(self, soquete, estado: "_EstadoChamada") -> None:
        self._soquete = soquete
        self._estado = estado

    def makefile(self, *a, **kw):
        return io.BufferedReader(_LeitorObservado(self._soquete, self._estado))

    def __getattr__(self, nome):
        return getattr(self._soquete, nome)


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, *, timeout: float = 10.0):
        super().__init__(host, 443, timeout=timeout, context=ssl.create_default_context())
        self.ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self.ip, 443), self.timeout)
        self.sock = self._context.wrap_socket(
            self.sock, server_hostname=self.host, do_handshake_on_connect=False
        )
        remaining = getattr(self, "capture_deadline", time.monotonic() + self.timeout) - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Prazo esgotado antes do handshake TLS")
        self.sock.settimeout(min(self.timeout, remaining))
        self.sock.do_handshake()


@dataclass
class TokenBucket:
    """Limitador simples por host (tokens/segundo)."""

    rate: float = 1.0
    capacity: float = 1.0
    tokens: float = field(default=1.0, init=False)
    updated: float = field(default_factory=time.monotonic, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def acquire(self, *, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self.updated
                self.updated = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / self.rate if self.rate > 0 else timeout
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Timeout("Rate limit: prazo esgotado")
            time.sleep(min(wait, remaining))


@dataclass
class CircuitBreaker:
    """Abre após N falhas consecutivas; permanece aberto por cooldown segundos."""

    failure_threshold: int = 5
    cooldown: float = 120.0
    failures: int = field(default=0, init=False)
    opened_at: float | None = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def before_call(self) -> None:
        with self._lock:
            if self.opened_at is not None:
                if time.monotonic() - self.opened_at < self.cooldown:
                    raise Timeout("Circuit breaker aberto para este host")
                self.opened_at = None
                self.failures = 0

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.opened_at = time.monotonic()


_RATE_LIMITERS: dict[str, TokenBucket] = {}
_CIRCUIT_BREAKERS: dict[str, CircuitBreaker] = {}
_GUARD_LOCK = threading.Lock()
_DEFAULT_RATE = float(os.environ.get("FV_RATE_LIMIT", "1.0"))
# O BCB passou a recusar (HTTP 400) o notebook após três leituras completas a 1 req/s.
_HOST_RATES = {"www.bcb.gov.br": float(os.environ.get("FV_RATE_LIMIT_BCB", "0.2"))}


def _rate_limiter(host: str) -> TokenBucket:
    with _GUARD_LOCK:
        if host not in _RATE_LIMITERS:
            rate = _HOST_RATES.get(host, _DEFAULT_RATE)
            _RATE_LIMITERS[host] = TokenBucket(rate=rate, capacity=max(1.0, rate))
        return _RATE_LIMITERS[host]


def _circuit_breaker(host: str) -> CircuitBreaker:
    with _GUARD_LOCK:
        if host not in _CIRCUIT_BREAKERS:
            _CIRCUIT_BREAKERS[host] = CircuitBreaker()
        return _CIRCUIT_BREAKERS[host]


def reset_guards() -> None:
    """Limpa limitadores e breakers (uso em testes)."""
    with _GUARD_LOCK:
        _RATE_LIMITERS.clear()
        _CIRCUIT_BREAKERS.clear()


def circuit_retry_after() -> float:
    """Espera conservadora até a reabertura dos circuitos ativos."""
    with _GUARD_LOCK:
        breakers = list(_CIRCUIT_BREAKERS.values())
    return max([0.0] + [max(0.0, b.cooldown - (time.monotonic() - b.opened_at))
                        for b in breakers if b.opened_at is not None])


REPETICOES_PADRAO = 2
_STATUS_REPETIVEIS = frozenset({502, 503, 504})
_dormir = time.sleep  # trocáveis nos testes
_sortear = random.uniform


def _retry_after(falha: HTTPStatusError) -> float | None:
    """Segundos de `Retry-After` (inteiro ou data HTTP); None se ausente ou inválido."""
    valor = dict(falha.http.headers).get("retry-after") if falha.http is not None else None
    if valor is None:
        return None
    if valor.isdigit():
        return float(valor)
    try:
        alvo = parsedate_to_datetime(valor)
    except (ValueError, TypeError, OverflowError):
        return None
    return max(0.0, (alvo - datetime.now(timezone.utc)).total_seconds())


_STATUS_REDIRECIONAMENTO = (301, 302, 303, 307, 308)


@dataclass
class _EstadoChamada:
    """Progresso observável de uma chamada lógica (FIX9/F-06, F-13).

    Criado uma vez em `fetch` e compartilhado por todos os saltos, pelo controlador externo de
    prazo, pela validação/resolução de cada salto e pela leitura de desafio. Só `reiniciar`
    (uma repetição decidida pelo próprio transporte, que é um novo percurso) o zera.
    """

    prazo: float = float("inf")  # relógio monotônico do prazo total
    resposta_iniciada: bool = False  # qualquer byte de resposta recebido em qualquer salto
    saltos: list = field(default_factory=list)  # [{url, status}] de cada salto que respondeu
    bytes_recebidos: int = 0
    ultimo_status: int | None = None
    http: HTTPMetadata | None = None  # recibo do último salto que respondeu
    # por salto
    lendo_status: bool = False
    lento: bool = False
    expirou: bool = False
    cru: bytearray | None = None  # bytes do soquete até a validação dos cabeçalhos (FIX12/F-13)

    def reiniciar(self) -> None:
        self.resposta_iniciada = False
        self.saltos = []
        self.bytes_recebidos = 0
        self.ultimo_status = None
        self.novo_salto()

    def novo_salto(self) -> None:
        self.http = None
        self.lendo_status = False
        self.lento = False
        self.expirou = False
        self.cru = bytearray()


def _classificar(exc: BaseException, estado: _EstadoChamada) -> tuple[BaseException, bool]:
    """Único ponto do transporte que converte exceção em categoria. Devolve (falha, repetível).

    Regra: resposta iniciada em qualquer momento da chamada (byte recebido em qualquer salto) torna
    toda falha posterior `RespostaInvalida` (`resposta_inesperada`), nunca repetível. Sem nenhum byte
    de resposta, falha de conexão/DNS/prazo é `fonte_fora` e repetível. Status 502/503/504 sem
    desafio é repetível. Exceção que não é de transporte volta intacta, não repetível.
    """
    if (
        estado.lendo_status
        and isinstance(exc, http.client.HTTPException)
        and not isinstance(exc, OSError)
    ):
        # LineTooLong, BadStatusLine, protocolo desconhecido, cabeçalhos em excesso: houve bytes.
        estado.resposta_iniciada = True
    if isinstance(exc, TransportError):
        falha: BaseException = exc
        if type(exc) in (TransportError, Timeout) and estado.resposta_iniciada:
            falha = RespostaInvalida(str(exc), http=exc.http)
            falha.__cause__ = exc.__cause__ or exc
    elif isinstance(exc, (OSError, TimeoutError, ssl.SSLError, http.client.HTTPException)):
        if estado.lento:
            falha = TransporteLento("Taxa de leitura abaixo do mínimo")
        elif estado.resposta_iniciada:
            falha = RespostaInvalida(str(exc))
        elif (
            isinstance(exc, TimeoutError) or estado.expirou or time.monotonic() >= estado.prazo
        ):
            falha = Timeout(str(exc))
        else:
            falha = TransportError(str(exc))
        falha.__cause__ = exc
    else:
        return exc, False
    if falha.http is None:
        falha.http = estado.http
    if not falha.saltos and any(s["status"] in _STATUS_REDIRECIONAMENTO for s in estado.saltos):
        falha.saltos = list(estado.saltos)
    if isinstance(falha, HTTPStatusError):
        repetivel = falha.status in _STATUS_REPETIVEIS and not falha.desafio
    else:
        repetivel = type(falha) in (TransportError, Timeout)
    return falha, repetivel


def _espera_antes_de_repetir(falha: Exception, repeticoes: int, deadline: float) -> float | None:
    """Espera até a próxima tentativa, ou None se a espera não cabe no prazo (a falha já é repetível)."""
    espera = _retry_after(falha) if isinstance(falha, HTTPStatusError) else None
    if espera is None:
        base = float(2**repeticoes)  # 1s, 2s
        espera = base + _sortear(0.0, 0.25 * base)
    return espera if espera < deadline - time.monotonic() else None


def _fetch_once(url: str, *, estado: _EstadoChamada | None = None, **kw) -> Response:
    """Uma tentativa de captura (com redirecionamentos); toda falha passa por `_classificar` (FIX9).

    Regra: interrupção por taxa, tamanho ou prazo depois de recebido o status/cabeçalho é
    `RespostaInvalida` (categoria `resposta_inesperada`) e nunca se repete; só falha sem status
    recebido é `fonte_fora` e repetível (e só dentro de `fetch`, único lugar que repete).

    | exceção                                    | status recebido? | categoria            | repetível |
    |--------------------------------------------|------------------|----------------------|-----------|
    | HTTPStatusError 502/503/504, sem desafio   | sim              | fonte_fora           | sim       |
    | HTTPStatusError com desafio / demais status| sim              | desafio / conforme   | não       |
    | RespostaInvalida (MIME, framing, encoding) | sim              | resposta_inesperada  | não       |
    | TooLarge (declarado ou baixado)            | sim              | resposta_inesperada  | não       |
    | TransporteLento (taxa mínima)              | sim              | resposta_inesperada  | não       |
    | EmptyBody                                  | sim              | resposta_inesperada  | não       |
    | OSError/SSL/HTTP com resposta iniciada     | sim              | resposta_inesperada  | não       |
    | HTTPException ao ler status/cabeçalhos     | sim (bytes)      | resposta_inesperada  | não       |
    | (LineTooLong, BadStatusLine, protocolo     |                  |                      |           |
    |  desconhecido, cabeçalhos em excesso)      |                  |                      |           |
    | prazo/reset com cabeçalho incompleto       | sim (qualquer    | resposta_inesperada  | não       |
    |  (≥1 byte lido do soquete)                 |  byte)           |                      |           |
    | RemoteDisconnected (fechou sem nenhum byte)| não              | fonte_fora           | sim       |
    | prazo esgotado no corpo (aqui ou em fetch) | sim              | resposta_inesperada  | não       |
    | BlockedHost (política, redirecionamento)   | n/a              | recusa de política   | não       |
    | Timeout (prazo/DNS/soquete antes do status)| não              | fonte_fora           | sim       |
    | TransportError (conexão, TLS, reset)       | não              | fonte_fora           | sim       |

    Qualquer status ou byte recebido em QUALQUER salto da chamada (inclusive em falha de DNS,
    validação, prazo ou fechamento de um salto posterior) torna a falha `resposta_inesperada`.
    """
    estado = estado if estado is not None else _EstadoChamada(prazo=kw["deadline"])
    try:
        return _percorrer(url, estado=estado, **kw)
    except Exception as exc:
        falha, _ = _classificar(exc, estado)
        if falha is exc:
            raise
        raise falha from exc


def _percorrer(
    url: str,
    *,
    estado: _EstadoChamada,
    method: str,
    body: bytes | None,
    caller_headers: dict[str, str],
    allowed_hosts: frozenset[str],
    allowed_path_prefixes: dict[str, tuple[str, ...]] | None,
    allowed_mimes: frozenset[str],
    max_bytes: int,
    max_redirects: int,
    deadline: float,
    min_bytes_per_second: float | None = None,
    session: Session | None = None,
    sink: BinaryIO | None = None,
    antes_do_salto: Callable[[str], None] | None = None,
) -> Response:
    """Percurso bruto dos saltos: levanta a exceção original; `_fetch_once` a classifica."""
    original = url
    redirects: list[str] = []
    saltos = estado.saltos  # progresso é da chamada lógica: o status de qualquer salto vale para a cadeia
    current_method = method
    current_body = body
    req_extra = dict(caller_headers)

    for _ in range(max_redirects + 1):
        estado.novo_salto()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Timeout("Prazo de captura esgotado")
        host, target, ip = validate_url(
            url,
            allowed_hosts,
            timeout=remaining,
            allowed_path_prefixes=allowed_path_prefixes,
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Timeout("Prazo de captura esgotado")
        # Prazo do soquete acompanha o timeout da captura (CKAN/STJ ~25–90s).
        connection = PinnedHTTPSConnection(host, ip, timeout=max(1.0, remaining))
        connection.capture_deadline = deadline
        connection.response_class = _RespostaEstrita
        timed_out = threading.Event()
        slow = threading.Event()
        finished = threading.Event()
        rate_timer = None
        network_state: dict = {"socket": None}

        def expire(expired=timed_out, conn=connection, state=network_state) -> None:
            expired.set()
            estado.expirou = True
            active_socket = state["socket"] or getattr(conn, "sock", None)
            if active_socket is not None:
                try:
                    if isinstance(active_socket, socket.socket):
                        socket.socket.shutdown(active_socket, socket.SHUT_RDWR)
                    else:
                        active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        timer = threading.Timer(remaining, expire)
        timer.daemon = True
        timer.start()
        response = None
        try:
            req_headers = _contact_headers()
            req_headers.update(req_extra)
            req_headers["Host"] = host
            if session is not None:
                # Cookie da sessão por hop (não misturar com recibo).
                req_headers.pop("Cookie", None)
                cookie = session.cookie_header(url)
                if cookie:
                    req_headers["Cookie"] = cookie
            connection.request(
                current_method, target, body=current_body, headers=req_headers
            )
            network_state["socket"] = getattr(connection, "sock", None)
            if getattr(connection, "sock", None) is not None:
                connection.sock = _SoqueteObservado(connection.sock, estado)
            estado.lendo_status = True
            response = connection.getresponse()
            estado.lendo_status = False
            estado.resposta_iniciada = True
            estado.ultimo_status = response.status
            estado.http = _failure_http(response)
            saltos.append({"url": url, "status": response.status})
            if session is not None:
                session.absorb_response(url, response)
            cru, estado.cru = bytes(estado.cru or b""), None
            declared_size = _validar_framing(response, cru)  # todo status, antes de qualquer classificação
            # Único ponto, qualquer status (FIX14/F-18): o transporte não decodifica corpo comprimido, e
            # "não examinei" nunca vale "sem marcador"; logo, qualquer codificação além de identity é inválida.
            encoding = response.getheader("Content-Encoding")
            if encoding is not None and encoding.strip().lower() != "identity":
                raise RespostaInvalida(
                    "Apenas Content-Encoding identity é suportado",
                    http=_failure_http(response),
                )
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise BlockedHost(
                        "Redirecionamento sem Location",
                        http=_failure_http(response),
                    )
                next_url = urljoin(url, location)
                redirects.append(next_url)
                validate_reference(
                    next_url,
                    allowed_hosts,
                    allowed_path_prefixes=allowed_path_prefixes,
                )
                same_origin = _origin(url) == _origin(next_url)
                if response.status in (301, 302, 303):
                    if current_method == "POST":
                        current_method = "GET"
                        current_body = None
                elif response.status in (307, 308):
                    if not same_origin:
                        raise BlockedHost(
                            "307/308 entre origens distintas não permitido",
                            http=_failure_http(response),
                        )
                if not same_origin:
                    req_extra = {
                        name: value
                        for name, value in req_extra.items()
                        if name.lower() not in _HOP_CREDENTIAL_HEADERS
                    }
                if antes_do_salto is not None:
                    # Controlador externo (guarda de execução): pode recusar o host seguinte, sem requisição.
                    try:
                        antes_do_salto(_host_canonico(urlsplit(next_url)))
                    except Exception as recusa:
                        recusa.sem_requisicao = True  # não é falha da fonte: o breaker não conta
                        raise
                url = next_url
                continue
            if response.status != 200:
                raise HTTPStatusError(
                    response.status,
                    http=_failure_http(response),
                    desafio=_desafio_na_resposta(response),
                )
            raw_type = response.getheader("Content-Type", "") or ""
            if "," in raw_type:
                raise RespostaInvalida(
                    "Content-Type ambíguo", http=_failure_http(response)
                )
            mime = raw_type.split(";", 1)[0].strip().lower()
            if not mime or not _mime_allowed(mime, allowed_mimes):
                raise RespostaInvalida(
                    f"MIME não permitido: {mime or '(ausente)'}",
                    http=_failure_http(response),
                )
            if declared_size is not None and declared_size > max_bytes:
                raise TooLarge(
                    "Corpo declarado acima do limite",
                    http=_failure_http(response),
                )
            chunks: list[bytes] = []
            digest = hashlib.sha256()
            size = 0
            window_start = time.monotonic()
            window_size = 0

            def check_rate() -> None:
                nonlocal window_start, window_size, rate_timer
                if finished.is_set():
                    return
                now = time.monotonic()
                if (size - window_size) / max(now - window_start, 0.001) < (MIN_BYTES_PER_SECOND if min_bytes_per_second is None else min_bytes_per_second):
                    slow.set()
                    estado.lento = True
                    expire()
                    return
                window_start, window_size = now, size
                rate_timer = threading.Timer(SLOW_WINDOW, check_rate)
                rate_timer.daemon = True
                rate_timer.start()

            rate_timer = threading.Timer(SLOW_WINDOW, check_rate)
            rate_timer.daemon = True
            rate_timer.start()
            while True:
                if slow.is_set():
                    raise TransporteLento("Taxa de leitura abaixo do mínimo", http=_failure_http(response))
                if timed_out.is_set() or time.monotonic() >= deadline:
                    raise RespostaInvalida(
                        "Prazo de captura esgotado após o início da resposta",
                        http=_failure_http(response),
                    )
                # read(n) pode aguardar n bytes apesar de receber dados continuamente.
                # read1 devolve os bytes disponíveis, permitindo medir o progresso real.
                reader = getattr(response, "read1", response.read)
                chunk = reader(min(65536, max_bytes + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise TooLarge(
                        "Corpo baixado acima do limite",
                        http=_failure_http(response),
                    )
                digest.update(chunk)
                if sink is None:
                    chunks.append(chunk)
                else:
                    sink.write(chunk)
            if slow.is_set():
                raise TransporteLento("Taxa de leitura abaixo do mínimo", http=_failure_http(response))
            if timed_out.is_set() or time.monotonic() >= deadline:
                raise RespostaInvalida(
                    "Prazo de captura esgotado após o início da resposta",
                    http=_failure_http(response),
                )
            if declared_size is not None and size != declared_size:
                raise RespostaInvalida(
                    "Content-Length difere dos bytes recebidos",
                    http=_failure_http(response),
                )
            payload = b"".join(chunks)
            if current_method == "GET" and not size:
                raise EmptyBody("GET com corpo vazio", http=_failure_http(response))
            http_meta = observe_http_response(response)
            return Response(
                url=original,
                final_url=url,
                status=response.status,
                headers=dict(http_meta.headers),
                body=payload,
                sha256=digest.hexdigest(),
                size=size,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                redirects=list(redirects),
                mime=mime,
                http=http_meta,
            )
        finally:
            finished.set()
            if rate_timer is not None:
                rate_timer.cancel()
            timer.cancel()
            if response is not None:
                close_response = getattr(response, "close", None)
                if close_response is not None:
                    close_response()
            connection.close()
    raise BlockedHost("Limite de redirecionamentos excedido")


def fetch(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    allowed_hosts: frozenset[str],
    allowed_path_prefixes: dict[str, tuple[str, ...]] | None = None,
    allowed_mimes: frozenset[str] | None = None,
    max_bytes: int = MAX_BYTES,
    timeout: float = 30.0,
    min_bytes_per_second: float | None = None,
    max_redirects: int = MAX_REDIRECTS,
    session: Session | None = None,
    sink: str | os.PathLike | None = None,
    repeticao: int = REPETICOES_PADRAO,
    idempotente: bool = False,
    antes_do_salto: Callable[[str], None] | None = None,
) -> Response:
    """Baixa URL HTTPS com IP fixado, validando cada redirecionamento.

    `sink` grava atomicamente em arquivo; body vazio, size e sha256 preenchidos.
    `session` opcional: CookieJar efêmero por consulta (cookies fora dos recibos).
    `repeticao`: máximo de repetições (além da primeira tentativa) após 502/503/504 sem marcador
    de desafio ou falha de conexão/leitura; POST só repete com `idempotente=True`. 403, 429 e
    desafio nunca repetem. A espera cabe no prazo total; senão a falha original é devolvida.
    `antes_do_salto(host)`: chamado antes de seguir cada redirecionamento; se levantar, a cadeia
    termina com essa exceção, sem nova requisição.
    """
    if isinstance(repeticao, bool) or not isinstance(repeticao, int) or repeticao < 0:
        raise ValueError("repeticao inválida")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= (4 * 1024**3 if sink is not None else 50 * 1024 * 1024):
        raise ValueError("max_bytes inválido")
    if not isinstance(max_redirects, int) or max_redirects < 0:
        raise ValueError("max_redirects inválido")
    method = method.upper()
    if method not in {"GET", "HEAD", "POST"}:
        raise ValueError("método HTTP não suportado")
    mimes = DEFAULT_ALLOWED_MIMES if allowed_mimes is None else allowed_mimes
    if not mimes or any(
        not isinstance(m, str) or not re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", m)
        for m in mimes
    ):
        raise ValueError("allowed_mimes inválido")
    if min_bytes_per_second is not None and not 1 <= min_bytes_per_second <= 1024 * 1024:
        raise ValueError("taxa mínima inválida")
    caller_headers = _normalize_caller_headers(headers)

    # Prazo total inicia antes do rate limiter; a espera conta no prazo.
    deadline = time.monotonic() + timeout
    slots = _CAPTURE_SLOTS
    if not slots.acquire(blocking=False):
        raise Timeout("Limite de concorrência de captura atingido")
    outcome: Queue = Queue(maxsize=1)
    cancelled = threading.Event()
    worker_done = threading.Event()
    estado = _EstadoChamada(prazo=deadline)  # uma vez por chamada lógica; todo salto e o controlador o veem
    temporary: list[Path] = []

    def worker() -> None:
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Timeout("Prazo de captura esgotado")
            host_hint, _ = validate_reference(
                url, allowed_hosts, allowed_path_prefixes=allowed_path_prefixes
            )
            limiter = _rate_limiter(host_hint)
            breaker = _circuit_breaker(host_hint)
            breaker.before_call()
            try:
                output = None
                if sink is not None:
                    output = tempfile.NamedTemporaryFile(
                        dir=Path(sink).parent, prefix=".fv-download-", delete=False
                    )
                    temporary.append(Path(output.name))
                try:
                    repeticoes = 0
                    while True:
                        limiter.acquire(timeout=max(0.0, deadline - time.monotonic()))
                        if output is not None:
                            output.seek(0)
                            output.truncate()
                        try:
                            result = _fetch_once(
                                url,
                                method=method,
                                body=body,
                                caller_headers=caller_headers,
                                allowed_hosts=allowed_hosts,
                                allowed_path_prefixes=allowed_path_prefixes,
                                allowed_mimes=mimes,
                                max_bytes=max_bytes,
                                max_redirects=max_redirects,
                                deadline=deadline,
                                **({"min_bytes_per_second": min_bytes_per_second} if min_bytes_per_second is not None else {}),
                                session=session,
                                estado=estado,
                                antes_do_salto=antes_do_salto,
                                **({"sink": output} if output is not None else {}),
                            )
                            break
                        except Exception as erro:
                            falha, repetivel = _classificar(erro, estado)
                            espera = None
                            if repetivel and repeticoes < repeticao and (method != "POST" or idempotente):
                                espera = _espera_antes_de_repetir(falha, repeticoes, deadline)
                            if espera is None:
                                if falha is erro:
                                    raise
                                raise falha from erro
                            repeticoes += 1
                            estado.reiniciar()  # repetição decidida pelo transporte = novo percurso
                            _dormir(espera)
                finally:
                    if output is not None:
                        output.close()
                breaker.record_success()
                outcome.put((result, None))
            except Exception as exc:
                if getattr(exc, "sem_requisicao", False):
                    pass
                elif isinstance(exc, HTTPStatusError) and exc.status in {404,410}:
                    breaker.record_success()
                else:
                    breaker.record_failure()
                outcome.put((None, exc))
        except Exception as exc:
            outcome.put((None, exc))
        finally:
            worker_done.set()
            if cancelled.is_set() and temporary:
                temporary[0].unlink(missing_ok=True)
            slots.release()

    try:
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
    except Exception:
        slots.release()
        raise

    thread.join(timeout=max(0.0, deadline - time.monotonic()))
    if thread.is_alive():
        cancelled.set()
        if worker_done.is_set() and temporary:
            temporary[0].unlink(missing_ok=True)
        raise _classificar(Timeout("Prazo de captura esgotado"), estado)[0]
    try:
        result, error = outcome.get_nowait()
    except Empty as exc:
        raise Timeout("Prazo de captura esgotado") from exc
    try:
        if error is not None:
            raise error
        if sink is not None:
            if time.monotonic() >= deadline:
                raise Timeout("Prazo de captura esgotado")
            os.replace(temporary[0], sink)
        return result
    finally:
        if temporary:
            temporary[0].unlink(missing_ok=True)
