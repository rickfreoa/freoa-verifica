"""Partição determinística do texto canônico de uma decisão (PARIDADE-1.4, CH1–CH6; decisão 0073, seção 7).

Módulo puro: não importa rede, subprocesso nem runtime de modelo.

Regra de corte (versão única; mudar a regra muda os bytes das partes e exige decisão em `docs/decisoes/`):

1. Unidade: ponto de código Unicode do texto canônico extraído (`str` do Python). Como o corte é sempre entre
   pontos de código, nunca separa um caractere nem o par substituto de um caractere fora do BMP (CH4).
2. Sobreposição fixa de `SOBREPOSICAO` (200) pontos de código: a parte `i + 1` começa em `fim(i) - 200`.
3. A parte `i` começa em `inicio(i)`; a janela vai até `w = min(inicio(i) + parte_tamanho, len(texto))`.
   Se `w == len(texto)`, a parte termina em `w` e é a última.
4. Senão, o fim é procurado nos últimos 200 pontos de código da janela, `texto[w - 200 : w]`: o fim do último
   parágrafo (`\\n\\n`, cortando depois da quebra dupla); sem ele, o fim da última linha (`\\n`, cortando depois da
   quebra); sem nenhum dos dois, o limite da janela `w`. A busca por `\\n\\n` precede a de `\\n`, mesmo que esta
   caia mais perto de `w`.
5. Como `parte_tamanho >= 500`, o fim cai a pelo menos 300 pontos de código do início e o início seguinte avança
   pelo menos 100: o laço termina e nenhuma parte é vazia.

`partes_total` vem de percorrer o texto inteiro com esta regra; concatenar a parte 0 inteira com cada parte
seguinte sem os primeiros 200 pontos de código reconstrói o texto.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

SOBREPOSICAO = 200
PARTE_TAMANHO_MIN = 500
PARTE_TAMANHO_MAX = 10_000
PARTE_TAMANHO_PADRAO = 2_000
SEGMENTOS_SEM_SEGMENTACAO = ("nao_identificado",)


@dataclass(frozen=True)
class Particao:
    parte_idx: int
    partes_total: int
    parte_tamanho: int
    intervalo: tuple[int, int]
    texto_parte: str
    sha256_parte: str
    sha256_texto: str

    def como_dict(self) -> dict:
        return {
            "parte_idx": self.parte_idx,
            "partes_total": self.partes_total,
            "parte_tamanho": self.parte_tamanho,
            "sobreposicao": SOBREPOSICAO,
            "intervalo": [self.intervalo[0], self.intervalo[1]],
            "sha256_parte": self.sha256_parte,
            "sha256_texto": self.sha256_texto,
            "segmentos": list(SEGMENTOS_SEM_SEGMENTACAO),
        }


def sha256_utf8(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _fim(texto: str, inicio: int, parte_tamanho: int) -> int:
    """Fim (exclusivo) da parte que começa em `inicio`, pela regra do docstring do módulo."""
    n = len(texto)
    w = min(inicio + parte_tamanho, n)
    if w == n:
        return n
    lo = w - SOBREPOSICAO
    i = texto.rfind("\n\n", lo, w)
    if i >= 0:
        return i + 2
    i = texto.rfind("\n", lo, w)
    if i >= 0:
        return i + 1
    return w


def intervalos(texto: str, parte_tamanho: int = PARTE_TAMANHO_PADRAO) -> list[tuple[int, int]]:
    """Intervalos [início, fim) de todas as partes do texto, em pontos de código."""
    if not PARTE_TAMANHO_MIN <= parte_tamanho <= PARTE_TAMANHO_MAX:
        raise ValueError(f"parte_tamanho fora de {PARTE_TAMANHO_MIN}..{PARTE_TAMANHO_MAX}: {parte_tamanho}")
    n = len(texto)
    out: list[tuple[int, int]] = []
    inicio = 0
    while True:
        fim = _fim(texto, inicio, parte_tamanho)
        out.append((inicio, fim))
        if fim >= n:
            return out
        inicio = fim - SOBREPOSICAO


def particionar(texto: str, parte_idx: int, parte_tamanho: int = PARTE_TAMANHO_PADRAO) -> Particao:
    """A parte `parte_idx` do texto. `IndexError` (com `partes_total` na mensagem) se fora do intervalo."""
    todos = intervalos(texto, parte_tamanho)
    if not 0 <= parte_idx < len(todos):
        raise IndexError(f"parte_idx {parte_idx} fora do intervalo 0..{len(todos) - 1} (partes_total={len(todos)})")
    inicio, fim = todos[parte_idx]
    parte = texto[inicio:fim]
    return Particao(parte_idx, len(todos), parte_tamanho, (inicio, fim), parte, sha256_utf8(parte), sha256_utf8(texto))
