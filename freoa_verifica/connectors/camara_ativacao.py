"""Fluxo de ativação da rota Câmara (decisão 0080, §2; correções da 0081): etapas ordenadas, com falha fechada.

1. robots dos dois hosts lidos e decididos (§4) pelo mesmo fluxo do portão (a recusa persiste o bloqueio do host);
2. termo capturado pela exceção do §3 e preservado íntegro (recibo completo e vínculo à política);
3. revisão do auditor registrada em arquivo (lido uma só vez; os bytes ficam preservados), com o hash do termo conferido;
4. só então `camara_ativacao.json` é gravado no home, depois de o próprio registro final ser validado.

O fluxo é duas fases porque a revisão é humana: `capturar` cumpre 1–2 e grava `camara/pre-ativacao.json`;
`registrar` confere 3 e grava 4. Sem registro válido o conector continua `ativacao_ao_vivo_pendente`. A mesma
validação (`validar_registro`) vale ao registrar e antes de CADA obtenção viva.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

from freoa_verifica import __version__
from freoa_verifica.connectors import camara_robots as rb
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_estado import (Estado, EstadoIndisponivel, Relogio, _de_iso, eh_sha256, iso,
                                                     json_de_bytes, sha256)
from freoa_verifica.connectors.camara_policy import HOSTS, TERMO_URL
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO
from freoa_verifica.texto_resposta import texto_da_resposta, texto_do_response
from freoa_verifica.transport import RespostaInvalida

CAMINHOS_DE_CONTEUDO = {
    "www2.camara.leg.br": (urlsplit(TERMO_URL).path,
                           "/legin/fed/lei/1970-1979/lei-6404-15-dezembro-1976-368447-norma-pl.html"),
    "www.camara.leg.br": ("/legislacao", "/legislacao/busca"),
}
_CAMPOS = ("termo_sha256", "termo_url", "robots_sha256", "versao_produto", "instante", "revisao", "registro_sha256")
_CAMPOS_DA_REVISAO = {"sha256", "auditor", "revisado_em", "resultado", "termo_sha256"}


class AtivacaoRecusada(Unavailable):
    """Etapa que impede a ativação (falha fechada); o `reason` é estável."""


def _data_exibida(texto: str) -> str | None:
    achado = re.search(r"(?:atualiza\w+|vers[aã]o|vig[eê]ncia)[^0-9<]{0,40}(\d{1,2}/\d{1,2}/\d{4})", texto, re.I)
    return achado.group(1) if achado else None


def _selo(registro: dict) -> str:
    base = {k: v for k, v in registro.items() if k != "registro_sha256"}
    return sha256(json.dumps(base, ensure_ascii=False, sort_keys=True).encode())


def _local(exc: Exception) -> Unavailable:
    return AtivacaoRecusada("persistencia_local_falhou", None, {"causa": type(exc).__name__})


def capturar(portao: Portao, estado: Estado, relogio: Relogio | None = None) -> dict:
    """Etapas 1 e 2. Qualquer falha levanta `Unavailable` e nada é gravado como pré-condição cumprida."""
    relogio = relogio or portao.relogio
    robots = {}
    for host in ("www2.camara.leg.br", "www.camara.leg.br"):
        try:
            politica = portao.verificar_caminhos(host, CAMINHOS_DE_CONTEUDO[host])
        except AtivacaoRecusada:
            raise
        except Unavailable as exc:
            if exc.reason.startswith("robots_") and exc.evidencia.get("bloqueio"):
                # Recusa ou inconclusão do robots: o portão já persistiu o bloqueio do host (0080 §6).
                raise AtivacaoRecusada(exc.reason, exc.categoria, {**exc.evidencia, "host": host}) from exc
            raise
        robots[host] = politica["sha256"]
    resposta = portao.obter(TERMO_URL)
    if resposta.status != 200 or resposta.final_url != TERMO_URL or resposta.redirects or not resposta.body:
        raise AtivacaoRecusada("termo_resposta_invalida")
    try:
        texto = texto_do_response(resposta)
    except RespostaInvalida as exc:
        raise AtivacaoRecusada("termo_resposta_invalida") from exc
    if sha256(resposta.body) != resposta.sha256:
        raise AtivacaoRecusada("termo_hash_divergente")
    if portao.politica_de.get(TERMO_URL) != robots["www2.camara.leg.br"]:
        raise AtivacaoRecusada("politica_mudou_durante_a_captura")
    recibo = {"url": resposta.url, "capturado_em": resposta.fetched_at, "status": resposta.status, "mime": resposta.mime,
              "bytes": len(resposta.body), "sha256": resposta.sha256, "data_ou_versao_exibida": _data_exibida(texto),
              "politica_robots_sha256": portao.politica_de.get(TERMO_URL), "user_agent": USER_AGENT_IDENTIFICADO}
    pre = {"termo_sha256": resposta.sha256, "termo_recibo": recibo, "robots_sha256": robots,
           "versao_produto": __version__, "instante": iso(relogio.agora())}
    try:
        estado.guardar_termo(resposta.body, recibo)
        estado.gravar_pre_ativacao(pre)
    except EstadoIndisponivel as exc:
        raise _local(exc) from exc
    return pre


def _pre_valida(pre) -> bool:
    return (isinstance(pre, dict) and eh_sha256(pre.get("termo_sha256")) and isinstance(pre.get("robots_sha256"), dict)
            and set(pre["robots_sha256"]) == set(HOSTS) and all(eh_sha256(v) for v in pre["robots_sha256"].values()))


def _content_type_preservado(estado: Estado, host: str, digest: str) -> str:
    """Content-Type do recibo da política que tem este hash (vigente ou arquivada)."""
    atual = estado.politica(host)
    if atual and atual["sha256"] == digest:
        return atual["content_type"]
    for registro in estado.politicas_arquivadas(host):
        if registro["sha256"] == digest:
            return registro["content_type"]
    raise EstadoIndisponivel("recibo_da_politica_ausente")


def _politica_decide_o_conteudo(estado: Estado, host: str, digest: str) -> bool:
    """Bytes preservados do robots (hash conferido) permitem os caminhos de conteúdo do host (0080 §2.1)."""
    corpo = estado.corpo_da_politica(host, digest)
    grupos = rb.interpretar(texto_da_resposta(corpo, _content_type_preservado(estado, host, digest)))
    return all(rb.decidir(grupos, c).estado == rb.PERMITIDO for c in CAMINHOS_DE_CONTEUDO[host])


def registrar(estado: Estado, revisao_arquivo: Path | str, relogio: Relogio | None = None) -> dict:
    """Etapas 3 e 4: confere o registro de revisão do auditor e só então grava a ativação."""
    relogio = relogio or Relogio()
    try:
        pre = estado.ler_pre_ativacao()
    except EstadoIndisponivel as exc:
        raise AtivacaoRecusada("pre_condicoes_nao_cumpridas") from exc
    if not pre or not _pre_valida(pre):
        raise AtivacaoRecusada("pre_condicoes_nao_cumpridas")
    try:
        dados = Path(revisao_arquivo).read_bytes()  # lido UMA vez: o hash registrado é o dos bytes interpretados
        revisao = json_de_bytes(dados)
    except (OSError, ValueError) as exc:  # inclui UnicodeDecodeError e JSON inválido
        raise AtivacaoRecusada("revisao_do_auditor_ausente_ou_ilegivel") from exc
    if not isinstance(revisao, dict) or not all(isinstance(revisao.get(k), str) and revisao[k].strip()
                                                 for k in ("auditor", "revisado_em", "termo_sha256", "resultado")):
        raise AtivacaoRecusada("revisao_do_auditor_incompleta")
    if revisao["resultado"] != "conforme":
        raise AtivacaoRecusada("termo_divergente_exige_revisao_da_decisao")
    if revisao["termo_sha256"] != pre["termo_sha256"] or estado.termo_preservado(pre["termo_sha256"]) is None:
        raise AtivacaoRecusada("termo_revisado_difere_do_preservado")
    agora = relogio.agora()
    try:
        for host, digest in pre["robots_sha256"].items():
            atual = estado.politica(host)
            if not atual or atual.get("sha256") != digest:
                raise AtivacaoRecusada("robots_mudou_desde_a_captura")
        for host, digest in pre["robots_sha256"].items():
            if estado.politica_valida(host, agora) is None:
                raise AtivacaoRecusada("robots_expirado_desde_a_captura")
            if not _politica_decide_o_conteudo(estado, host, digest):
                raise AtivacaoRecusada("robots_nao_permite_o_conteudo")
        revisao_sha = estado.guardar_revisao(dados)
    except (EstadoIndisponivel, rb.RobotsInconclusivo, RespostaInvalida) as exc:
        raise AtivacaoRecusada("robots_preservado_invalido", None, {"causa": type(exc).__name__}) from exc
    registro = {"termo_sha256": pre["termo_sha256"], "termo_url": TERMO_URL, "robots_sha256": pre["robots_sha256"],
                "versao_produto": __version__, "instante": iso(agora),
                "revisao": {"sha256": revisao_sha, "auditor": revisao["auditor"],
                            "revisado_em": revisao["revisado_em"], "resultado": "conforme",
                            "termo_sha256": revisao["termo_sha256"]}}
    registro["registro_sha256"] = _selo(registro)
    if not validar_registro(estado, registro):  # o registro final é validado ANTES de ser publicado
        raise AtivacaoRecusada("registro_de_ativacao_invalido")
    try:
        estado.gravar_ativacao(registro)
    except EstadoIndisponivel as exc:
        raise _local(exc) from exc
    return registro


def _data_valida(texto) -> bool:
    for ler in (date.fromisoformat, datetime.fromisoformat):
        try:
            ler(texto)
            return True
        except (TypeError, ValueError):
            continue
    return False


def validar_registro(estado: Estado, registro) -> bool:
    """Registro de ativação íntegro, completo e coerente com TODA a evidência documental preservada: estrutura,
    revisão (campos e bytes), termo (recibo e vínculo à política) e robots (bytes e decisão sobre o conteúdo)."""
    try:
        if not isinstance(registro, dict) or set(registro) != set(_CAMPOS):
            return False
        revisao = registro["revisao"]
        if (registro["termo_url"] != TERMO_URL or registro["registro_sha256"] != _selo(registro)
                or not eh_sha256(registro["termo_sha256"]) or not isinstance(registro["versao_produto"], str)
                or not registro["versao_produto"] or _de_iso(registro["instante"]) is None
                or not isinstance(registro["robots_sha256"], dict) or set(registro["robots_sha256"]) != set(HOSTS)
                or not all(eh_sha256(v) for v in registro["robots_sha256"].values())):
            return False
        if (not isinstance(revisao, dict) or set(revisao) != _CAMPOS_DA_REVISAO
                or not eh_sha256(revisao["sha256"]) or revisao["resultado"] != "conforme"
                or revisao["termo_sha256"] != registro["termo_sha256"]
                or not all(isinstance(revisao[k], str) and revisao[k].strip() for k in ("auditor", "revisado_em"))
                or not _data_valida(revisao["revisado_em"])):
            return False
        bytes_da_revisao = estado.revisao_preservada(revisao["sha256"])
        if bytes_da_revisao is None:
            return False
        original = json_de_bytes(bytes_da_revisao)
        if (not isinstance(original, dict)
                or any(original.get(k) != revisao[k] for k in ("auditor", "revisado_em", "resultado", "termo_sha256"))):
            return False
        recibo = estado.termo_preservado(registro["termo_sha256"])
        if recibo is None or recibo["politica_robots_sha256"] != registro["robots_sha256"]["www2.camara.leg.br"]:
            return False
        return all(_politica_decide_o_conteudo(estado, host, digest) for host, digest in registro["robots_sha256"].items())
    except (OSError, KeyError, TypeError, ValueError, RespostaInvalida):
        return False


def ativacao(estado: Estado) -> dict | None:
    """Registro de ativação válido (`validar_registro`); senão None (rota pendente)."""
    try:
        registro = estado.ler_ativacao()
    except OSError:
        return None
    return registro if validar_registro(estado, registro) else None


def atribuicao_do_termo(estado: Estado) -> tuple[str, str | None]:
    """(URL, SHA-256) do termo da ativação deste home; o hash é None se não houve captura registrada."""
    registro = ativacao(estado)
    return TERMO_URL, (registro["termo_sha256"] if registro else None)
