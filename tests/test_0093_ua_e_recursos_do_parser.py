"""0093: recibo persistido com o User-Agent de outra versão do pacote não é estado incoerente; bloqueios por recurso
causados pela leitura antiga de `encoding` saem só por reabertura registrada."""
from __future__ import annotations

import pytest

from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors import normas_leg as nl
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.guarda import da_chamada
from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO, eh_user_agent_identificado
from tests._camara_util import BUSCA, ROBOTS_WWW, ROBOTS_WWW2, portao, robots_resp
from tests.test_camara_0081_ativacao_e_robots import _regravar_recibo, ativar_em
from tests.test_camara_0081_ritmo_falhas_barreiras import BUSCA2, WWW
from tests.test_camara_0081_r2_portao import com_delay, rotas_www

URL = "(+https://github.com/rickfreoa/freoa-verifica)"


@pytest.mark.parametrize("valor,esperado", [
    (USER_AGENT_IDENTIFICADO, True),
    (f"freoa-verifica/1.4.0a6 {URL}", True),
    (f"freoa-verifica/1.4.0 {URL}", True),
    (f"freoa-verifica/2.0.0rc1 {URL}", True),
    (f"freoa-verifica/1.4.0.post1 {URL}", True),
    ("Mozilla/5.0", False),
    ("outro", False),
    (f"freoa-verifica/x {URL}", False),
    ("freoa-verifica/1.4.0a6 (+https://alheio.invalid)", False),
    (f"freoa-verifica/1.4.0a6 {URL} extra", False),
    ("freoa-verifica/\u0661.4.0 (+https://github.com/rickfreoa/freoa-verifica)", False),  # dígito não ASCII
    (None, False),
    (1, False),
])
def test_formato_do_user_agent_identificado(valor, esperado):
    assert eh_user_agent_identificado(valor) is esperado


def test_politica_obtida_por_versao_anterior_continua_valida(tmp_path):
    """Defeito visto no home real na 1.4.0a7: recibo da a6 virava `politica_recibo_incoerente` e encerrava o escopo."""
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots_resp(ROBOTS_WWW, com_delay(30)), **rotas_www(BUSCA, BUSCA2)})
    p.obter(BUSCA)
    recibo = estado.politica(WWW)
    estado._gravar(f"robots-{WWW}.json", {**recibo, "user_agent": f"freoa-verifica/1.4.0a6 {URL}"})
    relogio.avancar(60)
    with da_chamada():
        p.obter(BUSCA2)  # sem persistencia_local_falhou
    assert estado.politica(WWW)["user_agent"].startswith("freoa-verifica/1.4.0a6")


@pytest.mark.parametrize("ua", ["Mozilla/5.0", "freoa-verifica/1.4.0a6 (+https://alheio.invalid)"])
def test_user_agent_fora_do_formato_continua_falha_local_terminal(tmp_path, ua):
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots_resp(ROBOTS_WWW, com_delay(30)), **rotas_www(BUSCA, BUSCA2)})
    p.obter(BUSCA)
    estado._gravar(f"robots-{WWW}.json", {**estado.politica(WWW), "user_agent": ua})
    relogio.avancar(60)
    with da_chamada():
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(BUSCA2)
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(ROBOTS_WWW2)


def test_recibo_do_termo_de_versao_anterior_continua_preservado(tmp_path):
    registro, estado, relogio, t = ativar_em(tmp_path)
    selo = _regravar_recibo(estado, registro, lambda r: r.update(user_agent=f"freoa-verifica/1.4.0a5 {URL}"))
    assert estado.termo_preservado(registro["termo_sha256"], selo) is not None
    assert ativ.ativacao(estado) is not None


# --- (b) bloqueios por recurso causados pelo parser -----------------------------------------------------------------

API = f"https://{nl.HOST}/api/public/normas?urn=urn:lex:br:federal:lei:2025;15177&tipo_documento=maior-detalhe"
API2 = f"https://{nl.HOST}/api/public/normas?urn=urn:lex:br:federal:lei:2024;15042&tipo_documento=maior-detalhe"
API3 = f"https://{nl.HOST}/api/public/normas?urn=urn:lex:br:federal:lei:2016;13256&tipo_documento=maior-detalhe"


def _bloqueio(motivo, classe, desde="2026-11-26T22:44:32+00:00"):
    return {"motivo": motivo, "classe": classe, "categoria": motivo, "desde": desde, "ate": None,
            "evidencia": {"url": API}}


def _portao_normas(tmp_path):
    return nl.NormasPortao(lambda *a, **k: (_ for _ in ()).throw(AssertionError("sem rede")), home=tmp_path)


def test_libera_so_os_bloqueios_de_parser_e_registra(tmp_path):
    p = _portao_normas(tmp_path)
    p.estado.bloquear_recurso(nl.HOST, API, _bloqueio("resposta_inesperada", "corpo_ou_mime"))
    p.estado.bloquear_recurso(nl.HOST, API2, _bloqueio("resposta_inesperada", "corpo_ou_mime"))
    p.estado.bloquear_recurso(nl.HOST, API3, _bloqueio("nao_encontrado", "recurso_persistente"))
    liberados = p.liberar_recursos_do_parser("0093, titular, 27/11/2026")
    assert liberados == sorted([API, API2])
    assert p.estado.bloqueio_do_recurso(nl.HOST, API) is None and p.estado.bloqueio_do_recurso(nl.HOST, API2) is None
    assert p.estado.bloqueio_do_recurso(nl.HOST, API3) is not None  # outro motivo: intacto
    reab = [r for r in p.estado.reaberturas(nl.HOST) if r["escopo"] == "recurso"]
    assert {r["url"] for r in reab} == {API, API2}
    assert all("0093, titular, 27/11/2026" in r["revisao"] and r["anterior"]["motivo"] == "resposta_inesperada"
               and "causa não reconstituída" in r["revisao"] for r in reab)


@pytest.mark.parametrize("desde", [
    "2026-11-27T10:08:15+00:00",   # o próprio instante da publicação da correção
    "2026-11-28T09:00:00+00:00",   # gravado pela leitura corrigida: identidade divergente, encoding inválido etc.
])
def test_bloqueio_posterior_a_correcao_nao_e_liberado(tmp_path, desde):
    """Codex 0093, achado 1: repetir o comando liberava bloqueios novos e atribuía causa sem prova."""
    p = _portao_normas(tmp_path)
    p.estado.bloquear_recurso(nl.HOST, API, _bloqueio("resposta_inesperada", "corpo_ou_mime", desde))
    assert p.liberar_recursos_do_parser("0093, titular, 27/11/2026") == []
    assert p.estado.bloqueio_do_recurso(nl.HOST, API) is not None


@pytest.mark.parametrize("desde,esperado", [
    ("2026-11-26T22:44:32+00:00", True), ("2026-11-27T10:08:14+00:00", True), ("2026-11-27T10:08:15+00:00", False),
    ("2026-11-27T07:08:14-03:00", True), ("2026-11-26T22:44:32", False), ("ontem", False), (None, False),
])
def test_corte_temporal_da_correcao(desde, esperado):
    assert nl._anterior_a_correcao(desde) is esperado


@pytest.mark.parametrize("decisao", ["", "   ", None])
def test_liberacao_exige_decisao(tmp_path, decisao):
    p = _portao_normas(tmp_path)
    p.estado.bloquear_recurso(nl.HOST, API, _bloqueio("resposta_inesperada", "corpo_ou_mime"))
    with pytest.raises(ValueError, match="decisao_necessaria"):
        p.liberar_recursos_do_parser(decisao)
    assert p.estado.bloqueio_do_recurso(nl.HOST, API) is not None


def test_cli_so_libera_recursos_com_a_opcao(tmp_path, monkeypatch):
    from freoa_verifica.cli import main
    from freoa_verifica.service import Verifica

    chamadas = []
    monkeypatch.setattr(Verifica, "abrir_normas_leg",
                        lambda self, decisao, liberar_recursos_do_parser=False: chamadas.append(
                            (decisao, liberar_recursos_do_parser)) or {"status": "ok"})
    for extra in ([], ["--liberar-recursos-do-parser"]):
        with pytest.raises(SystemExit) as exc:
            main(["--home", str(tmp_path), "acervo", "abrir-normas-leg", "--decisao", "0093, titular", *extra, "--json"])
        assert exc.value.code == 0
    assert chamadas == [("0093, titular", False), ("0093, titular", True)]
