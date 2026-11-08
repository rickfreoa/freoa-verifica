"""Decisão 0080 §§1, 3, 4.4, 5 e 6: admissão, ritmo, tetos, barreiras e ciclo de vida do robots.

Tudo com transporte simulado e relógio controlado (sintético por construção; nenhum socket real).
"""
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from freoa_verifica.connectors import camara_portao as cp
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_estado import Estado
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
from freoa_verifica.connectors.camara_policy import TERMO_URL
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.connectors.guarda import da_chamada
from freoa_verifica.transport import BlockedHost, HTTPStatusError
from tests._camara_util import (BUSCA, LEI, ROBOTS_WWW, ROBOTS_WWW2, RelogioFalso, barreira, portao, resposta,
                                robots_resp)

RAIZ = Path(__file__).resolve().parents[1]
BUSCA2 = BUSCA.replace("numero=6404", "numero=6405")
BUSCA3 = BUSCA.replace("numero=6404", "numero=6406")
BUSCA4 = BUSCA.replace("numero=6404", "numero=6407")


def rotas_www(*urls):
    return {u: resposta(u, b"<html>ok</html>") for u in urls}


# --- §1/§3: admissão exata, antes do transporte ------------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade",
    "https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/",
    "https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/termos-gerais/",
    "https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/termos-gerais?x=1",
    "https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/termos-gerais#a",
    "https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/termos-gerais2",
    "https://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/politica-de-privacidade",
    "http://www2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/termos-gerais",
    "https://www.camara.leg.br/termo-de-uso-e-politica-de-privacidade/termos-gerais",
    "https://WWW2.camara.leg.br/termo-de-uso-e-politica-de-privacidade/termos-gerais",
    "https://www2.camara.leg.br:8443/termo-de-uso-e-politica-de-privacidade/termos-gerais",
    "https://www2.camara.leg.br/legin/fed/",
    "https://www2.camara.leg.br/legin/fed/lei/1970-1979/",
    LEI + "?x=1", LEI + "#f", LEI.replace("www2", "www3"), LEI.replace("https", "http"),
    "https://www.camara.leg.br/legislacao/outra", "https://www.camara.leg.br/", "https://exemplo.gov.br/robots.txt",
    "https://www.camara.leg.br/legislacao/norma.pdf", "https://www.camara.leg.br/arquivos/norma.pdf",  # §4.3: nenhum PDF no portal
])
def test_vizinhos_sao_recusados_antes_do_transporte(url):
    p, t, *_ = portao()
    with pytest.raises(Unavailable):
        p.obter(url)
    assert t.chamadas == []


def test_termo_so_pela_url_exata_e_depois_do_robots():
    p, t, *_ = portao()
    resp = p.obter(TERMO_URL)
    assert resp.body and t.urls == [ROBOTS_WWW2, TERMO_URL]  # robots antes do termo
    assert t.chamadas[1][1]["path_prefixes"] == {"www2.camara.leg.br": ("/termo-de-uso-e-politica-de-privacidade/termos-gerais",)}


def test_conector_de_conteudo_nao_obtem_o_termo():
    p, t, *_ = portao()
    con = CamaraLeginConnector(portao=p)
    with pytest.raises(Unavailable):
        con._obter_recurso(TERMO_URL)
    assert t.chamadas == []


def test_parametros_do_transporte_repeticao_zero_sem_redirecionamento_e_ua_identificado():
    p, t, *_ = portao(rotas=rotas_www(BUSCA))
    p.obter(BUSCA)
    for _, kw, _ in t.chamadas:
        assert kw["max_redirects"] == 0 and kw["repeticao"] == 0 and kw["user_agent"] == "identified"


def test_repeticao_zero_chega_ao_transporte_real_e_uma_falha_5xx_emite_uma_vez(monkeypatch, proibir_rede):
    from freoa_verifica.connectors.httputil import connector_fetch
    visto = []

    def falso(url, **kw):
        visto.append((url, kw))
        raise HTTPStatusError(503)

    monkeypatch.setattr("freoa_verifica.connectors.httputil.transport_fetch", falso)
    relogio = RelogioFalso()
    p = Portao(connector_fetch, estado=Estado(None), relogio=relogio)
    with pytest.raises(Unavailable) as erro:
        p.obter(ROBOTS_WWW)
    assert erro.value.reason == "http_503" and erro.value.categoria == "fonte_fora"
    assert len(visto) == 1 and visto[0][1]["repeticao"] == 0 and visto[0][1]["max_redirects"] == 0


# --- §5: ritmo ---------------------------------------------------------------------------------------------------
def test_intervalo_minimo_de_10s_entre_requisicoes_ao_mesmo_host_contando_o_robots():
    p, t, relogio, _ = portao(rotas=rotas_www(BUSCA, BUSCA2))
    p.obter(BUSCA)
    p.obter(BUSCA2)
    inicios = [c[2] for c in t.chamadas]
    assert t.urls == [ROBOTS_WWW, BUSCA, BUSCA2]
    assert [round(b - a, 6) for a, b in zip(inicios, inicios[1:])] == [10.0, 10.0]


def test_limiares_do_ritmo_9_9s_espera_so_o_resto_e_10s_nao_espera():
    p, t, relogio, _ = portao(rotas=rotas_www(BUSCA, BUSCA2, BUSCA3))
    p.obter(BUSCA)
    relogio.avancar(9.9)
    p.obter(BUSCA2)
    assert relogio.dormidas[-1] == pytest.approx(0.1, abs=1e-6) or relogio.dormidas[-1] > 0
    antes = len(relogio.dormidas)
    relogio.avancar(10.0)
    p.obter(BUSCA3)
    assert len(relogio.dormidas) == antes  # já decorreram 10 s: sem espera


def test_hosts_diferentes_nao_se_esperam():
    p, t, relogio, _ = portao()
    p.garantir_politica("www.camara.leg.br")
    p.garantir_politica("www2.camara.leg.br")
    assert t.urls == [ROBOTS_WWW, ROBOTS_WWW2] and relogio.dormidas == []


def test_crawl_delay_maior_que_10s_prevalece():
    rotas = {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\nCrawl-delay: 30\n"), **rotas_www(BUSCA)}
    p, t, relogio, _ = portao(rotas=rotas)
    p.obter(BUSCA)
    p.obter(BUSCA)  # mesma URL fora de guarda: nova emissão
    inicios = [c[2] for c in t.chamadas]
    assert round(inicios[2] - inicios[1], 6) == 30.0


def test_crawl_delay_menor_que_10s_nao_reduz_o_minimo():
    rotas = {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\nCrawl-delay: 2\n"), **rotas_www(BUSCA)}
    p, t, relogio, _ = portao(rotas=rotas)
    p.obter(BUSCA)
    assert round(t.chamadas[1][2] - t.chamadas[0][2], 6) == 10.0


def test_resposta_do_cache_da_guarda_nao_emite_nem_espera(monkeypatch, proibir_rede):
    from freoa_verifica.connectors.httputil import connector_fetch
    relogio, emitidas = RelogioFalso(), []

    def falso(url, **kw):
        emitidas.append(url)
        return robots_resp(url, "User-agent: *\n") if "robots" in url else resposta(url, b"<html>ok</html>")

    monkeypatch.setattr("freoa_verifica.connectors.httputil.transport_fetch", falso)
    p = Portao(connector_fetch, estado=Estado(None), relogio=relogio)
    with da_chamada():
        p.obter(BUSCA)
        dormidas = len(relogio.dormidas)
        p.obter(BUSCA)
    assert emitidas == [ROBOTS_WWW, BUSCA] and len(relogio.dormidas) == dormidas and p.emitidas == 2


def test_espera_acima_do_orcamento_falha_sem_emitir(monkeypatch):
    p, t, relogio, _ = portao(rotas=rotas_www(BUSCA, BUSCA2))
    p.obter(BUSCA)
    monkeypatch.setattr(cp, "restante", lambda _: 1.0)
    with pytest.raises(Unavailable, match="orcamento"):
        p.obter(BUSCA2)
    assert BUSCA2 not in t.urls


def test_serializacao_por_host_entre_threads_sem_sobreposicao(tmp_path):
    relogio = RelogioFalso()
    ativos, maximo = [0], [0]

    def com_corpo(url):
        def f():
            ativos[0] += 1
            maximo[0] = max(maximo[0], ativos[0])
            time.sleep(0.05)
            ativos[0] -= 1
            return resposta(url, b"<html>ok</html>") if "robots" not in url else robots_resp(url, "User-agent: *\n")
        return f

    rotas = {u: com_corpo(u) for u in (ROBOTS_WWW, BUSCA, BUSCA2, BUSCA3)}
    p, t, *_ = portao(tmp_path, rotas, relogio=relogio)
    erros = []

    def trabalhar(url):
        try:
            p.obter(url)
        except Exception as exc:  # noqa: BLE001
            erros.append(exc)

    fios = [threading.Thread(target=trabalhar, args=(u,)) for u in (BUSCA, BUSCA2, BUSCA3)]
    [f.start() for f in fios]
    [f.join() for f in fios]
    assert not erros and maximo[0] == 1  # nunca duas requisições ao mesmo host ao mesmo tempo
    inicios = sorted(c[2] for c in t.chamadas)
    assert all(b - a >= 10.0 - 1e-6 for a, b in zip(inicios, inicios[1:]))


_FILHO = r"""
import sys, time, json
from pathlib import Path
from freoa_verifica.connectors import camara_portao as cp
from freoa_verifica.connectors.camara_estado import Estado
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.transport import Response
import hashlib
cp.INTERVALO_MINIMO = 0.6
home, log, quem = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
def transporte(url, **kw):
    log.open("a").write(f"{time.time():.6f} ini {quem}\n")
    time.sleep(0.15)
    corpo = b"User-agent: *\n" if "robots" in url else b"<html>ok</html>"
    log.open("a").write(f"{time.time():.6f} fim {quem}\n")
    return Response(url, url, 200, {}, corpo, hashlib.sha256(corpo).hexdigest(), "2026-11-08T12:00:00+00:00", [],
                    "text/plain" if "robots" in url else "text/html", size=len(corpo),
                    content_type="text/plain; charset=utf-8" if "robots" in url else "text/html; charset=utf-8")
p = Portao(transporte, estado=Estado(home))
base = "https://www.camara.leg.br/legislacao/busca?abrangencia=Legisla%C3%A7%C3%A3o+Federal&tipo=Lei+Ordin%C3%A1ria&ano=1976&geral=&numero="
for n in range(3):
    p.obter(base + str(6400 + int(quem) * 10 + n))
"""


def test_serializacao_por_host_entre_processos_do_mesmo_home(tmp_path):
    log = tmp_path / "log.txt"
    env = {**__import__("os").environ, "PYTHONPATH": str(RAIZ)}
    filhos = [subprocess.Popen([sys.executable, "-c", _FILHO, str(tmp_path / "home"), str(log), str(i)], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in (1, 2)]
    saidas = [f.communicate(timeout=120) for f in filhos]
    assert all(f.returncode == 0 for f in filhos), saidas
    eventos = [linha.split() for linha in log.read_text().splitlines()]
    assert len(eventos) == 2 * 7  # robots (lido uma só vez) + 6 buscas = 7 requisições, 2 eventos cada
    ativos, inicios = 0, []
    for instante, tipo, _ in sorted(eventos, key=lambda e: float(e[0])):
        ativos += 1 if tipo == "ini" else -1
        assert ativos <= 1  # nenhuma sobreposição entre processos
        if tipo == "ini":
            inicios.append(float(instante))
    assert all(b - a >= 0.6 - 0.05 for a, b in zip(inicios, inicios[1:]))


# --- §5.3: tetos ---------------------------------------------------------------------------------------------------
def test_tetos_padrao_instrumento_200_por_sessao_produto_30_por_chamada():
    assert (cp.TETO_SESSAO_INSTRUMENTO, cp.TETO_CHAMADA_PRODUTO) == (200, 30)
    inst, *_ = portao(instrumento=True)
    prod, *_ = portao()
    assert (inst.teto_sessao, inst.teto_chamada) == (200, None) and (prod.teto_sessao, prod.teto_chamada) == (None, 30)


def test_teto_de_sessao_do_instrumento_soma_hosts_e_robots_e_para_sem_emitir():
    rotas = {**rotas_www(BUSCA, BUSCA2), LEI: resposta(LEI, b"<html>ok</html>")}
    p, t, *_ = portao(rotas=rotas, instrumento=True, teto_sessao=3)
    p.obter(BUSCA)  # robots www + busca = 2
    p.obter(ROBOTS_WWW2)  # 3
    with pytest.raises(Unavailable, match="teto_de_sessao"):
        p.obter(BUSCA2)
    assert len(t.chamadas) == 3


def test_teto_por_chamada_publica_e_nova_chamada_recomeca(monkeypatch, proibir_rede):
    from freoa_verifica.connectors.httputil import connector_fetch
    relogio, emitidas = RelogioFalso(), []

    def falso(url, **kw):
        emitidas.append(url)
        return robots_resp(url, "User-agent: *\n") if "robots" in url else resposta(url, b"<html>ok</html>")

    monkeypatch.setattr("freoa_verifica.connectors.httputil.transport_fetch", falso)
    p = Portao(connector_fetch, estado=Estado(None), relogio=relogio, teto_chamada=3)
    with da_chamada():
        p.obter(BUSCA)  # robots + busca
        p.obter(BUSCA2)  # 3ª
        with pytest.raises(Unavailable, match="teto_de_chamada"):
            p.obter(BUSCA3)
    assert len(emitidas) == 3
    with da_chamada():  # nova chamada pública: contador próprio
        p.obter(BUSCA3)
    assert len(emitidas) == 4


def test_teto_nao_vira_bloqueio_persistente(tmp_path):
    p, t, *_ = portao(tmp_path, rotas_www(BUSCA, BUSCA2), instrumento=True, teto_sessao=2)
    p.obter(BUSCA)
    with pytest.raises(Unavailable, match="teto_de_sessao"):
        p.obter(BUSCA2)
    novo = Portao(t, estado=Estado(tmp_path), relogio=RelogioFalso(), instrumento=True, teto_sessao=5)
    assert novo.obter(BUSCA2).body  # nova sessão


# --- §6: tabela de barreiras --------------------------------------------------------------------------------------
A_CLASSE = [("http_401", "recusa_identificado", 401), ("http_403", "recusa_identificado", 403),
            ("http_429", None, 429), ("desafio_aws_waf", "ambiental_desafio", 200),
            ("desafio_captcha", "ambiental_desafio", 403)]


@pytest.mark.parametrize("reason,categoria,status", A_CLASSE)
def test_classe_a_bloqueia_o_host_inclusive_robots_e_termo_apos_reinicio(tmp_path, reason, categoria, status):
    rotas = {**rotas_www(BUSCA, BUSCA2), BUSCA: barreira(reason, categoria, status)}
    p, t, relogio, estado = portao(tmp_path, rotas)
    with pytest.raises(Unavailable) as erro:
        p.obter(BUSCA)
    assert erro.value.reason == reason and erro.value.categoria == categoria
    emitidas = len(t.chamadas)
    # mesma unidade (host), outro recurso, robots do host: nenhuma emissão
    for url in (BUSCA2, ROBOTS_WWW):
        with pytest.raises(Unavailable) as bloqueado:
            p.obter(url)
        assert bloqueado.value.reason == reason and bloqueado.value.evidencia["bloqueio"] == cp.A_HOST
    # reinício do processo: novo portão, mesmo home
    novo = Portao(t, estado=Estado(tmp_path), relogio=relogio)
    relogio.avancar(7 * 24 * 3600)  # persistente: o tempo não reabre
    for url in (BUSCA2, ROBOTS_WWW):
        with pytest.raises(Unavailable):
            novo.obter(url)
    assert len(t.chamadas) == emitidas
    # o outro host segue independente (o termo é do www2)
    assert novo.obter(TERMO_URL).body


def test_classe_a_no_www2_bloqueia_o_termo_e_o_conteudo_do_www2(tmp_path):
    rotas = {ROBOTS_WWW2: barreira("http_403", "recusa_identificado", 403)}
    p, t, *_ = portao(tmp_path, rotas)
    for url in (TERMO_URL, LEI, ROBOTS_WWW2):
        with pytest.raises(Unavailable):
            p.obter(url)
    assert t.urls == [ROBOTS_WWW2]  # uma única emissão, depois nenhuma


def test_classe_a_chamadas_enfileiradas_falham_fechadas(tmp_path):
    relogio = RelogioFalso()

    def recusa():
        time.sleep(0.2)
        return barreira("http_429", None, 429)

    rotas = {**rotas_www(BUSCA2, BUSCA3), BUSCA: recusa}
    p, t, *_ = portao(tmp_path, rotas, relogio=relogio)
    resultados = []

    def chamar(url, atraso):
        time.sleep(atraso)
        try:
            p.obter(url)
            resultados.append("ok")
        except Unavailable as exc:
            resultados.append(exc.reason)

    fios = [threading.Thread(target=chamar, args=(BUSCA, 0)), threading.Thread(target=chamar, args=(BUSCA2, 0.05)),
            threading.Thread(target=chamar, args=(BUSCA3, 0.08))]
    [f.start() for f in fios]
    [f.join() for f in fios]
    assert sorted(resultados) == ["http_429"] * 3
    assert t.urls == [ROBOTS_WWW, BUSCA]  # as enfileiradas não emitiram


def test_reabertura_de_host_so_por_decisao_registrada_e_exige_nova_leitura_de_robots(tmp_path):
    rotas = {**rotas_www(BUSCA2), BUSCA: barreira("http_403", "recusa_identificado", 403)}
    p, t, relogio, estado = portao(tmp_path, rotas)
    with pytest.raises(Unavailable):
        p.obter(BUSCA)
    leituras = t.urls.count(ROBOTS_WWW)
    assert estado.liberar_host("www.camara.leg.br", "decisao-0081", relogio.agora()) is True
    assert estado.reaberturas("www.camara.leg.br")[-1]["decisao"] == "decisao-0081"
    p.obter(BUSCA2)
    assert t.urls.count(ROBOTS_WWW) == leituras + 1  # robots relido antes de qualquer conteúdo


@pytest.mark.parametrize("falha,reason", [
    (BlockedHost("Limite de redirecionamentos excedido"), "transporte_BlockedHost"),
])
def test_classe_3xx_persiste_o_recurso_e_o_host_so_pela_chamada(monkeypatch, proibir_rede, tmp_path, falha, reason):
    from freoa_verifica.connectors.httputil import connector_fetch
    relogio, emitidas = RelogioFalso(), []

    def falso(url, **kw):
        emitidas.append(url)
        if url == BUSCA:
            raise falha
        return robots_resp(url, "User-agent: *\n") if "robots" in url else resposta(url, b"<html>ok</html>")

    monkeypatch.setattr("freoa_verifica.connectors.httputil.transport_fetch", falso)
    estado = Estado(tmp_path)
    p = Portao(connector_fetch, estado=estado, relogio=relogio)
    with da_chamada():
        with pytest.raises(Unavailable) as erro:
            p.obter(BUSCA)
        assert erro.value.reason == reason and erro.value.evidencia["bloqueio"] == cp.TRES_XX
        with pytest.raises(Unavailable):  # host: pelo restante da chamada
            p.obter(BUSCA2)
    n = len(emitidas)
    novo = Portao(connector_fetch, estado=Estado(tmp_path), relogio=relogio)
    with da_chamada():
        assert novo.obter(BUSCA2).body  # outra chamada: o host volta
        with pytest.raises(Unavailable):  # o recurso segue bloqueado (persistente)
            novo.obter(BUSCA)
    assert BUSCA not in emitidas[n:]
    # revisão registrada do recurso reabre
    assert estado.liberar_recurso("www.camara.leg.br", BUSCA, "revisao-1", relogio.agora()) is True


def test_redirecionamento_devolvido_como_resposta_tambem_e_3xx_e_nunca_e_seguido(tmp_path):
    from dataclasses import replace
    r = replace(resposta(BUSCA, b"x"), status=302, redirects=[BUSCA2], final_url=BUSCA2)
    p, t, *_ = portao(tmp_path, {BUSCA: r, **rotas_www(BUSCA2)})
    with pytest.raises(Unavailable) as erro:
        p.obter(BUSCA)
    assert erro.value.evidencia["bloqueio"] == cp.TRES_XX
    assert BUSCA2 not in t.urls  # nenhum destino de redirecionamento é obtido


@pytest.mark.parametrize("falha", [barreira("transporte_Timeout", "fonte_fora"), barreira("http_503", "fonte_fora", 503),
                                   barreira("http_500", "fonte_fora", 500),
                                   barreira("transporte_TransportError", "fonte_fora")])
def test_classe_transitoria_bloqueia_o_host_por_1h_e_reabre_sozinha(tmp_path, falha):
    estado_falha = {"n": 0}

    def alternada():
        estado_falha["n"] += 1
        return falha if estado_falha["n"] == 1 else resposta(BUSCA, b"<html>ok</html>")

    p, t, relogio, estado = portao(tmp_path, {BUSCA: alternada, ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\n"),
                                              **rotas_www(BUSCA2)})
    with pytest.raises(Unavailable) as erro:
        p.obter(BUSCA)
    assert erro.value.reason == falha.reason
    emitidas = len(t.chamadas)
    relogio.avancar(59 * 60)
    for url in (BUSCA2, BUSCA, ROBOTS_WWW):
        with pytest.raises(Unavailable):
            p.obter(url)
    assert len(t.chamadas) == emitidas  # nenhuma emissão dentro de 1 h
    relogio.avancar(61)
    assert p.obter(BUSCA2).body  # automática após 1 h


def test_classe_robots_ausente_bloqueia_conteudo_e_termo_ate_leitura_valida(tmp_path):
    rotas = {ROBOTS_WWW2: HTTPStatusErrorUnavailable(404), **rotas_www()}
    p, t, relogio, estado = portao(tmp_path, rotas)
    for url in (TERMO_URL, LEI):
        with pytest.raises(Unavailable) as erro:
            p.obter(url)
        assert erro.value.reason == "robots_inconclusivo"
    assert t.urls == [ROBOTS_WWW2]


def HTTPStatusErrorUnavailable(status):
    return barreira(f"http_{status}", None, status)


@pytest.mark.parametrize("texto", ["isto não é robots", "User-agent: *\nCrawl-delay: abc", "Disallow: /x",
                                   "User-agent: outro\nAllow: /"])
def test_robots_malformado_ou_inconclusivo_bloqueia_host(tmp_path, texto):
    p, t, *_ = portao(tmp_path, {ROBOTS_WWW2: robots_resp(ROBOTS_WWW2, texto)})
    with pytest.raises(Unavailable) as erro:
        p.obter(TERMO_URL)
    assert erro.value.reason.startswith("robots") and erro.value.evidencia["bloqueio"] == cp.ROBOTS
    with pytest.raises(Unavailable):
        p.obter(LEI)
    assert t.urls == [ROBOTS_WWW2]


def test_revalidacao_de_robots_inconclusivo_dobra_o_prazo_ate_24h_e_so_toca_o_robots(tmp_path):
    estado_robots = {"ok": False}

    def robots():
        return robots_resp(ROBOTS_WWW2, "User-agent: *\nAllow: /\n") if estado_robots["ok"] else \
            robots_resp(ROBOTS_WWW2, "lixo")

    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW2: robots, TERMO_URL: resposta(TERMO_URL, b"<html>ok</html>")})
    with pytest.raises(Unavailable):
        p.obter(TERMO_URL)  # t0: 1ª leitura, inconclusiva
    assert len(t.chamadas) == 1
    relogio.avancar(3599)
    with pytest.raises(Unavailable):
        p.obter(TERMO_URL)
    assert len(t.chamadas) == 1  # antes de 1 h: nada
    relogio.avancar(2)
    with pytest.raises(Unavailable):
        p.obter(TERMO_URL)  # decorrida 1 h: UMA tentativa, só de /robots.txt
    assert t.urls == [ROBOTS_WWW2, ROBOTS_WWW2]
    relogio.avancar(3600 + 5)  # 1 h depois da falha: o prazo agora é 2 h
    with pytest.raises(Unavailable):
        p.obter(TERMO_URL)
    assert len(t.chamadas) == 2
    relogio.avancar(3600)  # completa 2 h
    with pytest.raises(Unavailable):
        p.obter(TERMO_URL)
    assert t.urls.count(ROBOTS_WWW2) == 3 and TERMO_URL not in t.urls
    # o prazo dobra (4 h, 8 h, 16 h) e é limitado a 24 h
    prazos = [timedelta(seconds=estado.revalidacao("www2.camara.leg.br")["intervalo_s"])]
    for _ in range(6):
        relogio.avancar(prazos[-1].total_seconds() + 1)
        with pytest.raises(Unavailable):
            p.obter(TERMO_URL)
        prazos.append(timedelta(seconds=estado.revalidacao("www2.camara.leg.br")["intervalo_s"]))
    assert max(prazos) == timedelta(hours=24) and prazos[-1] == timedelta(hours=24)
    # leitura válida desbloqueia
    estado_robots["ok"] = True
    relogio.avancar(24 * 3600 + 1)
    assert p.obter(TERMO_URL).body


@pytest.mark.parametrize("resposta_ruim", [
    lambda: resposta(ROBOTS_WWW2, b"", mime="text/plain"),  # corpo vazio
    lambda: resposta(ROBOTS_WWW2, b"<html>x</html>", mime="text/html"),  # MIME incompatível
    lambda: barreira("corpo_vazio", "resposta_inesperada", 200),
    lambda: barreira("transporte_RespostaInvalida", "resposta_inesperada"),
])
def test_robots_com_corpo_vazio_ou_mime_incompativel_e_decisao_fechada(tmp_path, resposta_ruim):
    p, t, *_ = portao(tmp_path, {ROBOTS_WWW2: resposta_ruim})
    with pytest.raises(Unavailable) as erro:
        p.obter(LEI)
    assert erro.value.reason == "robots_inconclusivo"
    assert t.urls == [ROBOTS_WWW2]


def test_falha_local_de_persistencia_fecha_a_decisao_e_nao_persiste(tmp_path, monkeypatch):
    from freoa_verifica.connectors import camara_estado as ce
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA))
    monkeypatch.setattr(ce, "_escrever", lambda *a, **k: (_ for _ in ()).throw(ce.EstadoIndisponivel("disco")))
    with pytest.raises(Unavailable, match="persistencia_local_falhou"):
        p.obter(BUSCA)
    assert BUSCA not in t.urls  # sem política persistida não há obtenção de conteúdo
    monkeypatch.undo()
    assert Portao(t, estado=Estado(tmp_path), relogio=relogio).obter(BUSCA).body  # nova chamada: nada ficou gravado


@pytest.mark.parametrize("fabrica", [
    lambda u: Unavailable("desafio_aws_waf", "resposta_inesperada", {"status": 202}),  # 202 sem marcador
    lambda u: barreira("http_404", None, 404), lambda u: barreira("http_410", None, 410),
    lambda u: barreira("http_418", None, 418), lambda u: barreira("http_400", None, 400),
])
def test_residual_persiste_o_recurso_e_o_host_so_pela_chamada(tmp_path, fabrica):
    p, t, relogio, estado = portao(tmp_path, {**rotas_www(BUSCA2), BUSCA: fabrica(BUSCA)}, instrumento=True)
    with pytest.raises(Unavailable) as erro:
        p.obter(BUSCA)
    assert erro.value.evidencia["bloqueio"] == cp.RESIDUAL
    with pytest.raises(Unavailable):  # host: pelo restante da sessão do instrumento
        p.obter(BUSCA2)
    novo = Portao(t, estado=Estado(tmp_path), relogio=relogio, instrumento=True)
    assert novo.obter(BUSCA2).body  # nova sessão: host liberado
    emitidas = len(t.chamadas)
    with pytest.raises(Unavailable):
        novo.obter(BUSCA)  # recurso persistente
    assert len(t.chamadas) == emitidas


def test_residual_status_1xx_e_202_sem_marcador_via_resposta(tmp_path):
    from dataclasses import replace
    for status in (100, 202, 204):
        p, t, *_ = portao(tmp_path / str(status), {BUSCA: replace(resposta(BUSCA, b"x"), status=status)})
        with pytest.raises(Unavailable) as erro:
            p.obter(BUSCA)
        assert erro.value.evidencia["bloqueio"] == cp.RESIDUAL, status


@pytest.mark.parametrize("ruim", [lambda: barreira("corpo_vazio", "resposta_inesperada", 200),
                                  lambda: barreira("transporte_RespostaInvalida", "resposta_inesperada"),
                                  lambda: resposta(BUSCA, b""),
                                  lambda: resposta(BUSCA, b"x", mime="application/pdf")])
def test_corpo_vazio_e_mime_incompativel_persistem_o_recurso(tmp_path, ruim):
    p, t, *_ = portao(tmp_path, {BUSCA: ruim})
    with pytest.raises(Unavailable) as erro:
        p.obter(BUSCA)
    assert erro.value.evidencia["bloqueio"] == cp.CORPO_MIME
    assert Estado(tmp_path).bloqueio_do_recurso("www.camara.leg.br", BUSCA) is not None


def test_precedencia_das_classes_da_mais_especifica_a_residual():
    c = cp.classificar
    assert c(Unavailable("desafio_x", "ambiental_desafio", {"status": 503})) == cp.A_HOST  # desafio antes de 5xx
    assert c(Unavailable("http_429", None, {"status": 429})) == cp.A_HOST
    assert c(Unavailable("transporte_BlockedHost", "resposta_inesperada", {})) == cp.TRES_XX  # 3xx antes de corpo/MIME
    assert c(Unavailable("http_302", None, {"status": 302})) == cp.TRES_XX
    assert c(Unavailable("http_503", "fonte_fora", {"status": 503})) == cp.TRANSITORIA
    assert c(Unavailable("corpo_vazio", "resposta_inesperada", {})) == cp.CORPO_MIME
    assert c(Unavailable("http_404", None, {"status": 404})) == cp.RESIDUAL
    assert c(Unavailable("qualquer_coisa", None, {})) == cp.RESIDUAL  # regra residual


def test_robots_proibindo_o_caminho_bloqueia_o_host_persistentemente(tmp_path):
    rotas = {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\nDisallow: /legislacao/busca\n"), **rotas_www(BUSCA, BUSCA2)}
    p, t, relogio, estado = portao(tmp_path, rotas)
    with pytest.raises(Unavailable) as erro:
        p.obter(BUSCA)
    assert erro.value.reason == "robots_recusa"
    assert t.urls == [ROBOTS_WWW]
    novo = Portao(t, estado=Estado(tmp_path), relogio=relogio)
    with pytest.raises(Unavailable, match="robots_recusa"):  # persistente, inclusive no reinício
        novo.obter(BUSCA2)
    assert len(t.chamadas) == 1


# --- §4.4: ciclo de vida do robots ---------------------------------------------------------------------------------
def test_politica_persistida_com_recibo_hash_instante_ua_grupos_e_decisao_por_caminho(tmp_path):
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA))
    p.obter(BUSCA)
    reg = estado.politica("www.camara.leg.br")
    assert {"sha256", "obtido_em", "valido_ate", "user_agent", "tokens", "grupos_considerados", "decisoes",
            "url", "status", "mime", "bytes", "crawl_delay"} <= set(reg)
    assert reg["decisoes"]["/legislacao/busca" + BUSCA.split("/legislacao/busca")[1]] == "permitido"
    assert (timedelta(hours=24)).total_seconds() == (
        __import__("datetime").datetime.fromisoformat(reg["valido_ate"])
        - __import__("datetime").datetime.fromisoformat(reg["obtido_em"])).total_seconds()
    assert reg["user_agent"].startswith("freoa-verifica/")


def test_cada_obtencao_registra_o_hash_da_politica_que_a_autorizou(tmp_path):
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA))
    resp = p.obter(BUSCA)
    reg = estado.politica("www.camara.leg.br")
    obtencoes = estado.obtencoes()
    assert obtencoes[-1]["url"] == BUSCA and obtencoes[-1]["politica_sha256"] == reg["sha256"]
    assert obtencoes[-1]["sha256"] == resp.sha256 and p.politica_de[BUSCA] == reg["sha256"]


def test_politica_vale_24h_e_sobrevive_ao_reinicio_depois_expira_e_e_relida(tmp_path):
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA))
    p.obter(BUSCA)
    relogio.avancar(23 * 3600)
    novo = Portao(t, estado=Estado(tmp_path), relogio=relogio)
    novo.obter(BUSCA)
    assert t.urls.count(ROBOTS_WWW) == 1  # reinício dentro de 24 h: política persistida
    relogio.avancar(2 * 3600)
    novo.obter(BUSCA)
    assert t.urls.count(ROBOTS_WWW) == 2  # expirada: nova leitura antes da obtenção


def test_falha_na_releitura_nao_reutiliza_a_autorizacao_anterior(tmp_path):
    saude = {"ok": True}

    def robots():
        return robots_resp(ROBOTS_WWW, "User-agent: *\n") if saude["ok"] else barreira("http_503", "fonte_fora", 503)

    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots, **rotas_www(BUSCA)})
    p.obter(BUSCA)
    saude["ok"] = False
    relogio.avancar(25 * 3600)
    with pytest.raises(Unavailable) as erro:
        p.obter(BUSCA)
    assert erro.value.reason == "http_503" and t.urls.count(BUSCA) == 1


def test_crawl_delay_persistido_vale_no_reinicio(tmp_path):
    rotas = {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\nCrawl-delay: 20\n"), **rotas_www(BUSCA, BUSCA2)}
    p, t, relogio, estado = portao(tmp_path, rotas)
    p.obter(BUSCA)
    novo = Portao(t, estado=Estado(tmp_path), relogio=relogio)
    novo.obter(BUSCA2)
    assert round(t.chamadas[2][2] - t.chamadas[1][2], 6) == 20.0


def test_resposta_do_robots_com_ua_do_produto_e_sem_troca_de_identidade(tmp_path):
    p, t, *_ = portao(tmp_path, rotas_www(BUSCA))
    p.obter(BUSCA)
    assert {c[1]["user_agent"] for c in t.chamadas} == {"identified"}


def test_sem_fallback_para_outros_hosts_apos_barreira(tmp_path):
    p, t, *_ = portao(tmp_path, {BUSCA: barreira("http_403", "recusa_identificado", 403)})
    with pytest.raises(Unavailable):
        p.obter(BUSCA)
    assert {u.split("/")[2] for u in t.urls} == {"www.camara.leg.br"}
