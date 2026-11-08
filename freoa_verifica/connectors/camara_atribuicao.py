"""Atribuição das evidências de origem Câmara (decisão 0080, §7). Campo aditivo; nunca altera `texto`.

O hash do termo é por CAPTURA: vem do registro de obtenção (`camara/obtencoes.jsonl`) que ligou aquele
conteúdo (SHA-256 e URL) ao termo vigente no instante da obtenção, e só vale se os bytes e o recibo desse termo
estão preservados no home e conferem. Nunca se substitui pelo termo corrente do home, e nada é herdado sem conferência.
"""
from __future__ import annotations

import re
from pathlib import Path

from freoa_verifica.connectors.camara_estado import Estado, EstadoIndisponivel
from freoa_verifica.connectors.camara_policy import TERMO_URL

FONTE = "Câmara dos Deputados"
FORMA_DE_CITACAO = "trecho entre aspas, com fonte e autoria quando houver"
CHAVES = ("fonte", "autoria", "forma_de_citacao", "termo_url", "termo_sha256")
_INDICE: dict[tuple, dict[str, list[dict]]] = {}


def _assinatura(caminho: Path):
    try:
        estado = caminho.stat()
        return estado.st_mtime_ns, estado.st_size
    except OSError:
        return None


def _obtencoes_por_conteudo(estado: Estado) -> dict[str, list[dict]]:
    """Índice SHA-256 do conteúdo → obtenções registradas (ordem do arquivo); renovado quando o arquivo muda."""
    chave = (str(estado.home), _assinatura(estado.pasta / "obtencoes.jsonl"))
    if chave not in _INDICE:
        indice: dict[str, list[dict]] = {}
        for registro in estado.obtencoes():
            indice.setdefault(registro["sha256"], []).append(registro)
        _INDICE.clear()  # um só estado vivo por vez basta; evita crescimento sem limite
        _INDICE[chave] = indice
    return _INDICE[chave]


def termo_da_captura(home: Path | None, sha256: str | None, url: str | None = None) -> str | None:
    """Hash do termo vinculado a ESTA captura (conteúdo e URL), conferido contra o termo preservado; senão None."""
    if not sha256:
        return None
    if home is None:
        from freoa_verifica.store.db import data_home
        home = data_home()
    estado = Estado(Path(home))
    try:
        candidatos = _obtencoes_por_conteudo(estado).get(sha256, [])
        for registro in candidatos:
            digest = registro.get("termo_sha256")
            if (url is None or registro["url"] == url) and digest and estado.termo_preservado(digest) is not None:
                return digest
    except EstadoIndisponivel:
        return None
    return None


def autoria_declarada(texto: str | None) -> str | None:
    """Autoria só se o próprio documento a declara (`Autor:`/`Autoria:` em linha própria); nunca inferida."""
    achado = re.search(r"^\s*Autor(?:ia)?\s*:\s*(\S.*?)\s*$", texto or "", re.M)
    return achado.group(1) if achado else None


def atribuicao(home: Path | None = None, autoria: str | None = None, *, sha256: str | None = None,
               url: str | None = None) -> dict:
    """`sha256`/`url` identificam a captura de que o texto veio; sem captura vinculada o hash do termo é nulo."""
    return {"fonte": FONTE, "autoria": autoria or None, "forma_de_citacao": FORMA_DE_CITACAO,
            "termo_url": TERMO_URL, "termo_sha256": termo_da_captura(home, sha256, url)}
