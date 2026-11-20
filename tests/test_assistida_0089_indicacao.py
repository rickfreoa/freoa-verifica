"""0089 (b): cenarios sinteticos offline, sem navegador ou rede."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from freoa_verifica.assistida import indicacao as ind

from freoa_verifica.store.db import connect

from tests.assistida_0089_util import sessao as sessao, URL, META


@pytest.mark.parametrize(
    "fonte,op,prova,dias,esperado",
    [
        ("planalto", "verificar_texto", "0048", 0, True),
        ("normas_leg", "obter_dispositivo", "0085", 30, True),
        ("normas_leg", "obter_dispositivo", "0085", 31, False),
        ("normas_leg", "obter_dispositivo", None, 0, False),
        ("tjsp", "obter_dispositivo", "0085", 0, False),
        ("dou", "obter_dispositivo", "0085", 0, False),
        ("planalto", "obter_evidencia", "0048", 0, False),
    ],
)
def test_indicacao_conjuntiva(fonte, op, prova, dias, esperado):
    agora = datetime.now(timezone.utc)
    tentativa = {
        "em": (agora - timedelta(days=dias)).isoformat(),
        "prova": prova,
        "alvo": URL,
    }
    assert bool(ind.indicacao(fonte, op, tentativa, agora=agora)) == esperado


def test_401_categoria_isolada_e_sucesso_apagam_indicacao():
    from freoa_verifica.connectors.base import Unavailable

    tentativas = {}
    token = ind.TENTATIVAS.set(tentativas)
    try:
        ind.observar_tentativa(
            META,
            metodo="GET",
            user_agent="identified",
            erro=Unavailable(
                "captcha", "ambiental_desafio", {"status": 403, "marcador": "captcha"}
            ),
        )
        assert tentativas["normas_leg"]["prova"] == "0085"
        ind.observar_tentativa(
            META,
            metodo="GET",
            user_agent="identified",
            erro=Unavailable(
                "http_401", "ambiental_desafio", {"status": 401, "marcador": "captcha"}
            ),
        )
        assert tentativas["normas_leg"]["prova"] is None
        ind.observar_tentativa(
            URL,
            metodo="GET",
            user_agent="identified",
            erro=Unavailable("x", "recusa_identificado"),
        )
        assert tentativas["planalto"]["prova"] is None
    finally:
        ind.TENTATIVAS.reset(token)


def test_contrato_indicacao_preserva_motivo_tipo(tmp_path):
    conn = connect(tmp_path / "verifica.sqlite3")
    tentativa = {
        "em": datetime.now(timezone.utc).isoformat(),
        "prova": "0048",
        "alvo": URL,
    }
    ind.atualizar(conn, "buscar_legislacao", {"planalto": tentativa})
    out = {
        "fontes_indisponiveis": {"planalto": "recusa"},
        "fontes": {
            "planalto": {"motivo": "recusa", "categoria": "recusa_identificado"}
        },
        "falhas": [{"fonte": "planalto", "motivo": "recusa"}],
    }
    ind.anexar(conn, "buscar_legislacao", out)
    assert out["fontes_indisponiveis"] == {"planalto": "recusa"}
    assert out["fontes"]["planalto"]["motivo"] == "recusa"
    assert (
        out["falhas"][0]["sessao_assistida"]["indicacao"] == "requer_sessao_assistida"
    )
    assert out["sessoes_assistidas"]["planalto"]["comando"].startswith(
        "fv sessao planalto"
    )
    conn.close()
