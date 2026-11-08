"""Contraexemplos r1: capturas intactas, replay offline e saída das três fachadas."""
import hashlib
import json

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Unavailable
from freoa_verifica.parsers.model import Issue
from freoa_verifica.service import Verifica
from freoa_verifica.verify import SourceUnavailable
from tests.contrato import harness
from tests.test_camara_legin import servidor, response  # noqa: F401


def _conteudo(valor):
    """Só retira o envelope público de dados, preservando todo o texto interno."""
    from freoa_verifica.sanitizacao import DOC_OPEN, DOC_CLOSE
    if isinstance(valor, str) and valor.startswith(DOC_OPEN + "\n") and valor.endswith("\n" + DOC_CLOSE):
        return valor[len(DOC_OPEN) + 1:-len(DOC_CLOSE) - 1]
    if isinstance(valor, dict):
        return {k: _conteudo(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_conteudo(v) for v in valor]
    return valor


@pytest.fixture(params=["python", "rest", "mcp"])
def chamar(request, monkeypatch):
    def call(svc, ferramenta, **args):
        if request.param == "python":
            return harness.chamar_python(svc, ferramenta, args)
        if request.param == "mcp":
            pytest.importorskip("mcp")
            from freoa_verifica import mcp_server as ms
            monkeypatch.setitem(ms._servicos, str(svc.home), svc)
            return harness.chamar_mcp(ms.create_mcp(home=str(svc.home), registro=svc.registro), ferramenta, args)
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from freoa_verifica.rest import create_app
        with TestClient(create_app(home=str(svc.home), token=None, registro=svc.registro),
                        client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as client:
            return harness.chamar_rest(client, ferramenta, args)
    return call


@pytest.fixture
def acervo_r1(tmp_path, servidor, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(home=tmp_path / "home", registro="completo") as svc:
        for kind, number, year in [("lei", "6404", 1976), ("lei_complementar", "123", 2006),
                                   ("lei", "13874", 2019)]:
            svc._capture_work(WorkKey("federal", kind, number, year))
        svc._capture_work(WorkKey("federal", "lei", "6404", 1976), versao="publicacao_original")
        monkeypatch.setenv("FV_OFFLINE", "1")
        yield svc


def test_f1_notas_reais_nao_sao_texto_normativo(acervo_r1, chamar):
    casos = [
        ("art. 161, parágrafo 6 da Lei 6404/1976",
         "(Primitivo § 5º renumerado pela Lei nº 10.303, de 31/10/2001)"),
        ("art. 143 da Lei 6404/1976", "em vigor 90 dias após a publicação"),
        ("art. 1, parágrafo 3 da Lei Complementar 123/2006",
         "(Parágrafo acrescido pela Lei Complementar nº 147, de 7/8/2014)"),
        ("art. 63-B da Lei Complementar 123/2006",
         "(VETADO na Lei Complementar nº 155, de 27/10/2016)"),
    ]
    for citacao, trecho in casos:
        out = chamar(acervo_r1, "verificar_citacao", citacao=citacao, trecho=trecho)
        assert out["text"]["status"] != "verified", (citacao, out)
        obtido = chamar(acervo_r1, "obter_dispositivo", citacao=citacao)
        assert trecho not in (obtido.get("texto") or "")
    vetado = chamar(acervo_r1, "obter_dispositivo", citacao=casos[-1][0])
    assert vetado["status"] == "unknown" and vetado["texto"] is None
    lc = acervo_r1._resolve(WorkKey("federal", "lei_complementar", "123", 2006)).document
    # Lista externa do parecer r1; os corpos de captura permanecem intactos.
    stubs = ["art3.par17", "art3.par18", "art4.par5", "art18.par5-L", "art18.par27",
             "art18-A.par23", "art24.par2", "art34.par2", "art34.par4", "art49-B",
             "art56.par8", "art58.par3", "art60-C", "art61-E.par1", "art61-E.par2",
             "art61-E.par6", "art63-A", "art63-B", "art63-C", "art63-D", "art63-E",
             "art65-A.par12", "art75-B"]
    for path in stubs:
        prov = lc.provision(path)
        assert any(a.kind == "veto" and a.target_path == path for a in prov.redactions[0].annotations), path
        out = chamar(acervo_r1, "obter_dispositivo", work_id=acervo_r1._resolve(
            WorkKey("federal", "lei_complementar", "123", 2006)).work_id, caminho=path)
        assert out["status"] == "unknown" and out["texto"] is None, (path, out)


def test_f1_guarda_comum_causal_antes_de_identidade(verifica_populada, chamar, monkeypatch):
    svc, rw, doc = verifica_populada
    monkeypatch.setattr(Verifica, "_resolve", lambda *a, **kw: rw)
    for code in ["NOTA_NAO_RECONHECIDA", "DUPLICATE_CURRENT", "UNCERTAIN_CONTINUATION",
                 "VETO", "MARGEM_ADJACENTE", "SCOPE_COLLISION", "REVOGACAO_PARCIAL"]:
        # Sintético: impedimento no filho de um agregado com texto coincidente.
        monkeypatch.setattr(doc, "issues", [Issue(
            code, "art254-A.par1", "gerador r1: impedimento de descendente", "provision")])
        out = chamar(svc, "verificar_citacao", citacao="art. 254-A da Lei 6404/1976",
                     trecho="A alienação, direta ou indireta, do controle de companhia aberta")
        assert out["identity"]["status"] != "verified", (code, out)
        assert out["text"]["status"] == "unknown", (code, out)
        assert out["identity"]["reason_code"] == code


def test_f1_duplicidade_real_do_agregado_original(acervo_r1, chamar):
    out = chamar(acervo_r1, "obter_dispositivo", citacao="art. 49 da Lei 6404/1976",
                 versao="publicacao_original")
    assert out["status"] == "unknown" and out["texto"] is None
    assert any(i["code"] == "DUPLICATE_CURRENT" for i in out["pendencias"])


def test_f2_lei_alteradora_nao_possui_inciso_do_codigo_civil(acervo_r1, chamar):
    citacao = "art. 7, parágrafo 3, inciso I da Lei 13874/2019"
    out = chamar(acervo_r1, "verificar_citacao", citacao=citacao,
                 trecho="a limitação da responsabilidade de cada investidor ao valor de suas cotas;")
    assert out["identity"]["status"] != "verified"
    assert out["text"]["status"] != "verified"
    out = chamar(acervo_r1, "obter_dispositivo", citacao=citacao)
    assert out["status"] != "encontrada" and out["texto"] is None
    rw = acervo_r1._resolve(WorkKey("federal", "lei", "13874", 2019))
    assert not any(p.path.startswith("art7.") and p.path != "art7.caput" for p in rw.document.provisions)
    assert any("Art. 1.368-D." in q.text and "CAPÍTULO X" in q.text for q in rw.document.amendments)


def test_f2_escopo_incerto_bloqueia_saida(verifica_populada, chamar, monkeypatch):
    from tests.test_camara_legin import sintetico
    svc, rw, _ = verifica_populada
    rw.document = sintetico('<p>Art. 1º A Lei nº 2 passa a vigorar com as seguintes alterações:</p>'
                            '<p>"CAPÍTULO X</p><p>Art. 1.368-D. Texto estrangeiro.</p>'
                            '<p>§ 3º Texto estrangeiro ainda sem fecho.</p>')
    rw.quarantined = rw.document.quarantined
    monkeypatch.setattr(Verifica, "_resolve", lambda *a, **kw: rw)
    out = chamar(svc, "verificar_citacao", citacao="art. 1 da Lei 1/2001", trecho="Texto estrangeiro")
    assert out["identity"]["status"] == "unknown"
    assert out["text"]["status"] == "unknown"
    assert {p.path for p in rw.document.provisions} == {"art1", "art1.caput"}


def test_f3_revogacao_parcial_preserva_alvo(acervo_r1, chamar):
    out = chamar(acervo_r1, "obter_dispositivo", citacao="art. 110 da Lei 6404/1976")
    assert out["vigencia"]["status"] == "unknown"
    assert out["reason_code"] == "REVOGACAO_PARCIAL"
    rw = acervo_r1._resolve(WorkKey("federal", "lei", "6404", 1976))
    assert not any(a.kind == "revogado" for a in rw.document.provision("art110").redactions[0].annotations)
    revoked = [a for p in rw.document.provisions if p.path.startswith("art110.")
               for r in p.redactions for a in r.annotations if a.kind == "revogado"]
    assert revoked and all(a.target_path.startswith("art110.") for a in revoked)
    # Inventário externo do parecer: o mesmo erro em artigos e parágrafos,
    # nas três famílias capturadas, não apenas no contraexemplo do art. 110.
    agregados = [
        ("lei", "6404", 1976, "art62 art110 art140 art177 art177.par2 art179 art182 "
         "art182.par1 art183 art187 art188 art255 art293"),
        ("lei_complementar", "123", 2006, "art4 art17 art17.par1 art18 art18.par5 "
         "art18.par5-B art18.par5-C art18.par5-D art21 art26 art26.par1 art29"),
        ("lei", "13874", 2019, "art3"),
    ]
    for kind, number, year, paths in agregados:
        rw = acervo_r1._resolve(WorkKey("federal", kind, number, year))
        for path in paths.split():
            prov = rw.document.provision(path)
            assert not any(a.kind == "revogado" for a in prov.redactions[0].annotations), path
            out = chamar(acervo_r1, "obter_dispositivo", work_id=rw.work_id, caminho=path)
            assert out["status"] == "unknown" and out["texto"] is None, (path, out)
            assert out["vigencia"]["status"] == "unknown", (path, out)
        for prov in rw.document.provisions:
            for red in prov.redactions:
                assert all(a.target_path == prov.path or (
                    a.target_path is None and any(i.code == "ALVO_NOTA_INCERTO" and i.path == prov.path
                                                  for i in rw.document.issues))
                    for a in red.annotations), prov.path


def test_modelo_anterior_nao_reutiliza_falso_positivo(acervo_r1, chamar, monkeypatch):
    rw = acervo_r1._resolve(WorkKey("federal", "lei", "6404", 1976))
    rw.document.parser_version = "camara-legin-1"
    monkeypatch.setattr(Verifica, "_selecionar_camara", lambda *a, **kw: rw)
    out = chamar(acervo_r1, "obter_dispositivo", citacao="art. 110 da Lei 6404/1976")
    assert out["status"] == "unavailable"
    assert out["motivo"] == "camara_modelo_requer_reprocessamento"


def test_f4_contrato_consumidor_sem_alterar_esquema(acervo_r1, chamar):
    from tests.contrato.test_contrato import validar_resposta_consumidor, _spec, DEPRECATED
    for versao in ["vigente", "publicacao_original"]:
        for data in [None, "2025-01-01", "2099-01-01"]:
            rw = acervo_r1._resolve(WorkKey("federal", "lei", "6404", 1976), versao=versao)
            comum = acervo_r1._resposta_dispositivo(rw, "art289", data)
            out = chamar(acervo_r1, "obter_dispositivo", citacao="art. 289 da Lei 6404/1976",
                         versao=versao, **({"data": data} if data else {}))
            assert not validar_resposta_consumidor("obter_dispositivo", _spec("obter_dispositivo"), out, DEPRECATED)
            assert out["situacao_obra"] is None
            assert "regras" in out["vigencia"] and "intervalo" in out["vigencia"]
            assert out["redacoes_anteriores"] == []
            assert out["texto_atual"] is None or data
            for campo in ["texto", "texto_atual", "truncado", "redacoes_anteriores",
                          "redacao_anterior_ausente_na_fonte", "situacao_obra"]:
                assert _conteudo(out[campo]) == comum[campo], (versao, data, campo, out)
            for campo in ["regras", "intervalo"]:
                assert out["vigencia"][campo] == comum["vigencia"][campo]


def test_f5_pendencia_bloqueia_antes_do_transporte(tmp_path, chamar, proibir_rede, monkeypatch):
    calls = []
    monkeypatch.setattr("freoa_verifica.connectors.httputil.transport_fetch", lambda *a, **k: calls.append(a))
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(home=tmp_path / "bloqueio") as svc:
        out = chamar(svc, "buscar_legislacao", q="Lei 6404/1976", fonte="camara_legin")
        assert out["fontes"]["camara_legin"]["motivo"] == "ativacao_ao_vivo_pendente"
        out = chamar(svc, "obter_dispositivo", citacao="art. 1 da Lei 6404/1976")
        assert out["status"] == "indisponivel"
        assert "ativacao_ao_vivo_pendente" in out["motivo"]
    assert calls == [] and proibir_rede == []


def test_f5_planalto_apenas_acervo_em_todas_as_buscas(tmp_path, chamar, monkeypatch, proibir_rede):
    from freoa_verifica.connectors.planalto import PlanaltoConnector
    def proibido(*a, **kw):
        pytest.fail("Planalto não pode iniciar nova captura")
    monkeypatch.setattr(PlanaltoConnector, "search", proibido)
    monkeypatch.setattr(PlanaltoConnector, "fetch", proibido)
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(home=tmp_path / "legado") as svc:
        # Demais fontes bloqueadas localmente: a prova não depende de rede.
        original_get = Verifica._get
        def get(self, cid):
            if cid != "planalto":
                raise Unavailable("fixture_sem_fonte")
            return original_get(self, cid)
        monkeypatch.setattr(Verifica, "_get", get)
        for fonte in [None, "planalto"]:
            out = chamar(svc, "buscar_legislacao", q="Lei 6404/1976", **({"fonte": fonte} if fonte else {}))
            assert out["fontes"]["planalto"]["motivo"] == "acervo_legado_sem_nova_captura"
    assert proibir_rede == []


def test_f5_semente_e_alteradores_nao_capturam_legado(verifica_populada, monkeypatch, proibir_rede):
    from freoa_verifica.parsers.model import Annotation
    from freoa_verifica.semente import SyncState

    svc, rw, doc = verifica_populada
    monkeypatch.setenv("FV_OFFLINE", "0")
    corpus = {"planalto": [{"tipo": "LEI", "numero": "6404", "ano": 1976}],
              "leis_principais_alteradores": [{"tipo": "LEI", "numero": "6404", "ano": 1976}]}
    monkeypatch.setattr("freoa_verifica.semente.load_corpus", lambda: corpus)

    def proibido(*args, **kwargs):
        pytest.fail("semente não pode iniciar consulta no legado")

    monkeypatch.setattr(svc, "_get", proibido)
    sincronizado = svc.sincronizar(fontes=["planalto"])
    assert sincronizado["fontes"][0]["status"] == "indisponivel"
    assert sincronizado["fontes"][0]["motivo"] == "acervo_legado_sem_nova_captura"
    out = svc.sincronizar(semente=True, fontes=["planalto"], max_itens=1)
    assert out["fontes"][0]["motivos"] == {"acervo_legado_sem_nova_captura": 1}
    state = SyncState(svc.conn)
    state.set("planalto", "LEI:6404:1976", "parseado")
    monkeypatch.setattr(doc.provisions[0].redactions[-1], "annotations", [
        Annotation("redacao_dada", "nota sintética F5", "Lei 7.000, de 2000", act_date="2000")])
    monkeypatch.setattr(svc, "_resolve", lambda *args, **kwargs: rw)
    svc.sincronizar(semente=True, fontes=["planalto"], max_itens=1)
    for fonte in ("alterador_data", "alterador"):
        row = state.get(fonte, "LEI:7000:2000")
        assert row["status"] == "indisponivel"
        assert row["motivo"] == "acervo_legado_sem_nova_captura"
    assert proibir_rede == []


def test_f5_diagnostico_nao_captura_legado(verifica_populada, monkeypatch, proibir_rede):
    svc, _, _ = verifica_populada
    monkeypatch.setattr("freoa_verifica.service.registry", lambda: {"planalto": object()})

    def proibido(*args, **kwargs):
        pytest.fail("diagnóstico não pode iniciar consulta no legado")

    monkeypatch.setattr(svc, "_get", proibido)
    out = svc.doctor()
    fonte = next(c for c in out["verificacoes"] if c["nome"] == "fonte:planalto")
    assert fonte["status"] == "falha" and fonte["detalhe"] == "acervo_legado_sem_nova_captura"
    assert proibir_rede == []


@pytest.mark.repositorio
def test_f5_instrumento_nao_captura_legado(tmp_path, monkeypatch, proibir_rede, capsys):
    from freoa_verifica import captura

    def proibido(*args, **kwargs):
        pytest.fail("instrumento não pode iniciar captura do legado")

    monkeypatch.setattr(captura, "_buscar", proibido)
    with pytest.raises(Unavailable, match="acervo_legado_sem_nova_captura"):
        captura.capturar(conector="planalto", url="https://www.planalto.gov.br/ccivil_03/leis/l6404.htm",
                         destino=tmp_path / "captura", sonda=False)
    from scripts import capturar_fixture as cli
    assert cli.main(["--conector", "planalto", "--sonda", "--saida", str(tmp_path / "captura"),
                     "--url", "https://www.planalto.gov.br/ccivil_03/leis/l6404.htm"]) == 1
    assert capsys.readouterr().err.strip() == "unavailable(acervo_legado_sem_nova_captura)"
    assert proibir_rede == []


@pytest.mark.parametrize("politica", ["completo", "sem_conteudo"])
def test_f6_falha_tipificada_por_citacao_e_work_id(verifica_populada, chamar, monkeypatch, politica):
    svc, rw, _ = verifica_populada
    svc.registro = politica
    consultadas = [{"fonte": "camara_legin", "resultado": "indisponivel", "motivo": "http_403",
                    "categoria": "recusa_identificado", "evidencia_indisponibilidade":
                    {"url": "https://www.camara.leg.br/robots.txt", "status": 403}}]
    def falhar(*a, **kw):
        raise SourceUnavailable("camara_legin:http_403", consultadas)
    monkeypatch.setattr(Verifica, "_resolve", falhar)
    for args in [{"citacao": "art. 1 da Lei 6404/1976"}, {"work_id": rw.work_id, "caminho": "art1", "fonte": "camara_legin"}]:
        out = chamar(svc, "obter_dispositivo", **args)
        assert out["status"] == "indisponivel"
        assert out["fontes_consultadas"] == consultadas
        row = svc.conn.execute("SELECT result_json FROM run WHERE id=?", (out["run_id"],)).fetchone()
        persisted = json.loads(row[0])
        record = chamar(svc, "obter_registro", run_id=out["run_id"])
        assert record["integridade"]["confere"] is True
        if politica == "completo":
            assert persisted["fontes_consultadas"] == consultadas
            assert record["estado"]["fontes_consultadas"] == consultadas
        else:
            from freoa_verifica.registro import hmac_entrada
            assert persisted["fontes_consultadas_sha256"] == hmac_entrada(
                svc.conn, "fontes_consultadas", json.dumps(consultadas, ensure_ascii=False, sort_keys=True))
            assert "fontes_consultadas" not in persisted
            assert "fontes_consultadas" not in record["estado"]
            # sem_conteudo conserva dimensões e códigos de decisão (contrato C5),
            # mas a lista estruturada e a URL ficam somente no compromisso HMAC.
            assert persisted["identity"]["reason_code"] == out["motivo"]
            assert persisted["temporal"]["reason_code"] == out["motivo"]
            assert "camara.leg.br" not in row[0]


def test_f6_sem_historico_preserva_omissao_antiga(verifica_populada, chamar, monkeypatch):
    svc, rw, _ = verifica_populada

    def falhar(*args, **kwargs):
        raise SourceUnavailable("COBERTURA")

    monkeypatch.setattr(Verifica, "_resolve", falhar)
    for args in [{"citacao": "art. 1 da Lei 6404/1976"},
                 {"work_id": rw.work_id, "caminho": "art1", "fonte": "camara_legin"}]:
        out = chamar(svc, "obter_dispositivo", **args)
        assert out["status"] == "indisponivel" and out["motivo"] == "COBERTURA"
        assert "fontes_consultadas" not in out
        row = svc.conn.execute("SELECT result_json FROM run WHERE id=?", (out["run_id"],)).fetchone()
        persisted = json.loads(row[0])
        assert "fontes_consultadas" not in persisted
        assert "fontes_consultadas_sha256" not in persisted


def test_f7_fixture_atinge_fronteira_e_nao_tenta_conexao(tmp_path, planalto_offline, proibir_rede, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(home=tmp_path / "replay") as svc:
        rw = svc._capture_work(WorkKey("federal", "lei", "6404", 1976))
        assert rw.source_id == "camara_legin"
        assert rw.sha256 == response("textos_atualizado_lei6404").sha256
        assert svc._get("camara_legin").paginas
    assert proibir_rede == []


def test_f8_busca_ate_persistencia_e_reinicio(tmp_path, servidor, chamar, monkeypatch, proibir_rede):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    home = tmp_path / "busca"
    with Verifica(home=home) as svc:
        out = chamar(svc, "buscar_legislacao", q="Lei 6404/1976", fonte="camara_legin")
        item = out["itens"][0]
        assert item["capture_id"] and item["work_id"], out
        # 0080 §4.4: o robots deixou de ser uma linha da tabela `capture` (antes 2 das 5 linhas) e passou a ser política
        # persistida por host, com bytes nomeados pelo hash e recibo, em `camara/`. As 3 capturas de conteúdo (busca,
        # página da norma, texto atualizado) permanecem; a evidência do robots é exigida AQUI, nos dois hosts.
        assert svc.conn.execute("SELECT count(*) FROM capture WHERE source_id='camara_legin'").fetchone()[0] == 3
        for host in ("www.camara.leg.br", "www2.camara.leg.br"):
            recibo = json.loads((home / "camara" / f"robots-{host}.json").read_bytes())
            corpo = (home / "camara" / f"robots-{host}-{recibo['sha256']}.txt").read_bytes()
            assert hashlib.sha256(corpo).hexdigest() == recibo["sha256"] and recibo["status"] == 200
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(home=home) as reopened:
        out = chamar(reopened, "obter_dispositivo", citacao="art. 1, caput da Lei 6404/1976")
        assert out["status"] == "encontrada", out
        assert _conteudo(out["texto"]).startswith("A companhia ou sociedade anônima")
        assert out["evidencia"]["sha256"] == response("textos_atualizado_lei6404").sha256
    assert proibir_rede == []
