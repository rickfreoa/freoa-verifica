"""Leitura do robots.txt na S0 segundo o RFC 9309 (decisão 0071).

Módulo puro: sem rede, sem arquivo. Recebe status, Content-Type e corpo (ou o registro `.captura.json` de uma
sonda) e devolve a leitura do robots do host e, para cada URL, a decisão: seguir, caminho vedado, sem restrições
ou barreira, sempre com o motivo. É importado só pelo instrumento de captura (`freoa_verifica.captura`) e pelo
orquestrador oficial (`scripts/s0_orquestrar.py`). O serviço, o MCP e a CLI `fv` não o importam (teste estrutural
em `tests/test_robots_s0.py`): é ferramenta de sonda, não parte do produto.

Regra (decisão 0071):

| Resposta                                                                        | Leitura                          |
|---------------------------------------------------------------------------------|----------------------------------|
| 200 com regras interpretáveis (grupo `User-agent` e só diretivas conhecidas)    | regras: obedecer                 |
| 200 sem regras interpretáveis (HTML, outro MIME, vazio, só comentários)         | sem restrições (Content-Type e   |
|                                                                                 | sha256 do corpo registrados)     |
| 404, 410                                                                        | sem restrições (ausência)        |
| 401, 403, 429, desafio, WAF, 5xx, timeout, erro de transporte, redirecionamento | barreira                         |
| outro 4xx, ou resposta que o transporte recusou                                 | barreira (conservadorismo)       |

Lacunas da regra, resolvidas aqui por conservadorismo (regra invariável 2) e registradas na decisão 0071: 200 com
`Allow`/`Disallow` que não é interpretável (sem `User-agent`, ou misturado a linhas desconhecidas) é barreira
(`regras_ambiguas`), e não "sem restrições". O `urllib.robotparser` não implementa `*`, `$` nem a precedência por
correspondência mais longa do RFC 9309; por isso a decisão por caminho só libera o que o `robotparser` e o
avaliador RFC deste módulo liberam (vedado se qualquer um vedar). Corpo 200 que não se examina com segurança (charset
que não fecha fora da exceção abaixo, NUL, UTF-16/32 sem BOM) é barreira `corpo_nao_interpretavel`, nunca "sem
restrições". Exceção (decisão do titular de 28/10/2026, 0071 item 5): corpo que não decodifica em UTF-8 estrito nem no
charset declarado é lido como charset legado ASCII-compatível só se não tem NUL, BOM nem padrão UTF-16/32 e todo byte
>= 0x80 está em comentário (depois de `#` na mesma linha); o resultado registra `charset_legado_em_comentario`.
"""

from __future__ import annotations

import hashlib
import re
import urllib.robotparser
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

from freoa_verifica.connectors.challenge import detect_challenge
from freoa_verifica.texto_resposta import texto_da_resposta, vista_bytes
from freoa_verifica.transport import RespostaInvalida

AGENTE = "freoa-verifica"  # produto do User-Agent identificado, usado na leitura do robots.txt

# O transporte só aceita MIMEs de uma lista (e recusa resposta sem Content-Type). Para o robots.txt a lista é
# larga, para poder gravar o corpo de qualquer resposta 200 como evidência; MIME fora dela, ou ausente, é recusa
# do transporte e vira barreira (`resposta_200_recusada`).
MIMES_ROBOTS = frozenset({
    "text/plain", "text/html", "application/octet-stream", "binary/octet-stream", "application/xhtml+xml",
    "application/xml", "text/xml", "application/json", "text/json", "text/css", "text/javascript",
    "application/javascript", "text/csv", "text/markdown", "application/pdf",
})

SEGUIR, VEDADO, SEM_RESTRICOES, BARREIRA = "seguir", "vedado", "sem_restricoes", "barreira"
REGRAS = "regras"  # estado da leitura: há regras a obedecer

# Diretivas aceitas como "conhecidas": as do RFC 9309 e as extensões comuns em robots reais (sem elas, um robots
# verdadeiro com `Host:` ou `Request-rate:` pareceria "sem regras" e o seu `Disallow` seria ignorado).
_CONHECIDAS = frozenset({
    "user-agent", "allow", "disallow", "sitemap", "crawl-delay", "host", "request-rate", "visit-time",
    "clean-param", "noindex", "nofollow", "cache-delay", "content-signal",
})
_DIRETIVA = re.compile(r"([A-Za-z][A-Za-z0-9-]*)\s*:")
_PARECE_HTML = re.compile(r"<\s*(?:!doctype|html|head|body|script|meta)\b", re.I)
SHA256_VAZIO = hashlib.sha256(b"").hexdigest()


@dataclass(frozen=True)
class Decisao:
    """Decisão para uma URL: `acao` em {seguir, vedado, sem_restricoes, barreira}, com motivo estável."""

    acao: str
    motivo: str
    detalhe: str = ""


@dataclass(frozen=True)
class LeituraRobots:
    """O que o robots.txt de um host determina. `estado`: `regras`, `sem_restricoes` ou `barreira`."""

    estado: str
    motivo: str
    detalhe: str = ""
    status: int | None = None
    content_type: str | None = None
    sha256: str | None = None
    regras: tuple[str, ...] = ()  # linhas do arquivo; só com estado `regras`
    marcador: str | None = None  # tipo do desafio, quando o motivo é `desafio_no_robots`
    charset_legado_em_comentario: bool = False  # corpo lido como charset legado ASCII-compatível (só em comentários)

    def decidir(self, url: str) -> Decisao:
        """Decisão para `url` (do mesmo host do robots): seguir, vedado, sem restrições ou barreira."""
        if self.estado == BARREIRA:
            return Decisao(BARREIRA, self.motivo, self.detalhe)
        if self.estado == SEM_RESTRICOES:
            return Decisao(SEM_RESTRICOES, self.motivo, self.detalhe)
        parser = urllib.robotparser.RobotFileParser()
        parser.parse(self.regras)
        parser.modified()  # sem isso `can_fetch` recusa tudo (nunca foi lido)
        pelo_parser = parser.can_fetch(AGENTE, url)
        pelo_rfc = _permitido_rfc(self.regras, url)
        if pelo_parser and pelo_rfc:
            return Decisao(SEGUIR, "regras_obedecidas", "nenhum Disallow aplicável ao caminho")
        quem = "robotparser" if not pelo_parser else "avaliador RFC 9309"
        return Decisao(VEDADO, "disallow_aplicavel", f"vedado pelo {quem}")


def _barreira(motivo: str, detalhe: str = "", **kw: Any) -> LeituraRobots:
    return LeituraRobots(BARREIRA, motivo, detalhe, **kw)


def _sem_restricoes(motivo: str, detalhe: str = "", **kw: Any) -> LeituraRobots:
    return LeituraRobots(SEM_RESTRICOES, motivo, detalhe, **kw)


def ler_robots(
    status: int | None, content_type: str | None, corpo: bytes | None, *, cabecalhos: Mapping[str, str] | None = None
) -> LeituraRobots:
    """Leitura do robots.txt a partir do que o host respondeu. `status` None = sem resposta HTTP (use `ler_do_registro`)."""
    if status is None:
        return _barreira("sem_resposta", "nenhum status recebido")
    if status == 200:
        return _ler_200(content_type, corpo, cabecalhos)
    if status in (404, 410):
        return _sem_restricoes(f"ausente_{status}", f"HTTP {status}: ausência de robots (RFC 9309, 2.3.1.3)", status=status)
    if status in (401, 403, 429) or 500 <= status <= 599:
        return _barreira(f"http_{status}", f"HTTP {status}: barreira", status=status)
    if 300 <= status <= 399:
        return _barreira("redirecionamento", f"HTTP {status} não seguido (um pedido, sem redirecionamento)", status=status)
    if 400 <= status <= 499:
        return _barreira(f"http_{status}_outro_4xx", f"HTTP {status}: 4xx fora de 401/403/404/410/429; barreira por "
                         "conservadorismo (decisão 0071)", status=status)
    return _barreira("status_inesperado", f"HTTP {status}", status=status)


def _texto(corpo: bytes, content_type: str | None) -> str | None:
    """Texto do corpo pela interpretação única, ou None se o charset não fecha (corpo que não se examina com segurança)."""
    try:
        return texto_da_resposta(corpo, content_type)
    except (RespostaInvalida, ValueError):
        return None


_SEPARADOR_LINHA = re.compile(rb"\r\n|\r|\n")  # fim de linha do RFC 9309 (2.2): CR, LF ou CRLF
# `str.splitlines` também parte nestes; o RFC não. Presentes no texto, o corpo não se examina com segurança
# (parecer PR #18 r2, B1): nunca viram linha nova, nem dentro de comentário.
_SEPARADOR_FORA_DO_RFC = re.compile("[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")
_BOMS = (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")
_CHARSET_LARGO = re.compile(r"charset\s*=\s*[\"']?\s*(utf-?(?:16|32)|ucs-?[24])", re.I)


def _texto_legado_em_comentario(corpo: bytes, content_type: str | None) -> str | None:
    """Texto do corpo em charset legado ASCII-compatível, só se todo byte >= 0x80 está em comentário; senão None.

    Decisão do titular de 28/10/2026 (0071, item 5). Recusa (None) com NUL, BOM, charset declarado de largura
    variável (UTF-16/32), ou nenhum byte >= 0x80 (não é caso de charset legado). Os bytes >= 0x80, todos em
    comentário, viram U+FFFD: não importa o que dizem, e assim `splitlines` não parte linha em U+0085.
    """
    if b"\x00" in corpo or corpo.startswith(_BOMS) or _CHARSET_LARGO.search(content_type or ""):
        return None
    if not any(b >= 0x80 for b in corpo):
        return None
    for linha in _SEPARADOR_LINHA.split(corpo):
        antes, marca, depois = linha.partition(b"#")
        if any(b >= 0x80 for b in antes):
            return None
    return "".join("\ufffd" if b >= 0x80 else chr(b) for b in corpo)


_LARGURAS_SEM_BOM = ("utf-16-le", "utf-16-be", "utf-32-le", "utf-32-be")


def _diretiva_escondida(corpo: bytes) -> bool:
    """Busca suplementar nos bytes: User-agent/Allow/Disallow em UTF-16 ou UTF-32 sem BOM (invisível no texto ASCII).

    Só acrescenta detecção: achar significa que há regras que a leitura não consegue obedecer; não achar nada
    não libera coisa alguma.
    """
    for codec in _LARGURAS_SEM_BOM:
        visto = str(corpo, codec, "ignore")  # busca de detecção, não interpretação do texto
        if any(_diretiva(ln) in ("user-agent", "allow", "disallow") for ln in _linhas_uteis(visto)):
            return True
    return False


def _tem_regras_no_texto(texto: str) -> bool:
    return any(_diretiva(ln) in ("user-agent", "allow", "disallow") for ln in _linhas_uteis(texto))


def _linhas_uteis(texto: str) -> list[str]:
    saida = []
    for bruta in texto.splitlines():
        linha = bruta.split("#", 1)[0].strip().lstrip("﻿").strip()
        if linha:
            saida.append(linha)
    return saida


def _diretiva(linha: str) -> str | None:
    m = _DIRETIVA.match(linha)
    return m.group(1).lower() if m and m.group(1).lower() in _CONHECIDAS else None


def interpretavel(texto: str) -> bool:
    """Ao menos um grupo `User-agent` e toda linha não vazia é comentário ou diretiva conhecida."""
    linhas = _linhas_uteis(texto)
    nomes = [_diretiva(ln) for ln in linhas]
    return "user-agent" in nomes and all(nomes)


def _desafio(corpo: bytes, content_type: str | None, cabecalhos: Mapping[str, str] | None) -> str | None:
    """Tipo do desafio pelos marcadores do projeto (`connectors.challenge`, sem lista própria), ou None."""
    try:
        achado = detect_challenge(status=200, headers=cabecalhos, body=corpo, content_type=content_type)
    except RespostaInvalida:
        achado = detect_challenge(status=200, headers=cabecalhos, body=vista_bytes(corpo))
    return (str(achado.args[0]) if achado.args else "desconhecido") if achado is not None else None


def _desafio_no_robots(tipo: str, base: dict[str, Any]) -> LeituraRobots:
    return _barreira("desafio_no_robots", f"200 com marcador de desafio ({tipo})", marcador=tipo, **base)


def _ler_200(content_type: str | None, corpo: bytes | None, cabecalhos: Mapping[str, str] | None) -> LeituraRobots:
    base = {"status": 200, "content_type": content_type}
    if corpo is None:  # passe final PR #18, B1: ausência de corpo não é corpo vazio
        return _barreira("corpo_ausente", "200 sem corpo examinado: barreira por conservadorismo (decisão 0071)", **base)
    if not corpo:
        return _sem_restricoes("200_corpo_vazio", "arquivo vazio: sem restrições", sha256=SHA256_VAZIO, **base)
    sha = hashlib.sha256(corpo).hexdigest()
    base["sha256"] = sha
    texto = _texto(corpo, content_type)
    legado = False
    if texto is None:
        texto = _texto_legado_em_comentario(corpo, content_type)
        legado = texto is not None
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    inexaminavel = texto is None or "\x00" in texto or bool(_SEPARADOR_FORA_DO_RFC.search(texto)) or (
        not _tem_regras_no_texto(texto) and _diretiva_escondida(corpo))
    if inexaminavel:  # nunca libera: a busca de marcador nos bytes só acrescenta detecção
        achado = _desafio(corpo, content_type, cabecalhos)
        if achado:
            return _desafio_no_robots(achado, base)
        return _barreira("corpo_nao_interpretavel", "200 cujo corpo não pôde ser examinado com segurança (charset que "
                         "não fecha, NUL em qualquer MIME, separador de linha fora do RFC 9309 ou diretivas em UTF-16/32 sem "
                         "BOM): barreira por conservadorismo "
                         "(decisão 0071)", **base)
    if mime != "text/plain":  # fora de text/plain o marcador de desafio vence, mesmo que haja linhas de regra
        achado = _desafio(corpo, content_type, cabecalhos)
        if achado:
            return _desafio_no_robots(achado, base)
    if interpretavel(texto):
        return LeituraRobots(REGRAS, "regras_interpretaveis", "grupo User-agent e só diretivas conhecidas",
                             regras=tuple(texto.splitlines()), charset_legado_em_comentario=legado, **base)
    nomes = {_diretiva(ln) for ln in _linhas_uteis(texto)}
    if not _PARECE_HTML.search(texto[:2048]) and nomes & {"allow", "disallow"}:
        return _barreira("regras_ambiguas", "Allow/Disallow em arquivo não interpretável (sem User-agent ou com linhas "
                         "desconhecidas): barreira por conservadorismo (decisão 0071)", **base)
    achado = _desafio(corpo, content_type, cabecalhos)  # text/plain sem regras: ainda pode ser página de desafio
    if achado:
        return _desafio_no_robots(achado, base)
    forma = "HTML" if _PARECE_HTML.search(texto[:2048]) else (content_type or "sem Content-Type")
    return _sem_restricoes("200_sem_regras_interpretaveis", f"200 sem regras interpretáveis ({forma}): sem restrições",
                           **base)


def _inteiro(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _incoerencia(registro: Mapping[str, Any], corpo: bytes | None) -> tuple[str, str] | None:
    """(motivo, detalhe) se o registro não pode decidir nada; None se é coerente. Roda antes de qualquer retorno.

    I2.7 r2 (parecer PR #20 r1, B1): saltos e tipos são validados primeiro; o registro de sucesso não pode trazer
    motivo, categoria, exceção, marcador ou status de recusa; os únicos motivos que podem liberar (`http_404`,
    `http_410`, `corpo_vazio`) exigem evidência limpa e corpo ausente ou vazio. Tudo o mais é barreira.
    """
    ev = registro.get("evidencia")
    if ev is None:
        ev = {}
    if not isinstance(ev, Mapping):
        return "registro_malformado", "evidencia não é objeto"
    saltos = ev.get("saltos")
    if saltos is None:
        saltos = []
    if not isinstance(saltos, list) or not all(isinstance(s, Mapping) and _inteiro(s.get("status")) for s in saltos):
        return "registro_malformado", f"saltos malformados: {saltos!r}"
    if any(300 <= s["status"] <= 399 for s in saltos):
        return "redirecionamento", f"redirecionamento não seguido: {list(saltos)}"
    unavailable = registro.get("unavailable")
    if not isinstance(unavailable, bool):
        return "registro_malformado", "unavailable não é booleano"
    motivo, categoria = registro.get("motivo"), registro.get("categoria")
    st_ev, st_reg = ev.get("status"), registro.get("status")
    recusa = ev.get("excecao") or ev.get("marcador")
    if st_ev is not None and not _inteiro(st_ev):
        return "registro_malformado", f"status da evidência não inteiro: {st_ev!r}"
    if not unavailable:
        if st_reg != 200 or not _inteiro(st_reg) or corpo is None:
            return "registro_inconsistente", f"sucesso sem 200 ou sem corpo gravado (status {st_reg!r})"
        if registro.get("sha256") != hashlib.sha256(corpo).hexdigest():
            return "corpo_nao_confere", "sha256 do corpo difere do registro"
        if motivo or categoria or recusa or st_ev not in (None, 200) or ev.get("sha256") not in (None, registro["sha256"]):
            return "registro_contraditorio", f"sucesso com sinal de recusa (motivo {motivo!r}, categoria {categoria!r}, " \
                                             f"evidência {st_ev!r}, exceção {recusa!r})"
        return None
    if not isinstance(motivo, str) or not motivo:
        return "registro_malformado", "indisponibilidade sem motivo"
    # O corpo de uma recusa (página do 404, do 403) é evidência gravada pelo instrumento (0071) e não decide nada;
    # só em `corpo_vazio` o corpo precisa ser, de fato, vazio.
    if motivo in ("http_404", "http_410", "corpo_vazio"):  # os únicos que podem liberar
        esperado = 200 if motivo == "corpo_vazio" else int(motivo.removeprefix("http_"))
        # categoria aceita: nenhuma no 4xx (o mapeamento não prova categoria para 404/410); `resposta_inesperada`
        # em `corpo_vazio`, que é como o transporte classifica o corpo vazio (`EmptyBody`).
        categoria_ok = categoria in ((None, "resposta_inesperada") if motivo == "corpo_vazio" else (None,))
        # O instrumento grava o tipo da exceção em toda indisponibilidade (captura.py): `HTTPStatusError` na recusa
        # HTTP e `EmptyBody` no corpo vazio, sem marcador. Qualquer outra exceção ou marcador é contradição.
        excecao_ok = ev.get("excecao") in (None, "EmptyBody" if motivo == "corpo_vazio" else "HTTPStatusError")
        if st_ev != esperado or st_reg not in (None, esperado) or ev.get("marcador") or not excecao_ok or not categoria_ok:
            return "registro_contraditorio", f"motivo {motivo} com status {st_ev!r}, categoria {categoria!r}, exceção {recusa!r}"
        if motivo == "corpo_vazio" and (corpo or ev.get("sha256") not in (None, SHA256_VAZIO)
                                        or registro.get("sha256") not in (None, SHA256_VAZIO)):
            return "registro_contraditorio", "corpo_vazio com corpo gravado ou sha256 de corpo não vazio"
        return None
    if motivo.startswith("http_"):
        numero = motivo.removeprefix("http_")
        if not (numero.isdigit() and st_ev == int(numero) and st_ev != 200):
            return "registro_contraditorio", f"motivo {motivo} com status {st_ev!r} na evidência"
    return None


def ler_do_registro(registro: Mapping[str, Any], corpo: bytes | None = None) -> LeituraRobots:
    """Leitura do robots.txt a partir do `.captura.json` da sonda (e do corpo gravado, se 200).

    Primeiro a coerência do registro (`_incoerencia`); só registro coerente decide algo além de barreira.
    """
    problema = _incoerencia(registro, corpo)
    if problema is not None:
        return _barreira(*problema)
    ev = registro.get("evidencia") or {}
    cab = registro.get("cabecalhos") or {}
    ct = cab.get("content-type") or registro.get("content_type") or ev.get("content_type")
    motivo = str(registro.get("motivo") or "")
    if not registro.get("unavailable"):
        return ler_robots(200, ct, corpo, cabecalhos=cab)
    if motivo.startswith("desafio_") or registro.get("categoria") == "ambiental_desafio":
        return _barreira(motivo or "desafio", "desafio ou WAF", status=ev.get("status"), content_type=ct,
                         sha256=ev.get("sha256"))
    status = ev.get("status")
    if motivo.startswith("http_"):
        return ler_robots(status, ct, None)
    if motivo == "corpo_vazio":
        return ler_robots(200, ct, b"")
    excecao = ev.get("excecao") or motivo.removeprefix("transporte_")
    mensagem = ev.get("mensagem") or ""
    if excecao == "BlockedHost" or motivo == "transporte_BlockedHost":
        return _barreira("bloqueio_do_transporte", f"recusa de política do transporte: {mensagem}".strip(": "))
    if excecao in ("Timeout", "TransportError") or ev.get("marcador") in ("transporte:Timeout", "transporte:TransportError"):
        return _barreira("timeout" if excecao == "Timeout" else "erro_transporte", f"{excecao}: {mensagem}".strip(": "))
    if motivo.startswith("transporte_") or excecao in ("RespostaInvalida", "TooLarge", "TransporteLento", "EmptyBody"):
        if status == 200:
            causa = "content_type_ausente" if "(ausente)" in mensagem else "resposta_200_recusada"
            return _barreira(causa, f"200 recusado pelo transporte ({excecao}): {mensagem}".strip(": "),
                             status=200, content_type=ct)
        return _barreira("resposta_recusada", f"{excecao}: {mensagem}".strip(": "), status=status)
    return _barreira(f"indisponivel_{motivo or 'sem_motivo'}", "indisponibilidade sem regra própria")


# --- avaliador RFC 9309 (só para somar restrições ao robotparser) ---------------------------------------------


def _grupos(linhas: tuple[str, ...]) -> list[tuple[list[str], list[tuple[bool, str]]]]:
    """Grupos (agentes, regras (permite, padrão)); `User-agent` consecutivos formam um grupo."""
    grupos: list[tuple[list[str], list[tuple[bool, str]]]] = []
    atual: tuple[list[str], list[tuple[bool, str]]] | None = None
    ultimo_foi_agente = False
    for bruta in linhas:
        linha = bruta.split("#", 1)[0].strip().lstrip("﻿").strip()
        m = _DIRETIVA.match(linha)
        if not m:
            continue
        nome, valor = m.group(1).lower(), linha[m.end():].strip()
        if nome == "user-agent":
            if atual is None or not ultimo_foi_agente:
                atual = ([], [])
                grupos.append(atual)
            atual[0].append(valor.lower())
            ultimo_foi_agente = True
            continue
        if nome not in ("allow", "disallow"):
            continue  # extensão (Crawl-delay, Request-rate, Sitemap...): não interfere no agrupamento (RFC 9309, 2.2.4)
        ultimo_foi_agente = False  # só Allow/Disallow encerram a sequência de agentes
        if atual is not None and valor:
            atual[1].append((nome == "allow", valor))
    return grupos


_NAO_RESERVADOS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_CRUS = _NAO_RESERVADOS | frozenset("/*$?&=:@;,+!'()[]")  # permanecem como estão; o resto vira %XX
_HEX = frozenset("0123456789abcdefABCDEF")


def _normalizar(texto: str) -> str:
    """Forma única para comparar caminho e regra (RFC 9309, 2.2.2; RFC 3986, 6.2.2.2).

    Decodifica só octetos não reservados (RFC 3986 unreserved) e deixa em caixa alta os demais octetos codificados:
    `%2F` continua distinto de `/`. Caracteres fora do ASCII viram os octetos UTF-8 em `%XX`.
    """
    saida: list[str] = []
    i = 0
    while i < len(texto):
        c = texto[i]
        if c == "%" and i + 2 < len(texto) and texto[i + 1] in _HEX and texto[i + 2] in _HEX:
            octeto = int(texto[i + 1:i + 3], 16)
            letra = chr(octeto)
            saida.append(letra if letra in _NAO_RESERVADOS else f"%{octeto:02X}")
            i += 3
            continue
        if c in _CRUS:
            saida.append(c)
        else:
            saida.extend(f"%{b:02X}" for b in c.encode("utf-8", "surrogateescape"))
        i += 1
    return "".join(saida)


def _casa(padrao: str, caminho: str) -> int:
    """Comprimento do padrão se casa com o início de `caminho` (`*` qualquer sequência, `$` fim); senão -1."""
    ancorado = padrao.endswith("$")
    corpo = padrao[:-1] if ancorado else padrao
    rx = ".*".join(re.escape(parte) for parte in corpo.split("*"))
    return len(padrao) if re.match(rx + ("$" if ancorado else ""), caminho, re.S) else -1


def _permitido_rfc(linhas: tuple[str, ...], url: str) -> bool:
    partes = urlsplit(url)
    caminho = _normalizar(partes.path or "/") + (f"?{partes.query}" if partes.query else "")
    grupos = _grupos(linhas)
    token = AGENTE.lower()
    especificos = [g for g in grupos if any(a != "*" and a in token for a in g[0])]
    aplicaveis = especificos or [g for g in grupos if "*" in g[0]]
    melhor, permite = -1, True
    for _, regras in aplicaveis:
        for libera, padrao in regras:
            tam = _casa(_normalizar(padrao), caminho)
            if tam > melhor or (tam == melhor and libera):
                melhor, permite = tam, libera
    return permite
