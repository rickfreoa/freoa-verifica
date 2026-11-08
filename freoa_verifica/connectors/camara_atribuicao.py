"""Atribuição das evidências de origem Câmara (decisão 0080, §7). Campo aditivo; nunca altera `texto`."""
from __future__ import annotations

import re
from pathlib import Path

from freoa_verifica.connectors.camara_ativacao import ativacao
from freoa_verifica.connectors.camara_estado import ATIVACAO, Estado
from freoa_verifica.connectors.camara_policy import TERMO_URL

FONTE = "Câmara dos Deputados"
FORMA_DE_CITACAO = "trecho entre aspas, com fonte e autoria quando houver"
CHAVES = ("fonte", "autoria", "forma_de_citacao", "termo_url", "termo_sha256")
_CACHE: dict[tuple, str | None] = {}


def _mtime(caminho: Path):
    try:
        return caminho.stat().st_mtime_ns, caminho.stat().st_size
    except OSError:
        return None


def _termo_sha256(home: Path | None) -> str | None:
    """Hash do termo: o da ativação deste home; senão o que o snapshot instalado declarou (manifesto conferido)."""
    if home is None:
        from freoa_verifica.store.db import data_home
        home = data_home()
    home = Path(home)
    herdado = home / "camara" / "termo-de-snapshot.json"
    chave = (str(home), _mtime(home / ATIVACAO), _mtime(herdado), _mtime(home / "camara" / "termo"))
    if chave not in _CACHE:
        registro = ativacao(Estado(home))
        digest = registro["termo_sha256"] if registro else None
        if digest is None:
            try:
                dados = Estado(home)._ler("termo-de-snapshot.json", None)
            except OSError:
                dados = None
            if isinstance(dados, dict) and dados.get("termo_url") == TERMO_URL:
                digest = dados.get("termo_sha256")
        _CACHE[chave] = digest
    return _CACHE[chave]


def autoria_declarada(texto: str | None) -> str | None:
    """Autoria só se o próprio documento a declara (`Autor:`/`Autoria:` em linha própria); nunca inferida."""
    achado = re.search(r"^\s*Autor(?:ia)?\s*:\s*(\S.*?)\s*$", texto or "", re.M)
    return achado.group(1) if achado else None


def atribuicao(home: Path | None = None, autoria: str | None = None) -> dict:
    return {"fonte": FONTE, "autoria": autoria or None, "forma_de_citacao": FORMA_DE_CITACAO,
            "termo_url": TERMO_URL, "termo_sha256": _termo_sha256(home)}
