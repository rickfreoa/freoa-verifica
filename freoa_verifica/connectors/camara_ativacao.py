"""Fluxo de ativação da rota Câmara (decisão 0080, §2): etapas ordenadas, com falha fechada.

1. robots dos dois hosts lidos e decididos (§4);
2. termo capturado pela exceção do §3 e preservado íntegro;
3. revisão do auditor registrada em arquivo, com o hash do termo conferido;
4. só então `camara_ativacao.json` é gravado no home.

O fluxo é duas fases porque a revisão é humana: `capturar` cumpre 1–2 e grava `camara/pre-ativacao.json`;
`registrar` confere 3 e grava 4. Sem registro válido o conector continua `ativacao_ao_vivo_pendente`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from freoa_verifica import __version__
from freoa_verifica.connectors import camara_robots as rb
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_estado import Estado, Relogio, iso, sha256
from freoa_verifica.connectors.camara_policy import HOSTS, TERMO_URL
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO

CAMINHOS_DE_CONTEUDO = {
    "www2.camara.leg.br": (urlsplit(TERMO_URL).path,
                           "/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-norma-pl.html"),
    "www.camara.leg.br": ("/legislacao", "/legislacao/busca"),
}
_CAMPOS = ("termo_sha256", "termo_url", "robots_sha256", "versao_produto", "instante", "revisao", "registro_sha256")


class AtivacaoRecusada(Unavailable):
    """Etapa que impede a ativação (falha fechada); o `reason` é estável."""


def _data_exibida(texto: str) -> str | None:
    achado = re.search(r"(?:atualiza\w+|vers[aã]o|vig[eê]ncia)[^0-9<]{0,40}(\d{1,2}/\d{1,2}/\d{4})", texto, re.I)
    return achado.group(1) if achado else None


def _selo(registro: dict) -> str:
    base = {k: v for k, v in registro.items() if k != "registro_sha256"}
    return sha256(json.dumps(base, ensure_ascii=False, sort_keys=True).encode())


def capturar(portao: Portao, estado: Estado, relogio: Relogio | None = None) -> dict:
    """Etapas 1 e 2. Qualquer falha levanta `Unavailable` e nada é gravado como pré-condição cumprida."""
    relogio = relogio or portao.relogio
    robots = {}
    for host in ("www2.camara.leg.br", "www.camara.leg.br"):
        politica = portao.garantir_politica(host)
        grupos = rb.interpretar(portao._corpo(politica))
        for caminho in CAMINHOS_DE_CONTEUDO[host]:
            decisao = rb.decidir(grupos, caminho)
            if decisao.estado != rb.PERMITIDO:
                raise AtivacaoRecusada(f"robots_{'recusa' if decisao.estado == rb.PROIBIDO else 'inconclusivo'}",
                                       evidencia={"host": host, "robots_sha256": politica["sha256"]})
        robots[host] = politica["sha256"]
    resposta = portao.obter(TERMO_URL)
    if resposta.status != 200 or resposta.final_url != TERMO_URL or resposta.redirects or not resposta.body:
        raise AtivacaoRecusada("termo_resposta_invalida")
    texto = resposta.body.decode("utf-8", "replace")
    recibo = {"url": resposta.url, "capturado_em": resposta.fetched_at, "status": resposta.status, "mime": resposta.mime,
              "bytes": len(resposta.body), "sha256": resposta.sha256, "data_ou_versao_exibida": _data_exibida(texto),
              "politica_robots_sha256": portao.politica_de.get(TERMO_URL), "user_agent": USER_AGENT_IDENTIFICADO}
    if sha256(resposta.body) != resposta.sha256:
        raise AtivacaoRecusada("termo_hash_divergente")
    estado.guardar_termo(resposta.body, recibo)
    pre = {"termo_sha256": resposta.sha256, "termo_recibo": recibo, "robots_sha256": robots,
           "versao_produto": __version__, "instante": iso(relogio.agora())}
    estado.gravar_pre_ativacao(pre)
    return pre


def registrar(estado: Estado, revisao_arquivo: Path | str, relogio: Relogio | None = None) -> dict:
    """Etapas 3 e 4: confere o registro de revisão do auditor e só então grava a ativação."""
    relogio = relogio or Relogio()
    pre = estado.ler_pre_ativacao()
    if not pre:
        raise AtivacaoRecusada("pre_condicoes_nao_cumpridas")
    try:
        bruto = Path(revisao_arquivo).read_bytes()
        revisao = json.loads(bruto)
    except (OSError, ValueError) as exc:
        raise AtivacaoRecusada("revisao_do_auditor_ausente_ou_ilegivel") from exc
    if not isinstance(revisao, dict) or not all(isinstance(revisao.get(k), str) and revisao[k].strip()
                                                 for k in ("auditor", "revisado_em", "termo_sha256", "resultado")):
        raise AtivacaoRecusada("revisao_do_auditor_incompleta")
    if revisao["resultado"] != "conforme":
        raise AtivacaoRecusada("termo_divergente_exige_revisao_da_decisao")
    if revisao["termo_sha256"] != pre["termo_sha256"] or estado.termo_preservado(pre["termo_sha256"]) is None:
        raise AtivacaoRecusada("termo_revisado_difere_do_preservado")
    for host, digest in pre["robots_sha256"].items():
        atual = estado.politica(host)
        if not atual or atual.get("sha256") != digest:
            raise AtivacaoRecusada("robots_mudou_desde_a_captura")
    registro = {"termo_sha256": pre["termo_sha256"], "termo_url": TERMO_URL, "robots_sha256": pre["robots_sha256"],
                "versao_produto": __version__, "instante": iso(relogio.agora()),
                "revisao": {"sha256": sha256(bruto), "auditor": revisao["auditor"],
                            "revisado_em": revisao["revisado_em"], "resultado": "conforme",
                            "termo_sha256": revisao["termo_sha256"]}}
    registro["registro_sha256"] = _selo(registro)
    estado.gravar_ativacao(registro)
    return registro


def ativacao(estado: Estado) -> dict | None:
    """Registro de ativação íntegro e coerente com o termo preservado; senão None (rota pendente)."""
    try:
        registro = estado.ler_ativacao()
    except OSError:
        return None
    if not isinstance(registro, dict) or any(k not in registro for k in _CAMPOS):
        return None
    revisao = registro["revisao"]
    if (registro["termo_url"] != TERMO_URL or registro["registro_sha256"] != _selo(registro)
            or not isinstance(revisao, dict) or revisao.get("resultado") != "conforme"
            or revisao.get("termo_sha256") != registro["termo_sha256"]
            or not isinstance(registro["robots_sha256"], dict) or set(registro["robots_sha256"]) != set(HOSTS)
            or estado.termo_preservado(registro["termo_sha256"]) is None):
        return None
    return registro


def atribuicao_do_termo(estado: Estado) -> tuple[str, str | None]:
    """(URL, SHA-256) do termo para a atribuição (§7); o hash é None se não houve captura registrada."""
    registro = ativacao(estado)
    return TERMO_URL, (registro["termo_sha256"] if registro else None)
