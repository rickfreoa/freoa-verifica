"""Atribuição das evidências de origem Câmara (decisão 0080, §7). Campo aditivo; nunca altera `texto`.

O hash do termo é por CAPTURA: vem do registro de obtenção (`camara/obtencoes.jsonl`) que ligou a captura, identificada
pela MESMA tripla que o banco usa (SHA-256 do conteúdo, URL e instante `fetched_at`), ao termo vigente NA EMISSÃO, e só
vale se os bytes e o recibo desse termo estão preservados no home e conferem. Duas capturas de mesmo conteúdo e URL em
instantes diferentes não se confundem; se os registros da mesma captura apontam termos diferentes, o vínculo é ambíguo e
fica nulo. Nunca se substitui pelo termo corrente do home, e nada é herdado sem conferência.
"""
from __future__ import annotations

import re
from pathlib import Path

from freoa_verifica.connectors.camara_estado import Estado, EstadoIndisponivel, _de_iso, iso
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


def _chave(sha256: str, url: str, instante: str) -> tuple[str, str, str]:
    """Identidade da captura: a tripla do banco, com o instante normalizado (formato de escrita não distingue)."""
    return sha256, url, iso(_de_iso(instante))


def _obtencoes_por_captura(estado: Estado) -> dict[tuple[str, str, str], list[dict]]:
    """Índice (SHA-256, URL, instante) da captura → obtenções registradas; renovado quando o arquivo muda."""
    chave = (str(estado.home), _assinatura(estado.pasta / "obtencoes.jsonl"))
    if chave not in _INDICE:
        indice: dict[tuple[str, str, str], list[dict]] = {}
        for registro in estado.obtencoes():
            indice.setdefault(_chave(registro["sha256"], registro["url"], registro["capturado_em"]), []).append(registro)
        _INDICE.clear()  # um só estado vivo por vez basta; evita crescimento sem limite
        _INDICE[chave] = indice
    return _INDICE[chave]


def termo_da_captura(home: Path | None, sha256: str | None, url: str | None, fetched_at: str | None) -> str | None:
    """Hash do termo vinculado a ESTA captura (conteúdo, URL e instante), conferido contra o termo preservado; senão
    None. Termos preservados e conferidos que divergem entre os registros da mesma captura tornam o vínculo ambíguo."""
    if not (sha256 and url and fetched_at):
        return None
    if home is None:
        from freoa_verifica.store.db import data_home
        home = data_home()
    estado = Estado(Path(home))
    try:
        termos = {r["termo_sha256"] for r in _obtencoes_por_captura(estado).get(_chave(sha256, url, fetched_at), [])
                  if r.get("termo_sha256") and estado.termo_preservado(r["termo_sha256"]) is not None}
    except (EstadoIndisponivel, ValueError):
        return None
    return next(iter(termos)) if len(termos) == 1 else None


def autoria_declarada(texto: str | None) -> str | None:
    """Autoria só se o próprio documento a declara (`Autor:`/`Autoria:` em linha própria); nunca inferida."""
    achado = re.search(r"^\s*Autor(?:ia)?\s*:\s*(\S.*?)\s*$", texto or "", re.M)
    return achado.group(1) if achado else None


def atribuicao(home: Path | None = None, autoria: str | None = None, *, sha256: str | None = None,
               url: str | None = None, fetched_at: str | None = None) -> dict:
    """`sha256`/`url`/`fetched_at` identificam a captura de que o texto veio; sem captura vinculada o hash do termo é
    nulo."""
    return {"fonte": FONTE, "autoria": autoria or None, "forma_de_citacao": FORMA_DE_CITACAO,
            "termo_url": TERMO_URL, "termo_sha256": termo_da_captura(home, sha256, url, fetched_at)}
