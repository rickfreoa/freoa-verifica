"""Paridade da leitura de HTML entre versões da libxml2 (decisão 0096).

A lxml embute libxml2 diferentes por plataforma (2.11 nas wheels de Windows, 2.14 nas de Linux na 1.4.0a9), e as
duas divergem em dois pontos que o HTML do Planalto exercita:

1. referência numérica de 128 a 159 (`&#150;`): a 2.14 segue o HTML5 e lê o caractere do cp1252 ("–"); a 2.11 grava
   o caractere de controle U+0096, e o travessão do inciso desaparece;
2. `</body>` ou `</html>` no meio do documento: a 2.14 descarta o que vem depois; a 2.11 mantém.

O texto entregue à lxml é normalizado antes: a referência vira o caractere que o HTML5 define, e os fechamentos de
`body` e `html` saem (o parser fecha ambos no fim do documento), de modo que as duas versões leiam a página inteira.
Nenhuma outra marcação é tocada.
"""

from __future__ import annotations

import re

_REFERENCIA_NUMERICA = re.compile(r"&#(?:[xX]([0-9a-fA-F]{1,6})|([0-9]{1,7}));?")
_FECHAMENTO_BODY_HTML = re.compile(r"</(?:body|html)\s*>", re.IGNORECASE)


def _caractere_html5(codigo: int) -> str | None:
    """Caractere que o HTML5 atribui à referência de 128 a 159; None fora da faixa ou sem mapeamento no cp1252."""
    if not 0x80 <= codigo <= 0x9F:
        return None
    try:
        return bytes([codigo]).decode("cp1252")
    except UnicodeDecodeError:  # 0x81, 0x8D, 0x8F, 0x90, 0x9D: o HTML5 mantém o código; as duas versões concordam
        return None


def _substituir(m: re.Match[str]) -> str:
    codigo = int(m.group(1), 16) if m.group(1) is not None else int(m.group(2))
    return _caractere_html5(codigo) or m.group(0)


def normalizar_para_lxml(html_text: str) -> str:
    """HTML com as duas divergências neutralizadas, para leitura idêntica em qualquer libxml2."""
    return _FECHAMENTO_BODY_HTML.sub("", _REFERENCIA_NUMERICA.sub(_substituir, html_text))
