"""Correção r1 da 0080 (parecer do PR #39), achados 4, 5 e 6: ritmo e teto entre instâncias e hosts, falha local terminal
e barreiras detectadas depois do portão. Contraprovas C04, C05, C06, C07/C15, C16 e C20 e variantes por classe.
Sintético por construção: transporte simulado, relógio controlado, nenhum socket.
"""
import json
import threading
from datetime import timedelta

import pytest

from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_estado import Estado, EstadoIndisponivel
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
from freoa_verifica.connectors.camara_policy import TERMO_URL
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.connectors.guarda import da_chamada
from tests._camara_util import (BUSCA, LEI, ROBOTS_WWW, ROBOTS_WWW2, RelogioFalso, barreira, da_fixture,
                                portao, resposta, robots_resp)
from tests.test_camara_legin import ATUAL, ORIGINAL

BUSCA2 = BUSCA.replace("numero=6404", "numero=6405")
BUSCA3 = BUSCA.replace("numero=6404", "numero=6406")
WWW, WWW2 = "www.camara.leg.br", "www2.camara.leg.br"


def rotas_www(*urls):
    return {u: resposta(u, b"<html>ok</html>") for u in urls}


class RelogioSeparado(RelogioFalso):
    """Relógio civil que pode andar sozinho (ajuste, NTP, suspensão) sem mexer no monotônico."""

    def __init__(self):
        super().__init__()
        self.civil = 0.0

    def agora(self):
        return self.inicio + timedelta(seconds=self.t + self.civil)

    def avancar_civil(self, segundos):
        self.civil += segundos


# --- achado 4: ritmo entre instâncias e teto entre hosts ------------------------------------------------------------------
def test_c06_avanco_isolado_do_relogio_civil_entre_instancias_nao_zera_o_intervalo(tmp_path):
    relogio = RelogioSeparado()
    p1, t, _, estado = portao(tmp_path, rotas_www(BUSCA, BUSCA2), relogio=relogio)
    p1.obter(BUSCA)
    relogio.avancar_civil(3600)  # o civil saltou 1 h; o monotônico não andou
    dormidas = len(relogio.dormidas)
    p2 = Portao(t, estado=Estado(tmp_path), relogio=relogio)  # outra instância sobre o mesmo estado
    p2.obter(BUSCA2)
    assert relogio.dormidas[dormidas:] == [10.0]  # esperou o intervalo inteiro, medido pelo monotônico persistido
    inicios = [c[2] for c in t.chamadas]
    assert inicios[-1] - inicios[-2] >= 10.0


def test_ritmo_recuo_do_civil_ou_reinicio_da_marca_monotonica_contam_como_nada_decorrido(tmp_path):
    relogio = RelogioSeparado()
    p1, t, _, estado = portao(tmp_path, rotas_www(BUSCA, BUSCA2, BUSCA3), relogio=relogio)
    p1.obter(BUSCA)
    relogio.avancar_civil(-5)  # recuo do relógio civil (a política ainda vale)
    antes = len(relogio.dormidas)
    Portao(t, estado=Estado(tmp_path), relogio=relogio).obter(BUSCA2)
    assert relogio.dormidas[antes:] == [10.0]
    relogio.t -= 500  # a marca monotônica reiniciou (nova inicialização): o civil, adiante, não basta
    relogio.avancar_civil(5000)
    antes = len(relogio.dormidas)
    Portao(t, estado=Estado(tmp_path), relogio=relogio).obter(BUSCA3)
    assert relogio.dormidas[antes:] == [10.0]


def test_ritmo_ja_decorrido_nos_dois_relogios_nao_espera(tmp_path):
    relogio = RelogioSeparado()
    p1, t, _, estado = portao(tmp_path, rotas_www(BUSCA, BUSCA2), relogio=relogio)
    p1.obter(BUSCA)
    relogio.avancar(30)
    antes = len(relogio.dormidas)
    Portao(t, estado=Estado(tmp_path), relogio=relogio).obter(BUSCA2)
    assert len(relogio.dormidas) == antes


def test_marca_de_ritmo_persistida_traz_o_civil_e_o_monotonico(tmp_path):
    relogio = RelogioSeparado()
    p, t, _, estado = portao(tmp_path, rotas_www(BUSCA), relogio=relogio)
    p.obter(BUSCA)
    civil, mono = estado.ultimo_inicio(WWW)
    assert mono == relogio.t and civil == relogio.agora()


def _preparar_teto(tmp_path, relogio):
    """Políticas dos dois hosts já persistidas (sem leitura de robots no teste) e um portão a uma vaga do teto."""
    rotas = {**rotas_www(BUSCA), LEI: resposta(LEI, b"<html>lei</html>")}
    p0, t, _, estado = portao(tmp_path, rotas, relogio=relogio)
    p0.verificar_caminhos(WWW, ["/legislacao/busca"])
    p0.verificar_caminhos(WWW2, ["/legin/fed/x"])
    p = Portao(t, estado=Estado(tmp_path), relogio=relogio, instrumento=True)
    p.emitidas = p.teto_sessao - 1
    t.chamadas.clear()
    return p, t


def test_c20_ultima_vaga_do_teto_entre_hosts_e_reservada_atomicamente(tmp_path, monkeypatch):
    relogio = RelogioFalso()
    p, t = _preparar_teto(tmp_path, relogio)
    barreira_de_espera = threading.Barrier(2)

    def esperar_juntas(self, host, intervalo):  # as duas chamadas chegam juntas ao ponto de espera
        try:
            barreira_de_espera.wait(timeout=1.0)
        except threading.BrokenBarrierError:
            pass

    monkeypatch.setattr(Portao, "_esperar", esperar_juntas)
    resultados = []

    def chamar(url):
        try:
            resultados.append(("ok", p.obter(url).sha256))
        except Unavailable as exc:
            resultados.append(("falha", exc.reason))

    threads = [threading.Thread(target=chamar, args=(u,)) for u in (BUSCA, LEI)]
    [th.start() for th in threads]
    [th.join(10) for th in threads]
    assert sorted(r[0] for r in resultados) == ["falha", "ok"] and ("falha", "teto_de_sessao") in resultados
    assert p.emitidas == p.teto_sessao == 200 and len(t.chamadas) == 1  # 200, não 201


def test_reserva_do_teto_e_devolvida_quando_a_emissao_e_abortada(tmp_path):
    relogio = RelogioFalso()
    p, t = _preparar_teto(tmp_path, relogio)
    with pytest.raises(Unavailable):
        p.obter(TERMO_URL + "/")  # recusado antes de reservar
    assert p.emitidas == 199

    def estoura(segundos):
        raise Unavailable("orcamento")

    relogio.sleep = estoura  # a espera do ritmo estoura o orçamento: nada é emitido
    with pytest.raises(Unavailable, match="orcamento"):
        p.obter(BUSCA)
    assert p.emitidas == 199 and t.chamadas == []  # a vaga reservada foi devolvida


def test_teto_por_chamada_e_compartilhado_entre_instancias_da_mesma_chamada(tmp_path):
    relogio = RelogioFalso()
    rotas = rotas_www(BUSCA, BUSCA2, BUSCA3)
    a, t, _, estado = portao(tmp_path, rotas, relogio=relogio, teto_chamada=3)
    b = Portao(t, estado=Estado(tmp_path), relogio=relogio, teto_chamada=3)
    with da_chamada():
        a.obter(BUSCA)  # robots + busca: duas emissões
        b.obter(BUSCA2)  # a política vale: uma emissão (total 3)
        with pytest.raises(Unavailable, match="teto_de_chamada"):
            a.obter(BUSCA3)
        with pytest.raises(Unavailable, match="teto_de_chamada"):
            b.obter(BUSCA3)
    assert BUSCA3 not in t.urls
    with da_chamada():  # nova chamada pública recomeça
        a.obter(BUSCA3)


def test_teto_da_sessao_do_instrumento_nao_ultrapassa_200_entre_hosts_sob_concorrencia_repetida(tmp_path):
    relogio = RelogioFalso()
    p, t = _preparar_teto(tmp_path, relogio)
    p.emitidas = 190
    resultados = []

    def chamar(url):
        for _ in range(8):
            try:
                p.obter(url)
            except Unavailable as exc:
                resultados.append(exc.reason)

    threads = [threading.Thread(target=chamar, args=(u,)) for u in (BUSCA, LEI)]
    [th.start() for th in threads]
    [th.join(30) for th in threads]
    assert p.emitidas == 200 and len(t.chamadas) == 10 and "teto_de_sessao" in resultados  # as 10 vagas, nenhuma a mais


# --- achado 5: falha local é terminal para a chamada ou sessão, nos dois hosts ---------------------------------------------
def _boom(*a, **k):
    raise EstadoIndisponivel("disco")


def _rotas_basicas():
    return {**rotas_www(BUSCA), LEI: resposta(LEI, b"<html>lei</html>")}


CENARIOS = {
    "registrar_obtencao": _rotas_basicas,  # C04
    "gravar_politica": _rotas_basicas,
    "regravar_politica": _rotas_basicas,  # gravação da decisão por caminho
    "marcar_inicio": _rotas_basicas,
    "bloquear_host": lambda: {ROBOTS_WWW: barreira("http_403", "recusa_identificado", 403), **_rotas_basicas()},
    "bloquear_robots_inconclusivo": lambda: {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "lixo"), **_rotas_basicas()},
    "bloquear_recurso": lambda: {**_rotas_basicas(), BUSCA: barreira("http_404", None, 404)},
}


@pytest.mark.parametrize("escopo", ["chamada", "sessao"])
@pytest.mark.parametrize("ponto", sorted(CENARIOS))
def test_falha_local_encerra_a_chamada_ou_sessao_para_os_dois_hosts(tmp_path, monkeypatch, ponto, escopo):
    p, t, relogio, estado = portao(tmp_path, CENARIOS[ponto](), instrumento=escopo == "sessao")
    contexto = da_chamada() if escopo == "chamada" else _Nada()
    with contexto:
        monkeypatch.setattr(Estado, ponto, _boom)
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(BUSCA)
        monkeypatch.undo()  # o disco volta, mas a chamada (ou a sessão) já terminou localmente
        emitidas = list(t.urls)
        for url in (LEI, BUSCA, ROBOTS_WWW2):
            with pytest.raises(Unavailable, match="persistencia_local_falhou"):
                p.obter(url)
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.verificar_caminhos(WWW2, ["/legin/fed/x"])
        assert t.urls == emitidas  # nada foi emitido depois da falha, nem ao outro host
    if escopo == "chamada":
        with da_chamada():  # nova chamada pública: o estado terminal não persiste
            assert p.obter(LEI).body
    else:
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(LEI)  # a sessão do instrumento permanece encerrada


class _Nada:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_c04_nova_chamada_publica_funciona_depois_da_falha_local_da_anterior(tmp_path, monkeypatch):
    p, t, relogio, estado = portao(tmp_path, _rotas_basicas())
    with da_chamada():
        monkeypatch.setattr(Estado, "registrar_obtencao", _boom)
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(BUSCA)
        monkeypatch.undo()
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(LEI)
    with da_chamada():
        assert p.obter(LEI).body  # a falha não persiste: nova chamada


def test_falha_local_do_parser_encerra_a_chamada_sem_culpar_o_recurso(tmp_path, monkeypatch):
    rotas = {r.url: r for r in (da_fixture(k) for k in ("robots_portal", "robots_legin", "busca_lei6404", "norma_lei6404",
                                                         "textos_atualizado_lei6404", "textos_original_lei6404"))}
    p, t, relogio, estado = portao(tmp_path / "home", {**rotas, **rotas_www(BUSCA2)})
    con = CamaraLeginConnector(portao=p, home=tmp_path / "home")

    def parser_quebrado(*a, **k):
        raise Unavailable("parser_AttributeError")

    monkeypatch.setattr("freoa_verifica.parsers.isolated.parse_ou_indisponivel", parser_quebrado)
    with da_chamada():
        cand = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
        resp = con.fetch(cand)
        with pytest.raises(Unavailable, match="falha_parser_camara"):
            con.parse(resp)
        antes = list(t.urls)
        with pytest.raises(Unavailable, match="falha_parser_camara"):  # terminal: nenhuma outra emissão na chamada
            p.obter(BUSCA2)
        assert t.urls == antes
    assert estado.bloqueio_do_recurso(WWW2, ATUAL) is None  # falha local não é barreira do servidor


PAYLOADS_INVALIDOS = [
    (f"robots-{WWW}.json", []), (f"robots-{WWW}.json", {}), (f"robots-{WWW}.json", {"host": WWW}),
    (f"robots-{WWW}.json", {"host": WWW, "url": f"https://{WWW}/robots.txt", "sha256": 1}),
    (f"bloqueio-{WWW}.json", []), (f"bloqueio-{WWW}.json", {"host": "x"}),
    (f"bloqueio-{WWW}.json", {"host": {"classe": "a"}}), (f"bloqueio-{WWW}.json", {"recursos": []}),
    (f"bloqueio-{WWW}.json", {"revalidacao": {"proxima": "x", "intervalo_s": 1}}),
    (f"bloqueio-{WWW}.json", {"reaberturas": [1]}),
    (f"ritmo-{WWW}.json", []), (f"ritmo-{WWW}.json", {"inicio": "x", "mono": 1}),
    (f"ritmo-{WWW}.json", {"inicio": "2026-11-08T12:00:00+00:00"}),
    (f"ritmo-{WWW}.json", {"inicio": "2026-11-08T12:00:00", "mono": 1}),
]


@pytest.mark.parametrize("arquivo,conteudo", PAYLOADS_INVALIDOS)
def test_esquema_persistido_invalido_e_falha_local_tipada_e_nada_e_emitido(tmp_path, arquivo, conteudo):
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA))
    (tmp_path / "camara").mkdir(parents=True)
    (tmp_path / "camara" / arquivo).write_text(json.dumps(conteudo), encoding="utf-8")
    with pytest.raises(Unavailable, match="persistencia_local_falhou"):  # nunca KeyError, TypeError ou ValueError soltos
        p.obter(BUSCA)
    assert t.urls == []


def test_obtencoes_com_esquema_invalido_sao_falha_local_tipada(tmp_path):
    estado = Estado(tmp_path)
    (tmp_path / "camara").mkdir(parents=True)
    (tmp_path / "camara" / "obtencoes.jsonl").write_text('{"url": 1}\n', encoding="utf-8")
    with pytest.raises(EstadoIndisponivel):
        estado.obtencoes()


def test_politica_persistida_cujo_corpo_nao_e_interpretavel_e_falha_local_tipada(tmp_path):
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA))
    p.obter(BUSCA)
    registro = estado.politica(WWW)
    import hashlib
    corpo = b"isto nao e robots"
    registro = {**registro, "sha256": hashlib.sha256(corpo).hexdigest()}
    # adulteração local escrita POR BAIXO da validação: o hash confere, mas o conteúdo não é interpretável
    estado._gravar_bytes(f"robots-{WWW}-{registro['sha256']}.txt", corpo)
    estado._gravar(f"robots-{WWW}.json", registro)
    relogio.avancar(20)
    antes = list(t.urls)
    with pytest.raises(Unavailable, match="persistencia_local_falhou"):
        p.obter(BUSCA)
    assert t.urls == antes


# --- achado 6: barreiras detectadas depois do portão -----------------------------------------------------------------------
def _conector(tmp_path, rotas):
    p, t, relogio, estado = portao(tmp_path / "home", rotas)
    return CamaraLeginConnector(portao=p, home=tmp_path / "home"), p, t, estado


def _fixtures(*chaves):
    return {r.url: r for r in (da_fixture(k) for k in chaves)}


ROBOTS_REAIS = ("robots_portal", "robots_legin")
SEM_PERFIL = resposta(BUSCA, b"<html><body><p>nada reconhecivel</p></body></html>")
SEM_LINKS = resposta(BUSCA, b"<html><body><p>Exibindo resultados de 0 a 0</p></body></html>")


@pytest.mark.parametrize("pagina,motivo", [(SEM_PERFIL, "busca_sem_estrutura_reconhecida"),
                                           (SEM_LINKS, "busca_sem_marcador_zero_validado")])
def test_c05_busca_com_200_sem_perfil_bloqueia_o_recurso_e_o_host_pelo_restante_da_chamada(tmp_path, pagina, motivo):
    con, p, t, estado = _conector(tmp_path, {**_fixtures(*ROBOTS_REAIS), BUSCA: pagina, **rotas_www(BUSCA2)})
    with da_chamada():
        with pytest.raises(Unavailable) as erro:
            con.search("Lei 6404/1976")
        assert erro.value.reason == motivo
        bloqueio = estado.bloqueio_do_recurso(WWW, BUSCA)
        assert bloqueio is not None  # primeiro a existência do bloqueio (sem `TypeError` ao indexar None), depois os campos
        assert bloqueio["classe"] == "corpo_ou_mime" and bloqueio["motivo"] == motivo  # persistente para o recurso
        emitidas = list(t.urls)
        with pytest.raises(Unavailable) as depois:
            con.search("Lei 6405/1976")  # outro recurso do mesmo host, na mesma chamada: bloqueado
        assert depois.value.evidencia["bloqueio"] == "corpo_ou_mime" and t.urls == emitidas
    with da_chamada():  # nova chamada: o host volta, mas o recurso persistido continua vedado
        with pytest.raises(Unavailable) as persistido:
            con.search("Lei 6404/1976")
        assert persistido.value.evidencia["bloqueio"] == "corpo_ou_mime"
        assert BUSCA2 not in t.urls
        with pytest.raises(Unavailable):
            con.search("Lei 6405/1976")  # outro recurso, nova chamada: é pedido (sua página também não tem perfil)
        assert BUSCA2 in t.urls


PAGINA_SEM_CONTEUDO = b"<html><body><p>pagina sem dados da norma</p></body></html>"
PAGINA_SEM_TITULO = ("<html><body><div id='content'>Legislação Informatizada - Dados da Norma <h1>Titulo qualquer</h1>"
                     "</div></body></html>").encode()


@pytest.mark.parametrize("pagina,motivo", [(PAGINA_SEM_CONTEUDO, "pagina_norma_nao_reconhecida"),
                                           (PAGINA_SEM_TITULO, "identidade_nao_declarada")])
def test_pagina_de_norma_sem_perfil_bloqueia_o_recurso_e_o_host_da_norma(tmp_path, pagina, motivo):
    rotas = {**_fixtures(*ROBOTS_REAIS, "busca_lei6404"), LEI: resposta(LEI, pagina), ORIGINAL: resposta(ORIGINAL, b"x")}
    con, p, t, estado = _conector(tmp_path, rotas)
    with da_chamada():
        with pytest.raises(Unavailable) as erro:
            con.resolve({"kind": "lei", "number": "6404", "year": 1976})
        assert erro.value.reason == motivo
        bloqueio = estado.bloqueio_do_recurso(WWW2, LEI)
        assert bloqueio is not None
        assert bloqueio["classe"] == "corpo_ou_mime"
        emitidas = list(t.urls)
        with pytest.raises(Unavailable) as depois:
            p.obter(ORIGINAL)  # outro recurso de www2 na mesma chamada
        assert depois.value.evidencia["bloqueio"] == "corpo_ou_mime" and t.urls == emitidas


def test_texto_normativo_sem_perfil_bloqueia_o_recurso_do_texto(tmp_path):
    rotas = {**_fixtures(*ROBOTS_REAIS, "busca_lei6404", "norma_lei6404"),
             ATUAL: resposta(ATUAL, b"<html><body><p>nenhum dispositivo</p></body></html>")}
    con, p, t, estado = _conector(tmp_path, rotas)
    with da_chamada():
        cand = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
        resp = con.fetch(cand)
        with pytest.raises(Unavailable) as erro:
            con.parse(resp)
        assert erro.value.categoria == "resposta_inesperada"
        assert estado.bloqueio_do_recurso(WWW2, ATUAL) is not None


def test_entrada_invalida_do_chamador_nao_bloqueia_o_servidor(tmp_path):
    con, p, t, estado = _conector(tmp_path, {**_fixtures(*ROBOTS_REAIS, "busca_lei6404", "norma_lei6404")})
    with da_chamada():
        with pytest.raises(Unavailable, match="busca_camara_exige_identidade"):
            con.search("texto que não é citação")
        with pytest.raises(Unavailable, match="especie_busca_nao_demonstrada"):
            con.resolve({"kind": "decreto", "number": "1", "year": 1976})
        cand = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
        with pytest.raises(ValueError, match="versao_invalida"):
            con.fetch(type(cand)(cand.source_id, cand.key, cand.title, cand.url, metadata={"versao": "inexistente"}))
        assert con.search("Lei 6404/1976")  # nada foi bloqueado: nenhuma barreira por mero erro de uso
    assert estado.bloqueio_do_host(WWW, RelogioFalso().agora()) is None and estado.bloqueio_do_recurso(WWW, BUSCA) is None


# --- achado 6.2: recusa de robots durante a ativação persiste o bloqueio do host ------------------------------------------
@pytest.mark.parametrize("host,texto,vedado", [
    (WWW2, "User-agent: *\nDisallow: /legin/fed/\n", TERMO_URL),
    (WWW2, "User-agent: *\nDisallow: /termo-de-uso-e-politica-de-privacidade/termos-gerais\n", TERMO_URL),
    (WWW, "User-agent: *\nDisallow: /legislacao\n", BUSCA),
])
def test_c07_c15_recusa_de_robots_na_ativacao_persiste_o_bloqueio_do_host(tmp_path, host, texto, vedado):
    robots = ROBOTS_WWW2 if host == WWW2 else ROBOTS_WWW
    p, t, relogio, estado = portao(tmp_path, {robots: robots_resp(robots, texto), **rotas_www(BUSCA)}, instrumento=True)
    with pytest.raises(Unavailable) as erro:
        ativ.capturar(p, estado, relogio)
    assert erro.value.reason == "robots_recusa"
    bloqueio = estado.bloqueio_do_host(host, relogio.agora())
    assert bloqueio["classe"] == "host_persistente" and bloqueio["motivo"] == "robots_recusa"  # persistido
    with pytest.raises(Unavailable, match="robots_recusa"):
        p.obter(vedado)  # no mesmo instrumento, o host recusado não é consultado de novo
    novo = Portao(t, estado=Estado(tmp_path), relogio=relogio, instrumento=True)  # após reinício
    with pytest.raises(Unavailable, match="robots_recusa"):
        novo.obter(vedado)
    assert vedado not in t.urls


def test_robots_inconclusivo_na_ativacao_persiste_bloqueio_e_agendamento(tmp_path):
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW2: robots_resp(ROBOTS_WWW2, "lixo")}, instrumento=True)
    with pytest.raises(Unavailable, match="robots_inconclusivo"):
        ativ.capturar(p, estado, relogio)
    assert estado.bloqueio_do_host(WWW2, relogio.agora())["classe"] == "robots_inconclusivo"
    assert estado.revalidacao(WWW2)["intervalo_s"] == 3600
    assert TERMO_URL not in t.urls


# --- achado 6.3: reabertura indivisível -------------------------------------------------------------------------------------
def _host_bloqueado_com_politica(tmp_path):
    """Política vigente e bloqueio persistente do host ao mesmo tempo: o conteúdo respondeu 403."""
    p, t, relogio, estado = portao(tmp_path, {**rotas_www(BUSCA2), BUSCA: barreira("http_403", "recusa_identificado", 403)})
    with pytest.raises(Unavailable):
        p.obter(BUSCA)
    assert estado.politica(WWW) is not None and estado.bloqueio_do_host(WWW, relogio.agora())
    return p, t, relogio, estado


def test_c16_falha_no_descarte_da_politica_mantem_o_bloqueio(tmp_path, monkeypatch):
    p, t, relogio, estado = _host_bloqueado_com_politica(tmp_path)
    monkeypatch.setattr(Estado, "descartar_politica", _boom)
    with pytest.raises(EstadoIndisponivel):
        estado.liberar_host(WWW, "d-1", relogio.agora())
    assert estado.bloqueio_do_host(WWW, relogio.agora()) is not None  # o bloqueio não caiu antes da invalidação
    emitidas = list(t.urls)
    monkeypatch.undo()
    with pytest.raises(Unavailable):
        p.obter(BUSCA2)
    assert t.urls == emitidas


def test_c16_falha_ao_gravar_o_desbloqueio_mantem_o_bloqueio_e_a_politica_ja_descartada(tmp_path, monkeypatch):
    p, t, relogio, estado = _host_bloqueado_com_politica(tmp_path)
    original = Estado._gravar

    def gravar(self, nome, valor):
        if nome.startswith("bloqueio-"):
            raise EstadoIndisponivel("disco")
        return original(self, nome, valor)

    monkeypatch.setattr(Estado, "_gravar", gravar)
    with pytest.raises(EstadoIndisponivel):
        estado.liberar_host(WWW, "d-1", relogio.agora())
    monkeypatch.undo()
    assert estado.bloqueio_do_host(WWW, relogio.agora()) is not None and estado.politica(WWW) is None
    with pytest.raises(Unavailable):
        p.obter(BUSCA2)  # ainda bloqueado


def test_reabertura_completa_obriga_nova_leitura_de_robots_antes_de_qualquer_obtencao(tmp_path):
    p, t, relogio, estado = _host_bloqueado_com_politica(tmp_path)
    assert estado.liberar_host(WWW, "d-1", relogio.agora()) is True
    assert estado.politica(WWW) is None and estado.bloqueio_do_host(WWW, relogio.agora()) is None
    relogio.avancar(20)
    p.obter(BUSCA2)
    assert t.urls.count(ROBOTS_WWW) == 2  # a política antiga não foi reaproveitada


def test_reabrir_devolve_falha_controlada_e_nao_excecao_de_disco(tmp_path, monkeypatch):
    from freoa_verifica import camara_instrumento as ci
    p, t, relogio, estado = _host_bloqueado_com_politica(tmp_path)
    monkeypatch.setattr(Estado, "descartar_politica", _boom)
    saida = ci.reabrir(tmp_path, host=WWW, decisao="d-1", relogio=relogio)
    assert saida["resultado"] == "falha" and saida["motivo"] == "persistencia_local_falhou"
    assert str(tmp_path) not in json.dumps(saida)  # sem caminho de disco na falha


# --- causais (§9): a proteção removida faz o teste correspondente falhar ------------------------------------------------------
def _c06(tmp_path):
    relogio = RelogioSeparado()
    p1, t, _, estado = portao(tmp_path, rotas_www(BUSCA, BUSCA2), relogio=relogio)
    p1.obter(BUSCA)
    relogio.avancar_civil(3600)
    dormidas = len(relogio.dormidas)
    Portao(t, estado=Estado(tmp_path), relogio=relogio).obter(BUSCA2)
    return relogio.dormidas[dormidas:]


def test_causal_ritmo_so_pelo_relogio_civil_quebra_o_c06(tmp_path, monkeypatch):
    assert _c06(tmp_path / "a") == [10.0]

    def so_civil(self, host, intervalo):
        marca = self.estado.ultimo_inicio(host)
        if marca is not None:
            decorrido = max(0.0, (self.relogio.agora() - marca[0]).total_seconds())
            if intervalo - decorrido > 0:
                self.relogio.sleep(intervalo - decorrido)

    monkeypatch.setattr(Portao, "_esperar", so_civil)
    assert _c06(tmp_path / "b") == []  # a defeituosa não espera: o intervalo monotônico zero que o parecer demonstrou


def test_causal_teto_sem_reserva_atomica_emite_201(tmp_path, monkeypatch):
    def nao_atomica(self, escopo):
        with self._orcamento:
            if self.teto_sessao is not None and self.emitidas >= self.teto_sessao:
                raise Unavailable("teto_de_sessao")
        _juntas.wait(timeout=1.0)  # verifica e só depois incrementa: a janela do parecer
        with self._orcamento:
            self.emitidas += 1
        return False

    _juntas = threading.Barrier(2)
    relogio = RelogioFalso()
    p, t = _preparar_teto(tmp_path, relogio)
    monkeypatch.setattr(Portao, "_reservar", nao_atomica)
    threads = [threading.Thread(target=lambda u=u: p.obter(u)) for u in (BUSCA, LEI)]
    [th.start() for th in threads]
    [th.join(10) for th in threads]
    assert p.emitidas == 201  # sem a reserva atômica o teto de 200 é ultrapassado


def test_causal_falha_local_sem_estado_terminal_deixa_o_outro_host_emitir(tmp_path, monkeypatch):
    p, t, relogio, estado = portao(tmp_path, _rotas_basicas())
    monkeypatch.setattr(Portao, "_checar_terminal", staticmethod(lambda escopo: None))
    with da_chamada():
        monkeypatch.setattr(Estado, "registrar_obtencao", _boom)
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(BUSCA)
        monkeypatch.undo()
        monkeypatch.setattr(Portao, "_checar_terminal", staticmethod(lambda escopo: None))
        assert p.obter(LEI).body  # sem a condição terminal compartilhada, o outro host é atendido (C04)
