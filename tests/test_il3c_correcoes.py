"""D0–D4: regressões causais offline, apenas material de desenvolvimento.

HTML sintético inline testa classes; capturas reais são pares importados pelo
instrumento. Nenhum gabarito ou dado da reserva é usado aqui.
"""
import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from freoa_verifica import camara_instrumento as ci
from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.connectors.camara_legin import CamaraLeginConnector
from freoa_verifica.connectors.guarda import da_chamada
from freoa_verifica.parsers.camara_legin import parse_camara_legin
from freoa_verifica.parsers import isolated
from freoa_verifica.service import Verifica
from freoa_verifica.transport import Response
from tests._camara_util import RelogioFalso, Transporte, da_fixture
from tests.test_camara_0081_atribuicao_inventario_snapshot import ativar_com, normas_em, rotas_da_fixture
from tests.test_camara_legin import ATUAL, LSA
from tests.test_camara_service import acervo, servidor  # noqa: F401

FIX = Path(__file__).parent / "fixtures" / "camara_legin"


def desenvolvimento(numero):
    respostas = {}
    for p in FIX.glob(f"il3c_{numero}_*.captura.json"):
        meta = json.loads(p.read_bytes())
        body = p.with_name(p.name.replace(".captura.json", ".corpo")).read_bytes()
        assert hashlib.sha256(body).hexdigest() == meta["sha256"]
        respostas[meta["url"]] = Response(meta["url"], meta["url_final"], 200, {}, body,
                                           meta["sha256"], meta["capturado_em"], [], meta["content_type"],
                                           content_type=meta["content_type"], size=len(body))
    assert len(respostas) == 4
    return respostas


def conector(tmp_path, numero):
    r = desenvolvimento(numero)
    relogio = RelogioFalso()
    t = Transporte(relogio, r)
    return CamaraLeginConnector(home=tmp_path, transporte_offline=t, relogio=relogio), t


@pytest.mark.parametrize("path,expected", [
    ("art1", "Art. 1º Corpo.\n§ 1º Parágrafo.\nI - Inciso.\na) Alínea.\n1. Item."),
    ("art1.caput", "Art. 1º Corpo."),
    ("art1.par1", "§ 1º Parágrafo.\nI - Inciso.\na) Alínea.\n1. Item."),
    ("art1.par1.inc1", "I - Inciso.\na) Alínea.\n1. Item."),
    ("art1.par1.inc1.ali-a", "a) Alínea.\n1. Item."),
    ("art1.par1.inc1.ali-a.item1", "1. Item."),
    ("art1-A", "Art. 1º-A. Complemento.\nParágrafo único. Único."),
    ("art1-A.parunico", "Parágrafo único. Único."),
])
def test_d0_rotulo_literal_em_cada_classe_sem_mudar_corpo(path, expected):
    html = """<html><body><p>Art. 1º Corpo.</p><p>§ 1º Parágrafo.</p>
    <p>I - Inciso.</p><p>a) Alínea.</p><p>1. Item.</p><p>Art. 1º-A. Complemento.</p>
    <p>Parágrafo único. Único.</p><p>Brasília, 1 de janeiro de 2000</p></body></html>"""
    doc = parse_camara_legin(html)
    assert doc.provision(path).current_text() == expected
    red = doc.provision(path).current_redaction()
    assert doc.text[red.span[0]:red.span[1]] == expected


@pytest.mark.repositorio  # usa o normalizador congelado em scripts/, ausente da wheel
def test_d0_fachada_igual_ao_gabarito_congelado_de_desenvolvimento(acervo):  # noqa: F811
    casos = [json.loads(s) for s in (Path(__file__).parent / "porta_l" / "desenvolvimento.jsonl").read_text("utf-8").splitlines()]
    caso = next(c for c in casos if c["id"] == "L-b-001")
    out = acervo.obter_dispositivo(caso["citacao"])
    from scripts.porta_l import norm
    assert out["status"] == "encontrada"
    assert norm(out["texto"]) == norm(caso["gabarito"]["texto"])


def test_d1_inventario_alimenta_home_reabre_offline_com_captura_original(tmp_path, proibir_rede, monkeypatch):
    rotas = rotas_da_fixture()
    home, relogio, _ = ativar_com(tmp_path, rotas)
    out = ci.inventariar(home, normas_em(tmp_path), tmp_path / "saida", transporte=Transporte(relogio, rotas), relogio=relogio)
    assert out == {"resultado": "ok", "obtidas": 1, "nao_obtidas": 0, "falhas": []}
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(home=home) as svc:
        for versao in ("vigente", "publicacao_original"):
            got = svc.obter_dispositivo("art. 14 da Lei 6404/1976", versao=versao)
            assert got["status"] == "encontrada"
            assert got["texto"].startswith("Art. 14.")
            ev = svc.obter_evidencia(got["evidencia"]["capture_id"])
            assert ev["status"] == "encontrada"
            cap = svc.conn.execute("SELECT * FROM capture WHERE id=?", (got["evidencia"]["capture_id"],)).fetchone()
            original = rotas[cap["url"]]
            assert (cap["sha256"], cap["fetched_at"], cap["procedencia"]) == (original.sha256, original.fetched_at, "captura_direta")
        assert svc.conn.execute("SELECT count(*) FROM capture").fetchone()[0] == 4
    assert proibir_rede == []


def test_d1_preflight_recusa_hash_adulterado_sem_indexar(tmp_path):
    r = da_fixture("textos_atualizado_lei6404")
    con = CamaraLeginConnector()
    con.paginas[r.url] = replace(r, body=r.body + b"x")
    with pytest.raises(Unavailable, match="hash_captura_divergente"):
        ci._persistir_unidade(tmp_path / "home", con, {"kind": "lei", "number": "6404", "year": 1976})
    assert not (tmp_path / "home").exists()


def test_d1_capturas_integrais_sobrevivem_a_falha_local_do_parser(tmp_path, monkeypatch, proibir_rede):
    from freoa_verifica.store import blobs
    rotas = rotas_da_fixture()
    home, relogio, _ = ativar_com(tmp_path, rotas)
    monkeypatch.setattr(isolated, "parse_isolated", lambda profile, *a, **k: isolated._failure(profile, "importacao"))
    out = ci.inventariar(home, normas_em(tmp_path), tmp_path / "saida", transporte=Transporte(relogio, rotas), relogio=relogio)
    assert out["resultado"] == "parcial"
    assert len(out["falhas"]) == 1
    assert out["falhas"][0] == {"motivo": "falha_parser_camara", "categoria": None,
                                "fase": "persistencia_interpretacao", "bloqueio": None, "url": ATUAL,
                                "evidencia": {"url": ATUAL, "sha256": rotas[ATUAL].sha256,
                                              "causa": "importacao", "fase": "interpretacao", "perfil": "camara_legin"}}
    with Verifica(home=home) as svc:
        caps = svc.conn.execute("SELECT * FROM capture").fetchall()
        assert len(caps) == 4
        assert svc.conn.execute("SELECT count(*) FROM parsed_document").fetchone()[0] == 0
        for cap in caps:
            assert blobs.get_blob(cap["sha256"], home=home) == rotas[cap["url"]].body
            assert cap["fetched_at"] == rotas[cap["url"]].fetched_at


@pytest.mark.parametrize("causa", ["import", "processo", "tempo", "memoria", "saida"])
@pytest.mark.parametrize("formato", ["html", "pdf"])
def test_d2_falha_do_isolamento_terminal_sem_barreira_persistente(tmp_path, monkeypatch, causa, formato, proibir_rede):
    from tests._camara_util import portao
    rotas = rotas_da_fixture()
    for role in ("busca", "norma", "textos_anexo"):
        r = da_fixture(role + "_lc123")
        rotas[r.url] = r
    p, t, _, estado = portao(tmp_path / "h", rotas)
    con = CamaraLeginConnector(portao=p, home=tmp_path / "h")
    with da_chamada():
        cand = con.resolve({"kind": "lei", "number": "6404", "year": 1976} if formato == "html" else
                           {"kind": "lei_complementar", "number": "123", "year": 2006})
        resp = con.fetch(cand) if formato == "html" else con.fetch_anexo(cand)
        if causa == "processo":
            def popen(*a, **k):
                raise OSError("C:/dev/tmp/SYNTHETIC_PRIVATE criacao")
            monkeypatch.setattr(subprocess, "Popen", popen)
        else:
            class Filho:
                returncode = {"import": 77, "memoria": 3}.get(causa, 0)
            monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: Filho())
            monkeypatch.setattr(isolated, "_bounded_io", lambda *a: (
                b"invalido", b"C:/dev/tmp/SYNTHETIC_PRIVATE stderr",
                "timeout" if causa == "tempo" else None))
        with pytest.raises(Unavailable, match="falha_parser_camara") as failure:
            con.parse(resp)
        assert "SYNTHETIC_PRIVATE" not in json.dumps(ci._causa(failure.value, "interpretacao"))
        assert failure.value.categoria is None
        assert failure.value.classificacao() == {}
        assert failure.value.evidencia["perfil"] == ("camara_legin" if formato == "html" else "camara_anexo")
        assert failure.value.evidencia["causa"] == {"import": "importacao", "processo": "criacao_processo",
                                                   "tempo": "tempo", "memoria": "memoria", "saida": "protocolo"}[causa]
        antes = list(t.urls)
        with pytest.raises(Unavailable, match="falha_parser_camara"):
            p.obter(LSA)
        assert t.urls == antes
    assert estado.bloqueio_do_recurso("www2.camara.leg.br", resp.url) is None
    assert estado.bloqueio_do_host("www2.camara.leg.br", p.relogio.agora()) is None
    monkeypatch.undo()
    with da_chamada():
        doc = con.parse(resp)  # nova chamada retoma, sem reabertura registrada
        assert doc.provisions if formato == "html" else doc.text
    assert proibir_rede == []


def test_d2_conteudo_sem_perfil_continua_barreira(tmp_path, proibir_rede):
    from tests._camara_util import portao, resposta
    p, _, _, estado = portao(tmp_path / "h", {**rotas_da_fixture(), ATUAL: resposta(ATUAL, b"<html><body>sem norma</body></html>")})
    con = CamaraLeginConnector(portao=p)
    with da_chamada():
        cand = con.resolve({"kind": "lei", "number": "6404", "year": 1976})
        with pytest.raises(Unavailable, match="texto_normativo_nao_reconhecido"):
            con.parse(con.fetch(cand))
    assert estado.bloqueio_do_recurso("www2.camara.leg.br", ATUAL) is not None


def test_d2_pdf_invalido_e_conteudo_nao_falha_do_isolamento(proibir_rede):
    from freoa_verifica.connectors.base import LocalParserFailure
    with pytest.raises(Unavailable) as erro:
        isolated.parse_ou_indisponivel("camara_anexo", b"%PDF-1.7\nsem estrutura", 60)
    assert not isinstance(erro.value, LocalParserFailure)
    assert erro.value.reason == "camara_anexo_conteudo_nao_processavel"


def indexar_so_recorte(con, monkeypatch, path, conferir):
    """Parse real completo; índice de teste só do artigo consultado.

    Conserva bytes, texto integral, spans, notas, emendas, todos os problemas e
    metadados de descoberta. Evita gerar derivados quadráticos de milhares de
    dispositivos que D3/D4 não consultam, como já faz a fixture _lsa_art254a.
    A conferência do documento integral ocorre ANTES da projeção.
    """
    parse = con.parse
    def interpretar(resp):
        full = parse(resp)
        conferir(full)
        selected = [p for p in full.provisions if p.path == path or p.path.startswith(path + ".")
                    or path.startswith(p.path + ".")]
        return replace(full, provisions=selected or full.provisions[:1])
    monkeypatch.setattr(con, "parse", interpretar)


@pytest.mark.parametrize("numero,ano", [("13105", 2015), ("13709", 2018)])
def test_d3_autorreferencia_nao_substitui_raiz_e_releitura_confere(tmp_path, numero, ano, monkeypatch, proibir_rede):
    con, t = conector(tmp_path / "h", numero)
    def conferir(full):
        assert full.provision("art1") is not None
        if numero == "13105":
            assert any(i.code == "ORDER" for i in full.issues)
    indexar_so_recorte(con, monkeypatch, "art1", conferir)
    with Verifica(home=tmp_path / "h") as svc:
        monkeypatch.setattr(svc, "_get", lambda _: con)
        monkeypatch.setattr(svc, "_offline", lambda: False)
        rw = svc._capture_work(WorkKey("federal", "lei", numero, ano))
        inv = next(json.loads(b.text) for b in rw.document.editorial_blocks if b.kind == "camara_inventario")
        chain = inv["descoberta"]
        assert len(chain) == 2
        assert chain[0]["origem_url"] == chain[1]["url"]
        assert "/busca?" in chain[1]["origem_url"]
        assert any(r["url"] == chain[1]["url"] for r in inv["recursos"])  # autorreferência real
        assert any(r["classe"] == "autorreferencia" and r["destino"] == chain[1]["url"]
                   for r in con.relacoes_observadas)
        assert con.falhas_descoberta == []
        svc._revalidar_camara(rw)
        monkeypatch.setattr(svc, "_offline", lambda: True)
        antes = list(t.urls)
        got = svc.obter_dispositivo(f"art. 1º da Lei {numero}/{ano}")
        if numero == "13105":
            assert (got["status"], got["texto"], got["reason_code"]) == ("unknown", None, "ORDER")
        else:
            assert got["status"] == "encontrada" and got.get("reason_code") is None
            assert got["texto"] == (
                "Art. 1º Esta Lei dispõe sobre o tratamento de dados pessoais, inclusive nos meios digitais, "
                "por pessoa natural ou por pessoa jurídica de direito público ou privado, com o objetivo de "
                "proteger os direitos fundamentais de liberdade e de privacidade e o livre desenvolvimento "
                "da personalidade da pessoa natural.\nParágrafo único. As normas gerais contidas nesta Lei "
                "são de interesse nacional e devem ser observadas pela União, Estados, Distrito Federal e Municípios.")
        assert t.urls == antes
    assert proibir_rede == []


def test_d3_ciclo_efetivo_sem_raiz_continua_recusado(tmp_path, proibir_rede):
    con, _ = conector(tmp_path, "13709")
    cand = con.resolve({"kind": "lei", "number": "13709", "year": 2018})
    resp = con.fetch(cand)
    page = con.paginas[cand.url]
    self_link = next(r for r in con.inventarios[cand.url]["recursos"] if r["url"] == cand.url)
    con.links[cand.url] = (page, self_link["href"], self_link["rotulo"])
    with pytest.raises(Unavailable, match="ciclo_descoberta"):
        con.parse(resp)


@pytest.mark.parametrize("numero,ano,versao,path,detail", [
    ("10406", 2002, "vigente", "art421", "sequência de artigos com lacuna não explicada"),
    ("10406", 2002, "publicacao_original", "art1031", "sequência de artigos com lacuna não explicada"),
    ("13874", 2019, "publicacao_original", "art1", "citacao_alteradora_sem_fim"),
])
def test_d4_limites_documentais_permanecem_unknown(tmp_path, numero, ano, versao, path, detail, monkeypatch, proibir_rede):
    con, _ = conector(tmp_path / "h", numero)
    def conferir(full):
        assert full.title.startswith("LEI Nº")
        assert any(i.code == "TRUNCATED" and i.detail == detail for i in full.issues)
        if numero == "10406":
            assert "Art. 1.031" in full.text
            assert full.provision("art1031") is None
    indexar_so_recorte(con, monkeypatch, path, conferir)
    with Verifica(home=tmp_path / "h") as svc:
        monkeypatch.setattr(svc, "_get", lambda _: con)
        monkeypatch.setattr(svc, "_offline", lambda: False)
        rw = svc._capture_work(WorkKey("federal", "lei", numero, ano), versao=versao)
        assert rw.document.title.startswith("LEI Nº")  # identidade confirmada; não era a causa
        assert any(i.code == "TRUNCATED" and i.detail == detail for i in rw.document.issues)
        if numero == "10406":
            assert "Art. 1.031" in rw.document.text
            assert rw.document.provision("art1031") is None  # limitação de rótulo com milhar
        monkeypatch.setattr(svc, "_offline", lambda: True)
        out = svc.obter_dispositivo(work_id=rw.work_id, caminho=path, versao=versao)
        assert out["status"] == "unknown"
        assert out["texto"] is None
        assert out["reason_code"] == ("primeira_publicacao_do_dispositivo_nao_obtida" if path == "art1031" else "TRUNCATED")


def test_d4_aspas_sem_fecho_nao_liberam_texto():
    doc = parse_camara_legin('<body><p>Art. 1º Início.</p><p>Art. 2º Passa a vigorar:</p>'
                            '<p>“Art. 1º Outro texto.</p><p>Brasília, 1 de janeiro de 2000</p></body>')
    assert doc.quarantined
    assert any(i.detail == "citacao_alteradora_sem_fim" for i in doc.issues)


@pytest.mark.parametrize("mutacao", [None, "corpo", "sha256", "status", "mime", "fetched_at", "origem"])
def test_instrumento_importa_recibo_0081_sem_fabricar_metadados(tmp_path, mutacao, proibir_rede):
    from freoa_verifica.captura import importar_fixture_offline
    pares = {}
    for role in ("busca", "norma", "original"):
        p = FIX / f"il3c_10406_{role}.captura.json"
        meta = json.loads(p.read_bytes())
        corpo = tmp_path / meta["arquivo"]
        corpo.write_bytes(p.with_name(p.name.replace(".captura.json", ".corpo")).read_bytes())
        recibo = corpo.with_suffix(".recibo.json")
        recibo.write_text(json.dumps(meta["importacao_offline"]["recibo_original"]), encoding="utf-8")
        pares[role] = (recibo, corpo)
    recibo, corpo = pares["original"]
    if mutacao == "corpo":
        corpo.write_bytes(corpo.read_bytes() + b"x")
    elif mutacao:
        meta = json.loads(recibo.read_bytes())
        meta[mutacao] = {"sha256": "0" * 64, "status": 403, "mime": "application/pdf",
                         "fetched_at": "2026-11-09", "origem": {"url": "adulterada"}}[mutacao]
        recibo.write_text(json.dumps(meta), encoding="utf-8")
    destino = tmp_path / "fixtures"
    destino.mkdir()
    (destino / "FIXTURES.json").write_text("{}")
    if mutacao:
        with pytest.raises(ValueError):
            importar_fixture_offline(recibo, corpo, "diagnostico", destino, pares["norma"][0])
        assert (destino / "FIXTURES.json").read_text() == "{}"
    else:
        reg = importar_fixture_offline(recibo, corpo, "diagnostico", destino, pares["norma"][0])
        assert reg.capturado_em == json.loads(recibo.read_bytes())["fetched_at"]
        assert reg.user_agent == ""
        assert reg.versao == "nao_registrada"
        assert reg.importacao_offline["recibo_original"] == json.loads(recibo.read_bytes())
        assert reg.importacao_offline["recibo_sha256"] == hashlib.sha256(recibo.read_bytes()).hexdigest()
        assert importar_fixture_offline(recibo, corpo, "diagnostico", destino, pares["norma"][0]).meta() == reg.meta()
