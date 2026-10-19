"""Captura reproduzível de respostas oficiais para fixtures e sondas.

A requisição é montada exclusivamente pelo `build_*` do conector e enviada pelo
transporte (mesma allowlist, limites e UA do conector). Nada de rede aqui fora
de `freoa_verifica.transport`.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from freoa_verifica import __version__
from freoa_verifica.connectors import tjdft
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.httputil import connector_fetch, ua_header

UA_IDENTIFICADO = f"freoa-verifica/{__version__} (+https://github.com/rickfreoa/freoa-verifica)"
UA_MODOS = ("identificado", "conector")


@dataclass
class RegistroCaptura:
    conector: str
    versao: str
    url: str
    metodo: str
    parametros: dict[str, Any]
    user_agent: str
    capturado_em: str
    unavailable: bool = False
    motivo: str | None = None
    categoria: str | None = None
    url_final: str | None = None
    status: int | None = None
    content_type: str | None = None
    cabecalhos: dict[str, str] = field(default_factory=dict)
    sha256: str | None = None
    bytes: int | None = None
    arquivo: str | None = None
    corpo: bytes | None = field(default=None, repr=False)

    def meta(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("corpo")
        return d


def _tjdft(consulta: dict[str, Any]) -> dict[str, Any]:
    payload = tjdft.build_search_payload(
        consulta["query"],
        pagina=int(consulta.get("pagina", 0)),
        tamanho=int(consulta.get("tamanho", 10)),
        extras=consulta.get("extras"),
    )
    return {
        "url": tjdft.SEARCH_URL,
        "metodo": "POST",
        "payload": payload,
        "hosts": tjdft.TjdftConnector.hosts,
        "path_prefixes": tjdft.TjdftConnector.path_prefixes,
        "mimes": tjdft.TjdftConnector.mimes,
        "user_agent": tjdft.TjdftConnector.user_agent,
    }


_CONECTORES: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {"tjdft": _tjdft}


def _atomico(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def capturar(
    conector: str,
    consulta: dict[str, Any],
    *,
    destino: Path,
    sonda: bool,
    user_agent: str = "conector",
    chave: str | None = None,
) -> RegistroCaptura:
    """Captura uma consulta e grava corpo (bytes brutos) + `<chave>.captura.json` em `destino`.

    `sonda` não altera o envio; só sinaliza no registro que o destino é fora do manifesto.
    """
    if conector not in _CONECTORES:
        raise ValueError(f"conector sem captura: {conector}")
    if user_agent not in UA_MODOS:
        raise ValueError(f"user_agent inválido: {user_agent}")
    req = _CONECTORES[conector](consulta)
    ua = UA_IDENTIFICADO if user_agent == "identificado" else ua_header(req["user_agent"])["User-Agent"]
    reg = RegistroCaptura(
        conector=conector, versao=__version__, url=req["url"], metodo=req["metodo"],
        parametros=req["payload"], user_agent=ua,
        capturado_em=datetime.now(timezone.utc).isoformat(),
    )
    body = json.dumps(req["payload"], ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if user_agent == "identificado":
        headers["User-Agent"] = UA_IDENTIFICADO
    try:
        resp = connector_fetch(
            req["url"], hosts=req["hosts"], path_prefixes=req["path_prefixes"], mimes=req["mimes"],
            user_agent=req["user_agent"], method=req["metodo"], body=body, headers=headers, timeout=60.0,
        )
    except Unavailable as exc:
        reg.unavailable, reg.motivo = True, exc.reason
        reg.categoria = exc.reason.split("_", 1)[0]
    else:
        reg.url_final, reg.status, reg.content_type = resp.final_url, resp.status, resp.mime
        reg.cabecalhos = dict(resp.headers)
        reg.sha256, reg.bytes, reg.corpo = resp.sha256, len(resp.body), resp.body
        reg.corpo = resp.body
        if resp.status != 200:
            reg.unavailable, reg.motivo, reg.categoria = True, f"http_{resp.status}", "http"
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    chave = chave or f"{conector}_{(reg.sha256 or reg.capturado_em.replace(':', ''))[:12]}"
    if not reg.unavailable and reg.corpo is not None:
        reg.arquivo = f"{chave}.json"
        _atomico(destino / reg.arquivo, reg.corpo)
    _atomico(destino / f"{chave}.captura.json", json.dumps(reg.meta(), ensure_ascii=False, indent=1).encode("utf-8"))
    return reg


def registrar_fixture(reg: RegistroCaptura, chave: str, fixtures: Path) -> None:
    """Grava os bytes em `fixtures/<conector>/` e a entrada em FIXTURES.json; desfaz os bytes se o manifesto falhar."""
    if reg.unavailable or reg.arquivo is None or reg.corpo is None:
        raise ValueError("captura indisponível não vira fixture")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_]*", chave):
        raise ValueError(f"chave inválida: {chave}")
    manifesto = fixtures / "FIXTURES.json"
    bruto = manifesto.read_bytes()
    dados = json.loads(bruto.decode("utf-8"))
    nl = "\r\n" if b"\r\n" in bruto else "\n"  # preserva o fim de linha do manifesto
    if chave in dados:
        raise ValueError(f"chave já existe no manifesto: {chave}")
    pasta = fixtures / reg.conector
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{chave}.json"
    dados[chave] = {
        "bytes": reg.bytes, "categoria": "captura_real", "content_type": reg.content_type,
        "fetched_at": reg.capturado_em, "file": f"{reg.conector}/{arquivo.name}",
        "final_url": reg.url_final, "sha256": reg.sha256, "status": reg.status, "url": reg.url,
    }
    _atomico(arquivo, reg.corpo)
    try:
        texto = json.dumps(dados, ensure_ascii=False, indent=1, sort_keys=True).replace("\n", nl) + nl
        _atomico(manifesto, texto.encode("utf-8"))
    except Exception:
        arquivo.unlink(missing_ok=True)
        raise
