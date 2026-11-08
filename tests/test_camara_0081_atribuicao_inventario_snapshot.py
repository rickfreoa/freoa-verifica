"""Correção r1 da 0080 (parecer do PR #39), achados 7, 8 e 9: instrumento (falhas e inventário durável), atribuição por
captura em todas as entregas de texto e snapshot com evidência administrativa. Contraprovas C10, C14 e C17.
Sintético por construção: transporte simulado e capturas reais intactas servidas por dublê; nenhum socket.
"""
import hashlib
import json

import pytest

from freoa_verifica import camara_instrumento as ci
from freoa_verifica.cli import build_parser
from freoa_verifica.connectors import camara_ativacao as ativ
from freoa_verifica.connectors import camara_evidencias as ev
from freoa_verifica.connectors.camara_atribuicao import atribuicao, termo_da_captura
from freoa_verifica.connectors.camara_estado import Estado, EstadoIndisponivel
from freoa_verifica.connectors.camara_policy import TERMO_URL
from freoa_verifica.identidade_http import USER_AGENT_IDENTIFICADO
from freoa_verifica.service import Verifica
from tests._camara_util import (BUSCA, FETCHED_PADRAO, LEI, TERMO_HTML, RelogioFalso, Transporte, barreira, da_fixture,
                                obter_vinculado, portao, resposta)
from tests.test_camara_0080_atribuicao import (ART, TERMO_SHA, acervo, ativar_home, esperada, exportar,  # noqa: F401
                                               refazer_checksums)
from tests.test_camara_legin import ATUAL, ORIGINAL, servidor  # noqa: F401

WWW, WWW2 = "www.camara.leg.br", "www2.camara.leg.br"
TERMO2 = b"<html><body><h1>Termos gerais</h1><p>Atualizado em 07/11/2026</p></body></html>"
CHAVES_FIXTURE = ("robots_portal", "robots_legin", "busca_lei6404", "norma_lei6404", "textos_atualizado_lei6404",
                  "textos_original_lei6404")


def _boom(*a, **k):
    raise EstadoIndisponivel("disco")


def rotas_da_fixture(**sobrescrever):
    rotas = {r.url: r for r in (da_fixture(k) for k in CHAVES_FIXTURE)}
    return {**rotas, **sobrescrever}


def ativar_com(tmp_path, rotas, *, home=None):
    """Ativa um home em disco (instrumento) com as rotas dadas. Devolve (home, relogio, transporte)."""
    home = home or tmp_path / "home"
    tmp_path.mkdir(parents=True, exist_ok=True)
    p, t, relogio, estado = portao(home, rotas, instrumento=True)
    pre = ativ.capturar(p, estado, relogio)
    revisao = tmp_path / f"revisao-{home.name}.json"
    revisao.write_text(json.dumps({"auditor": "Auditor", "revisado_em": "2026-11-09", "termo_sha256": pre["termo_sha256"],
                                   "resultado": "conforme"}), encoding="utf-8")
    ativ.registrar(estado, revisao, relogio)
    return home, relogio, t


def normas_em(tmp_path, *normas):
    arquivo = tmp_path / "normas.json"
    arquivo.write_text(json.dumps(list(normas) or [{"kind": "lei", "number": "6404", "year": 1976}]))
    return arquivo


# --- achado 9 (instrumento): inventário durável por unidade, material parcial, acumuladores, falhas controladas ----------------
def test_inventario_grava_por_unidade_todos_os_recursos_com_motivo(tmp_path):
    rotas = rotas_da_fixture()
    home, relogio, t = ativar_com(tmp_path, rotas)
    t2 = Transporte(relogio, rotas)
    out = ci.inventariar(home, normas_em(tmp_path), tmp_path / "saida", transporte=t2, relogio=relogio)
    assert out["resultado"] == "ok" and out["obtidas"] == 1
    inv = json.loads((tmp_path / "saida" / "lei-6404-1976" / "inventario.json").read_text("utf-8"))
    assert inv["resultado"] == "obtida" and inv["falha"] is None and inv["norma"]["number"] == "6404"
    por_url = {r["url"]: r for r in inv["recursos"]}
    assert por_url[ATUAL]["obtido"] is True and por_url[ATUAL]["motivo"] == "obtido"
    assert por_url[ORIGINAL]["obtido"] is True
    # recursos publicados que a gramática não admite ou que não foram pedidos ficam inventariados com motivo
    nao_obtidos = [r for r in inv["recursos"] if not r["obtido"]]
    assert nao_obtidos and all(r["motivo"] and r["motivo"] != "obtido" for r in nao_obtidos)
    assert all(r["origem_sha256"] and r["href"] for r in inv["recursos"])
    assert {p["url"] for p in inv["paginas"]} >= {LEI, ATUAL, ORIGINAL}


def test_unidade_que_falha_no_meio_preserva_o_material_parcial_e_o_motivo(tmp_path):
    rotas = rotas_da_fixture()
    home, relogio, t = ativar_com(tmp_path, rotas)
    t2 = Transporte(relogio, {**rotas, ORIGINAL: barreira("http_404", None, 404)})
    out = ci.inventariar(home, normas_em(tmp_path), tmp_path / "saida", transporte=t2, relogio=relogio)
    assert out["resultado"] == "parcial" and out["nao_obtidas"] == 1
    pasta = tmp_path / "saida" / "lei-6404-1976"
    inv = json.loads((pasta / "inventario.json").read_text("utf-8"))
    assert inv["resultado"] == "falha" and inv["falha"]["motivo"] == "http_404" and inv["falha"]["url"] == ORIGINAL
    por_url = {r["url"]: r for r in inv["recursos"]}
    assert por_url[ATUAL]["obtido"] is True  # o atualizado foi obtido e NÃO foi descartado com a falha da original
    assert por_url[ORIGINAL]["obtido"] is False and por_url[ORIGINAL]["motivo"] == "http_404"
    corpos = {p.name for p in pasta.glob("*.corpo")}
    assert len(corpos) == 3 and not any(ORIGINAL in p["url"] for p in inv["paginas"])  # busca, norma e atualizado gravados
    for pagina in inv["paginas"]:
        corpo = (pasta / pagina["arquivo"]).read_bytes()
        assert hashlib.sha256(corpo).hexdigest() == pagina["sha256"]


def test_acumuladores_do_conector_sao_zerados_por_norma():
    from types import SimpleNamespace
    pagina = resposta(LEI, b"x")
    con = SimpleNamespace(paginas={LEI: pagina}, links={LEI: (pagina, "h", "r")}, inventarios={LEI: {"recursos": []}},
                          politicas=[{"url": LEI}])
    ci._zerar(con)
    assert con.paginas == {} and con.links == {} and con.inventarios == {} and con.politicas == []


def test_c17_falha_de_gravacao_vira_falha_controlada_sem_oserror_nem_caminho(tmp_path, monkeypatch):
    rotas = rotas_da_fixture()
    home, relogio, t = ativar_com(tmp_path, rotas)
    monkeypatch.setattr(ci, "_escrever", _boom)
    out = ci.inventariar(home, normas_em(tmp_path), tmp_path / "saida", transporte=Transporte(relogio, rotas),
                         relogio=relogio)  # não levanta
    assert out["resultado"] == "parcial" and out["falhas"][0]["motivo"] == "persistencia_local_falhou"
    assert str(tmp_path) not in json.dumps(out) and "lei-6404" not in json.dumps(out)


def test_c17_em_reserva_a_mesma_falha_de_gravacao_nao_aparece_em_canal_nenhum(tmp_path, monkeypatch, capsys):
    rotas = rotas_da_fixture()
    home, relogio, t = ativar_com(tmp_path, rotas)
    monkeypatch.setattr(ci, "_escrever", _boom)
    capsys.readouterr()
    parsed = build_parser().parse_args(["--home", str(home), "camara", "inventariar", str(normas_em(tmp_path)),
                                        "--destino", str(tmp_path / "reserva"), "--reserva", "--saida-privada",
                                        str(tmp_path / "guardiao.json")])
    assert ci.executar(parsed, transporte=Transporte(relogio, rotas), relogio=relogio) == 0
    visto = capsys.readouterr()
    assert (visto.out, visto.err) == ("", "")
    assert json.loads((tmp_path / "guardiao.json").read_text("utf-8"))["falhas"][0]["motivo"] == "persistencia_local_falhou"


def test_ativar_com_falha_de_gravacao_do_termo_e_falha_controlada(tmp_path, monkeypatch):
    p, t, relogio, estado = portao(tmp_path / "home", instrumento=True)
    monkeypatch.setattr(Estado, "guardar_termo", _boom)
    saida = ci.ativar(tmp_path / "home", etapa="capturar", transporte=t, relogio=relogio)
    assert saida["resultado"] == "falha" and saida["motivo"] == "persistencia_local_falhou"
    assert str(tmp_path) not in json.dumps(saida) and estado.ler_pre_ativacao() is None


def test_situacao_com_estado_corrompido_e_falha_controlada(tmp_path):
    (tmp_path / "camara").mkdir(parents=True)
    (tmp_path / "camara" / f"bloqueio-{WWW}.json").write_text("[1]", encoding="utf-8")
    saida = ci.situacao(tmp_path, RelogioFalso())
    assert saida["resultado"] == "falha" and saida["motivo"] == "persistencia_local_falhou"


def test_inventario_so_obtem_com_a_ativacao_revalidada_a_cada_obtencao(tmp_path):
    rotas = rotas_da_fixture()
    home, relogio, t = ativar_com(tmp_path, rotas)
    t2 = Transporte(relogio, rotas)
    original = relogio.sleep

    def dormir_e_perder(segundos):  # a ativação some no meio da sessão
        original(segundos)
        (home / "camara_ativacao.json").unlink(missing_ok=True)

    relogio.sleep = dormir_e_perder
    out = ci.inventariar(home, normas_em(tmp_path), tmp_path / "saida", transporte=t2, relogio=relogio)
    assert out["resultado"] == "parcial" and out["obtidas"] == 0
    assert t2.urls == [BUSCA]  # só a busca saiu; a ativação se perdeu na espera da página seguinte e nada mais foi emitido


# --- achado 8: atribuição por captura em todas as entregas de texto ---------------------------------------------------------
def test_buscar_legislacao_local_entrega_atribuicao_em_cada_item_de_origem_camara(acervo):  # noqa: F811
    out = acervo.buscar_legislacao("companhia ou sociedade anônima", fonte="__somente_local__")
    itens = [i for i in out["itens"] if i["trecho"]]
    assert itens and all(i["atribuicao"] == esperada() for i in itens)
    assert all(i["obra"] and "atribuicao" in i for i in itens)


def test_candidato_ao_vivo_do_staging_e_o_indexador_entregam_atribuicao(acervo, monkeypatch):  # noqa: F811
    monkeypatch.setattr(acervo, "_offline", lambda: False)
    con = acervo._get("camara_legin")
    cand = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
    item = acervo._index_candidate_legis(con, cand)
    assert item["capture_id"] and item["trecho"] and item["atribuicao"] == esperada()
    # o indexador não duplica no staging o que o FTS canônico já tem: o candidato ao vivo é simulado com a mesma redação
    texto, rotulo, caminho = acervo.conn.execute(
        "SELECT text, work_label, path FROM fts_redaction WHERE path='art1' LIMIT 1").fetchone()
    acervo.conn.execute("INSERT INTO fts_staging(text, work_label, path) VALUES (?,?,?)", (texto, rotulo, caminho))
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    busca = acervo.buscar_legislacao("responsabilidade dos sócios ou acionistas será limitada ao preço de emissão",
                                     fonte="camara_legin", limite=50)
    staging = [i for i in busca["itens"] if i.get("candidato_ao_vivo")]
    assert staging and all(i["atribuicao"] == esperada() for i in staging)
    assert all(i["atribuicao"] == esperada() for i in busca["itens"] if i["trecho"])


def test_obter_evidencia_extrai_a_autoria_do_documento_correspondente(acervo, monkeypatch):  # noqa: F811
    sem = acervo.obter_evidencia(acervo.capturas[0].capture_id)
    assert sem["atribuicao"] == esperada()  # o documento não declara autoria: nunca fabricada
    monkeypatch.setattr("freoa_verifica.texto_resposta.texto_para_exibicao",
                        lambda corpo, ctype: "Autoria: Comissão de Estudos\nArt. 1º A companhia ou sociedade anônima")
    com = acervo.obter_evidencia(acervo.capturas[0].capture_id)
    assert com["atribuicao"] == esperada(autoria="Comissão de Estudos") and "Autoria" in com["texto"]


CAP_EM = "2026-11-08T12:00:05+00:00"


def _registro(sha, url, termo, capturado_em=CAP_EM):
    return {"url": url, "sha256": sha, "capturado_em": capturado_em, "politica_sha256": "a" * 64,
            "politica_obtida_em": "2026-11-08T12:00:00+00:00", "em": "2026-11-08T12:00:10+00:00",
            "termo_sha256": termo}


def _guardar_termo2(estado):
    digest = hashlib.sha256(TERMO2).hexdigest()
    estado.guardar_termo(TERMO2, {"url": TERMO_URL, "capturado_em": "2026-11-09T12:00:00+00:00", "status": 200,
                                  "mime": "text/html", "bytes": len(TERMO2), "sha256": digest,
                                  "data_ou_versao_exibida": "07/11/2026", "politica_robots_sha256": "b" * 64,
                                  "user_agent": USER_AGENT_IDENTIFICADO})
    return digest


def test_atribuicao_e_por_captura_e_nao_pelo_termo_corrente_do_home(tmp_path):
    home = tmp_path / "h"
    ativar_home(home, tmp_path)  # a ativação do home usa o termo T1
    estado = Estado(home)
    t2 = _guardar_termo2(estado)
    a, b = hashlib.sha256(b"a").hexdigest(), hashlib.sha256(b"b").hexdigest()
    estado.registrar_obtencao(_registro(a, "https://www2.camara.leg.br/a", TERMO_SHA))
    estado.registrar_obtencao(_registro(b, "https://www2.camara.leg.br/b", t2))
    assert atribuicao(home, sha256=a, url="https://www2.camara.leg.br/a", fetched_at=CAP_EM)["termo_sha256"] == TERMO_SHA
    assert atribuicao(home, sha256=b, url="https://www2.camara.leg.br/b", fetched_at=CAP_EM)["termo_sha256"] == t2  # não vira T1


def test_termo_herdado_sem_conferencia_nao_gera_atribuicao_e_o_indice_acompanha_o_arquivo(tmp_path):
    home = tmp_path / "h"
    ativar_home(home, tmp_path)
    (home / "camara" / "termo-de-snapshot.json").write_text(json.dumps({"termo_url": TERMO_URL, "termo_sha256": TERMO_SHA}))
    conteudo = hashlib.sha256(b"novo").hexdigest()
    n = "https://www2.camara.leg.br/n"
    assert termo_da_captura(home, conteudo, n, CAP_EM) is None  # arquivo solto não vale
    Estado(home).registrar_obtencao(_registro(conteudo, n, TERMO_SHA))
    assert termo_da_captura(home, conteudo, n, CAP_EM) == TERMO_SHA  # índice renovado
    (home / "camara" / "termo" / f"{TERMO_SHA}.recibo.json").write_text("{}")
    assert termo_da_captura(home, conteudo, n, CAP_EM) is None  # alteração interna é vista


# --- achado 9 (snapshot): evidência administrativa, reexportação, anexação -------------------------------------------------
def test_c14_reexportacao_de_home_instalado_preserva_a_evidencia_e_a_atribuicao(acervo, tmp_path, monkeypatch,  # noqa: F811
                                                                                 proibir_rede):
    primeira = exportar(acervo, tmp_path / "snap1")
    m1 = json.loads((primeira / "MANIFEST.json").read_text("utf-8"))
    monkeypatch.setenv("FV_OFFLINE", "1")
    meio = Verifica(home=tmp_path / "meio")
    try:
        assert meio.snapshot_install(primeira, aceitar_nao_vinculado=True)["status"] == "ok"
        assert Estado(meio.home).ler_ativacao() is None  # instalar não ativa a rota
        segunda = exportar(meio, tmp_path / "snap2")  # reexporta o home que só tem a evidência herdada
    finally:
        meio.close()
    m2 = json.loads((segunda / "MANIFEST.json").read_text("utf-8"))
    assert m2["camara_evidencias"]["termos"] == m1["camara_evidencias"]["termos"] == [TERMO_SHA]
    assert m2["camara_evidencias"]["arquivos"] == m1["camara_evidencias"]["arquivos"]
    assert any("evidencias/ativacao-" in a for a in m2["camara_evidencias"]["arquivos"])
    final = Verifica(home=tmp_path / "final")
    try:
        assert final.snapshot_install(segunda, aceitar_nao_vinculado=True)["status"] == "ok"
        depois = final.obter_dispositivo(ART, versao="publicacao_original")["evidencia"]
        assert depois["atribuicao"] == esperada()
        assert Estado(final.home).obtencoes() == Estado(acervo.home).obtencoes()  # vínculos captura → política → termo
        for rw in acervo.capturas:
            assert final.obter_evidencia(rw.capture_id)["atribuicao"] == esperada()
    finally:
        final.close()


def test_instalacao_recupera_a_evidencia_administrativa_completa(acervo, tmp_path, monkeypatch):  # noqa: F811
    pasta = exportar(acervo, tmp_path / "snap")
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "novo")
    try:
        assert novo.snapshot_install(pasta, aceitar_nao_vinculado=True)["status"] == "ok"
        camara = novo.home / "camara"
        assert (camara / "termo" / f"{TERMO_SHA}.html").read_bytes() == TERMO_HTML
        assert Estado(novo.home).termo_preservado(TERMO_SHA)["politica_robots_sha256"]
        ativacao = acervo._camara_ativada() and Estado(acervo.home).ler_ativacao()
        assert (camara / "revisao" / f"{ativacao['revisao']['sha256']}.json").exists()
        for host, digest in ativacao["robots_sha256"].items():
            assert Estado(novo.home).corpo_da_politica(host, digest)  # bytes originais com o hash conferido
            assert list((camara / "politicas").glob(f"{host}-{digest}-*.json"))
        assert (camara / "evidencias" / f"ativacao-{ativacao['registro_sha256']}.json").exists()
    finally:
        novo.close()


def _homes_com_termos_diferentes(tmp_path):
    """Dois homes ativados com termos diferentes; cada um obtém, pelo portão, um conteúdo seu (vínculo real)."""
    a, b = tmp_path / "a", tmp_path / "b"
    ra = {TERMO_URL: resposta(TERMO_URL, TERMO_HTML), LEI: resposta(LEI, b"capa")}
    rb = {TERMO_URL: resposta(TERMO_URL, TERMO2), LEI: resposta(LEI, b"capb")}
    _, rel_a, _ = ativar_com(tmp_path / "ta", ra, home=a)
    _, rel_b, _ = ativar_com(tmp_path / "tb", rb, home=b)
    obter_vinculado(a, ra, rel_a, LEI)
    obter_vinculado(b, rb, rel_b, LEI)
    ca, cb = hashlib.sha256(b"capa").hexdigest(), hashlib.sha256(b"capb").hexdigest()
    ta, tb = hashlib.sha256(TERMO_HTML).hexdigest(), hashlib.sha256(TERMO2).hexdigest()
    return a, b, (ca, ta), (cb, tb)


def _empacotar(home, destino):
    hashes, entrada = ev.exportar(home, destino)
    return {"camara_evidencias": entrada, "arquivos_sha256": hashes}


def test_anexacao_de_snapshots_com_termos_diferentes_preserva_a_atribuicao_de_cada_captura(tmp_path):
    a, b, (ca, ta), (cb, tb) = _homes_com_termos_diferentes(tmp_path)
    c = tmp_path / "c"
    for home, nome in ((a, "sa"), (b, "sb")):
        destino = tmp_path / nome
        manifesto = _empacotar(home, destino)
        ev.instalar(c, ev.preparar(destino, manifesto))
    assert termo_da_captura(c, ca, LEI, FETCHED_PADRAO) == ta  # a anexação de B não troca o termo de A
    assert termo_da_captura(c, cb, LEI, FETCHED_PADRAO) == tb
    assert {ca, cb} <= {r["sha256"] for r in Estado(c).obtencoes()}
    antes = len(Estado(c).obtencoes())
    ev.instalar(c, ev.preparar(tmp_path / "sa2", _empacotar(a, tmp_path / "sa2")))  # idempotente
    assert len(Estado(c).obtencoes()) == antes
    reexport = _empacotar(c, tmp_path / "sc")  # e a reexportação do anexado leva os dois termos
    assert sorted(reexport["camara_evidencias"]["termos"]) == sorted([ta, tb])


@pytest.mark.parametrize("adulterar,motivo", [
    (lambda pasta, h: (pasta / "camara" / "termo" / f"{TERMO_SHA}.recibo.json").write_text(
        json.dumps({**json.loads((pasta / "camara" / "termo" / f"{TERMO_SHA}.recibo.json").read_text("utf-8")),
                    "status": 403})), "camara_evidencia_ilegivel"),
    (lambda pasta, h: (pasta / "camara" / "obtencoes.jsonl").write_text('{"url": 1}\n'), "camara_evidencia_ilegivel"),
    (lambda pasta, h: [p.write_bytes(p.read_bytes() + b" x") for p in (pasta / "camara").glob("robots-*.txt")],
     "camara_evidencia_hash_diverge"),
    (lambda pasta, h: [p.write_text(p.read_text("utf-8").replace('"auditor"', '"auditor_"'))
                       for p in (pasta / "camara" / "evidencias").glob("ativacao-*.json")],
     "camara_ativacao_evidencia_invalida"),
], ids=["recibo_incompativel", "obtencao_invalida", "robots_adulterado", "ativacao_incoerente"])
def test_snapshot_com_evidencia_incoerente_e_checksums_refeitos_nao_instala(acervo, tmp_path, monkeypatch,  # noqa: F811
                                                                           adulterar, motivo):
    pasta = exportar(acervo, tmp_path / "snap")
    adulterar(pasta, None)
    refazer_checksums(pasta)
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "novo")
    try:
        r = novo.snapshot_install(pasta, aceitar_nao_vinculado=True)
        assert r["status"] == "erro" and r["motivo"].startswith(motivo), r
        assert not [p for p in (novo.home / "camara").rglob("*") if p.is_file()]  # nenhum arquivo da evidência entrou
    finally:
        novo.close()


def test_exportacao_recusa_home_com_evidencia_administrativa_incoerente(acervo, tmp_path):  # noqa: F811
    (acervo.home / "camara" / "termo" / f"{TERMO_SHA}.recibo.json").write_text(
        json.dumps({"url": "https://alheio.invalid"}), encoding="utf-8")
    saida = acervo.snapshot_export(tmp_path / "snap")
    assert saida["status"] == "erro" and saida["motivo"].startswith("camara_evidencia")  # nada é omitido em silêncio


def test_snapshot_sem_evidencia_da_camara_continua_instalavel_e_sem_o_campo(tmp_path, verifica_populada, monkeypatch):
    svc, rw, _ = verifica_populada
    saida = svc.snapshot_export(tmp_path / "snap")
    assert saida["status"] == "ok"
    manifesto = json.loads((tmp_path / "snap" / "MANIFEST.json").read_text("utf-8"))
    assert "camara_evidencias" not in manifesto and not (tmp_path / "snap" / "camara").exists()
