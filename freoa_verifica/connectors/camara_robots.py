"""Robots da Câmara por token (decisão 0080, §4). Funções puras; sem I/O.

Cada token (o do produto e a lista fechada de IA) é avaliado de forma independente pela RFC 9309: grupos cujo
`User-agent` é igual ao token (sem distinção de caixa) são combinados; sem grupo correspondente aplica-se `*`;
a regra de maior correspondência decide e `Allow` vence o empate. A combinação é conservadora: proibido se
qualquer token proíbe; inconclusivo se algum é inconclusivo; permitido só se todos permitem.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

TOKEN_PRODUTO = "freoa-verifica"  # noqa: S105  (token de User-agent, não credencial)
TOKENS_IA = ("GPTBot", "ChatGPT-User", "Google-Extended", "anthropic-ai", "Claude-Web", "ClaudeBot",
             "Claude-User", "Claude-SearchBot", "Omgilibot", "Omgili", "FacebookBot", "CCBot", "PerplexityBot")
TOKENS = (TOKEN_PRODUTO,) + TOKENS_IA
# Atraso acima deste teto é válido e honrado na política; o portão o declara como abstenção operacional (0081 §3).
TETO_OPERACIONAL_DO_ATRASO = 3600.0

PERMITIDO, PROIBIDO, INCONCLUSIVO = "permitido", "proibido", "inconclusivo"


class RobotsInconclusivo(ValueError):
    """Arquivo que não permite decisão segura: o motivo estável fica em `args[0]`."""


@dataclass
class Grupo:
    agentes: list[str]
    regras: list[tuple[str, str]] = field(default_factory=list)  # ("allow"|"disallow", padrão)
    atrasos: list[str] = field(default_factory=list)  # valores crus de Crawl-delay
    invalido: bool = False  # regra malformada dentro do grupo


@dataclass(frozen=True)
class Decisao:
    estado: str
    crawl_delay: float
    por_token: dict[str, str]
    grupos_considerados: tuple[tuple[str, ...], ...]
    motivo: str | None = None

    @property
    def permitido(self) -> bool:
        return self.estado == PERMITIDO


def interpretar(texto: str) -> list[Grupo]:
    """Agrupa as linhas. Linha sem `:`, regra fora de grupo, `User-agent` vazio ou diretiva desconhecida
    tornam o arquivo inconclusivo; regra malformada só invalida o grupo em que está."""
    grupos: list[Grupo] = []
    atual: Grupo | None = None
    viu_regra = False
    for original in texto.lstrip("﻿").splitlines():
        linha = original.split("#", 1)[0].strip()
        if not linha:
            continue
        if ":" not in linha:
            raise RobotsInconclusivo("robots_inconclusivo")
        chave, valor = (parte.strip() for parte in linha.split(":", 1))
        chave = chave.lower()
        if chave == "user-agent":
            if not valor:
                raise RobotsInconclusivo("robots_inconclusivo")
            if atual is None or viu_regra:
                atual = Grupo([])
                grupos.append(atual)
                viu_regra = False
            atual.agentes.append(valor.lower())
        elif chave in {"allow", "disallow", "crawl-delay"}:
            if atual is None:
                raise RobotsInconclusivo("robots_inconclusivo")
            viu_regra = True
            if chave == "crawl-delay":
                atual.atrasos.append(valor)
            elif valor:
                if not valor.startswith(("/", "*")):
                    atual.invalido = True
                else:
                    atual.regras.append((chave, valor))
        elif chave != "sitemap":
            raise RobotsInconclusivo("robots_diretiva_nao_suportada")
    return grupos


def _atraso_valido(valor: str) -> float | None:
    try:
        numero = float(valor)
    except ValueError:
        return None
    if not math.isfinite(numero) or numero < 0:
        return None
    return numero


_NAO_RESERVADOS = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
_RESERVADOS = frozenset(b":/?#[]@!$&'()*+,;=")
_HEX = frozenset(b"0123456789abcdefABCDEF")


def normalizar(dados: bytes) -> bytes:
    """Octetos comparáveis (RFC 9309, §2.2.2): `%XX` de octeto não reservado é decodificado; `%XX` de octeto
    reservado ou fora do ASCII fica codificado com hexadecimal maiúsculo; octeto literal fora do ASCII e fora
    do conjunto reservado é codificado. Aplica-se igualmente ao caminho e ao padrão da regra."""
    saida = bytearray()
    i = 0
    while i < len(dados):
        octeto = dados[i]
        par = dados[i + 1:i + 3]
        if octeto == 0x25 and len(par) == 2 and all(c in _HEX for c in par):
            valor = int(par, 16)
            saida += bytes([valor]) if valor in _NAO_RESERVADOS else b"%%%02X" % valor
            i += 3
            continue
        if octeto in _NAO_RESERVADOS or octeto in _RESERVADOS or octeto == 0x25:
            saida.append(octeto)
        else:
            saida += b"%%%02X" % octeto
        i += 1
    return bytes(saida)


@lru_cache(maxsize=4096)
def _compilar(padrao: str) -> tuple["re.Pattern[bytes]", int]:
    """(expressão sobre octetos, especificidade em octetos do padrão normalizado, com `*` e `$` contados)."""
    terminal = padrao.endswith("$")
    partes = [normalizar(p.encode("utf-8")) for p in (padrao[:-1] if terminal else padrao).split("*")]
    expr = b"^" + b".*".join(re.escape(p) for p in partes) + (b"$" if terminal else b"")
    return re.compile(expr, re.S), sum(len(p) for p in partes) + len(partes) - 1 + (1 if terminal else 0)


def _casa(padrao: str, caminho: bytes) -> int | None:
    """Especificidade se o padrão alcança o caminho (já normalizado em octetos); senão None."""
    expressao, tamanho = _compilar(padrao)
    return tamanho if expressao.search(caminho) is not None else None


def _grupos_do_token(grupos: list[Grupo], token: str) -> list[Grupo] | None:
    proprios = [g for g in grupos if token.lower() in g.agentes]
    if proprios:
        return proprios
    gerais = [g for g in grupos if "*" in g.agentes]
    return gerais or None


def decidir(grupos: list[Grupo], caminho: str) -> Decisao:
    """`caminho` inclui a query, se houver. Nunca levanta: o inconclusivo é um estado da decisão."""
    por_token: dict[str, str] = {}
    aplicados: list[Grupo] = []
    motivo = None
    octetos = normalizar(caminho.encode("utf-8"))
    for token in TOKENS:
        escolhidos = _grupos_do_token(grupos, token)
        if escolhidos is None:
            por_token[token], motivo = INCONCLUSIVO, motivo or "robots_sem_grupo_aplicavel"
            continue
        for g in escolhidos:
            if not any(g is x for x in aplicados):
                aplicados.append(g)
        if any(g.invalido for g in escolhidos):
            por_token[token], motivo = INCONCLUSIVO, motivo or "robots_inconclusivo"
            continue
        achadas = [(tamanho, acao == "allow") for g in escolhidos for acao, padrao in g.regras
                   if (tamanho := _casa(padrao, octetos)) is not None]
        por_token[token] = PERMITIDO if (not achadas or max(achadas)[1]) else PROIBIDO
    atrasos = [_atraso_valido(v) for g in aplicados for v in g.atrasos]
    if any(a is None for a in atrasos):
        por_token = {**por_token, "crawl-delay": INCONCLUSIVO}
        motivo = motivo or "crawl_delay_invalido"
    atraso = max((a for a in atrasos if a is not None), default=0.0)
    estados = set(por_token.values())
    estado = PROIBIDO if PROIBIDO in estados else INCONCLUSIVO if INCONCLUSIVO in estados else PERMITIDO
    return Decisao(estado, atraso, por_token, tuple(tuple(g.agentes) for g in aplicados),
                   motivo if estado == INCONCLUSIVO else None)


def politica_robots(texto: str, caminho: str) -> tuple[bool, float]:
    """Compatibilidade com a assinatura da IL.2-c: levanta `ValueError` se inconclusivo."""
    decisao = decidir(interpretar(texto), caminho)
    if decisao.estado == INCONCLUSIVO:
        raise RobotsInconclusivo(decisao.motivo or "robots_inconclusivo")
    return decisao.permitido, decisao.crawl_delay
