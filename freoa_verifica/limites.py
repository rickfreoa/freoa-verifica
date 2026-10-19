"""Validação de entrada compartilhada (F02): fachada, REST e MCP usam os mesmos tetos."""

from __future__ import annotations

import os
import time
from contextvars import ContextVar
from typing import Any

# Prazo (time.monotonic) do orçamento da operação em curso; fetch e parse isolado o respeitam.
PRAZO: ContextVar[float | None] = ContextVar("prazo_orcamento", default=None)
# Evento de cancelamento da thread abandonada por `_com_prazo`: gravações verificam antes de confirmar.
CANCELADO: ContextVar[Any] = ContextVar("cancelado_orcamento", default=None)


def cancelado() -> bool:
    ev = CANCELADO.get()
    return bool(ev is not None and ev.is_set())


def restante(timeout: float) -> float:
    """min(restante do orçamento, timeout do perfil); 0 se o orçamento estourou."""
    prazo = PRAZO.get()
    return timeout if prazo is None else max(0.0, min(timeout, prazo - time.monotonic()))

# Tetos de comprimento por nome de parâmetro (espelham o MCP).
TETO_TEXTO = {
    "texto": 100_000, "trecho": 100_000, "proposicao": 100_000,
    "citacao": 4000, "q": 4000,
    "data": 32, "desde": 32, "ate": 32, "cursor": 20, "modo": 32, "parte": 32,
    "fonte": 256, "tipo": 256, "work_id": 256, "caminho": 256, "id": 256,
    "capture_id": 256, "autoridade_min": 256, "tribunal": 32,
}
# (mínimo, máximo) de parâmetros inteiros.
FAIXA_INT = {"limite": (1, 50), "max_chars": (1, 50_000), "offset": (0, 10_000_000)}
MAX_TRIBUNAIS = 5
MAX_CORPO_HTTP = 512 * 1024  # bytes; texto de 100k caracteres cabe com folga


class EntradaInvalida(ValueError):
    """Entrada fora do contrato; adaptadores a traduzem em 4xx."""


class Sobrecarga(RuntimeError):
    """Concorrência de operações caras esgotada; adaptadores a traduzem em 503."""


def validar(args: dict[str, Any]) -> None:
    for nome, valor in args.items():
        if valor is None:
            continue
        if nome in TETO_TEXTO:
            if not isinstance(valor, str):
                raise EntradaInvalida(f"{nome}: esperado texto")
            if len(valor) > TETO_TEXTO[nome]:
                raise EntradaInvalida(f"{nome}: excede {TETO_TEXTO[nome]} caracteres")
        elif nome in FAIXA_INT:
            lo, hi = FAIXA_INT[nome]
            if isinstance(valor, bool) or not isinstance(valor, int):
                raise EntradaInvalida(f"{nome}: esperado inteiro")
            if not lo <= valor <= hi:
                raise EntradaInvalida(f"{nome}: fora da faixa {lo}..{hi}")
        elif nome == "tribunais":
            if not isinstance(valor, (list, tuple)) or len(valor) > MAX_TRIBUNAIS:
                raise EntradaInvalida(f"tribunais: lista de até {MAX_TRIBUNAIS} itens")
            for t in valor:
                if not isinstance(t, str) or len(t) > 256:
                    raise EntradaInvalida("tribunais: itens de texto de até 256 caracteres")


def servidor_max_concorrencia() -> int:
    """Limite de operações caras simultâneas nas entradas de servidor (REST, MCP)."""
    return max(1, int(os.environ.get("FV_MAX_CONCORRENCIA") or 4))
