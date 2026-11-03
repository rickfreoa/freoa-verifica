"""`timeline_decisoes`, modo `processo`: entrada, ordem, paginação e estado (decisão 0073; PARIDADE-1.4, TD1 a TD5).

Módulo puro: não lê rede, disco nem banco. A leitura das fontes é do serviço (`Verifica.timeline_decisoes`).

Ordem (C5): `data` crescente (AAAA-MM-DD; evento sem data oficial legível tem `data` vazia e vem primeiro), depois
`fonte` (`acervo`, `datajud`, `djen`, em ordem alfabética), depois o identificador estável do evento. O identificador é
`<sha256(fonte, id de origem)[:16]>-<n>`, com `n` a ordem entre eventos da mesma data, fonte e id de origem (o conteúdo
desempata antes de `n`, para a ordem não depender da ordem em que a fonte devolveu). Ele não aparece nos itens: só
serve de desempate e de posição do `cursor`.

Paginação: o `cursor` é a posição (`data|fonte|identificador`) do último item entregue, não um deslocamento. A página
seguinte traz os eventos de posição estritamente maior, sem omitir nem repetir evento da fronteira, ainda que várias
datas e fontes empatem nela.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from freoa_verifica.citation import validate_cnj_dv
from freoa_verifica.limites import EntradaInvalida

LIMITE_MIN, LIMITE_MAX, LIMITE_PADRAO = 1, 200, 50
CURSOR_MAX = 64
NUMERO_CNJ_MAX = 64
FONTES = ("datajud", "djen", "acervo")  # fontes necessárias do modo `processo` (0073, seção 3), nesta ordem
ATRIBUICAO = (
    "Conselho Nacional de Justiça (CNJ)",
    "DataJud, Base Nacional de Dados do Poder Judiciário (Portaria CNJ nº 374/2026)",
)

_CNJ_MASCARA = re.compile(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})")
_CNJ_DIGITOS = re.compile(r"\d{20}")
_CURSOR = re.compile(r"((?:\d{4}-\d{2}-\d{2})?)\|(acervo|datajud|djen)\|([0-9a-f]{16}-\d{4})")
_DATA_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATA_BR = re.compile(r"(\d{2})/(\d{2})/(\d{4})")


def validar_modo(modo: Any) -> None:
    if modo == "processo":
        return
    if modo == "recentes":
        raise EntradaInvalida("modo 'recentes' não está disponível nesta versão (modo disponível: processo)")
    raise EntradaInvalida(f"modo inválido: {modo!r} (processo; o modo 'recentes' não está disponível nesta versão)")


def normalizar_cnj(numero: Any) -> str:
    """Número CNJ com ou sem máscara, com o dígito verificador conferido (módulo 97, Resolução CNJ 65/2008).

    Devolve os 20 dígitos. Qualquer outra forma (curto, letras, dígito errado) é `EntradaInvalida`."""
    if not isinstance(numero, str):
        raise EntradaInvalida("numero_cnj: esperado texto com o número CNJ (modo processo)")
    texto = numero.strip()
    if len(texto) > NUMERO_CNJ_MAX:
        raise EntradaInvalida(f"numero_cnj: excede {NUMERO_CNJ_MAX} caracteres")
    m = _CNJ_MASCARA.fullmatch(texto)
    if m:
        digitos = "".join(m.groups())
    elif _CNJ_DIGITOS.fullmatch(texto):
        digitos = texto
    else:
        raise EntradaInvalida("numero_cnj: formato inválido (NNNNNNN-DD.AAAA.J.TR.OOOO ou 20 dígitos)")
    mascarado = f"{digitos[:7]}-{digitos[7:9]}.{digitos[9:13]}.{digitos[13]}.{digitos[14:16]}.{digitos[16:]}"
    if not validate_cnj_dv(mascarado):
        raise EntradaInvalida("numero_cnj: dígito verificador inválido")
    return digitos


def validar_limite(limite: Any) -> int:
    if isinstance(limite, bool) or not isinstance(limite, int):
        raise EntradaInvalida(f"limite: esperado inteiro de {LIMITE_MIN} a {LIMITE_MAX}")
    if not LIMITE_MIN <= limite <= LIMITE_MAX:
        raise EntradaInvalida(f"limite: fora da faixa {LIMITE_MIN}..{LIMITE_MAX}")
    return limite


def validar_cursor(cursor: Any) -> tuple[str, str, str] | None:
    """Posição `(data, fonte, identificador)` do cursor, ou `None` sem cursor."""
    if cursor is None:
        return None
    if not isinstance(cursor, str):
        raise EntradaInvalida("cursor: esperado texto")
    if len(cursor) > CURSOR_MAX:
        raise EntradaInvalida(f"cursor: excede {CURSOR_MAX} caracteres")
    m = _CURSOR.fullmatch(cursor)
    if not m:
        raise EntradaInvalida("cursor: valor inválido (use o cursor devolvido pela ferramenta)")
    return m.group(1), m.group(2), m.group(3)


def normalizar_data(valor: Any) -> str:
    """AAAA-MM-DD a partir de data ISO (com ou sem hora) ou DD/MM/AAAA; vazio quando a fonte não traz data legível."""
    if not isinstance(valor, str):
        return ""
    texto = valor.strip()
    m = _DATA_ISO.match(texto)
    if m:
        a, mes, d = m.groups()
    else:
        m = _DATA_BR.match(texto)
        if not m:
            return ""
        d, mes, a = m.groups()
    return f"{a}-{mes}-{d}" if 1 <= int(mes) <= 12 and 1 <= int(d) <= 31 else ""


def ordenar(brutos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evento bruto: `{fonte, data, id_origem, item}`. Devolve os mesmos, com `ident`, na ordem documentada."""
    previa = sorted(brutos, key=lambda e: (e["data"], e["fonte"], e["id_origem"],
                                           e["item"]["tipo_documental"], e["item"]["descricao"]))
    vistos: dict[tuple[str, str, str], int] = {}
    out = []
    for e in previa:
        base = hashlib.sha256(f"{e['fonte']}\x1f{e['id_origem']}".encode("utf-8")).hexdigest()[:16]
        chave = (e["data"], e["fonte"], base)
        n = vistos.get(chave, 0)
        vistos[chave] = n + 1
        out.append({**e, "ident": f"{base}-{n:04d}"})
    out.sort(key=posicao)
    return out


def posicao(evento: dict[str, Any]) -> tuple[str, str, str]:
    return evento["data"], evento["fonte"], evento["ident"]


def codificar_cursor(evento: dict[str, Any]) -> str:
    return "|".join(posicao(evento))


def paginar(ordenados: list[dict[str, Any]], limite: int,
            depois_de: tuple[str, str, str] | None) -> tuple[list[dict[str, Any]], bool, str | None]:
    """`(página, truncado, cursor)`. `truncado` e `cursor` dizem que há eventos além da página."""
    restantes = ordenados if depois_de is None else [e for e in ordenados if posicao(e) > depois_de]
    pagina = restantes[:limite]
    truncado = len(restantes) > limite
    return pagina, truncado, codificar_cursor(pagina[-1]) if truncado else None


def estado(lidas: dict[str, bool], ha_resultado: bool) -> str:
    """Estados fechados da decisão 0073, seção 3, sobre as fontes necessárias (`lidas`: fonte -> lida)."""
    todas = all(lidas.get(f, False) for f in FONTES)
    if todas:
        return "ok" if ha_resultado else "nenhum_no_recorte"
    return "parcial" if ha_resultado else "indisponivel"
