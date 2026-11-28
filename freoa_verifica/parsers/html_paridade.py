"""Paridade da leitura de HTML entre versões da libxml2 (decisão 0096).

A lxml embute libxml2 diferentes por plataforma (2.11 nas wheels de Windows, 2.14 nas de Linux na 1.4.0a9), e as
duas divergem em dois pontos que o HTML do Planalto exercita:

1. referência numérica de 128 a 159 (`&#150;`): a 2.14 segue o HTML5 e lê o caractere do cp1252 ("–"); a 2.11 grava
   o caractere de controle U+0096, e o travessão do inciso desaparece;
2. `</body>` ou `</html>` no meio do documento: as duas versões divergem sobre o que vem depois.

O texto entregue à lxml é normalizado antes, com análise léxica: só o texto entre tags é tocado. Nele, a referência
de 128 a 159 vira o caractere que o HTML5 define; e as tags de fechamento `</body>` e `</html>`, inteiras, saem (o
parser fecha ambos no fim do documento). Comentários, `<script>`, `<style>`, CDATA e o interior de qualquer tag
(atributos) ficam como estão, e a remoção nunca junta fragmentos em marcação nova.
"""

from __future__ import annotations

import re

# Ordem importa: comentário, CDATA e elementos de conteúdo bruto antes de tag genérica.
_TOKEN = re.compile(
    r"(?P<bruto><!--.*?(?:-->|\Z)|<!\[CDATA\[.*?(?:\]\]>|\Z)|<(?P<raw>script|style)\b"
    r"(?:\"[^\"]*\"|'[^']*'|[^'\">])*>.*?(?:</(?P=raw)\s*>|\Z))"
    r"|(?P<tag><[A-Za-z/!?](?:\"[^\"]*\"|'[^']*'|[^'\">])*>)",
    re.IGNORECASE | re.DOTALL,
)
_FECHAMENTO_BODY_HTML = re.compile(r"</(?:body|html)\s*>\Z", re.IGNORECASE)
_REFERENCIA_NUMERICA = re.compile(r"&#(?:[xX]([0-9a-fA-F]+)|([0-9]+));?")
_MAX_DIGITOS = 8  # sem zeros à esquerda; acima disso o código está fora de 128-159 e não precisa ser convertido


def _caractere_html5(codigo: int) -> str | None:
    """Caractere que o HTML5 atribui à referência de 128 a 159; None fora da faixa ou sem mapeamento no cp1252."""
    if not 0x80 <= codigo <= 0x9F:
        return None
    try:
        return bytes([codigo]).decode("cp1252")
    except UnicodeDecodeError:  # 0x81, 0x8D, 0x8F, 0x90, 0x9D: o HTML5 mantém o código; as duas versões concordam
        return None


def _substituir(m: re.Match[str]) -> str:
    hexa, dec = m.group(1), m.group(2)
    digitos = (hexa if hexa is not None else dec).lstrip("0") or "0"
    if len(digitos) > _MAX_DIGITOS:
        return m.group(0)
    codigo = int(digitos, 16 if hexa is not None else 10)
    return _caractere_html5(codigo) or m.group(0)


def _texto(trecho: str) -> str:
    return _REFERENCIA_NUMERICA.sub(_substituir, trecho)


def normalizar_para_lxml(html_text: str) -> str:
    """HTML com as duas divergências neutralizadas, para leitura idêntica em qualquer libxml2."""
    partes: list[str] = []
    pos = 0
    for m in _TOKEN.finditer(html_text):
        partes.append(_texto(html_text[pos:m.start()]))
        token = m.group(0)
        if m.group("tag") is not None and _FECHAMENTO_BODY_HTML.match(token):
            # Retirar a tag não pode juntar um "<" literal anterior ao texto seguinte (`<</body>s>` não vira `<s>`).
            if partes and partes[-1].endswith("<"):
                partes[-1] = partes[-1][:-1] + "&lt;"
        else:
            partes.append(token)
        pos = m.end()
    partes.append(_texto(html_text[pos:]))
    return "".join(partes)
