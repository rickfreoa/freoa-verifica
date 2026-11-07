"""Matriz de capacidades por rota (IL.3-a, A3; emenda IL, seção 5, IL.3; decisão 0075, seção 3.3).

Dado versionado em `data/qualificacao_rotas.json`: por rota efetiva (fonte + perfil) e por capacidade, um estado e,
se diferente de `nao_apurada`, a referência ao relatório de apuração (caminho e SHA-256) e à versão. Nada aqui mede
capacidade nem declara aprovação: o estado só muda depois da apuração (IL.3-c). Informa; não liga nem desliga rota
no FREOA.

Leitura fechada. Estado diferente de `nao_apurada` só vale com um RELATÓRIO DE APURAÇÃO identificável: arquivo JSON do
pacote (`data/apuracoes/*.json`) de esquema próprio (`ESQUEMA_RELATORIO`), cujos bytes conferem com `relatorio_sha256` e
que declara a MESMA rota, capacidade, versão e resultado do item, produzido por execução qualificante do executor da
Porta L, com os hashes dos bytes conferidos (conjunto, mutantes e congelamento). Qualquer outra referência (hash de
arquivo qualquer, relatório de outra rota ou capacidade, arquivo ilegível) volta a `nao_apurada`; enquanto nenhum
relatório existir, a publicação é só `nao_apurada`.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
from typing import Any, Callable

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
# letra da capacidade da matriz IL.1 que o relatório de apuração declara; as transversais não têm letra
LETRA_DA_CAPACIDADE = {"texto_publicado": "a", "texto_consolidado_vigente": "b", "redacao_em_data": "c",
                       "anexos": "d", "remissoes": "e", "identificacao": "transversal", "vigencia_declarada": "transversal"}
ESQUEMA_RELATORIO = "freoa-verifica/apuracao-porta-l/1"
PREFIXO_RELATORIOS = "apuracoes/"
_SHA = re.compile(r"^[0-9a-f]{64}$")
CAMPOS_ITEM = {"estado", "rotulo", "versao", "relatorio", "relatorio_sha256"}
CAMPOS_RELATORIO = {"esquema", "rota", "capacidade", "capacidade_porta_l", "versao", "resultado", "executor",
                    "bytes_conferidos"}
Leitor = Callable[[str], "bytes | None"]  # caminho relativo do relatório -> bytes (None se ilegível)


def leitor_do_pacote(caminho: str) -> bytes | None:
    """Lê o relatório de `data/apuracoes/` do pacote instalado; qualquer outro caminho (absoluto, `..`, fora do prefixo,
    de outra extensão) é recusado."""
    if (not isinstance(caminho, str) or not caminho.startswith(PREFIXO_RELATORIOS) or not caminho.endswith(".json")
            or ".." in caminho.split("/") or "\\" in caminho or ":" in caminho):
        return None
    try:
        from importlib.resources import files
        return files("freoa_verifica").joinpath("data", *caminho.split("/")).read_bytes()
    except (OSError, ValueError, ModuleNotFoundError, AttributeError):
        return None


def _referencia_ok(item: dict[str, Any]) -> bool:
    return (isinstance(item.get("relatorio"), str) and bool(item["relatorio"])
            and isinstance(item.get("relatorio_sha256"), str) and bool(_SHA.match(item["relatorio_sha256"]))
            and isinstance(item.get("versao"), str) and bool(item["versao"]))


def _sha_ok(x: Any) -> bool:
    return isinstance(x, str) and bool(_SHA.match(x)) and x != "0" * 64


def erros_do_relatorio(rota: str, capacidade: str, item: dict[str, Any], dados: bytes | None) -> list[str]:
    """Problemas do relatório de apuração apontado por `item`; lista vazia = relatório identificável e coerente."""
    if dados is None:
        return ["relatório de apuração ilegível ou fora de data/apuracoes"]
    erros: list[str] = []
    if hashlib.sha256(dados).hexdigest() != item.get("relatorio_sha256"):
        return ["bytes do relatório não conferem com relatorio_sha256"]
    try:
        rel = json.loads(dados.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return ["relatório de apuração não é JSON"]
    if not isinstance(rel, dict) or set(rel) != CAMPOS_RELATORIO:
        return [f"relatório de apuração fora do esquema (campos devem ser exatamente {sorted(CAMPOS_RELATORIO)})"]
    if rel["esquema"] != ESQUEMA_RELATORIO:
        erros.append(f"esquema do relatório diferente de {ESQUEMA_RELATORIO}")
    for campo, esperado in (("rota", rota), ("capacidade", capacidade), ("versao", item.get("versao")),
                            ("resultado", item.get("estado")),
                            ("capacidade_porta_l", LETRA_DA_CAPACIDADE.get(capacidade))):
        if rel[campo] != esperado:
            erros.append(f"relatório declara {campo}={rel[campo]!r}; o item exige {esperado!r}")
    ex = rel["executor"]
    if (not isinstance(ex, dict) or set(ex) != {"versao_executor", "qualificante", "conjunto", "gerado_em"}
            or ex.get("qualificante") is not True or ex.get("conjunto") not in ("desenvolvimento", "reserva")
            or not isinstance(ex.get("versao_executor"), str) or not ex["versao_executor"]
            or not isinstance(ex.get("gerado_em"), str) or not ex["gerado_em"]):
        erros.append("executor do relatório sem execução qualificante identificada")
    bc = rel["bytes_conferidos"]
    if (not isinstance(bc, dict) or set(bc) != {"conjunto_sha256", "mutantes_sha256", "congelamento_sha256"}
            or not all(_sha_ok(v) for v in bc.values())):
        erros.append("bytes conferidos sem os hashes SHA-256 do conjunto, dos mutantes e do congelamento")
    return erros


def _erros(dados: Any, leitor: Leitor | None) -> tuple[list[str], list[str]]:
    """(erros estruturais, erros de estado). Estrutural invalida o arquivo todo; de estado rebaixa só o item."""
    estruturais: list[str] = []
    de_estado: list[str] = []
    if not isinstance(dados, dict) or not isinstance(dados.get("rotas"), list) or not dados["rotas"]:
        return ["rotas ausente ou vazia"], []
    vistas: set[str] = set()
    for r in dados["rotas"]:
        if not isinstance(r, dict) or not all(isinstance(r.get(k), str) and r[k] for k in ("rota", "fonte", "perfil")):
            estruturais.append(f"rota inválida: {r!r}")
            continue
        if r["rota"] in vistas:
            estruturais.append(f"rota repetida: {r['rota']}")
        vistas.add(r["rota"])
        caps = r.get("capacidades")
        if not isinstance(caps, dict) or set(caps) != set(CAPACIDADES):
            estruturais.append(f"{r['rota']}: capacidades devem ser exatamente {sorted(CAPACIDADES)}")
            continue
        for nome, item in caps.items():
            if not isinstance(item, dict) or set(item) != CAMPOS_ITEM:
                estruturais.append(f"{r['rota']}.{nome}: campos devem ser exatamente {sorted(CAMPOS_ITEM)}")
                continue
            if item["rotulo"] != CAPACIDADES[nome]:
                estruturais.append(f"{r['rota']}.{nome}: rótulo diverge do da emenda ({CAPACIDADES[nome]!r})")
            if item["estado"] not in ESTADOS:
                de_estado.append(f"{r['rota']}.{nome}: estado {item['estado']!r} fora de {ESTADOS}")
            elif item["estado"] != "nao_apurada":
                if not _referencia_ok(item):
                    de_estado.append(f"{r['rota']}.{nome}: estado {item['estado']} sem relatório de apuração e versão "
                                     f"referenciados por SHA-256")
                else:
                    dados_rel = leitor(item["relatorio"]) if leitor is not None else None
                    for e in erros_do_relatorio(r["rota"], nome, item, dados_rel):
                        de_estado.append(f"{r['rota']}.{nome}: {e}")
    return estruturais, de_estado


def validar(dados: Any, leitor: Leitor | None = None) -> list[str]:
    """Problemas do arquivo de rotas; lista vazia = conforme. Estado diferente de `nao_apurada` exige o relatório de
    apuração (esquema, rota, capacidade, versão, resultado e bytes por hash) lido por `leitor`; sem `leitor`, nenhum
    estado diferente de `nao_apurada` é demonstrável."""
    estruturais, de_estado = _erros(dados, leitor)
    return estruturais + de_estado


def carregar(texto_json: str, leitor: Leitor | None = leitor_do_pacote) -> list[dict[str, Any]]:
    """Rotas do arquivo, com leitura fechada: aplica `validar` por inteiro. Erro estrutural (arquivo ilegível, fora do
    esquema, rota ou capacidade fora do conjunto) não publica estado algum (lista vazia); estado sem relatório de
    apuração identificável vira `nao_apurada`."""
    try:
        dados = json.loads(texto_json)
    except (ValueError, TypeError):
        _log.warning("qualificacao_rotas.json ilegível", exc_info=True)
        return []
    estruturais, _ = _erros(dados, leitor)
    if estruturais:
        _log.warning("qualificacao_rotas.json fora do esquema: %s", estruturais[0])
        return []
    rotas = copy.deepcopy(dados["rotas"])
    for r in rotas:
        for nome, item in r["capacidades"].items():
            if item["estado"] == "nao_apurada":
                continue
            if not erros_do_relatorio(r["rota"], nome, item, leitor(item["relatorio"]) if leitor is not None else None) \
                    and item["estado"] in ESTADOS and _referencia_ok(item):
                continue
            _log.warning("estado sem relatório de apuração identificável rebaixado a nao_apurada")
            item.update(estado="nao_apurada", versao=None, relatorio=None, relatorio_sha256=None)
    return rotas


def anexar_rotas(itens: list[dict[str, Any]], rotas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cada item da Porta L ganha `rotas` (estado da capacidade em cada rota); os demais itens ficam como estão.
    O estado do item continua sendo o da Porta (nao_apurada até a apuração): a rota não o promove. Rota ou capacidade
    ausente é lida como `nao_apurada`, nunca como erro."""
    rotulo_para_cap = {v: k for k, v in CAPACIDADES.items()}
    saida = []
    for it in itens:
        it = dict(it)
        cap = rotulo_para_cap.get(it.get("rotulo")) if it.get("porta") == "L" else None
        if cap is not None:
            lista = []
            for r in rotas:
                c = (r.get("capacidades") or {}).get(cap) if isinstance(r, dict) else None
                c = c if isinstance(c, dict) else {}
                lista.append({"rota": r.get("rota") if isinstance(r, dict) else None,
                              "estado": c.get("estado", "nao_apurada"), "versao": c.get("versao"),
                              "relatorio_sha256": c.get("relatorio_sha256")})
            it["rotas"] = lista
        saida.append(it)
    return saida
