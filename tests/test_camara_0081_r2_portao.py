"""Correção r2 da 0080 (parecer do PR #39), R2-1 a R2-5 no portão e no conector: política que vence durante a espera,
recibo de robots como evidência dos bytes, falha local ao ler terminal, identidade que alimenta o classificador e
vínculo da obtenção com a captura e o termo vigentes na emissão.
Sintético por construção: transporte simulado, relógio controlado, nenhum socket; capturas reais intactas servidas por dublê.
"""
import dataclasses
import hashlib
import json
from datetime import timedelta

import pytest

from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_atribuicao import termo_da_captura
from freoa_verifica.connectors.camara_estado import (Estado, EstadoIndisponivel, LeituraLocalFalhou, _de_iso, iso)
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
from freoa_verifica.connectors.camara_policy import TERMO_URL
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.connectors.guarda import da_chamada
from tests._camara_util import (BUSCA, LEI, ROBOTS_WWW, ROBOTS_WWW2, TERMO_HTML, RelogioFalso,
                                Transporte, da_fixture, obter_vinculado, portao, resposta, robots_resp)
from tests.test_camara_0081_atribuicao_inventario_snapshot import TERMO2, ativar_com, rotas_da_fixture
from tests.test_camara_0081_ritmo_falhas_barreiras import (BUSCA2, BUSCA3, WWW, WWW2, ROBOTS_REAIS, _conector, _fixtures,
                                                           rotas_www)

LIVRE = "User-agent: *\nDisallow: /wp-admin*\n"


def com_delay(segundos):
    return f"User-agent: *\nCrawl-delay: {segundos}\nDisallow: /wp-admin*\n"


def robots_em_sequencia(*textos):
    """Rota de robots que serve um texto por leitura (o último se repete)."""
    entregues = []

    def servir():
        texto = textos[min(len(entregues), len(textos) - 1)]
        entregues.append(texto)
        return robots_resp(ROBOTS_WWW, texto)
    servir.entregues = entregues
    return servir


def _politica_valida_na_emissao(estado, t, inicio):
    """Toda emissão de conteúdo ocorreu dentro da validade da política que a autorizou (a registrada na obtenção)."""
    registradas = {o["url"]: o for o in estado.obtencoes()}
    arquivadas = {(r["sha256"], iso(_de_iso(r["obtido_em"]))): r for r in estado.politicas_arquivadas(WWW)}
    for url, _, mono in t.chamadas:
        if url == ROBOTS_WWW or url not in registradas:
            continue
        instante = inicio + timedelta(seconds=mono)
        obtencao = registradas[url]
        recibo = arquivadas[(obtencao["politica_sha256"], iso(_de_iso(obtencao["politica_obtida_em"])))]
        if not _de_iso(recibo["obtido_em"]) <= instante < _de_iso(recibo["valido_ate"]):
            return False
    return True


def _ate_cinco_segundos_do_vencimento(p, estado, relogio):
    """Obtém a política, anda até 5 s antes de ela vencer e emite um conteúdo (última emissão ao host)."""
    p.obter(BUSCA)
    valido_ate = _de_iso(estado.politica(WWW)["valido_ate"])
    relogio.avancar((valido_ate - relogio.agora()).total_seconds() - 5)
    p.obter(BUSCA2)
    return valido_ate


# --- R2-1: a política é revalidada imediatamente antes da emissão -------------------------------------------------------
@pytest.mark.parametrize("inicial,renovada", [(0, 0), (20, 40)], ids=["espera_de_10_s", "crawl_delay_maior"])
def test_r21_espera_que_atravessa_o_vencimento_renova_o_robots_e_recomputa_o_ritmo(tmp_path, inicial, renovada):
    robots = robots_em_sequencia(com_delay(inicial) if inicial else LIVRE, com_delay(renovada) if renovada else LIVRE)
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots, **rotas_www(BUSCA, BUSCA2, BUSCA3)})
    valido_ate = _ate_cinco_segundos_do_vencimento(p, estado, relogio)
    assert len(robots.entregues) == 1  # até aqui a política vale
    p.obter(BUSCA3)  # a espera obrigatória (10 s ou o Crawl-delay) atravessa o vencimento
    assert len(robots.entregues) == 2  # nova leitura ANTES da obtenção
    assert t.urls[-2:] == [ROBOTS_WWW, BUSCA3]
    leitura, conteudo = t.chamadas[-2][2], t.chamadas[-1][2]
    assert relogio.inicio + timedelta(seconds=conteudo) >= valido_ate  # a emissão ocorreu depois do vencimento da antiga
    assert conteudo - leitura >= max(10.0, renovada)  # e o ritmo foi recomputado a partir da política NOVA
    ultima = estado.obtencoes()[-1]
    assert ultima["url"] == BUSCA3 and _de_iso(ultima["politica_obtida_em"]) >= valido_ate  # vínculo à política vigente
    assert _politica_valida_na_emissao(estado, t, relogio.inicio)


def test_r21_o_invariante_detecta_a_emissao_sem_revalidacao(tmp_path, monkeypatch):
    """Mutante: sem a reconfirmação (o comportamento da r1) o cenário emite com política vencida e o invariante o vê."""
    monkeypatch.setattr(Portao, "_reconfirmar", lambda self, host, politica, caminho, url: politica)
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA, BUSCA2, BUSCA3))
    _ate_cinco_segundos_do_vencimento(p, estado, relogio)
    p.obter(BUSCA3)
    assert len([u for u in t.urls if u == ROBOTS_WWW]) == 1  # não releu o robots
    assert _politica_valida_na_emissao(estado, t, relogio.inicio) is False  # emitiu depois do vencimento


def test_r21_renovacao_que_proibe_o_caminho_nao_emite_e_bloqueia_o_host(tmp_path):
    robots = robots_em_sequencia(LIVRE, "User-agent: *\nDisallow: /legislacao\n")
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots, **rotas_www(BUSCA, BUSCA2, BUSCA3)})
    _ate_cinco_segundos_do_vencimento(p, estado, relogio)
    emitidas = list(t.urls)
    with pytest.raises(Unavailable, match="robots_recusa"):
        p.obter(BUSCA3)
    assert BUSCA3 not in t.urls and t.urls[len(emitidas):] == [ROBOTS_WWW]
    assert estado.bloqueio_do_host(WWW, relogio.agora())["motivo"] == "robots_recusa"


def test_r21_renovacao_que_falha_devolve_a_reserva_e_nao_emite_conteudo(tmp_path):
    robots = robots_em_sequencia(LIVRE)
    rotas = {ROBOTS_WWW: robots, **rotas_www(BUSCA, BUSCA2, BUSCA3)}
    p, t, relogio, estado = portao(tmp_path, rotas, teto_chamada=None, teto_sessao=100)
    _ate_cinco_segundos_do_vencimento(p, estado, relogio)
    antes = p.emitidas
    t.rotas[ROBOTS_WWW] = lambda: robots_resp(ROBOTS_WWW, "isto não é robots")
    with pytest.raises(Unavailable):
        p.obter(BUSCA3)
    assert BUSCA3 not in t.urls
    assert p.emitidas == antes + 1  # só a leitura de robots emitida e contada; a reserva do conteúdo foi devolvida


# --- R2-2: o recibo de robots é evidência coerente com os bytes ---------------------------------------------------------
ADULTERACOES = [
    ("crawl_delay", 0.0), ("status", 403), ("bytes", -1), ("user_agent", "outro"), ("tokens", []),
    ("grupos_considerados", []), ("mime", "text/html"), ("content_type", "text/html; charset=utf-8"),
    ("decisoes", {"/legislacao/busca": "proibido"}),
]


@pytest.mark.parametrize("campo,valor", ADULTERACOES, ids=[c for c, _ in ADULTERACOES])
def test_r22_recibo_que_contradiz_os_bytes_e_falha_local_terminal_sem_emissao(tmp_path, campo, valor):
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots_resp(ROBOTS_WWW, com_delay(30)), **rotas_www(BUSCA, BUSCA2)})
    p.obter(BUSCA)
    recibo = estado.politica(WWW)
    assert recibo["crawl_delay"] == 30.0 and estado.atraso_da_politica(recibo) == 30.0
    estado._gravar(f"robots-{WWW}.json", {**recibo, campo: valor})  # adulteração local do recibo; bytes e hash intactos
    emitidas = list(t.urls)
    relogio.avancar(60)
    with da_chamada():
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(BUSCA2)
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(ROBOTS_WWW2)  # e o outro host: o escopo terminou
    assert t.urls == emitidas


def test_r22_atraso_vem_dos_bytes_e_nao_do_campo_declarado(tmp_path):
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots_resp(ROBOTS_WWW, com_delay(30)), **rotas_www(BUSCA, BUSCA2)})
    p.obter(BUSCA)
    recibo = estado.politica(WWW)
    assert estado.atraso_da_politica({**recibo, "crawl_delay": 0.0}) == 30.0  # o campo declarado não conta
    relogio.dormidas.clear()
    p.obter(BUSCA2)
    assert relogio.dormidas == [30.0]  # esperou os 30 s dos bytes, não os 10 s mínimos


def test_r22_a_ativacao_recusa_o_recibo_adulterado_com_a_mesma_validacao(tmp_path):
    home, relogio, _ = ativar_com(tmp_path, rotas_da_fixture())
    estado = Estado(home)
    assert ativ.ativacao(estado) is not None
    recibo = estado.politica(WWW)
    estado._gravar(f"robots-{WWW}.json", {**recibo, "status": 403})
    assert ativ.ativacao(estado) is None  # evidência incoerente não sustenta a ativação
    estado._gravar(f"robots-{WWW}.json", recibo)
    assert ativ.ativacao(estado) is not None
    arquivado = next((home / "camara" / "politicas").glob(f"{WWW2}-*.json"))
    antes = arquivado.read_bytes()
    dados = json.loads(antes)
    dados["tokens"] = []
    arquivado.write_text(json.dumps(dados), encoding="utf-8")
    assert ativ.ativacao(estado) is None  # nem o recibo arquivado adulterado
    arquivado.write_bytes(antes)
    assert ativ.ativacao(estado) is not None


# --- R2-3: falha local ao ler é terminal; validação numérica total ------------------------------------------------------
def test_r23_falha_local_ao_ler_a_ativacao_nao_vira_pendencia_e_encerra_a_chamada(tmp_path, monkeypatch):
    rotas = rotas_da_fixture()
    home, relogio, _ = ativar_com(tmp_path, rotas)
    estado = Estado(home)
    t = Transporte(relogio, rotas)
    p = Portao(t, estado=estado, relogio=relogio, ativacao=lambda: ativ.ativacao(estado))
    original = Estado.ler_ativacao
    falhas = []

    def ler_com_falha(self):
        if not falhas:
            falhas.append(1)
            raise LeituraLocalFalhou("disco")
        return original(self)

    monkeypatch.setattr(Estado, "ler_ativacao", ler_com_falha)
    with da_chamada():
        with pytest.raises(Unavailable) as primeiro:
            p.obter(BUSCA)
        assert primeiro.value.reason == "persistencia_local_falhou"  # nunca `ativacao_ao_vivo_pendente`
        emitidas = list(t.urls)
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(LEI)  # o armazenamento voltou, mas a unidade terminou: o outro host também não é emitido
        assert t.urls == emitidas
    with da_chamada():  # só uma nova unidade funciona
        assert p.obter(BUSCA).body


def test_r23_ausencia_legitima_da_ativacao_continua_pendencia_e_nao_encerra(tmp_path):
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA, BUSCA2), ativacao=lambda: ativ.ativacao(Estado(tmp_path)))
    with da_chamada():
        with pytest.raises(Unavailable, match="ativacao_ao_vivo_pendente"):
            p.obter(BUSCA)
        with pytest.raises(Unavailable, match="ativacao_ao_vivo_pendente"):
            p.obter(BUSCA2)  # pendência, não terminal: cada tentativa reavalia
    assert t.urls == []


def test_r23_conector_com_leitura_local_falha_na_criacao_do_portao_encerra_o_escopo(tmp_path, monkeypatch):
    home = tmp_path / "home"
    con = CamaraLeginConnector(home=home)
    monkeypatch.setattr(Estado, "ler_ativacao", lambda self: (_ for _ in ()).throw(LeituraLocalFalhou("disco")))
    with da_chamada():
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            con.search("Lei 6404/1976")
        monkeypatch.undo()
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):  # mesma unidade: segue terminal
            con.search("Lei 6404/1976")


NUMEROS_INVALIDOS = [
    ("ritmo", lambda e, h: e._gravar(f"ritmo-{h}.json", {"inicio": "2026-11-08T12:00:00+00:00", "mono": 10**500})),
    ("ritmo_inicio_fora_do_intervalo",
     lambda e, h: e._gravar(f"ritmo-{h}.json", {"inicio": "0001-01-01T00:00:00+14:00", "mono": 1})),
    ("revalidacao", lambda e, h: e._gravar(f"bloqueio-{h}.json", {"revalidacao": {"proxima": "2026-11-08T12:00:00+00:00",
                                                                                "intervalo_s": 10**500}})),
]


@pytest.mark.parametrize("nome,gravar", NUMEROS_INVALIDOS, ids=[n for n, _ in NUMEROS_INVALIDOS])
@pytest.mark.parametrize("escopo", ["chamada", "sessao"])
def test_r23_numero_invalido_no_estado_e_falha_tipada_terminal_nos_dois_hosts(tmp_path, nome, gravar, escopo):
    p, t, relogio, estado = portao(tmp_path, {**rotas_www(BUSCA), LEI: resposta(LEI, b"<html>lei</html>")},
                                   instrumento=escopo == "sessao")
    gravar(estado, WWW)
    with da_chamada():
        with pytest.raises(Unavailable) as erro:
            p.obter(BUSCA)
        assert erro.value.reason == "persistencia_local_falhou"  # tipada: nunca OverflowError solto
        emitidas = list(t.urls)
        with pytest.raises(Unavailable, match="persistencia_local_falhou"):
            p.obter(LEI)  # outro host, mesma chamada ou sessão
        assert t.urls == emitidas


def test_r23_recibo_com_numero_gigante_e_esquema_invalido(tmp_path):
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA))
    p.obter(BUSCA)
    recibo = estado.politica(WWW)
    estado._gravar(f"robots-{WWW}.json", {**recibo, "crawl_delay": 10**500})
    with pytest.raises(EstadoIndisponivel):
        estado.politica(WWW)


def test_r23_excecao_aritmetica_inesperada_de_interpretacao_e_terminal(tmp_path, monkeypatch):
    p, t, relogio, estado = portao(tmp_path, {**rotas_www(BUSCA), LEI: resposta(LEI, b"<html>lei</html>")})
    monkeypatch.setattr(Estado, "ultimo_inicio", lambda self, host: (_ for _ in ()).throw(OverflowError("imprevisto")))
    with da_chamada():
        with pytest.raises(Unavailable, match="interpretacao_local_falhou"):
            p.obter(BUSCA)
        emitidas = list(t.urls)
        monkeypatch.undo()
        with pytest.raises(Unavailable, match="interpretacao_local_falhou"):
            p.obter(LEI)
        assert t.urls == emitidas


# --- R2-4: divergência de identidade alimenta o classificador de barreiras ----------------------------------------------
def _norma_com_titulo(de: bytes, para: bytes):
    base = da_fixture("norma_lei6404")
    corpo = base.body.replace(de, para)
    assert corpo != base.body
    return dataclasses.replace(base, body=corpo, sha256=hashlib.sha256(corpo).hexdigest(), size=len(corpo))


def test_r24_resolve_com_identidade_divergente_bloqueia_o_recurso_e_o_host_pelo_restante_da_chamada(tmp_path):
    divergente = _norma_com_titulo(b"6.404", b"6.405")
    rotas = {**_fixtures(*ROBOTS_REAIS, "busca_lei6404"), LEI: divergente, **rotas_www(BUSCA2)}
    con, p, t, estado = _conector(tmp_path, rotas)
    with da_chamada():
        with pytest.raises(Unavailable) as erro:
            con.resolve({"kind": "lei", "number": "6404", "year": 1976})
        assert erro.value.reason == "identidade_nao_confirmada" and erro.value.categoria == "resposta_inesperada"
        assert erro.value.evidencia["url"] == LEI
        bloqueio = estado.bloqueio_do_recurso(WWW2, LEI)
        assert bloqueio["classe"] == "corpo_ou_mime" and bloqueio["motivo"] == "identidade_nao_confirmada"
        emitidas = list(t.urls)
        with pytest.raises(Unavailable) as depois:
            p.obter(TERMO_URL)  # outro recurso de www2, mesma chamada: bloqueado pelo restante da chamada
        assert depois.value.evidencia["bloqueio"] == "corpo_ou_mime"
        assert t.urls == emitidas


def test_r24_fetch_com_identidade_divergente_classifica_como_perfil_incompativel(tmp_path):
    divergente = _norma_com_titulo(b"6.404", b"6.405")
    rotas = {**_fixtures(*ROBOTS_REAIS, "busca_lei6404"), LEI: divergente}
    con, p, t, estado = _conector(tmp_path, rotas)
    with da_chamada():
        candidato = con.search("Lei 6404/1976")[0]  # a busca publica o vínculo de descoberta da página
        with pytest.raises(Unavailable) as erro:
            con.fetch(candidato)
        assert erro.value.reason == "identidade_nao_confirmada" and erro.value.categoria == "resposta_inesperada"
        assert estado.bloqueio_do_recurso(WWW2, LEI)["classe"] == "corpo_ou_mime"


def test_r24_ausencia_demonstrada_e_erro_de_entrada_continuam_distintos(tmp_path):
    """Nenhuma página da norma pedida entre os candidatos: ausência (sem categoria, sem bloqueio); entrada inválida
    idem. Só a página que o endereço dá como a norma e que diz outra coisa é perfil incompatível."""
    busca_1977 = BUSCA.replace("ano=1976", "ano=1977")
    pagina = dataclasses.replace(da_fixture("busca_lei6404"), url=busca_1977, final_url=busca_1977)
    rotas = {**_fixtures(*ROBOTS_REAIS, "busca_lei6404", "norma_lei6404"), busca_1977: pagina}
    con, p, t, estado = _conector(tmp_path, rotas)
    with da_chamada():
        with pytest.raises(Unavailable) as ausente:
            con.resolve({"kind": "lei", "number": "6404", "year": 1977})  # a busca só lista a norma de 1976
        assert ausente.value.reason == "identidade_nao_confirmada" and ausente.value.categoria is None
        with pytest.raises(Unavailable, match="especie_busca_nao_demonstrada"):
            con.resolve({"kind": "decreto", "number": "1", "year": 1976})
    assert estado.bloqueio_do_recurso(WWW2, LEI) is None and estado.bloqueio_do_host(WWW2, relogio_agora()) is None


def relogio_agora():
    return RelogioFalso().agora()


# --- R2-5: o vínculo da obtenção identifica a captura e o termo vigentes na emissão -----------------------------------
def _reativar_com_termo(tmp_path, home, relogio, corpo):
    """Registra no mesmo home uma nova ativação (termo novo, revisão nova): o termo vigente passa a ser outro."""
    rotas = {**rotas_da_fixture(), TERMO_URL: resposta(TERMO_URL, corpo)}
    estado = Estado(home)
    p = Portao(Transporte(relogio, rotas), estado=estado, relogio=relogio, instrumento=True)
    pre = ativ.capturar(p, estado, relogio)
    revisao = tmp_path / f"revisao-{hashlib.sha256(corpo).hexdigest()[:8]}.json"
    revisao.write_text(json.dumps({"auditor": "Auditor", "revisado_em": "2026-11-09", "termo_sha256": pre["termo_sha256"],
                                   "resultado": "conforme"}), encoding="utf-8")
    ativ.registrar(estado, revisao, relogio)
    return pre["termo_sha256"]


def test_r25_mesmo_conteudo_e_url_em_instantes_diferentes_nao_se_confundem_e_a_ordem_nao_importa(tmp_path):
    rotas = rotas_da_fixture()
    home, relogio, _ = ativar_com(tmp_path, rotas)
    t1 = hashlib.sha256(TERMO_HTML).hexdigest()
    corpo = b"<html>mesmo conteudo</html>"
    f1, f2 = "2026-11-08T12:10:00+00:00", "2026-11-08T12:20:00+00:00"
    obter_vinculado(home, {**rotas, LEI: dataclasses.replace(resposta(LEI, corpo), fetched_at=f1)}, relogio, LEI)
    t2 = _reativar_com_termo(tmp_path, home, relogio, TERMO2)
    assert t2 != t1
    obter_vinculado(home, {**rotas, LEI: dataclasses.replace(resposta(LEI, corpo), fetched_at=f2)}, relogio, LEI)
    sha = hashlib.sha256(corpo).hexdigest()
    assert termo_da_captura(home, sha, LEI, f1) == t1 and termo_da_captura(home, sha, LEI, f2) == t2
    arquivo = home / "camara" / "obtencoes.jsonl"
    linhas = arquivo.read_bytes().splitlines(keepends=True)
    arquivo.write_bytes(b"".join(reversed(linhas)))  # inverter a ordem de anexação não muda a escolha
    assert termo_da_captura(home, sha, LEI, f1) == t1 and termo_da_captura(home, sha, LEI, f2) == t2
    assert termo_da_captura(home, sha, LEI, "2026-11-08T12:30:00+00:00") is None  # nenhuma captura nesse instante


def test_r25_registros_da_mesma_captura_com_termos_diferentes_tornam_o_vinculo_ambiguo(tmp_path):
    rotas = rotas_da_fixture()
    home, relogio, _ = ativar_com(tmp_path, rotas)
    corpo = b"<html>x</html>"
    resposta_fixa = dataclasses.replace(resposta(LEI, corpo), fetched_at="2026-11-08T12:10:00+00:00")
    obter_vinculado(home, {**rotas, LEI: resposta_fixa}, relogio, LEI)
    _reativar_com_termo(tmp_path, home, relogio, TERMO2)
    obter_vinculado(home, {**rotas, LEI: resposta_fixa}, relogio, LEI)  # a MESMA captura, sob outro termo
    assert termo_da_captura(home, hashlib.sha256(corpo).hexdigest(), LEI, "2026-11-08T12:10:00+00:00") is None


class RelogioQueTrocaAAtivacao(RelogioFalso):
    """Durante a espera obrigatória a ativação vigente muda (nova revisão e novo termo registrados)."""

    def __init__(self, ao_dormir):
        super().__init__()
        self.ao_dormir = ao_dormir

    def sleep(self, segundos):
        super().sleep(segundos)
        self.ao_dormir()


def test_r25_termo_registrado_e_o_da_ativacao_valida_na_emissao(tmp_path):
    t1, t2 = hashlib.sha256(b"termo 1").hexdigest(), hashlib.sha256(b"termo 2").hexdigest()
    vigente = {"termo_sha256": t1}
    relogio = RelogioQueTrocaAAtivacao(lambda: vigente.update(termo_sha256=t2))
    p, t, _, estado = portao(tmp_path, rotas_www(BUSCA, BUSCA2), relogio=relogio, ativacao=lambda: dict(vigente),
                             exigir_ativacao=False)
    p.obter(BUSCA)  # a primeira emissão já esperou (robots → conteúdo): a ativação virou T2 durante a espera
    assert [o["termo_sha256"] for o in estado.obtencoes()] == [t2]  # T2: o termo vigente na emissão, não o da admissão


# --- R2-1 e R2-5 juntos: nenhuma regressão de contagem de robots em fluxo normal ---------------------------------------
def test_fluxo_normal_nao_le_o_robots_a_mais(tmp_path):
    robots = robots_em_sequencia(LIVRE)
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots, **rotas_www(BUSCA, BUSCA2, BUSCA3)})
    for url in (BUSCA, BUSCA2, BUSCA3):
        p.obter(url)
    assert len(robots.entregues) == 1  # a reconfirmação não renova política que ainda vale
