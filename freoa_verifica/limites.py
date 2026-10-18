"""Validação de entrada compartilhada (F02): fachada, REST e MCP usam os mesmos tetos."""

from __future__ import annotations

from typing import Any

# Tetos de comprimento por nome de parâmetro (espelham o MCP).
TETO_TEXTO = {
    "texto": 100_000, "trecho": 100_000, "proposicao": 100_000,
    "citacao": 4000, "q": 4000,
    "data": 32, "desde": 32, "ate": 32, "cursor": 20, "modo": 32, "parte": 32,
    "fonte": 256, "tipo": 256, "work_id": 256, "caminho": 256, "id": 256,
    "capture_id": 256, "autoridade_min": 256,
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
