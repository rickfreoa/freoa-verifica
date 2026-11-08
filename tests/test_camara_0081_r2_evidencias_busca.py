"""Correção r2 da 0080 (parecer do PR #39), R2-5 (busca), R2-6 (fechamento dos vínculos e decisões arquivadas), R2-7
(instalação administrativa transacional) e R2-8 (contaminação entre unidades do inventário).
Sintético por construção: transporte simulado, capturas reais intactas servidas por dublê, banco SQLite temporário.
"""
import dataclasses
import hashlib
import json
import os
from pathlib import Path

import pytest

from freoa_verifica import camara_instrumento as ci
from freoa_verifica import snapshot as snapshot_mod
from freoa_verifica.connectors import camara_evidencias as ev
from freoa_verifica.connectors.camara_estado import Estado
from freoa_verifica.connectors.camara_legin import inventario
from freoa_verifica.service import Verifica
from freoa_verifica.store import repo
from tests._camara_util import LEI, Transporte, barreira, da_fixture, obter_vinculado, resposta
from tests.test_camara_0080_atribuicao import (ART, TERMO_SHA, acervo, ativar_home, esperada, exportar,  # noqa: F401
                                               refazer_checksums)
from tests.test_camara_0081_atribuicao_inventario_snapshot import (_empacotar, _guardar_termo2, _registro, ativar_com,
                                                                    normas_em, rotas_da_fixture)
from tests.test_camara_legin import ATUAL, ORIGINAL, servidor  # noqa: F401

WWW, WWW2 = "www.camara.leg.br", "www2.camara.leg.br"


# --- R2-5 (busca): a atribuição é da obra e da ocorrência que sustentam o item -----------------------------------------
def _ocorrencia_em_outra_obra(svc, *, texto, caminho, fonte, numero, ano, resp):
    """Outra norma, de outra fonte, com a MESMA redação no MESMO caminho (entrada válida: art. 1º iguais existem)."""
    svc.conn.execute("INSERT OR IGNORE INTO source(id, authority, profile, hosts_json) VALUES (?,?,?,?)",
                     (fonte, "federal", "camara_norma", "[]"))
    work_id = repo.upsert_work(svc.conn, jurisdiction="br", authority="federal", kind="lei", number=numero, year=ano,
                               label=f"Lei {numero}/{ano}")
    capture_id = repo.save_capture(svc.conn, resp, fonte, home=svc.home)
    with svc.conn:
        svc.conn.execute("INSERT INTO provision(id, work_id, scope, path) VALUES (?,?,?,?)",
                         (f"p-{numero}", work_id, "", caminho))
        svc.conn.execute("INSERT INTO redaction(id, provision_id, text, text_sha256) VALUES (?,?,?,?)",
                         (f"r-{numero}", f"p-{numero}", texto, hashlib.sha256(texto.encode()).hexdigest()))
        svc.conn.execute("INSERT INTO extract(id, capture_id, parser_version, text_sha256) VALUES (?,?,?,?)",
                         (f"e-{numero}", capture_id, "t", hashlib.sha256(texto.encode()).hexdigest()))
        svc.conn.execute("INSERT INTO occurrence(id, redaction_id, extract_id) VALUES (?,?,?)",
                         (f"o-{numero}", f"r-{numero}", f"e-{numero}"))
    return capture_id


def test_r25_busca_nao_empresta_atribuicao_de_outra_obra_com_o_mesmo_texto_e_caminho(verifica_populada, tmp_path):
    svc, rw, _ = verifica_populada  # obra A: Planalto
    ativar_home(svc.home, tmp_path)
    texto, caminho = svc.conn.execute(
        "SELECT r.text, p.path FROM redaction r JOIN provision p ON p.id=r.provision_id WHERE p.work_id=? "
        "ORDER BY length(r.text) DESC LIMIT 1", (rw.work_id,)).fetchone()
    corpo_b = b"<html>obra B</html>"
    resp_b = resposta("https://www2.camara.leg.br/legin/fed/lei/1990-1999/b.html", corpo_b)
    _ocorrencia_em_outra_obra(svc, texto=texto, caminho=caminho, fonte="camara_legin", numero="9999", ano=1999,
                              resp=resp_b)
    Estado(svc.home).registrar_obtencao(_registro(resp_b.sha256, resp_b.url, TERMO_SHA, resp_b.fetched_at))
    out = svc.buscar_legislacao(" ".join(texto.split()[:6]), fonte="__somente_local__", limite=50)
    itens_a = [i for i in out["itens"] if i["caminho"] == caminho and i["work_id"] == rw.work_id]
    assert itens_a  # o item da obra A (Planalto) existe...
    assert all("atribuicao" not in i and "atribuicoes" not in i for i in itens_a)  # ...e não ganha a atribuição da obra B
    # controle: o vínculo da obra B existe e seria conferido se ela fosse a obra do item
    assert svc._atribuicao_camara(texto, resp_b.sha256, resp_b.url, resp_b.fetched_at)["termo_sha256"] == TERMO_SHA


def test_r25_busca_preserva_separadas_as_origens_camara_distintas_da_mesma_obra(acervo):  # noqa: F811
    estado = Estado(acervo.home)
    t2 = _guardar_termo2(estado)
    texto, rotulo, caminho = acervo.conn.execute(
        "SELECT text, work_label, path FROM fts_redaction WHERE path='art1' LIMIT 1").fetchone()
    redacao = acervo.conn.execute(
        "SELECT r.id FROM redaction r JOIN provision p ON p.id=r.provision_id WHERE r.text=? AND p.path=?",
        (texto, caminho)).fetchone()[0]
    resp2 = dataclasses.replace(resposta(ATUAL, b"<html>segunda captura</html>"), fetched_at="2026-11-10T12:00:00+00:00")
    capture_id = repo.save_capture(acervo.conn, resp2, "camara_legin", home=acervo.home)
    with acervo.conn:
        acervo.conn.execute("INSERT INTO extract(id, capture_id, parser_version, text_sha256) VALUES (?,?,?,?)",
                            ("e-2", capture_id, "t", hashlib.sha256(texto.encode()).hexdigest()))
        acervo.conn.execute("INSERT INTO occurrence(id, redaction_id, extract_id) VALUES (?,?,?)", ("o-2", redacao, "e-2"))
    estado.registrar_obtencao(_registro(resp2.sha256, resp2.url, t2, resp2.fetched_at))
    out = acervo.buscar_legislacao(" ".join(texto.split()[:6]), fonte="__somente_local__", limite=50)
    item = next(i for i in out["itens"] if i["caminho"] == caminho and i["trecho"])
    assert "atribuicao" not in item  # duas origens com termos diferentes: nenhuma é escolhida por ordem
    assert sorted(a["termo_sha256"] for a in item["atribuicoes"]) == sorted([TERMO_SHA, t2])
    assert all(a["fonte"] == "Câmara dos Deputados" for a in item["atribuicoes"])


# --- R2-6: fechamento dos vínculos e decisões por caminho preservadas ------------------------------------------------------
@pytest.fixture
def home_com_evidencia(tmp_path):
    rotas = rotas_da_fixture()
    home, relogio, _ = ativar_com(tmp_path, rotas)
    obter_vinculado(home, rotas, relogio, LEI)
    return home


def _arquivos(home):
    return ev._arquivos_do_home(Estado(home))


def _nome(arquivos, padrao):
    return next(n for n in arquivos if n.startswith(padrao))


def test_r26_conjunto_completo_e_aceito(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    ev._validar(arquivos)  # o controle positivo: o conjunto íntegro passa
    assert any(n.startswith("termo/") for n in arquivos) and "obtencoes.jsonl" in arquivos


def test_r26_obtencao_sem_termo_nem_politica_e_recusada(home_com_evidencia):
    so_obtencoes = {"obtencoes.jsonl": _arquivos(home_com_evidencia)["obtencoes.jsonl"]}
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_sem_(termo|politica)"):
        ev._validar(so_obtencoes)
    ate_a_ativacao = [json.loads(linha) for linha in so_obtencoes["obtencoes.jsonl"].splitlines() if linha]
    com_termo = [o for o in ate_a_ativacao if o["termo_sha256"]]
    assert com_termo  # o conteúdo obtido depois da ativação aponta o termo...
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_sem_termo"):  # ...que, sozinho, não está no conjunto
        ev._validar({"obtencoes.jsonl": b"\n".join(json.dumps(o).encode() for o in com_termo) + b"\n"})


def test_r26_termo_sem_recibo_e_recusado(home_com_evidencia):
    arquivos = _arquivos(home_com_evidencia)
    so_corpo = {n: d for n, d in arquivos.items() if n.endswith(".html")}
    assert so_corpo
    with pytest.raises(ev.EvidenciaInvalida, match="camara_termo_sem_recibo"):
        ev._validar(so_corpo)


def _sem(arquivos, nome):
    return {n: d for n, d in arquivos.items() if n != nome}


def test_r26_toda_peca_referenciada_e_indispensavel(home_com_evidencia):
    """Suprimir QUALQUER arquivo de que um vínculo depende é recusado; só os que ninguém referencia podem faltar."""
    arquivos = _arquivos(home_com_evidencia)
    ev._validar(arquivos)
    livres = {"obtencoes.jsonl"} | {n for n in arquivos if n.startswith("evidencias/")}
    for nome in sorted(set(arquivos) - livres):
        with pytest.raises(ev.EvidenciaInvalida):
            ev._validar(_sem(arquivos, nome))
    for nome in sorted(livres):
        ev._validar(_sem(arquivos, nome))  # ausência TOTAL de obtenções ou de registros de ativação é legítima


def test_r26_obtencao_com_instante_da_politica_sem_recibo_e_recusada(home_com_evidencia):
    arquivos = dict(_arquivos(home_com_evidencia))
    linha = json.loads(arquivos["obtencoes.jsonl"].splitlines()[-1])
    linha["politica_obtida_em"] = "2020-01-01T00:00:00+00:00"
    arquivos["obtencoes.jsonl"] = json.dumps(linha).encode() + b"\n"
    with pytest.raises(ev.EvidenciaInvalida, match="camara_obtencao_instante_da_politica_sem_recibo|anterior"):
        ev._validar(arquivos)


@pytest.mark.parametrize("campo,valor,motivo", [
    ("termo_sha256", "0" * 64, "camara_obtencao_sem_termo"),
    ("politica_sha256", "0" * 64, "camara_obtencao_sem_politica"),
])
def test_r26_referencia_cruzada_quebrada_com_checksums_refeitos_nao_instala(acervo, tmp_path, monkeypatch,  # noqa: F811
                                                                           campo, valor, motivo):
    pasta = exportar(acervo, tmp_path / "snap")
    arquivo = pasta / "camara" / "obtencoes.jsonl"
    linhas = [json.loads(linha) for linha in arquivo.read_bytes().splitlines() if linha]
    linhas[0][campo] = valor
    arquivo.write_bytes(b"".join(json.dumps(linha, sort_keys=True).encode() + b"\n" for linha in linhas))
    refazer_checksums(pasta)
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "novo")
    try:
        resultado = novo.snapshot_install(pasta, aceitar_nao_vinculado=True)
        assert resultado["status"] == "erro" and resultado["motivo"].startswith(motivo), resultado
    finally:
        novo.close()


def _remover_do_snapshot(pasta: Path, nome: str):
    """Adversário que suprime um arquivo da evidência, atualiza o manifesto e refaz os checksums."""
    manifesto = json.loads((pasta / "MANIFEST.json").read_text("utf-8"))
    manifesto["arquivos_sha256"].pop(nome)
    manifesto["camara_evidencias"]["arquivos"].remove(nome)
    (pasta / nome).unlink()
    (pasta / "MANIFEST.json").write_text(json.dumps(manifesto, ensure_ascii=False, indent=2, sort_keys=True), "utf-8")
    refazer_checksums(pasta)


def test_r26_snapshot_sem_o_recibo_do_termo_com_checksums_refeitos_nao_instala(acervo, tmp_path, monkeypatch):  # noqa: F811
    pasta = exportar(acervo, tmp_path / "snap")
    _remover_do_snapshot(pasta, f"camara/termo/{TERMO_SHA}.recibo.json")
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "novo")
    try:
        resultado = novo.snapshot_install(pasta, aceitar_nao_vinculado=True)
        assert resultado["status"] == "erro" and "camara_" in resultado["motivo"], resultado
        assert not (novo.home / "camara").exists()
    finally:
        novo.close()


def test_r26_decisoes_por_caminho_chegam_ao_recibo_arquivado_que_viaja(home_com_evidencia):
    estado = Estado(home_com_evidencia)
    vigente = estado.politica(WWW2)
    assert vigente["decisoes"], "o conteúdo obtido registra a decisão do seu caminho"
    arquivos = _arquivos(home_com_evidencia)
    arquivado = json.loads(arquivos[_nome(arquivos, f"politicas/{WWW2}-")])
    assert arquivado["decisoes"] == vigente["decisoes"]  # o artefato arquivado não fica com o estado inicial
    assert estado.politicas_arquivadas(WWW2)[-1]["decisoes"] == vigente["decisoes"]


def test_r26_decisoes_sobrevivem_ao_roundtrip_exportar_instalar_reexportar(home_com_evidencia, tmp_path):
    antes = {json.loads(d)["sha256"]: json.loads(d)["decisoes"] for n, d in _arquivos(home_com_evidencia).items()
             if n.startswith(f"politicas/{WWW2}-")}
    destino = tmp_path / "sa"
    manifesto = _empacotar(home_com_evidencia, destino)
    novo = tmp_path / "novo-home"
    novo.mkdir()
    ev.instalar(novo, ev.preparar(destino, manifesto))
    depois = {json.loads(d)["sha256"]: json.loads(d)["decisoes"] for n, d in _arquivos(novo).items()
              if n.startswith(f"politicas/{WWW2}-")}
    assert depois == antes and any(depois.values())


def test_r26_politica_adulterada_com_checksums_refeitos_e_recusada_pela_mesma_validacao_do_portao(home_com_evidencia):
    arquivos = dict(_arquivos(home_com_evidencia))
    nome = _nome(arquivos, f"politicas/{WWW2}-")
    registro = json.loads(arquivos[nome])
    registro["crawl_delay"] = 99.0  # contradiz os bytes do robots
    arquivos[nome] = json.dumps(registro).encode()
    with pytest.raises(ev.EvidenciaInvalida, match="camara_evidencia_ilegivel"):
        ev._validar(arquivos)


# --- R2-7: instalação administrativa transacional -----------------------------------------------------------------------
def _estado_do_camara(home: Path) -> dict[str, bytes]:
    pasta = home / "camara"
    return {p.relative_to(pasta).as_posix(): p.read_bytes() for p in sorted(pasta.rglob("*")) if p.is_file()} \
        if pasta.exists() else {}


def _pacote(home_com_evidencia, tmp_path, nome="pacote"):
    destino = tmp_path / nome
    return ev.preparar(destino, _empacotar(home_com_evidencia, destino))


def test_r27_conflito_tardio_nao_deixa_escrita_anterior_no_home(home_com_evidencia, tmp_path):
    arquivos = _pacote(home_com_evidencia, tmp_path)
    ultimo = [n for n in arquivos if n != "obtencoes.jsonl"][-1]
    alvo_home = tmp_path / "novo"
    (alvo_home / "camara" / Path(ultimo).parent).mkdir(parents=True)
    (alvo_home / "camara" / ultimo).write_bytes(b"conteudo local diferente")  # conflita com o ÚLTIMO arquivo a ser escrito
    antes = _estado_do_camara(alvo_home)
    with pytest.raises(ev.EvidenciaInvalida, match="camara_evidencia_conflita_com_o_home"):
        ev.instalar(alvo_home, arquivos)
    assert _estado_do_camara(alvo_home) == antes  # nenhum dos arquivos anteriores (sem conflito) foi escrito
    assert not [p for p in alvo_home.iterdir() if p.name.startswith(".camara-staging")]


def test_r27_falha_de_escrita_no_meio_restaura_o_estado_anterior(home_com_evidencia, tmp_path, monkeypatch):
    arquivos = _pacote(home_com_evidencia, tmp_path)
    alvo_home = tmp_path / "novo"
    (alvo_home / "camara").mkdir(parents=True)
    existente = {"obtencoes.jsonl": b""}
    sobra = alvo_home / "camara" / "obtencoes.jsonl"
    sobra.write_bytes(existente["obtencoes.jsonl"])
    antes = _estado_do_camara(alvo_home)
    real = os.replace
    contagem = []

    def falhar_na_quarta_publicacao(origem, destino, *a, **k):
        if "camara" in Path(destino).parts and ".camara-staging" in str(origem):
            contagem.append(destino)
            if len(contagem) == 4:
                raise OSError("disco cheio")
        return real(origem, destino, *a, **k)

    monkeypatch.setattr(ev.os, "replace", falhar_na_quarta_publicacao)
    with pytest.raises(OSError, match="disco cheio"):
        ev.instalar(alvo_home, arquivos)
    assert len(contagem) == 4  # três arquivos já tinham sido publicados quando a quarta falhou
    monkeypatch.undo()
    assert _estado_do_camara(alvo_home) == antes  # e voltaram: o home é o de antes, inclusive o arquivo pré-existente
    assert {p.relative_to(alvo_home / "camara").as_posix() for p in (alvo_home / "camara").rglob("*")} == {"obtencoes.jsonl"}


def test_r27_snapshot_com_conflito_tardio_recusa_sem_alterar_banco_nem_camara(acervo, tmp_path, monkeypatch):  # noqa: F811
    pasta = exportar(acervo, tmp_path / "snap")
    monkeypatch.setenv("FV_OFFLINE", "1")
    manifesto = json.loads((pasta / "MANIFEST.json").read_text("utf-8"))
    ultimo = [n[len("camara/"):] for n in manifesto["camara_evidencias"]["arquivos"] if not n.endswith("obtencoes.jsonl")][-1]
    novo = Verifica(home=tmp_path / "novo")
    try:
        (novo.home / "camara" / Path(ultimo).parent).mkdir(parents=True, exist_ok=True)
        (novo.home / "camara" / ultimo).write_bytes(b"divergente")
        antes = _estado_do_camara(novo.home)
        obras = novo.conn.execute("SELECT count(*) FROM work").fetchone()[0]
        resultado = novo.snapshot_install(pasta, aceitar_nao_vinculado=True)
        assert resultado["status"] == "erro" and "conflita_com_o_home" in resultado["motivo"], resultado
        assert _estado_do_camara(novo.home) == antes
        assert novo.conn.execute("SELECT count(*) FROM work").fetchone()[0] == obras
    finally:
        novo.close()


@pytest.mark.parametrize("ponto", ["save_installed", "publicacao_do_camara"])
def test_r27_falha_posterior_ou_na_publicacao_desfaz_banco_blobs_e_camara(acervo, tmp_path, monkeypatch, ponto):  # noqa: F811
    pasta = exportar(acervo, tmp_path / "snap")
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "novo")
    try:
        obras = novo.conn.execute("SELECT count(*) FROM work").fetchone()[0]
        antes = _estado_do_camara(novo.home)
        if ponto == "save_installed":
            def explodir(*a, **k):
                raise RuntimeError("falha depois da publicação")
            monkeypatch.setattr(snapshot_mod.acervo, "save_installed", explodir)
        else:
            real = os.replace
            vistos = []

            def falhar_na_segunda(origem, destino, *a, **k):
                if "camara" in Path(destino).parts and "camara-novo" in str(origem):
                    vistos.append(destino)
                    if len(vistos) == 2:
                        raise OSError("disco cheio")
                return real(origem, destino, *a, **k)
            monkeypatch.setattr(snapshot_mod.os, "replace", falhar_na_segunda)
        resultado = novo.snapshot_install(pasta, aceitar_nao_vinculado=True)
        monkeypatch.undo()
        assert resultado["status"] == "erro" and resultado["rollback"] is True and "rollback_error" not in resultado, resultado
        assert novo.conn.execute("SELECT count(*) FROM work").fetchone()[0] == obras  # banco restaurado
        assert _estado_do_camara(novo.home) == antes == {}  # nenhum termo, revisão ou obtenção ficou no home
        assert not (novo.home / "camara").exists() or not list((novo.home / "camara").rglob("*.*"))
    finally:
        novo.close()


def test_r27_instalacao_integral_continua_funcionando_e_e_idempotente(acervo, tmp_path, monkeypatch):  # noqa: F811
    pasta = exportar(acervo, tmp_path / "snap")
    monkeypatch.setenv("FV_OFFLINE", "1")
    novo = Verifica(home=tmp_path / "novo")
    try:
        assert novo.snapshot_install(pasta, aceitar_nao_vinculado=True)["status"] == "ok"
        primeiro = _estado_do_camara(novo.home)
        assert primeiro and Estado(novo.home).termo_preservado(TERMO_SHA)
        assert novo.snapshot_install(pasta, aceitar_nao_vinculado=True)["status"] == "ok"  # idempotente
        assert _estado_do_camara(novo.home) == primeiro
    finally:
        novo.close()


def test_r27_decisoes_por_caminho_de_snapshots_diferentes_sao_unidas_e_a_contraria_e_conflito(home_com_evidencia, tmp_path):
    arquivos = _pacote(home_com_evidencia, tmp_path)
    nome = _nome(arquivos, f"politicas/{WWW2}-")
    registro = json.loads(arquivos[nome])
    caminho_novo = "/legin/fed/outra-norma.html"
    local = tmp_path / "local"
    (local / "camara" / "politicas").mkdir(parents=True)
    (local / "camara" / nome).write_text(json.dumps({**registro, "decisoes": {caminho_novo: "permitido"}}), "utf-8")
    pub = ev.Publicacao(local, {nome: arquivos[nome]}, tmp_path / "stg").preparar()
    pub.publicar()
    unidas = json.loads((local / "camara" / nome).read_bytes())["decisoes"]
    assert unidas == {**registro["decisoes"], caminho_novo: "permitido"}  # a união; nenhuma decisão se perde
    conflito = tmp_path / "conflito"
    (conflito / "camara" / "politicas").mkdir(parents=True)
    contraria = {k: ("proibido" if v == "permitido" else "permitido") for k, v in registro["decisoes"].items()}
    (conflito / "camara" / nome).write_text(json.dumps({**registro, "decisoes": contraria}), "utf-8")
    with pytest.raises(ev.EvidenciaInvalida, match="conflita_com_o_home"):
        ev.Publicacao(conflito, {nome: arquivos[nome]}, tmp_path / "stg2").preparar()


# --- R2-8: a unidade seguinte nunca herda o que a anterior acumulou ----------------------------------------------------------
def _inventario_de_duas_normas(tmp_path, monkeypatch):
    rotas = rotas_da_fixture()
    for chave in ("busca_lei13874", "norma_lei13874"):
        rotas[da_fixture(chave).url] = da_fixture(chave)
    inv13874 = inventario(da_fixture("norma_lei13874"))
    for r in inv13874["recursos"]:  # os textos da 13874 não estão no dublê: a unidade termina, mas depois de acumular
        if r["admitido"] and r["url"] not in rotas:
            rotas[r["url"]] = barreira("http_404", None, 404)
    home, relogio, _ = ativar_com(tmp_path, rotas)
    vistas = []
    original = ci._gravar_unidade

    def espiar(pasta, con, portao, norma, falha):
        vistas.append((norma["number"], set(con.paginas)))
        return original(pasta, con, portao, norma, falha)

    monkeypatch.setattr(ci, "_gravar_unidade", espiar)
    ci.inventariar(home, normas_em(tmp_path, {"kind": "lei", "number": "6404", "year": 1976},
                                   {"kind": "lei", "number": "13874", "year": 2019}), tmp_path / "saida",
                   transporte=Transporte(relogio, rotas), relogio=relogio)
    return vistas


def test_r28_unidade_seguinte_nunca_herda_paginas_exclusivas_da_anterior(tmp_path, monkeypatch):
    vistas = _inventario_de_duas_normas(tmp_path, monkeypatch)
    assert [n for n, _ in vistas] == ["6404", "13874"]
    primeira, segunda = vistas[0][1], vistas[1][1]
    exclusivas = {ATUAL, ORIGINAL, LEI}  # páginas só da Lei 6404, acumuladas pela primeira unidade
    assert exclusivas <= primeira
    assert not (exclusivas & segunda)  # a segunda não traz NENHUMA delas
    assert segunda and primeira.isdisjoint(segunda - {u for u in segunda if "busca" in u})  # só o que ela mesma obteve


def test_r28_o_mutante_sem_zeragem_e_morto_exatamente_por_este_teste(tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "_zerar", lambda con: None)  # o mutante: nada é zerado entre as unidades
    vistas = _inventario_de_duas_normas(tmp_path, monkeypatch)
    segunda = vistas[1][1]
    assert {ATUAL, ORIGINAL, LEI} & segunda  # sem zerar, a segunda herda as páginas da primeira: a regressão acima falharia
