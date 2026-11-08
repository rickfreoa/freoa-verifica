"""Correção r1 da 0080 (parecer do PR #39), achados 1 e 2: ativação revalidada por obtenção e robots com evidência íntegra.

Contraprovas C08, C11, C12, C13, C18, C21, C22 e C03 do parecer, com variantes por classe. Sintético por construção:
transporte simulado, relógio controlado, nenhum socket.
"""
import hashlib
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors import camara_estado as ce
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_estado import Estado, EstadoIndisponivel
from freoa_verifica.connectors.camara_policy import TERMO_URL
from freoa_verifica.connectors.camara_portao import Portao
from freoa_verifica.connectors.guarda import da_chamada
from tests._camara_util import (BUSCA, LEI, ROBOTS_WWW, ROBOTS_WWW2, RelogioFalso, Transporte, barreira, portao,
                                resposta, robots_resp)

BUSCA2 = BUSCA.replace("numero=6404", "numero=6405")
WWW, WWW2 = "www.camara.leg.br", "www2.camara.leg.br"


def rotas_www(*urls):
    return {u: resposta(u, b"<html>ok</html>") for u in urls}


def ativar_em(tmp_path, rotas=None):
    """Instrumento: captura e registra a ativação num home em disco. Devolve (registro, estado, relogio, transporte)."""
    p, t, relogio, estado = portao(tmp_path / "home", {**rotas_www(BUSCA, BUSCA2), **(rotas or {})}, instrumento=True)
    pre = ativ.capturar(p, estado, relogio)
    arquivo = tmp_path / "revisao.json"
    arquivo.write_text(json.dumps({"auditor": "Auditor", "revisado_em": "2026-11-09", "termo_sha256": pre["termo_sha256"],
                                   "resultado": "conforme"}), encoding="utf-8")
    return ativ.registrar(estado, arquivo, relogio), estado, relogio, t


def do_produto(estado, t, relogio, **kw):
    """Portão como o do conector vivo: a ativação é exigida e revalidada a cada obtenção."""
    return Portao(t, estado=estado, relogio=relogio, ativacao=lambda: ativ.ativacao(estado), **kw)


def home_de(estado):
    return estado.home


# --- achado 1: a ativação acompanha a vida do conector ---------------------------------------------------------------------
def test_c22_ativacao_removida_depois_da_criacao_recoloca_o_portao_em_pendente(tmp_path):
    registro, estado, relogio, t = ativar_em(tmp_path)
    p = do_produto(estado, t, relogio)
    p.obter(BUSCA)
    antes = list(t.urls)
    (home_de(estado) / "camara_ativacao.json").unlink()
    with pytest.raises(Unavailable) as erro:
        p.obter(BUSCA2)
    assert erro.value.reason == "ativacao_ao_vivo_pendente" and t.urls == antes  # nenhuma emissão depois da perda


@pytest.mark.parametrize("dano", [
    lambda h, r: (h / "camara_ativacao.json").unlink(),
    lambda h, r: (h / "camara" / "termo" / f"{r['termo_sha256']}.html").write_bytes(b"adulterado"),
    lambda h, r: (h / "camara" / "revisao" / f"{r['revisao']['sha256']}.json").unlink(),
    lambda h, r: (h / "camara" / "revisao" / f"{r['revisao']['sha256']}.json").write_bytes(b"{}"),
    lambda h, r: (h / "camara" / f"robots-{WWW2}-{r['robots_sha256'][WWW2]}.txt").write_bytes(b"User-agent: *\nAllow: /\n"),
    lambda h, r: (h / "camara" / "termo" / f"{r['termo_sha256']}.recibo.json").unlink(),
], ids=["registro_removido", "termo_adulterado", "revisao_removida", "revisao_adulterada", "robots_adulterado",
        "recibo_removido"])
def test_ativacao_e_revalidada_antes_de_cada_obtencao_viva_por_toda_a_evidencia(tmp_path, dano):
    registro, estado, relogio, t = ativar_em(tmp_path)
    p = do_produto(estado, t, relogio)
    p.obter(BUSCA)
    antes = list(t.urls)
    dano(home_de(estado), registro)
    with pytest.raises(Unavailable, match="ativacao_ao_vivo_pendente"):
        p.obter(BUSCA2)
    assert t.urls == antes


def test_ativacao_perdida_durante_a_espera_do_ritmo_nao_emite_e_devolve_a_vaga(tmp_path):
    registro, estado, relogio, t = ativar_em(tmp_path)
    p = do_produto(estado, t, relogio)
    p.obter(BUSCA)
    emitidas = p.emitidas
    original = relogio.sleep

    def dormir_e_perder(segundos):
        original(segundos)
        (home_de(estado) / "camara_ativacao.json").unlink()

    relogio.sleep = dormir_e_perder  # a ativação some DURANTE o intervalo de 10 s
    antes = list(t.urls)
    with pytest.raises(Unavailable, match="ativacao_ao_vivo_pendente"):
        p.obter(BUSCA2)
    assert t.urls == antes and p.emitidas == emitidas  # não emitiu e a reserva do teto foi devolvida


def test_conector_vivo_perde_a_ativacao_e_nao_emite_mais(tmp_path, monkeypatch, proibir_rede):
    from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
    from tests.test_camara_0080_ativacao import servir_fixtures
    respostas, chamadas = servir_fixtures(monkeypatch)
    relogio = RelogioFalso()
    home = tmp_path / "home"
    from freoa_verifica.connectors.httputil import connector_fetch
    pre = ativ.capturar(Portao(connector_fetch, estado=Estado(home), relogio=relogio, instrumento=True), Estado(home), relogio)
    revisao = tmp_path / "r.json"
    revisao.write_text(json.dumps({"auditor": "A", "revisado_em": "2026-11-09", "termo_sha256": pre["termo_sha256"],
                                   "resultado": "conforme"}))
    ativ.registrar(Estado(home), revisao, relogio)
    con = CamaraLeginConnector(home=home, relogio=relogio)
    con.search("Lei 6404/1976")
    emitidas = len(chamadas)
    (home / "camara_ativacao.json").unlink()
    with pytest.raises(Unavailable, match="ativacao_ao_vivo_pendente"):
        con.search("Lei 6404/1976")  # mesmo conector, mesmo portão: a ativação é conferida de novo
    assert len(chamadas) == emitidas


def _regravar_com_selo(estado, mutar):
    registro = estado.ler_ativacao()
    mutar(registro)
    registro["registro_sha256"] = ativ._selo(registro)  # o checksum público é recalculado: não substitui a estrutura
    estado.gravar_ativacao(registro)


@pytest.mark.parametrize("mutar", [
    lambda r: r["revisao"].pop("auditor"), lambda r: r["revisao"].pop("revisado_em"),
    lambda r: r["revisao"].pop("sha256"), lambda r: r["revisao"].update(auditor=" "),
    lambda r: r["revisao"].update(revisado_em="ontem"), lambda r: r["revisao"].update(sha256="x"),
    lambda r: r["revisao"].update(sha256="0" * 64), lambda r: r["revisao"].update(auditor="Outro"),
    lambda r: r["revisao"].update(extra=1), lambda r: r.update(revisao=None),
    lambda r: r.update(instante="agora"), lambda r: r.update(versao_produto=""),
    lambda r: r.update(termo_sha256="z" * 64), lambda r: r["robots_sha256"].pop(WWW),
    lambda r: r["robots_sha256"].update({WWW: "1" * 64}), lambda r: r.update(extra=1),
], ids=lambda f: f"mutacao{abs(hash(f.__code__.co_code)) % 997}")
def test_c08_revisao_estruturalmente_incompleta_ou_incoerente_nao_ativa(tmp_path, mutar):
    registro, estado, relogio, t = ativar_em(tmp_path)
    assert ativ.ativacao(estado) is not None
    _regravar_com_selo(estado, mutar)
    assert ativ.ativacao(estado) is None


RECIBO_VICIADO = [
    ("url", "https://alheio.invalid"), ("status", 403), ("mime", "text/plain"), ("bytes", 1),
    ("capturado_em", "ontem"), ("politica_robots_sha256", None), ("politica_robots_sha256", "abc"),
    ("user_agent", "Mozilla/5.0"),
]


@pytest.mark.parametrize("campo,valor", RECIBO_VICIADO)
def test_c18_recibo_do_termo_incompativel_nao_e_termo_preservado(tmp_path, campo, valor):
    registro, estado, relogio, t = ativar_em(tmp_path)
    arquivo = home_de(estado) / "camara" / "termo" / f"{registro['termo_sha256']}.recibo.json"
    recibo = json.loads(arquivo.read_text("utf-8"))
    recibo[campo] = valor  # o hash do corpo e `recibo.sha256` continuam corretos
    arquivo.write_text(json.dumps(recibo), encoding="utf-8")
    assert estado.termo_preservado(registro["termo_sha256"]) is None
    assert ativ.ativacao(estado) is None


def test_c18_recibo_de_outra_politica_nao_vincula_o_termo_a_ativacao(tmp_path):
    registro, estado, relogio, t = ativar_em(tmp_path)
    arquivo = home_de(estado) / "camara" / "termo" / f"{registro['termo_sha256']}.recibo.json"
    recibo = json.loads(arquivo.read_text("utf-8"))
    recibo["politica_robots_sha256"] = "9" * 64  # bem formado, mas não é a política de www2 da ativação
    arquivo.write_text(json.dumps(recibo), encoding="utf-8")
    assert estado.termo_preservado(registro["termo_sha256"]) is not None
    assert ativ.ativacao(estado) is None


def test_c13_variante_em_memoria_recibo_com_hash_correto_e_url_alheia_invalida_a_ativacao():
    relogio = RelogioFalso()
    p, t, relogio, estado = portao(None, home=None, instrumento=True, relogio=relogio)
    pre = ativ.capturar(p, estado, relogio)
    revisao = {"auditor": "A", "revisado_em": "2026-11-09", "termo_sha256": pre["termo_sha256"], "resultado": "conforme"}
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as pasta:
        arquivo = Path(pasta) / "r.json"
        arquivo.write_text(json.dumps(revisao))
        ativ.registrar(estado, arquivo, relogio)
    assert ativ.ativacao(estado) is not None
    chave = f"termo/{pre['termo_sha256']}.recibo.json"
    recibo = json.loads(estado._memoria[chave].decode("utf-8"))
    recibo.update(url="https://alheio.invalid", status=403)
    estado._memoria[chave] = json.dumps(recibo).encode("utf-8")
    assert ativ.ativacao(estado) is None


def test_c12_registrar_recusa_pre_ativacao_sem_robots_e_nao_grava(tmp_path):
    registro, estado, relogio, t = ativar_em(tmp_path)
    (home_de(estado) / "camara_ativacao.json").unlink()
    pre = estado.ler_pre_ativacao()
    for ruim in ({}, {WWW: pre["robots_sha256"][WWW]}, {**pre["robots_sha256"], WWW: "nao-e-hash"}):
        estado.gravar_pre_ativacao({**pre, "robots_sha256": ruim})
        with pytest.raises(Unavailable, match="pre_condicoes_nao_cumpridas"):
            ativ.registrar(estado, tmp_path / "revisao.json", relogio)
        assert estado.ler_ativacao() is None


def test_registrar_valida_o_registro_final_antes_de_publicar(tmp_path, monkeypatch):
    registro, estado, relogio, t = ativar_em(tmp_path)
    (home_de(estado) / "camara_ativacao.json").unlink()
    monkeypatch.setattr(ativ, "validar_registro", lambda estado, registro: False)
    with pytest.raises(Unavailable, match="registro_de_ativacao_invalido"):
        ativ.registrar(estado, tmp_path / "revisao.json", relogio)
    assert estado.ler_ativacao() is None  # nada foi publicado


def test_registrar_le_a_revisao_uma_so_vez_e_preserva_os_bytes_do_hash_registrado(tmp_path, monkeypatch):
    from pathlib import Path
    registro, estado, relogio, t = ativar_em(tmp_path)
    (home_de(estado) / "camara_ativacao.json").unlink()
    arquivo = tmp_path / "revisao.json"
    leituras = []
    original = Path.read_bytes

    def contar(self):
        if self == arquivo:
            leituras.append(self)
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", contar)
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: pytest.fail("leitura textual da revisão"))
    novo = ativ.registrar(estado, arquivo, relogio)
    assert len(leituras) == 1
    assert novo["revisao"]["sha256"] == hashlib.sha256(original(arquivo)).hexdigest()
    assert estado.revisao_preservada(novo["revisao"]["sha256"]) == original(arquivo)


def test_registrar_recusa_politica_expirada_e_corpo_adulterado(tmp_path):
    registro, estado, relogio, t = ativar_em(tmp_path)
    (home_de(estado) / "camara_ativacao.json").unlink()
    relogio.avancar(25 * 3600)  # políticas de 24 h vencidas sem nova leitura
    with pytest.raises(Unavailable, match="robots_expirado_desde_a_captura"):
        ativ.registrar(estado, tmp_path / "revisao.json", relogio)
    relogio.t -= 25 * 3600
    corpo = home_de(estado) / "camara" / f"robots-{WWW2}-{registro['robots_sha256'][WWW2]}.txt"
    corpo.write_bytes(b"User-agent: *\nAllow: /\n")
    with pytest.raises(Unavailable, match="robots_preservado_invalido"):
        ativ.registrar(estado, tmp_path / "revisao.json", relogio)


# --- achado 2: robots com evidência íntegra, sem renovação pelo cache -------------------------------------------------------
PROIBE_BUSCA = "User-agent: *\nDisallow: /legislacao/busca\n"


def test_c21_corpo_do_robots_substituido_mantendo_o_hash_nao_autoriza_nada_em_disco(tmp_path):
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots_resp(ROBOTS_WWW, PROIBE_BUSCA), **rotas_www(BUSCA)})
    with pytest.raises(Unavailable, match="robots_recusa"):
        p.obter(BUSCA)
    politica = estado.politica(WWW)
    assert politica is None or politica["sha256"] == hashlib.sha256(PROIBE_BUSCA.encode()).hexdigest()
    # nova política legítima que permite, depois o corpo é trocado por outro que não bate com o hash
    p2, t2, relogio2, estado2 = portao(tmp_path / "b", {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\nAllow: /\n"),
                                                         **rotas_www(BUSCA)})
    p2.obter(BUSCA)
    corpo = tmp_path / "b" / "camara" / f"robots-{WWW}-{estado2.politica(WWW)['sha256']}.txt"
    corpo.write_bytes(PROIBE_BUSCA.encode())
    antes = list(t2.urls)
    relogio2.avancar(20)
    with pytest.raises(Unavailable, match="persistencia_local_falhou"):
        p2.obter(BUSCA)
    assert t2.urls == antes  # corpo que não confere com o hash: nada é emitido


def test_c21_variante_em_memoria(tmp_path):
    p, t, relogio, estado = portao(None, {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\nAllow: /\n"),
                                          **rotas_www(BUSCA, BUSCA2)}, home=None)
    p.obter(BUSCA)
    estado._memoria[f"robots-{WWW}-{estado.politica(WWW)['sha256']}.txt"] = PROIBE_BUSCA.encode()
    antes = list(t.urls)
    with pytest.raises(Unavailable, match="persistencia_local_falhou"):
        p.obter(BUSCA2)
    assert t.urls == antes


def test_bytes_originais_do_robots_sao_preservados_e_relidos_pelo_charset(tmp_path):
    original = b"User-agent: *\r\nDisallow: /wp-admin\r\n# coment\xe1rio em latin-1\r\n"
    resp = replace(robots_resp(ROBOTS_WWW, ""), body=original, sha256=hashlib.sha256(original).hexdigest(), size=len(original),
                   content_type="text/plain; charset=iso-8859-1")
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: resp, **rotas_www(BUSCA)})
    p.obter(BUSCA)
    digest = hashlib.sha256(original).hexdigest()
    assert (tmp_path / "camara" / f"robots-{WWW}-{digest}.txt").read_bytes() == original  # CRLF e latin-1 intactos
    assert estado.politica(WWW)["sha256"] == digest and estado.corpo_da_politica(WWW, digest) == original
    novo = Portao(t, estado=Estado(tmp_path), relogio=relogio)
    relogio.avancar(20)
    novo.obter(BUSCA)  # releitura pelo Content-Type guardado: sem nova obtenção do robots
    assert t.urls.count(ROBOTS_WWW) == 1


def _transporte_vivo(monkeypatch, relogio):
    from freoa_verifica.connectors.httputil import connector_fetch
    emitidas = []

    def falso(url, **kw):
        emitidas.append(url)
        return robots_resp(url, "User-agent: *\n") if "robots" in url else resposta(url, b"<html>ok</html>")

    monkeypatch.setattr("freoa_verifica.connectors.httputil.transport_fetch", falso)
    return connector_fetch, emitidas


def test_c03_resposta_reaproveitada_da_guarda_nao_renova_a_validade_do_robots(monkeypatch, proibir_rede):
    relogio = RelogioFalso()
    fetch, emitidas = _transporte_vivo(monkeypatch, relogio)
    estado = Estado(None)
    p = Portao(fetch, estado=estado, relogio=relogio)
    with da_chamada():
        p.obter(BUSCA)
        original = estado.politica(WWW)["obtido_em"]
        relogio.avancar(25 * 3600)  # a política venceu; a guarda ainda tem a resposta antiga do robots
        with pytest.raises(Unavailable, match="robots_expirado_sem_nova_obtencao"):
            p.obter(BUSCA2)
    assert emitidas == [ROBOTS_WWW, BUSCA]  # nada novo foi emitido e nenhuma autorização antiga foi reaproveitada
    assert estado.politica(WWW)["obtido_em"] == original  # `obtido_em` não foi renovado pelo cache


def test_c03_resposta_reaproveitada_ainda_valida_conta_do_instante_original(monkeypatch, proibir_rede):
    relogio = RelogioFalso()
    fetch, emitidas = _transporte_vivo(monkeypatch, relogio)
    estado = Estado(None)
    p = Portao(fetch, estado=estado, relogio=relogio)
    with da_chamada():
        p.obter(BUSCA)
        estado.descartar_politica(WWW)  # força a releitura, que a guarda atende do cache
        relogio.avancar(3600)
        p.obter(BUSCA2)
        reaproveitada = estado.politica(WWW)
    assert emitidas.count(ROBOTS_WWW) == 1
    assert reaproveitada["obtido_em"] == "2026-11-08T12:00:00+00:00"  # instante ORIGINAL da obtenção, não o de agora
    assert reaproveitada["valido_ate"] == "2026-11-09T12:00:00+00:00"


def test_nova_obtencao_do_robots_renova_a_validade(tmp_path):
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA, BUSCA2))
    p.obter(BUSCA)
    primeiro = estado.politica(WWW)["obtido_em"]
    relogio.avancar(25 * 3600)
    p.obter(BUSCA2)
    assert t.urls.count(ROBOTS_WWW) == 2 and estado.politica(WWW)["obtido_em"] != primeiro


def test_c11_acesso_direto_ao_robots_segue_o_mesmo_backoff_da_revalidacao(tmp_path):
    texto = {"valor": "lixo"}
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: lambda: robots_resp(ROBOTS_WWW, texto["valor"]), **rotas_www(BUSCA)})
    with pytest.raises(Unavailable):
        p.obter(BUSCA)
    relogio.avancar(3600)
    with pytest.raises(Unavailable, match="robots_inconclusivo"):
        p.obter(ROBOTS_WWW)  # a única tentativa de revalidação, pelo acesso direto
    assert t.urls.count(ROBOTS_WWW) == 2
    assert estado.revalidacao(WWW)["intervalo_s"] == 7200  # o prazo dobrou: o acesso direto agendou como o fluxo comum
    emitidas = len(t.urls)
    for _ in range(2):
        with pytest.raises(Unavailable, match="robots_inconclusivo"):
            p.obter(ROBOTS_WWW)  # ainda dentro do prazo: bloqueado, nada emitido
    assert len(t.urls) == emitidas
    relogio.avancar(7200)
    texto["valor"] = "User-agent: *\nAllow: /\n"
    assert p.obter(ROBOTS_WWW).body
    assert estado.politica(WWW) is not None and estado.bloqueio_do_host(WWW, relogio.agora()) is None  # persistiu e liberou


def test_robots_direto_nao_persiste_politica_invalida(tmp_path):
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "lixo")})
    with pytest.raises(Unavailable, match="robots_inconclusivo"):
        p.obter(ROBOTS_WWW)
    assert estado.politica(WWW) is None and estado.bloqueio_do_host(WWW, relogio.agora())["classe"] == "robots_inconclusivo"


def test_limite_de_24h_vale_a_partir_do_instante_original_mesmo_com_valido_ate_adulterado(tmp_path):
    p, t, relogio, estado = portao(tmp_path, rotas_www(BUSCA, BUSCA2))
    p.obter(BUSCA)
    arquivo = tmp_path / "camara" / f"robots-{WWW}.json"
    registro = json.loads(arquivo.read_text("utf-8"))
    registro["valido_ate"] = (ce._de_iso(registro["obtido_em"]) + timedelta(days=30)).isoformat()
    arquivo.write_text(json.dumps(registro), encoding="utf-8")
    with pytest.raises(EstadoIndisponivel, match="politica_validade"):
        estado.politica_valida(WWW, relogio.agora())
    antes = list(t.urls)
    with pytest.raises(Unavailable, match="persistencia_local_falhou"):
        p.obter(BUSCA2)
    assert t.urls == antes


def test_decisoes_por_caminho_nunca_sao_descartadas_em_silencio():
    p, t, relogio, estado = portao(None, rotas_www(), home=None)
    caminhos = [f"/legislacao/busca?x={i}" for i in range(501)]
    p.verificar_caminhos(WWW, caminhos)
    decisoes = estado.politica(WWW)["decisoes"]
    assert set(decisoes) == set(caminhos) and set(decisoes.values()) == {"permitido"}  # 501 > 500: nenhuma sumiu


def test_decisao_proibida_e_registrada_antes_do_bloqueio_do_host(tmp_path):
    p, t, relogio, estado = portao(tmp_path, {ROBOTS_WWW: robots_resp(ROBOTS_WWW, PROIBE_BUSCA), **rotas_www(BUSCA)})
    with pytest.raises(Unavailable, match="robots_recusa"):
        p.obter(BUSCA)
    assert estado.politica(WWW)["decisoes"]["/legislacao/busca?abrangencia=Legisla%C3%A7%C3%A3o+Federal&tipo=Lei+Ordin"
                                             "%C3%A1ria&numero=6404&ano=1976&geral="] == "proibido"
    assert estado.bloqueio_do_host(WWW, relogio.agora())["classe"] == "host_persistente"


def test_crawl_delay_acima_do_teto_operacional_e_abstencao_declarada_sem_emitir_nem_bloquear(tmp_path):
    rotas = {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\nCrawl-delay: 7200\n"), **rotas_www(BUSCA)}
    p, t, relogio, estado = portao(tmp_path, rotas)
    with pytest.raises(Unavailable) as erro:  # a leitura do robots conta como requisição: o conteúdo teria de esperar 2 h
        p.obter(BUSCA)
    assert erro.value.reason == "crawl_delay_acima_do_teto_operacional" and t.urls == [ROBOTS_WWW]
    assert estado.bloqueio_do_host(WWW, relogio.agora()) is None  # abstenção operacional, não bloqueio persistente
    relogio.avancar(7200)
    p.obter(BUSCA)  # decorrido o atraso declarado, o acesso volta a ser honrado
    assert t.urls[-1] == BUSCA and relogio.dormidas == []


def test_crawl_delay_dentro_do_teto_operacional_e_honrado(tmp_path):
    rotas = {ROBOTS_WWW: robots_resp(ROBOTS_WWW, "User-agent: *\nCrawl-delay: 3600\n"), **rotas_www(BUSCA, BUSCA2)}
    p, t, relogio, estado = portao(tmp_path, rotas)
    p.obter(BUSCA)
    p.obter(BUSCA2)
    assert round(t.chamadas[-1][2] - t.chamadas[-2][2], 6) == 3600.0
