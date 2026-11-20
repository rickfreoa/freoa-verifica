"""Contrato aditivo; jamais importa ou chama o adaptador ou a porta."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from freoa_verifica.assistida.perfis import PERFIS
from freoa_verifica.sondas import FONTES_BARRADAS

TENTATIVAS = ContextVar("tentativas_automaticas_assistida", default=None)


def observar_tentativa(url, *, metodo, user_agent, erro=None):
    """Somente depois de tentativa automática real de connector_fetch, sem dados de pedido."""
    registro = TENTATIVAS.get()
    if registro is None:
        return
    try:
        host = urlsplit(url).hostname
    except (ValueError, TypeError, AttributeError):
        return
    for fonte, perfil in PERFIS.items():
        if host in perfil.porta.origens:
            ev = getattr(erro, "evidencia", {})
            prova = None
            if metodo == "GET" and user_agent == "identified" and erro is not None:
                if (
                    fonte == "planalto"
                    and erro.reason == "recusa_identificado_planalto"
                    and ev.get("causa") == "transporte_TransportError"
                    and "status" not in ev
                ):
                    prova = "0048"
                elif (
                    fonte == "normas_leg"
                    and ev.get("status") == 403
                    and erro.categoria == "ambiental_desafio"
                    and ev.get("marcador")
                ):
                    prova = "0085"
            registro[fonte] = {
                "em": datetime.now(timezone.utc).isoformat(),
                "prova": prova,
                "alvo": perfil.sanitizar(url),
            }


def atualizar(conn, operacao, tentativas):
    if operacao not in set().union(*(p.operacoes for p in PERFIS.values())):
        return
    for fonte, tentativa in tentativas.items():
        conn.execute(
            "INSERT INTO tentativa_assistida(fonte,operacao,em,prova,alvo) VALUES (?,?,?,?,?) "
            "ON CONFLICT(fonte,operacao) DO UPDATE SET em=excluded.em,prova=excluded.prova,alvo=excluded.alvo",
            (fonte, operacao, tentativa["em"], tentativa["prova"], tentativa["alvo"]),
        )
    if tentativas:
        conn.commit()


def indicacao(fonte, operacao, tentativa, *, agora=None):
    perfil = PERFIS.get(fonte)
    if (
        not perfil
        or fonte in FONTES_BARRADAS
        or operacao not in perfil.operacoes
        or not tentativa
    ):
        return None
    try:
        em = datetime.fromisoformat(tentativa["em"])
        agora = agora or datetime.now(timezone.utc)
        prova = "0048" if fonte == "planalto" else "0085"
        if tentativa["prova"] != prova or not timedelta(0) <= agora - em <= timedelta(
            days=30
        ):
            return None
    except (ValueError, KeyError, TypeError):
        return None
    alvo = perfil.sanitizar(tentativa["alvo"])
    return {
        "indicacao": "requer_sessao_assistida",
        "fonte": fonte,
        "comando": f"fv sessao {fonte}" + (f' --alvo "{alvo}"' if alvo else ""),
        "alvo": alvo,
    }


def anexar(conn, operacao, out):
    if not isinstance(out, dict):
        return out
    mapa = {}
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='tentativa_assistida'"
    ).fetchone():
        return out  # home antigo somente leitura, ainda sem a migração aditiva
    for fonte in PERFIS:
        row = conn.execute(
            "SELECT em,prova,alvo FROM tentativa_assistida WHERE fonte=? AND operacao=?",
            (fonte, operacao),
        ).fetchone()
        item = indicacao(fonte, operacao, dict(row) if row else None)
        if item:
            mapa[fonte] = item
    if mapa:
        out["sessoes_assistidas"] = mapa
        fontes = out.get("fontes", {})
        if isinstance(fontes, dict):
            for fonte, obj in fontes.items():
                if fonte in mapa and isinstance(obj, dict):
                    obj["sessao_assistida"] = mapa[fonte]
        for falha in out.get("falhas", []):
            fonte = falha.get("fonte")
            if fonte in mapa:
                falha["sessao_assistida"] = mapa[fonte]
    return out


def cobertura(conn, fonte):
    colunas = {r[1] for r in conn.execute("PRAGMA table_info(capture)")}
    if "modalidade_acesso" not in colunas:
        return {
            "publico_humano": {"declarado": fonte in PERFIS},
            "automatico": {"capturas": None},
            "assistido": {"habilitado": fonte in PERFIS, "capturas": None},
        }
    n = conn.execute(
        "SELECT COUNT(*) FROM capture WHERE source_id=? AND modalidade_acesso='sessao_assistida'",
        (fonte,),
    ).fetchone()[0]
    automaticas = conn.execute(
        "SELECT COUNT(*) FROM capture WHERE source_id=? AND modalidade_acesso='automatico'",
        (fonte,),
    ).fetchone()[0]
    return {
        "publico_humano": {"declarado": fonte in PERFIS},
        "automatico": {"capturas": automaticas},
        "assistido": {"habilitado": fonte in PERFIS, "capturas": n},
    }
