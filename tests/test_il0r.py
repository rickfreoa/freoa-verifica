"""IL.0-R (decisão 0075 + passe final do PR #25): provas por classe dos critérios C1 a C11."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import subprocess
import sys
import threading
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from freoa_verifica import registro, situacao
from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Candidate, ParsedDecision
from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.parsers.model import Annotation, Provision, Redaction
from freoa_verifica.service import _CONTADAS, Verifica
from freoa_verifica.temporal import select as temporal_select
from freoa_verifica.temporal import today_sp
from freoa_verifica.transport import Response
from freoa_verifica.verify import verificar
from tests.fixture_util import load_fixture

CITACAO_160 = "Resolução CVM 160/2022"
SEIS_EIXOS = ("captured_at", "acervo_ate", "source_kind", "natureza_texto", "procedencia", "esfera")
HOJE = today_sp()
PASSADA = "2023-01-01"
FUTURA = (HOJE + timedelta(days=400)).isoformat()


def _indexar_160(svc: Verifica):
    body = load_fixture("cvm_resol_160_consolid_docx")
    doc = parse_cvm_docx(body)
    rw = svc.indexar_obra(
        source_id="cvm_normas", work_key=WorkKey("cvm", "resolucao", "160", 2022), document=doc, body=body,
        url="https://conteudo.cvm.gov.br/legislacao/resolucoes/resol160.docx", fetched_at="2026-10-18T00:00:00Z",
        work_date="2022-07-13", label="Resolução CVM nº 160/2022",
    )
    return rw, doc


def _situacao(svc, rw, tipo, efeito):
    situacao.gravar(svc.conn, situacao.WorkStatus(
        rw.work_id, tipo, texto_oficial="Declarada pela página do ato", ato_revogador="Resolução CVM 200",
        data_efeito=efeito, captura_id=rw.capture_id, sha256=rw.sha256, lido_em=datetime.now(timezone.utc).isoformat()))


@pytest.fixture
def svc160(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    s = Verifica(home=tmp_path / "home")
    rw, doc = _indexar_160(s)
    _situacao(s, rw, "vigente_declarada", None)
    yield s, rw, doc
    s.close()


def _afirma_negativa(estado: dict) -> bool:
    return (estado.get("status") in ("verified", "divergent", "vigente_na_fonte", "revogado")
            or (estado.get("reason_code") or "") in ("REVOGADO", "OBRA_REVOGADA_NA_FONTE", "DISPOSITIVO_REVOGADO"))


# ----------------------------------------------------------------------------------------------
# C1: guarda histórica única
# ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("tipo", ["revogada", "cancelada"])
@pytest.mark.parametrize("efeito", ["2022-12-01", None])
@pytest.mark.parametrize("data", [PASSADA, FUTURA])
def test_c1_todos_os_dispositivos_da_rcvm160_nunca_negam_por_situacao(svc160, tipo, efeito, data):
    """Varre todos os dispositivos da RCVM 160 (a ocorrência futura do parecer está em art26.inc11.ali-a/b)."""
    svc, rw, doc = svc160
    _situacao(svc, rw, tipo, efeito)
    ws = situacao.carregar(svc.conn, rw, svc.home)
    assert len(doc.provisions) > 700
    for prov in doc.provisions:
        tr = temporal_select(prov, data, work_date=rw.work_date, amending_act_texts=rw.amending_act_texts,
                             fetched_at=rw.fetched_at)
        final = situacao.aplicar_situacao_tr(tr, ws, data)
        assert final.status in ("unknown", "nao_existia", "ambiguous"), (prov.path, final.status, final.reason)
        assert final.reason != situacao.REVOGADO_NA_FONTE, prov.path


@pytest.mark.parametrize("tipo", ["revogada", "cancelada"])
@pytest.mark.parametrize("efeito", ["2022-12-01", None])
@pytest.mark.parametrize("data", [PASSADA, FUTURA])
@pytest.mark.parametrize("intermediario", [("unknown", "FIM_DESCONHECIDO"), ("unknown", "INICIO_SUCESSOR_DESCONHECIDO"),
                                           ("unknown", "UNKNOWN"), ("unknown", None), ("not_assessed", "SEM_DISPOSITIVO"),
                                           ("not_assessed", "SEM_IDENTIDADE"), ("unknown", "sem_fundamento_do_periodo")])
def test_c1_guarda_cobre_todo_estado_intermediario(svc160, tipo, efeito, data, intermediario):
    """A situação nunca decide por D diferente de hoje, qualquer que seja o estado intermediário (dimensão e dict)."""
    from freoa_verifica.verify import Dimension

    svc, rw, _ = svc160
    _situacao(svc, rw, tipo, efeito)
    ws = situacao.carregar(svc.conn, rw, svc.home)
    status, motivo = intermediario
    dim = situacao.aplicar_situacao(Dimension(status, motivo), ws, data)
    assert (dim.status, dim.reason_code) == (status, motivo)
    d = situacao.aplicar_situacao_dict({"status": status, "reason_code": motivo, "evidence": []}, ws, data)
    assert (d["status"], d["reason_code"]) == (status, motivo)


def test_c1_consulta_corrente_continua_negando_pela_situacao(svc160):
    """Controle: com `data` ausente ou igual a hoje a situação revogada ainda converte (0075, §2, item 4)."""
    svc, rw, _ = svc160
    _situacao(svc, rw, "revogada", "2022-12-01")
    for data in (None, HOJE.isoformat()):
        out = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", data=data)
        assert out["temporal"]["status"] == "divergent"
        assert out["temporal"]["reason_code"] == "OBRA_REVOGADA_NA_FONTE"
    out = svc.verificar_citacao(CITACAO_160)  # sem dispositivo: not_assessed vira negativa só na consulta corrente
    assert out["temporal"]["status"] == "divergent"


@pytest.mark.parametrize("tipo", ["revogada", "cancelada"])
@pytest.mark.parametrize("efeito", ["2022-12-01", None])
@pytest.mark.parametrize("data", [PASSADA, FUTURA])
def test_c1_servico_python_nos_caminhos_publicos(svc160, tipo, efeito, data):
    svc, rw, doc = svc160
    _situacao(svc, rw, tipo, efeito)
    atual = doc.provision("art26.inc11.ali-a").redactions[-1]
    for cit in (CITACAO_160, "art. 26, XI, a da Resolução CVM 160/2022", "art. 1º da Resolução CVM nº 160/2022"):
        out = svc.verificar_citacao(cit, trecho=atual.text, data=data)
        for dim in ("identity", "text", "temporal"):
            if dim != "identity":
                assert not _afirma_negativa(out[dim]), (cit, dim, out[dim])
        assert out["temporal"]["status"] in ("unknown", "not_assessed", "not_found", "ambiguous")
        texto = svc.verificar_texto(f"Nos termos do {cit}.", data=data)
        for c in texto["citacoes"]:
            v = c["verificacao"]
            assert not _afirma_negativa(v["temporal"]) and not _afirma_negativa(v["text"])
    for kw in ({"citacao": "art. 26, XI, a da Resolução CVM 160/2022"},
               {"work_id": rw.work_id, "caminho": "art26.inc11.ali-a"},
               {"work_id": rw.work_id, "caminho": "art1"}):
        out = svc.obter_dispositivo(data=data, **kw)
        assert out["vigencia"]["status"] in ("unknown", "nao_existia", "ambiguous"), out["vigencia"]
        assert not _afirma_negativa(out["vigencia"])


def test_c1_guarda_final_rebaixa_resposta_adulterada_a_montante(svc160, monkeypatch):
    """Defesa em profundidade: mesmo que a seleção ou a situação deixassem passar, a saída final abstém."""
    svc, rw, _ = svc160
    from freoa_verifica import service

    def vaza(tr, status, data, hoje=None):
        from dataclasses import replace
        return replace(tr, status="revogado", reason=situacao.REVOGADO_NA_FONTE)

    def vaza_dict(temporal, status, data, hoje=None):
        return {**temporal, "status": "divergent", "reason_code": situacao.REVOGADO_NA_FONTE}

    monkeypatch.setattr(service.situacao, "aplicar_situacao_tr", vaza)
    monkeypatch.setattr(service.situacao, "aplicar_situacao_dict", vaza_dict)
    out = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", data=PASSADA)
    assert (out["temporal"]["status"], out["temporal"]["reason_code"]) == ("unknown", "sem_fundamento_do_periodo")
    od = svc.obter_dispositivo(citacao="art. 1º da Resolução CVM nº 160/2022", data=PASSADA)
    assert (od["vigencia"]["status"], od["vigencia"]["reason_code"]) == ("unknown", "sem_fundamento_do_periodo")
    corrente = svc.obter_dispositivo(citacao="art. 1º da Resolução CVM nº 160/2022")
    assert corrente["vigencia"]["status"] == "revogado"  # a corrente não é tocada


def test_c1_excecoes_mantidas_nao_existia_e_ambiguous(svc160):
    svc, rw, _ = svc160
    _situacao(svc, rw, "revogada", "2022-12-01")
    out = svc.obter_dispositivo(citacao="art. 1º da Resolução CVM nº 160/2022", data="2000-01-01")
    assert out["vigencia"]["status"] == "nao_existia"  # D anterior à obra: prova documental do próprio ato


# ----------------------------------------------------------------------------------------------
# C2: nenhum caminho aceita fundamento temporal
# ----------------------------------------------------------------------------------------------

_PROV = Provision(path="art1", label="Art. 1º", scope="norma",
                  redactions=[Redaction(order=0, text="Texto original", struck=False, annotations=[])])
_FUNDAMENTOS = [None, {}, False, 0, {"tipo": "versao_oficial_na_data"},
                {"tipo": "versao_oficial_na_data", "capture_id": "c1", "url": "https://example.org", "sha256": "abc",
                 "data": "2000-01-01"}]


def test_c2_parametro_removido_das_assinaturas():
    assert "fundamento_temporal" not in inspect.signature(temporal_select).parameters
    assert "fundamento_temporal" not in inspect.signature(verificar).parameters


@pytest.mark.parametrize("fundamento", _FUNDAMENTOS[1:], ids=["vazio", "false", "zero", "parcial", "completo"])
def test_c2_mutante_fundamento_recusado_como_erro_de_programacao(fundamento):
    with pytest.raises(TypeError):
        temporal_select(_PROV, "2000-01-01", work_date="1976-12-15", fundamento_temporal=fundamento)
    with pytest.raises(TypeError):
        verificar("art. 1º da Lei 1/2000", data="2000-01-01", resolver=object(), fundamento_temporal=fundamento)


def test_c2_historico_nunca_verified_nem_revogado():
    rev = Provision(path="art1", label="Art. 1º", scope="norma", redactions=[Redaction(
        order=0, text="T", struck=True,
        annotations=[Annotation(kind="revogado", raw="Revogado", act_ref="Lei 9", act_date="1995-01-01")])])
    assert temporal_select(_PROV, "2000-01-01", work_date="1976-12-15").status == "unknown"
    r = temporal_select(rev, "2000-01-01", work_date="1976-12-15")
    assert (r.status, r.reason) == ("unknown", "sem_fundamento_do_periodo")


def test_c2_fundamento_publicado_sempre_null(svc160):
    svc, _, _ = svc160
    for data in (None, PASSADA, FUTURA):
        out = svc.verificar_citacao("art. 1º da Resolução CVM nº 160/2022", data=data)
        assert out["fundamento_temporal"] is None
        assert svc.obter_dispositivo(citacao="art. 1º da Resolução CVM nº 160/2022", data=data)["fundamento_temporal"] is None
        run = svc.obter_registro(out["run_id"])
        assert run["fundamento_temporal"] is None


# ----------------------------------------------------------------------------------------------
# C3: consulta corrente inalterada (diferencial contra 430e654)
# ----------------------------------------------------------------------------------------------

def _temporal_da_base() -> types.ModuleType | None:
    try:
        src = subprocess.run(["git", "show", "430e654:freoa_verifica/temporal.py"], capture_output=True, check=True,
                             cwd=Path(__file__).resolve().parent.parent, timeout=60).stdout.decode("utf-8")
    except (OSError, subprocess.SubprocessError):
        return None
    # Carregado como módulo por importlib (sem exec); dataclasses resolvem anotações por sys.modules.
    spec = importlib.util.spec_from_loader("temporal_430e654", loader=None)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["temporal_430e654"] = mod
    code = compile(src, "temporal_430e654.py", "exec")
    types.FunctionType(code, mod.__dict__)()
    return mod


def _tudo(tr) -> tuple:
    return (tr.status, tr.reason, tuple(tr.flags), tr.redaction_id, tr.needs_judgment,
            (tr.interval.start, tr.interval.end, tr.interval.end_unknown) if tr.interval else None,
            tuple(tr.rules_applied))


def _provisoes_de_inclusao_futura() -> list[Provision]:
    futuro = (HOJE + timedelta(days=200)).isoformat()
    inc = Annotation(kind="incluido", raw="Incluído pela Lei 99", act_ref="Lei 99", act_date=futuro)
    notas = [Annotation(kind=k, raw=k) for k in ("vide", "vigencia", "producao_efeitos", "veto")]
    dada = Annotation(kind="redacao_dada", raw="Redação dada pela Lei 99", act_ref="Lei 99", act_date=futuro)
    out = [Provision(path="p-inc", label="a", scope="norma", redactions=[Redaction(0, "t", False, [inc])])]
    for n in notas:
        out.append(Provision(path=f"p-inc-{n.kind}", label="a", scope="norma",
                             redactions=[Redaction(0, "t", False, [inc, n])]))
    out.append(Provision(path="p-dada", label="a", scope="norma", redactions=[Redaction(0, "t", False, [dada])]))
    for n in notas:
        out.append(Provision(path=f"p-dada-{n.kind}", label="a", scope="norma",
                             redactions=[Redaction(0, "t", False, [dada, n])]))
    return out


@pytest.mark.repositorio
@pytest.mark.parametrize("data", [None, "HOJE"])
def test_c3_consulta_corrente_identica_a_430e654_em_inclusao_e_redacao_futuras(data):
    base = _temporal_da_base()
    if base is None:
        pytest.skip("git indisponível")
    d = HOJE.isoformat() if data == "HOJE" else None
    for prov in _provisoes_de_inclusao_futura():
        a = base.select(prov, d, work_date="1976-12-15")
        b = temporal_select(prov, d, work_date="1976-12-15")
        assert _tudo(a) == _tudo(b), (prov.path, _tudo(a), _tudo(b))


@pytest.mark.repositorio
def test_c3_consulta_corrente_identica_a_430e654_em_todos_os_dispositivos_da_rcvm160():
    base = _temporal_da_base()
    if base is None:
        pytest.skip("git indisponível")
    doc = parse_cvm_docx(load_fixture("cvm_resol_160_consolid_docx"))
    for d in (None, HOJE.isoformat()):
        for prov in doc.provisions:
            kw = {"work_date": "2022-07-13", "fetched_at": "2026-10-18T00:00:00Z"}
            assert _tudo(base.select(prov, d, **kw)) == _tudo(temporal_select(prov, d, **kw)), prov.path


@pytest.mark.repositorio
def test_c3_mudanca_historica_so_no_ramo_historico():
    """O que mudou em relação à base ocorre só com D diferente de hoje (a base afirma `verified`)."""
    base = _temporal_da_base()
    if base is None:
        pytest.skip("git indisponível")
    prov = _provisoes_de_inclusao_futura()[1]  # inclusão futura + `vide`
    futuro = (HOJE + timedelta(days=100)).isoformat()
    a = base.select(prov, futuro, work_date="1976-12-15")
    b = temporal_select(prov, futuro, work_date="1976-12-15")
    assert b.status == "unknown" and b.reason == "sem_fundamento_do_periodo"
    assert a.status == "nao_existia"  # consulta histórica: a base afirmava
    corrente = temporal_select(prov, None, work_date="1976-12-15")
    assert corrente.status == "nao_existia"


# ----------------------------------------------------------------------------------------------
# C4: campos aditivos depois de todos os rebaixamentos
# ----------------------------------------------------------------------------------------------

def test_c4_correspondencia_nula_quando_identidade_final_nao_verified(verifica_populada):
    svc, _, _ = verifica_populada
    out = svc.verificar_citacao(
        "Lei 6.404, art. 254-A", trecho="A alienação, direta ou indireta, do controle de companhia aberta",
        data="2020-01-01")
    assert out["identity"]["status"] == "unknown"
    assert out["identity"]["reason_code"] == "ASSOCIACAO_REQUER_CONFERENCIA"
    assert out["correspondencia_textual"] is None
    assert out["fundamento_temporal"] is None
    # controle: a mesma citação com identidade verificada preserva a correspondência
    ok = svc.verificar_citacao("art. 254-A da Lei 6.404/76",
                               trecho="A alienação, direta ou indireta, do controle de companhia aberta", data="2020-01-01")
    assert ok["identity"]["status"] == "verified" and ok["correspondencia_textual"] is not None


def test_c4_campos_presentes_em_todo_ramo_de_verificar_citacao(verifica_populada, monkeypatch):
    svc, _, _ = verifica_populada
    casos = [
        ("art. 254-A da Lei 6.404/76", None), ("Lei inventada 99.999/2099", None), ("xyz sem citação", None),
        ("art. 999 da Lei 6.404/76", "trecho"), ("Lei 6.404/76", None), ("art. 254-A da Lei 6.404/76", "x"),
        ("REsp 900.001", None), ("art. 1º da Lei 6.404/76", None),
    ]
    for cit, trecho in casos:
        for data in (None, "2020-01-01"):
            out = svc.verificar_citacao(cit, trecho=trecho, data=data)
            assert "fundamento_temporal" in out and out["fundamento_temporal"] is None, (cit, data)
            assert "correspondencia_textual" in out, (cit, data)
            if out["identity"]["status"] != "verified":
                assert out["correspondencia_textual"] is None, (cit, data)


def test_c4_obter_dispositivo_todo_ramo_encontrada_tem_os_campos(verifica_populada):
    svc, rw, _ = verifica_populada
    encontradas = [
        svc.obter_dispositivo(citacao="Lei 6.404/76"),  # sem caminho
        svc.obter_dispositivo(work_id=rw.work_id),  # sem caminho, por work_id
        svc.obter_dispositivo(citacao="art. 254-A da Lei 6.404/76"),
        svc.obter_dispositivo(citacao="art. 254-A da Lei 6.404/76", data="2020-01-01"),
        svc.obter_dispositivo(citacao="art. 254-A da Lei 6.404/76", data="1970-01-01"),  # nao_existia
    ]
    assert encontradas[0]["caminho"] is None and encontradas[1]["caminho"] is None
    for s in encontradas:
        assert s["status"] == "encontrada"
        assert "fundamento_temporal" in s and s["fundamento_temporal"] is None
        assert "correspondencia_textual" in s and s["correspondencia_textual"] is None
    # o status negativo segue mínimo (docs/CONTRATO.md)
    for neg in (svc.obter_dispositivo(citacao="Lei inventada 99.999/2099"), svc.obter_dispositivo(work_id="inexistente")):
        assert neg["status"] != "encontrada" and "fundamento_temporal" not in neg


# ----------------------------------------------------------------------------------------------
# C5: motivo textual da revogação histórica
# ----------------------------------------------------------------------------------------------

def _resolver_com(prov: Provision):
    from freoa_verifica.parsers.model import ParsedDocument
    from freoa_verifica.verify import MemoryResolver, ResolvedWork

    doc = ParsedDocument(profile="planalto", parser_version="t", title="Lei 6.404", ementa=None, text="",
                         provisions=[prov], issues=[])
    wk = WorkKey("federal", "lei", "6404", 1976)
    rw = ResolvedWork(work_id="w", work_key=wk, document=doc, work_date="1976-12-15", capture_id="c", sha256="s",
                      url="https://www.planalto.gov.br/x", fetched_at="2026-10-18T00:00:00Z", quarantined=False)
    r = MemoryResolver()
    r.add(rw)
    return r


@pytest.mark.parametrize("riscada", [True, False])
def test_c5_revogacao_anotada_historica_propaga_sem_fundamento_ao_texto(monkeypatch, riscada):
    monkeypatch.setattr("freoa_verifica.identity.validate_identity", lambda *a, **k: SimpleNamespace(year=1976))
    ann = Annotation(kind="revogado", raw="(Revogado pela Lei 9.000, de 1995)", act_ref="Lei 9.000", act_date="1995-01-01")
    prov = Provision(path="art5", label="Art. 5º", scope="norma",
                     redactions=[Redaction(order=0, text="Texto do artigo cinco", struck=riscada, annotations=[ann])])
    r = verificar("art. 5º da Lei 6.404/76", trecho="Texto do artigo cinco", data="2000-01-01",
                  resolver=_resolver_com(prov), repo=None)
    assert (r.temporal.status, r.temporal.reason_code) == ("unknown", "sem_fundamento_do_periodo")
    assert r.text.status == "unknown"
    assert r.text.reason_code == "sem_fundamento_do_periodo"


# ----------------------------------------------------------------------------------------------
# C6: evidência por construtor único, procedência persistida por captura
# ----------------------------------------------------------------------------------------------

def _indexar_decisao(svc, court, official, text="Texto sintético da decisão. " * 10):
    body = text.encode()
    url = f"https://example.org/{court}/{official}"
    resp = Response(url, url, 200, {}, body, hashlib.sha256(body).hexdigest(), "2026-10-18T00:00:00Z", [], "text/plain")
    parsed = ParsedDecision("fixture", "acordao", court, official, ementa="ementa", text=text, class_name="REsp",
                            organ="Terceira Turma", judgment_date="2025-05-05", rapporteur="Relator", metadata={})
    conn = SimpleNamespace(id=court.lower(), authority=court, hosts={"example.org"},
                           fetch=lambda _, r=resp: r, parse=lambda _, p=parsed: p)
    svc._index_candidate_juris(conn, Candidate(court.lower(), official, "Decisão"))


def _eixos_completos(ev: dict):
    for k in SEIS_EIXOS:
        assert k in ev, k
    for k in ("captured_at", "source_kind", "natureza_texto", "procedencia", "esfera"):
        assert isinstance(ev[k], str)


def test_c6_evidencia_de_decisao_tem_os_seis_eixos(verifica_populada, monkeypatch):
    svc, _, _ = verifica_populada
    _indexar_decisao(svc, "STJ", "900001")
    out = svc.verificar_citacao("REsp 900.001")
    assert out["identity"]["status"] == "verified"
    ev = out["identity"]["evidence"][0]
    _eixos_completos(ev)
    assert ev["procedencia"] == "captura_direta"
    assert ev["esfera"] == "federal"
    texto = svc.verificar_texto("Conforme o REsp 900.001.")
    _eixos_completos(texto["citacoes"][0]["evidencia"])


def test_c6_evidencia_normativa_nos_dois_caminhos_usa_a_procedencia_persistida(verifica_populada):
    svc, rw, _ = verifica_populada
    out = svc.verificar_citacao("art. 254-A da Lei 6.404/76")
    ev = out["identity"]["evidence"][0]
    _eixos_completos(ev)
    assert ev["procedencia"] == "captura_direta"
    od = svc.obter_dispositivo(citacao="art. 254-A da Lei 6.404/76")["evidencia"]
    assert {k: od[k] for k in SEIS_EIXOS} == {k: ev[k] for k in SEIS_EIXOS}
    # após reconstrução a partir do banco (nova instância) a marca persistida continua
    with Verifica(home=svc.home) as novo:
        again = novo.verificar_citacao("art. 254-A da Lei 6.404/76")["identity"]["evidence"][0]
        assert again["procedencia"] == "captura_direta"


def test_c6_captura_anterior_sem_marca_fica_nao_identificado(verifica_populada):
    svc, rw, _ = verifica_populada
    svc.conn.executescript("DROP TRIGGER capture_no_update;")
    svc.conn.execute("UPDATE capture SET procedencia=NULL")
    svc.conn.commit()
    svc._clear_caches()
    out = svc.verificar_citacao("art. 254-A da Lei 6.404/76")
    assert out["identity"]["evidence"][0]["procedencia"] == "nao_identificado"
    assert svc.obter_dispositivo(citacao="art. 254-A da Lei 6.404/76")["evidencia"]["procedencia"] == "nao_identificado"


def test_c6_sessao_assistida_rotulada_e_persistida(tmp_path):
    from freoa_verifica.store import repo
    from freoa_verifica.store.db import connect

    conn = connect(tmp_path / "v.sqlite3")
    conn.execute("INSERT INTO source(id,authority,profile,hosts_json) VALUES ('s','a','p','[]')")
    body = b"x"
    resp = Response("https://e.org/a", "https://e.org/a", 200, {}, body, hashlib.sha256(body).hexdigest(),
                    "2026-10-18T00:00:00Z", [], "text/plain")
    cid = repo.save_capture(conn, resp, "s", home=tmp_path, procedencia="sessao_assistida")
    assert conn.execute("SELECT procedencia FROM capture WHERE id=?", (cid,)).fetchone()[0] == "sessao_assistida"
    with pytest.raises(ValueError):
        repo.save_capture(conn, resp, "s", home=tmp_path, procedencia="snapshot")  # só o snapshot grava essa marca


def test_c6_snapshot_marca_so_as_capturas_incorporadas_em_acervo_misto(verifica_populada, tmp_path, monkeypatch):
    origem, rw, _ = verifica_populada
    pacote = tmp_path / "pacote.tar.gz"
    origem.snapshot_export(pacote)
    destino = tmp_path / "destino"
    with Verifica(home=destino) as t:
        monkeypatch.setenv("FV_OFFLINE", "1")
        _indexar_160(t)  # captura local anterior à instalação (acervo misto)
        r = t.snapshot_install(pacote, aceitar_nao_vinculado=True)
        assert r["status"] == "ok", r
        marcas = dict(t.conn.execute("SELECT source_id, procedencia FROM capture").fetchall())
        assert marcas["planalto"] == "snapshot"
        assert marcas["cvm_normas"] == "captura_direta"
        ev = t.verificar_citacao("art. 254-A da Lei 6.404/76")["identity"]["evidence"][0]
        assert ev["procedencia"] == "snapshot"
        loc = t.verificar_citacao("art. 1º da Resolução CVM nº 160/2022")["identity"]["evidence"][0]
        assert loc["procedencia"] == "captura_direta"


# ----------------------------------------------------------------------------------------------
# C7: acervo_ate sem cache obsoleto
# ----------------------------------------------------------------------------------------------

def test_c7_acervo_ate_acompanha_troca_externa_do_banco(verifica_populada):
    import sqlite3

    svc, rw, _ = verifica_populada
    antes = svc.obter_dispositivo(citacao="art. 254-A da Lei 6.404/76")["evidencia"]["acervo_ate"]
    assert antes
    externo = sqlite3.connect(str(svc.home / "verifica.sqlite3"))
    try:
        externo.execute(
            "INSERT INTO capture(id,source_id,url,final_url,fetched_at,status,headers_json,redirects_json,sha256,size)"
            " VALUES ('X1','planalto','https://p/x','https://p/x','2099-01-02T00:00:00Z',200,'{}','[]','ab',1)")
        externo.commit()
    finally:
        externo.close()
    depois = svc.obter_dispositivo(citacao="art. 254-A da Lei 6.404/76")["evidencia"]["acervo_ate"]
    assert depois == "2099-01-02" != antes
    ev = svc.verificar_citacao("art. 254-A da Lei 6.404/76")["identity"]["evidence"][0]
    assert ev["acervo_ate"] == "2099-01-02"


def test_c7_acervo_vazio_nao_fica_none_para_sempre(tmp_path, monkeypatch):
    with Verifica(home=tmp_path) as svc:
        assert svc._acervo_ate_planalto() is None
        svc.conn.execute("INSERT INTO source(id,authority,profile,hosts_json) VALUES ('planalto','federal','planalto','[]')")
        svc.conn.execute(
            "INSERT INTO capture(id,source_id,url,final_url,fetched_at,status,headers_json,redirects_json,sha256,size)"
            " VALUES ('X1','planalto','https://p/x','https://p/x','2026-05-06T00:00:00Z',200,'{}','[]','ab',1)")
        svc.conn.commit()
        assert svc._acervo_ate_planalto() == "2026-05-06"


# ----------------------------------------------------------------------------------------------
# C8, C9, C10: registro
# ----------------------------------------------------------------------------------------------

def _registro_novo(svc) -> str:
    out = svc.verificar_citacao("art. 254-A da Lei 6.404/76", trecho="A alienação, direta ou indireta")
    assert out["run_id"]
    return out["run_id"]


def _sem_triggers(conn):
    for (nome,) in conn.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='run'").fetchall():
        conn.execute(f"DROP TRIGGER {nome}")


def test_c8_registro_novo_integro_confere(verifica_populada):
    svc, _, _ = verifica_populada
    assert svc.obter_registro(_registro_novo(svc))["integridade"]["confere"] is True


def test_c8_mutante_apagar_o_mac_nao_vira_legado(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    _sem_triggers(svc.conn)
    svc.conn.execute("UPDATE run SET registro_mac=NULL WHERE id=?", (rid,))
    svc.conn.commit()
    assert svc.obter_registro(rid)["integridade"]["confere"] is False


def test_c8_mutante_apagar_mac_e_colunas_novas_e_adulterar_resultado(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    _sem_triggers(svc.conn)
    svc.conn.execute(
        "UPDATE run SET registro_mac=NULL, ferramenta=NULL, evidencias_compromissos=NULL, fundamento_compromisso=NULL,"
        " evidencias_claro=NULL, fundamento_claro=NULL, result_json=? WHERE id=?",
        (json.dumps({"temporal": {"status": "verified"}}), rid))
    svc.conn.commit()
    r = svc.obter_registro(rid)
    assert r["integridade"]["confere"] is False


def test_c8_mutante_apagar_o_selo_e_o_mac_tambem_nao_vira_legado(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    _sem_triggers(svc.conn)
    svc.conn.execute("UPDATE run SET registro_mac=NULL WHERE id=?", (rid,))
    svc.conn.execute("DELETE FROM meta WHERE key IN (?,?)", (registro.META_LEGADO, registro.META_LEGADO_MAC))
    svc.conn.commit()
    assert svc.obter_registro(rid)["integridade"]["confere"] is False


def test_c8_mutante_forjar_id_no_selo_nao_vale(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    _sem_triggers(svc.conn)
    svc.conn.execute("UPDATE run SET registro_mac=NULL WHERE id=?", (rid,))
    ids = json.loads(svc.conn.execute("SELECT value FROM meta WHERE key=?", (registro.META_LEGADO,)).fetchone()[0])
    svc.conn.execute("UPDATE meta SET value=? WHERE key=?", (json.dumps(ids + [rid]), registro.META_LEGADO))
    svc.conn.commit()
    assert svc.obter_registro(rid)["integridade"]["confere"] is False  # o selo não casa com o HMAC


def test_c8_registro_legado_anterior_a_migracao_continua_null(tmp_path, monkeypatch):
    """Home anterior à 1.4.0a2: o legado sem MAC é selado quando a chave nasce e segue `confere: null`."""
    with Verifica(home=tmp_path) as svc:
        svc.conn.execute(
            "INSERT INTO run(id, created_at, request_hash, request_json, policy_version, result_json) VALUES (?,?,?,?,?,?)",
            ("LEGADO0000000000000000000A", "2026-01-01T00:00:00+00:00", "h", "{}", "1", json.dumps({
                "identity": {"status": "verified"}})))
        svc.conn.commit()
        assert not (tmp_path / registro.ARQUIVO_CHAVE).exists()
        novo = svc.verificar_citacao("Lei inventada 99.999/2099")["run_id"]  # cria a chave e sela o legado
        assert svc.obter_registro("LEGADO0000000000000000000A")["integridade"]["confere"] is None
        assert svc.obter_registro(novo)["integridade"]["confere"] is True


def test_c8_migracao_sela_home_com_chave_existente(tmp_path):
    import sqlite3

    from freoa_verifica.store.db import connect

    caminho = tmp_path / "verifica.sqlite3"
    conn = connect(caminho)
    registro.chave_do_home(tmp_path, conn)  # home com chave e sem selo
    conn.execute("DELETE FROM meta WHERE key IN (?,?)", (registro.META_LEGADO, registro.META_LEGADO_MAC))
    conn.execute("DELETE FROM schema_version WHERE version=19")
    conn.execute(
        "INSERT INTO run(id, created_at, request_hash, request_json, policy_version, result_json) VALUES (?,?,?,?,?,?)",
        ("LEGADO0000000000000000000B", "2026-01-01T00:00:00+00:00", "h", "{}", "1", "{}"))
    conn.commit()
    conn.close()
    conn = connect(caminho)  # reaplica a 019
    assert registro.legado_autenticado(conn, "LEGADO0000000000000000000B")
    assert not registro.legado_autenticado(conn, "OUTRO")
    conn.close()
    assert isinstance(sqlite3.connect(str(caminho)), sqlite3.Connection)


def test_c9_obter_registro_em_home_somente_leitura(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    antes = svc.conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
    registro._cache_chaves.clear()  # processo "frio": a chave precisa ser relida do arquivo
    svc.conn.execute("PRAGMA query_only=ON")
    try:
        r = svc.obter_registro(rid, evidencias=[{"capture_id": "x", "sha256": "y", "url": "z"}])
        assert r["status"] == "encontrada"
        assert r["integridade"]["confere"] is True
        assert r["confere_evidencias"] == [{"capture_id": "x", "confere": False}]
    finally:
        svc.conn.execute("PRAGMA query_only=OFF")
    assert svc.conn.execute("SELECT COUNT(*) FROM meta").fetchone()[0] == antes


def test_c9_leitura_da_chave_nunca_cria_arquivo_nem_escreve(tmp_path):
    from freoa_verifica.store.db import connect

    conn = connect(tmp_path / "v.sqlite3")
    with pytest.raises(RuntimeError, match="CHAVE_REGISTRO_AUSENTE"):
        registro.ler_chave_do_home(tmp_path)
    assert not (tmp_path / registro.ARQUIVO_CHAVE).exists()
    chave = registro.chave_do_home(tmp_path, conn)
    registro._cache_chaves.clear()
    assert registro.ler_chave_do_home(tmp_path) == chave
    conn.close()


def test_c9_chave_ausente_nao_derruba_a_leitura(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    (svc.home / registro.ARQUIVO_CHAVE).unlink()
    registro._cache_chaves.clear()
    r = svc.obter_registro(rid)
    assert r["integridade"]["confere"] is False


def test_c10_obter_registro_e_operacao_contada():
    assert "obter_registro" in _CONTADAS


def test_c10_leitura_concorrente_bloqueia_operacao_exclusiva(verifica_populada):
    svc, _, _ = verifica_populada
    rid = _registro_novo(svc)
    dentro, sair = threading.Event(), threading.Event()
    real = registro.hmac_entrada

    def pausado(*a, **k):
        dentro.set()  # a leitura do registro já está em curso (depois da consulta SQL)
        sair.wait(5)
        return real(*a, **k)

    resultado: dict = {}
    with pytest.MonkeyPatch.context() as m:
        m.setattr(registro, "hmac_entrada", pausado)
        t = threading.Thread(target=lambda: resultado.update(r=svc.obter_registro(rid)))
        t.start()
        try:
            assert dentro.wait(5)
            assert svc._ops == 1  # causal: a leitura em curso está contada
            with pytest.raises(TimeoutError):
                with svc.exclusivo(timeout=0.2):
                    pass
        finally:
            sair.set()
            t.join()
    assert resultado["r"]["status"] == "encontrada"
    with svc.exclusivo(timeout=1):  # liberada depois
        pass


# ----------------------------------------------------------------------------------------------
# C11: recibo de todas as verificações
# ----------------------------------------------------------------------------------------------

def test_c11_decisao_avulsa_grava_recibo_recuperavel(verifica_populada):
    svc, _, _ = verifica_populada
    _indexar_decisao(svc, "STJ", "900001")
    out = svc.verificar_citacao("REsp 900.001")
    assert out["identity"]["status"] == "verified" and out["run_id"]
    r = svc.obter_registro(out["run_id"])
    assert r["status"] == "encontrada" and r["estado"]["identity"]["status"] == "verified"
    assert r["integridade"]["confere"] is True
    assert r["politica"] == "sem_conteudo"  # a política de minimização vigente


def test_c11_politica_completo_guarda_a_evidencia_da_decisao(verifica_populada):
    svc, _, _ = verifica_populada
    svc.registro = "completo"
    _indexar_decisao(svc, "STJ", "900001")
    out = svc.verificar_citacao("REsp 900.001")
    r = svc.obter_registro(out["run_id"])
    assert r["politica"] == "completo" and r["evidencias"]
    ev = out["identity"]["evidence"][0]
    assert r["evidencias"][0]["capture_id"] == ev["capture_id"]


def test_c11_decisao_nao_confirmada_tambem_tem_recibo(verifica_populada):
    svc, _, _ = verifica_populada
    out = svc.verificar_citacao("REsp 9.999.999")
    assert out["identity"]["status"] != "verified" and out["run_id"]
    assert svc.obter_registro(out["run_id"])["estado"]["identity"]["status"] == out["identity"]["status"]


def test_c11_saidas_antecipadas_gravam_recibo(verifica_populada):
    from dataclasses import replace

    from freoa_verifica.identity import IdentityMismatch
    from freoa_verifica.verify import SourceUnavailable

    svc, rw, _ = verifica_populada
    cit = "art. 254-A da Lei 6.404/76"

    def fonte_fora(*a, **k):
        raise SourceUnavailable("FONTE_FORA")

    def diverge(*a, **k):
        raise IdentityMismatch("x")

    with pytest.MonkeyPatch.context() as m:  # indisponibilidade da fonte
        m.setattr(svc, "_resolve", fonte_fora)
        out = svc.verificar_citacao(cit)
    assert out["identity"]["status"] == "unavailable" and out["run_id"]
    assert svc.obter_registro(out["run_id"])["estado"]["identity"]["reason_code"] == "FONTE_FORA"
    with pytest.MonkeyPatch.context() as m:  # divergência de identidade
        m.setattr("freoa_verifica.service.validate_identity", diverge)
        out = svc.verificar_citacao(cit)
    assert out["identity"]["reason_code"] == "IDENTIDADE_DIVERGENTE" and out["run_id"]
    sem_captura = replace(rw, capture_id=None)
    with pytest.MonkeyPatch.context() as m:  # ausência de captura
        m.setattr(svc, "_resolve", lambda *a, **k: sem_captura)
        out = svc.verificar_citacao(cit)
    assert out["identity"]["reason_code"] == "SEM_EVIDENCIA_CAPTURADA" and out["run_id"]
    assert svc.obter_registro(out["run_id"])["estado"]["identity"]["reason_code"] == "SEM_EVIDENCIA_CAPTURADA"


def test_c11_modo_somente_leitura_e_declarado(verifica_populada, monkeypatch):
    svc, _, _ = verifica_populada
    monkeypatch.setattr(svc, "_read_only", True)
    out = svc.verificar_citacao("REsp 9.999.999")
    assert out["run_id"] is None
    assert out["registro"] == {"gravado": False, "motivo": "somente_leitura"}
