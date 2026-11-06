"""C9/C11/C12/C15: integração em banco local, capturas oficiais e guarda final."""
import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.service import Verifica
from tests.test_camara_legin import servidor  # noqa: F401


@pytest.fixture
def acervo(tmp_path, servidor, monkeypatch):
    svc = Verifica(home=tmp_path / "home")
    monkeypatch.setattr(svc, "_offline", lambda: False)
    key = WorkKey("federal", "lei", "6404", 1976)
    current = svc._capture_work(key)
    original = svc._capture_work(key, versao="publicacao_original")
    assert current.capture_id != original.capture_id
    monkeypatch.setattr(svc, "_offline", lambda: True)
    yield svc
    svc.close()


def test_c9_selecao_coexiste_reinicio(acervo):
    current = acervo.obter_dispositivo("art. 289 da Lei 6404/1976")
    original = acervo.obter_dispositivo("art. 289 da Lei 6404/1976", versao="publicacao_original")
    assert current["status"] == original["status"] == "encontrada"
    assert current["versao"] == "vigente"
    assert current["texto"].startswith("As publicações ordenadas por esta Lei obedecerão às seguintes condições:")
    assert original["texto"].startswith("As publicações ordenadas pela presente Lei serão feitas no órgão oficial")
    assert original["vigencia"]["status"] == "unknown"
    assert original["vigencia"]["reason_code"] == "publicacao_nao_prova_aplicabilidade"
    assert original["evidencia"]["natureza_texto"] == "publicacao_original"
    assert current["evidencia"]["natureza_texto"] == "consolidacao_oficial"
    assert current["evidencia"]["acervo_ate"] is None
    home = acervo.home
    acervo.close()
    reopened = Verifica(home=home)
    try:
        for version, expected in [("vigente", current), ("publicacao_original", original)]:
            out = reopened.obter_dispositivo("art. 289 da Lei 6404/1976", versao=version)
            assert out["texto"] == expected["texto"]
            assert out["evidencia"] == expected["evidencia"]
    finally:
        reopened.close()


def test_c9_original_254a_e_invalida(acervo):
    out = acervo.obter_dispositivo("art. 254-A da Lei 6404/1976", versao="publicacao_original")
    assert out["status"] == "unknown"
    assert out["reason_code"] == "primeira_publicacao_do_dispositivo_nao_obtida"
    assert out["texto"] is None
    assert acervo.obter_dispositivo("art. 289 da Lei 6404/1976", versao="inventada")["status"] == "formato_invalido"


@pytest.mark.parametrize("trecho,coincide", [
    ("As publicações ordenadas por esta Lei", True),
    ("as publicações ordenadas por esta Lei", False),
    ("As publicações ordenadas por esta lei", False),
    ("As publicações ordenadas por esta Lei obedecerão às seguintes condições;", False),
])
def test_c8_comparacao_normalizada_preserva_caixa_e_pontuacao(acervo, trecho, coincide):
    out = acervo.verificar_citacao("art. 289 da Lei 6404/1976", trecho=trecho,
                                   modo="normalizado", data="2025-01-01")
    assert (out["correspondencia_textual"]["resultado"] == "coincide") is coincide
    assert out["text"]["status"] != "verified"


def test_c8_normalizacao_il1_ancora_sem_relaxar_comparador_legado():
    from freoa_verifica.textcmp import compare
    original = "Art. 1º — ‘Texto’, 12."
    out = compare("1o — 'Texto', 12.", original, "camara_il1", exact_only=True)
    assert out.status == "match"
    assert original[out.start:out.end] == "1º — ‘Texto’, 12."
    for changed in ["1o - 'Texto', 12.", "1o — 'texto', 12.", "1o — 'Texto', 13.", "1o — 'Texto'; 12."]:
        assert compare(changed, original, "camara_il1", exact_only=True).status == "no_match"
    assert compare("texto", "Texto", "normalizado").status == "match"


@pytest.mark.parametrize("date", ["1990-01-01", "2025-01-01", "2099-01-01"])
def test_c11_c12_abstencao_final_e_recibo(acervo, date):
    for version in ["vigente", "publicacao_original"]:
        out = acervo.obter_dispositivo("art. 289 da Lei 6404/1976", data=date, versao=version)
        assert out["vigencia"]["status"] == "unknown"
        assert out["vigencia"]["reason_code"] == "sem_versao_oficial_na_data"
        assert out["fundamento_temporal"] is None
        assert out["cadeia_completa"] is False
        assert out["pendencias_temporais"]
        assert out["cadeia_alteracoes"]
        assert all(c["texto"] is None and c["publicacao"]["data"] is None for c in out["cadeia_alteracoes"])
    check = acervo.verificar_citacao("art. 289 da Lei 6404/1976", trecho="As publicações ordenadas por esta Lei", data=date)
    assert check["temporal"]["status"] == "unknown"
    assert check["temporal"]["reason_code"] == "sem_versao_oficial_na_data"
    assert check["text"]["status"] != "verified"
    assert check["fundamento_temporal"] is None
    assert check["cadeia_completa"] is False
    record = acervo.obter_registro(check["run_id"])
    assert record["integridade"]["confere"] is True


def test_c17_campos_em_saida_antecipada(acervo):
    out = acervo.obter_dispositivo("???")
    for field in ("fundamento_temporal", "correspondencia_textual", "ultima_versao_oficial_anterior",
                  "cadeia_alteracoes", "cadeia_completa", "pendencias_temporais", "versao"):
        assert field in out


def test_c1_planalto_legado_e_camara_sem_escolha_silenciosa(acervo, _lsa_art254a):
    body, doc, entry = _lsa_art254a
    acervo.indexar_obra(source_id="planalto", work_key=WorkKey("federal", "lei", "6404", 1976),
                       document=doc, body=body, url=entry["url"], fetched_at=entry["capturado_em"],
                       work_date="1976-12-15", content_type="text/html; charset=windows-1252")
    out = acervo.obter_dispositivo("art. 254-A da Lei 6404/1976")
    assert out["status"] == "ambigua"
    camara = acervo.obter_dispositivo("art. 254-A da Lei 6404/1976", fonte="camara_legin")
    planalto = acervo.obter_dispositivo("art. 254-A da Lei 6404/1976", fonte="planalto")
    assert "camara.leg.br" in camara["evidencia"]["url"]
    assert camara["fontes_consultadas"][0]["fonte"] == "camara_legin"
    assert "planalto.gov.br" in planalto["evidencia"]["url"]
    assert planalto["evidencia"]["acervo_ate"] is not None
    assert acervo.obter_dispositivo(work_id=camara["work_id"], caminho="art254-A")["status"] == "ambigua"


def test_c11_c12_verificar_texto_embutido(acervo):
    out = acervo.verificar_texto('Conforme art. 289 da Lei 6404/1976, "As publicações ordenadas por esta Lei".', data="2025-01-01")
    assert out["citacoes"]
    for item in out["citacoes"]:
        assert item["verificacao"]["temporal"]["status"] == "unknown"
        assert item["verificacao"]["temporal"]["reason_code"] == "sem_versao_oficial_na_data"
        assert item["cadeia_completa"] is False
        assert item["pendencias_temporais"]
        assert item["fundamento_temporal"] is None


@pytest.mark.parametrize("adaptador", ["rest", "mcp"])
def test_c9_c12_fachadas_com_versao_e_data(acervo, monkeypatch, adaptador):
    from tests.contrato import harness
    args = {"citacao": "art. 289 da Lei 6404/1976", "versao": "publicacao_original", "data": "2025-01-01"}
    if adaptador == "mcp":
        pytest.importorskip("mcp")
        from freoa_verifica import mcp_server as ms
        monkeypatch.setitem(ms._servicos, str(acervo.home), acervo)
        mcp = ms.create_mcp(home=str(acervo.home))
        out = harness.chamar_mcp(mcp, "obter_dispositivo", args)
    else:
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient
        from freoa_verifica.rest import create_app
        app = create_app(home=str(acervo.home), token=None)
        with TestClient(app, client=("127.0.0.1", 50000), base_url="http://127.0.0.1") as client:
            out = client.get("/v1/dispositivos", params=args).json()
    assert out["versao"] == "publicacao_original"
    assert out["vigencia"]["reason_code"] == "sem_versao_oficial_na_data"
    assert out["fundamento_temporal"] is None
    assert out["cadeia_completa"] is False


def test_c1_c4_alternativas_sao_ambiguidade_sem_escolha(tmp_path, monkeypatch):
    from freoa_verifica.connectors.base import AmbiguousCandidates, Candidate
    class Fonte:
        def resolve(self, key):
            raise AmbiguousCandidates([
                Candidate("camara_legin", "id1", "Lei 6404/1976; recurso A"),
                Candidate("camara_legin", "id2", "Lei 6404/1976; recurso B"),
            ])
    with Verifica(home=tmp_path / "ambigua") as svc:
        monkeypatch.setattr(svc, "_offline", lambda: False)
        svc._connectors["camara_legin"] = Fonte()
        for method in (svc.resolver_citacao, svc.obter_dispositivo):
            out = method("art. 1º da Lei 6404/1976")
            assert out["status"] == "ambigua"
            assert [c["key"] for c in out["candidatos"]] == ["id1", "id2"]
        check = svc.verificar_citacao("art. 1º da Lei 6404/1976", data="2025-01-01")
        assert check["identity"]["status"] == "ambiguous"
        assert check["text"]["status"] == "not_assessed"
        assert check["fundamento_temporal"] is None


def test_c10_c11_c12_material_real_persistido_sem_confirmar_d(acervo, monkeypatch):
    con = acervo._connectors["camara_legin"]
    original_capture = con.capturar_relacoes
    def janela_do_lote(candidate):
        inv = con.inventarios[candidate.url]
        con.inventarios[candidate.url] = {**inv, "recursos": [r for r in inv["recursos"] if r["acao"] and
            ("lei-13874-" in r["url"] or "medidaprovisoria-881-" in r["url"])]}
        return original_capture(candidate)
    monkeypatch.setattr(con, "capturar_relacoes", janela_do_lote)
    monkeypatch.setattr(acervo, "_offline", lambda: False)
    acervo.registro = "completo"
    out = acervo.verificar_citacao("art. 289 da Lei 6404/1976", data="2025-01-01")
    assert out["temporal"]["status"] == "unknown"
    assert out["temporal"]["reason_code"] == "sem_versao_oficial_na_data"
    assert out["cadeia_completa"] is False and out["fundamento_temporal"] is None
    law = next(c for c in out["cadeia_alteracoes"] if c["ato"]["numero"] == "13874")
    assert law["publicacao"]["data"] == "2019-09-20"
    assert "Fica instituída a Declaração de Direitos de Liberdade Econômica" in law["texto"]
    assert law["evidencia"]["sha256"] == "4fd5ddbc75e7dc56ab3c2d53c7abdcbb3eee46c894e18b5a3d07041e7cd244c3"
    assert law["evidencia"]["source_kind"] == "lei"
    assert law["evidencia"]["natureza_texto"] == "publicacao_original"
    mp = next(c for c in out["cadeia_alteracoes"] if c["ato"]["numero"] == "881")
    assert mp["ato"]["especie"] == "medida_provisoria"
    assert mp["texto"] is None and mp["evidencia"] is None
    record = acervo.obter_registro(out["run_id"])
    assert record["integridade"]["confere"] is True
    assert any(e["capture_id"] == law["evidencia"]["capture_id"] for e in record["evidencias"])
    assert out["ultima_versao_oficial_anterior"]["data"] == "1976-12-17"
    monkeypatch.setattr(acervo, "_offline", lambda: True)
    again = acervo.verificar_citacao("art. 289 da Lei 6404/1976", data="2025-01-01")
    replay = next(c for c in again["cadeia_alteracoes"] if c["ato"]["numero"] == "13874")
    assert replay["texto"] == law["texto"]
    assert replay["evidencia"] == law["evidencia"]


@pytest.mark.parametrize("politica", ["completo", "sem_conteudo"])
def test_c12_recibo_obtencao_compromete_versao_e_evidencias(acervo, politica, monkeypatch):
    import json
    from freoa_verifica import registro
    if politica == "sem_conteudo":
        original = registro.hmac_entrada
        def hash_com_numero(conn, campo, valor, **kwargs):
            digest = original(conn, campo, valor, **kwargs)
            # Contraexemplo causal do falso alarme da CI: dígitos também ocorrem em HMAC.
            return "6404" + digest[4:] if campo == "citacao" else digest
        monkeypatch.setattr(registro, "hmac_entrada", hash_com_numero)
    acervo.registro = politica
    out = acervo.obter_dispositivo("art. 289 da Lei 6404/1976", data="2025-01-01", versao="publicacao_original")
    evidence = [{k: out["evidencia"][k] for k in ("capture_id", "sha256", "url")}]
    record = acervo.obter_registro(out["run_id"], evidencias=evidence)
    assert record["integridade"]["confere"] is True
    assert record["ferramenta"] == "obter_dispositivo"
    if politica == "completo":
        assert record["parametros"]["versao"] == "publicacao_original"
        assert evidence[0] in record["evidencias"]
    else:
        assert record["evidencias"] is None
        assert record["confere_evidencias"][0]["confere"] is True
        row = acervo.conn.execute("SELECT request_json,result_json FROM run WHERE id=?", (out["run_id"],)).fetchone()
        request = json.loads(row["request_json"])
        valores = {"citacao": "art. 289 da Lei 6404/1976", "trecho": None, "data": "2025-01-01",
                   "modo": "literal", "work_id": None, "caminho": None,
                   "versao": "publicacao_original", "fonte": None}
        assert request == {"registro": "sem_conteudo", **{
            f"{k}_sha256": None if v is None else registro.hmac_entrada(acervo.conn, k, str(v))
            for k, v in valores.items()}}
        reference = acervo.obter_dispositivo("art. 289 da Lei 6404/1976", versao="publicacao_original")
        assert reference["texto"] and reference["texto"] not in row["result_json"]
        assert "versao_sha256" in json.loads(row["request_json"])
    # Um escritor SQL comum já é barrado. Simular depois o atacante com poder de remover trigger.
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError, match="imutavel"):
        acervo.conn.execute("UPDATE run SET result_json='{}' WHERE id=?", (out["run_id"],))
    acervo.conn.execute("DROP TRIGGER run_no_update")
    with acervo.conn:
        acervo.conn.execute("UPDATE run SET result_json='{}' WHERE id=?", (out["run_id"],))
    assert acervo.obter_registro(out["run_id"])["integridade"]["confere"] is False


def test_c12_obtencao_somente_leitura_nao_grava(acervo, monkeypatch):
    count = acervo.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0]
    home = acervo.home
    acervo.close()
    monkeypatch.setenv("FV_READ_ONLY", "1")
    with Verifica(home=home) as readonly:
        out = readonly.obter_dispositivo("art. 289 da Lei 6404/1976", versao="publicacao_original", data="2025-01-01")
        assert out["texto"]
        assert out["run_id"] is None
        assert out["registro"] == {"gravado": False, "motivo": "somente_leitura"}
        assert out["fundamento_temporal"] is None
        assert readonly.conn.execute("SELECT COUNT(*) FROM run").fetchone()[0] == count


def test_c15_snapshot_preserva_instante_e_versoes(acervo, tmp_path):
    before = acervo.obter_dispositivo("art. 289 da Lei 6404/1976", versao="publicacao_original")
    exported = acervo.snapshot_export(tmp_path / "snapshot")
    assert exported["status"] == "ok"
    with Verifica(home=tmp_path / "instalado") as target:
        installed = target.snapshot_install(tmp_path / "snapshot", aceitar_nao_vinculado=True)
        assert installed["status"] == "ok", installed
        after = target.obter_dispositivo("art. 289 da Lei 6404/1976", versao="publicacao_original")
        assert after["status"] == "encontrada", after
        assert after["texto"] == before["texto"]
        assert after["evidencia"]["sha256"] == before["evidencia"]["sha256"]
        assert after["evidencia"]["captured_at"] == before["evidencia"]["captured_at"]
        assert after["evidencia"]["procedencia"] == "snapshot"
        assert after["evidencia"]["natureza_texto"] == "publicacao_original"
        assert after["evidencia"]["acervo_ate"] is None
