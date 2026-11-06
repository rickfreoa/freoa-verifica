"""Matriz de capacidades por rota (IL.3-a, A3; emenda IL, seção 5, IL.3; decisão 0075, seção 3.3).

Dado versionado em `data/qualificacao_rotas.json`: por rota efetiva (fonte + perfil) e por capacidade, um estado e,
se diferente de `nao_apurada`, a referência ao relatório de apuração (caminho e SHA-256) e à versão. Nada aqui mede
capacidade nem declara aprovação: o estado só muda depois da apuração (IL.3-c). Informa; não liga nem desliga rota
no FREOA. Leitura fechada: item que afirme estado sem referência verificável por hash volta a `nao_apurada`.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any

_log = logging.getLogger(__name__)

ESTADOS = ("nao_apurada", "aprovada", "reprovada", "nao_aplicavel")
# capacidades (a)-(e) da Porta L e as transversais, com o rótulo da emenda, seção 6
CAPACIDADES: dict[str, str] = {
    "identificacao": "Porta L: identificação",
    "texto_publicado": "Porta L: texto publicado",
    "texto_consolidado_vigente": "Porta L: texto consolidado vigente",
    "redacao_em_data": "Porta L: redação em data",
    "anexos": "Porta L: anexos",
    "remissoes": "Porta L: remissões",
    "vigencia_declarada": "Porta L: vigência declarada",
}
_SHA = re.compile(r"^[0-9a-f]{64}$")
CAMPOS_ITEM = {"estado", "rotulo", "versao", "relatorio", "relatorio_sha256"}


def validar(dados: Any) -> list[str]:
    """Problemas do arquivo de rotas; lista vazia = conforme."""
    erros: list[str] = []
    if not isinstance(dados, dict) or not isinstance(dados.get("rotas"), list) or not dados["rotas"]:
        return ["rotas ausente ou vazia"]
    vistas: set[str] = set()
    for r in dados["rotas"]:
        if not isinstance(r, dict) or not all(isinstance(r.get(k), str) and r[k] for k in ("rota", "fonte", "perfil")):
            erros.append(f"rota inválida: {r!r}")
            continue
        if r["rota"] in vistas:
            erros.append(f"rota repetida: {r['rota']}")
        vistas.add(r["rota"])
        caps = r.get("capacidades")
        if not isinstance(caps, dict) or set(caps) != set(CAPACIDADES):
            erros.append(f"{r['rota']}: capacidades devem ser exatamente {sorted(CAPACIDADES)}")
            continue
        for nome, item in caps.items():
            if not isinstance(item, dict) or set(item) != CAMPOS_ITEM:
                erros.append(f"{r['rota']}.{nome}: campos devem ser exatamente {sorted(CAMPOS_ITEM)}")
                continue
            if item["estado"] not in ESTADOS:
                erros.append(f"{r['rota']}.{nome}: estado {item['estado']!r} fora de {ESTADOS}")
            elif item["estado"] != "nao_apurada" and not _referencia_ok(item):
                erros.append(f"{r['rota']}.{nome}: estado {item['estado']} sem relatório de apuração e versão "
                             f"referenciados por SHA-256")
            if item["rotulo"] != CAPACIDADES[nome]:
                erros.append(f"{r['rota']}.{nome}: rótulo diverge do da emenda ({CAPACIDADES[nome]!r})")
    return erros


def _referencia_ok(item: dict[str, Any]) -> bool:
    return (isinstance(item.get("relatorio"), str) and bool(item["relatorio"])
            and isinstance(item.get("relatorio_sha256"), str) and bool(_SHA.match(item["relatorio_sha256"]))
            and isinstance(item.get("versao"), str) and bool(item["versao"]))


def carregar(texto_json: str) -> list[dict[str, Any]]:
    """Rotas do arquivo, com leitura fechada: estado sem referência verificável vira `nao_apurada`; arquivo ilegível
    ou fora do esquema não publica estado algum (lista vazia)."""
    try:
        dados = json.loads(texto_json)
    except (ValueError, TypeError):
        _log.warning("qualificacao_rotas.json ilegível", exc_info=True)
        return []
    if not isinstance(dados, dict) or not isinstance(dados.get("rotas"), list):
        _log.warning("qualificacao_rotas.json fora do esquema")
        return []
    rotas = copy.deepcopy(dados["rotas"])
    for r in rotas:
        caps = r.get("capacidades") if isinstance(r, dict) else None
        if not isinstance(caps, dict):
            return []
        for item in caps.values():
            if isinstance(item, dict) and item.get("estado") != "nao_apurada" and not (
                    item.get("estado") in ESTADOS and _referencia_ok(item)):
                _log.warning("estado sem referência de apuração rebaixado a nao_apurada")
                item.update(estado="nao_apurada", versao=None, relatorio=None, relatorio_sha256=None)
    return rotas


def anexar_rotas(itens: list[dict[str, Any]], rotas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada item da Porta L ganha `rotas` (estado da capacidade em cada rota); os demais itens ficam como estão.
    O estado do item continua sendo o da Porta (nao_apurada até a apuração): a rota não o promove."""
    rotulo_para_cap = {v: k for k, v in CAPACIDADES.items()}
    saida = []
    for it in itens:
        it = dict(it)
        cap = rotulo_para_cap.get(it.get("rotulo")) if it.get("porta") == "L" else None
        if cap is not None:
            it["rotas"] = [{"rota": r["rota"], "estado": r["capacidades"][cap]["estado"],
                            "versao": r["capacidades"][cap]["versao"],
                            "relatorio_sha256": r["capacidades"][cap]["relatorio_sha256"]} for r in rotas]
        saida.append(it)
    return saida
