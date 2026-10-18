"""C2 (situação da obra), A4/A9/M2/M3/M4 e F03: fixtures sintéticas, sem rede."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from urllib.parse import unquote

import pytest

from freoa_verifica import situacao
from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors import bcb, cvm_normas
from freoa_verifica.connectors.base import Candidate, Unavailable
from freoa_verifica.parsers.bcb_json import parse_bcb_json
from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.service import Verifica
from freoa_verifica.situacao import WorkStatus
from freoa_verifica.temporal import TemporalResult
from freoa_verifica.transport import Response
from freoa_verifica.verify import Dimension
from tests.fixture_util import load_fixture

CMN = WorkKey("cmn", "resolucao", "4966", 2021)
HOJE = date(2026, 10, 18)


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bcb_body(**campos) -> bytes:
    payload = json.loads(load_fixture("bcb_res_cmn_4966"))
    payload["conteudo"][0].update(campos)
    return json.dumps(payload).encode("utf-8")


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    s = Verifica(home=tmp_path)
    yield s
    s.close()


def _indexar_bcb(svc, body: bytes):
    doc = parse_bcb_json(body)
    rw = svc.indexar_obra(
        source_id="bcb", work_key=CMN, document=doc, body=body,
        url="https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=Resolu%C3%A7%C3%A3o+CMN&p2=4966",
        fetched_at=_agora(), work_date="2021-11-25", label="Resolução CMN 4.966")
    return rw, doc.provisions[0].path


def _art(path: str) -> str:
    m = re.match(r"art(\d+)", path)
    return f"art. {m.group(1)}" if m else path


def _cit(path: str | None = None) -> str:
    return "Resolução CMN 4.966/2021" + (f", {_art(path)}" if path else "")


# --- controle positivo ------------------------------------------------------

def test_bcb_vigente_declarada_continua_vigente_na_fonte(svc):
    rw, path = _indexar_bcb(svc, _bcb_body())
    row = svc.conn.execute("SELECT situacao FROM work_status WHERE work_id=?", (rw.work_id,)).fetchone()
    assert row[0] == "vigente_declarada"
    out = svc.verificar_citacao(_cit(path))
    assert out["temporal"]["status"] == "vigente_na_fonte"
    assert out["identity"]["status"] == "verified"


# --- B2 ---------------------------------------------------------------------

def test_bcb_revogado_bloqueia_vigente(svc):
    _indexar_bcb(svc, _bcb_body(Revogado=True))
    rw, path = _indexar_bcb(svc, _bcb_body(Revogado=True))
    out = svc.verificar_citacao(_cit(path))
    assert out["temporal"]["status"] != "vigente_na_fonte"
    assert out["temporal"]["reason_code"] == "OBRA_REVOGADA_NA_FONTE"
    assert any("Revogado=true" in (e["trecho_oficial"] or "") for e in out["temporal"]["evidence"])
    assert out["identity"]["status"] == "verified"  # identidade documental permanece


def test_recibo_reflete_situacao_aplicada_em_finalizar(svc):
    rw, path = _indexar_bcb(svc, _bcb_body(Revogado=True))
    out = svc.verificar_citacao(_cit(path))
    gravado = json.loads(svc.conn.execute("SELECT result_json FROM run WHERE id=?", (out["run_id"],)).fetchone()[0])
    assert gravado["temporal"]["reason_code"] == out["temporal"]["reason_code"] == "OBRA_REVOGADA_NA_FONTE"


def test_revogacao_no_ramo_sem_dispositivo(svc):
    _indexar_bcb(svc, _bcb_body(Cancelado=True))
    out = svc.verificar_citacao(_cit())
    assert out["temporal"]["status"] == "divergent"
    assert out["temporal"]["reason_code"] == "OBRA_REVOGADA_NA_FONTE"


def test_bcb_sem_campos_de_situacao_e_ilegivel_nao_vigente(svc):
    payload = json.loads(_bcb_body())
    del payload["conteudo"][0]["Revogado"]
    _, path = _indexar_bcb(svc, json.dumps(payload).encode())
    out = svc.verificar_citacao(_cit(path))
    assert out["temporal"]["status"] == "unknown"
    assert out["temporal"]["reason_code"] == "SITUACAO_INDISPONIVEL"


def test_data_passada_sem_data_efeito_unknown(svc):
    _, path = _indexar_bcb(svc, _bcb_body(Revogado=True))
    out = svc.verificar_citacao(_cit(path), data="2023-01-10")
    assert out["temporal"]["status"] == "unknown"
    assert out["temporal"]["reason_code"] == "REVOGACAO_DATA_DESCONHECIDA"


def _ws(sit, **kw):
    return WorkStatus("w", sit, **kw)


def _dim(status, reason=None):
    return Dimension(status, reason)


def test_regras_com_data_efeito():
    rev = _ws("revogada", data_efeito="2025-01-01", texto_oficial="x", lido_em="2026-10-01")
    out = situacao.aplicar_situacao(_dim("verified"), rev, "2025-06-01", HOJE)
    assert (out.status, out.reason_code) == ("divergent", "OBRA_REVOGADA_NA_FONTE")
    fut = _ws("revogada", data_efeito="2027-01-01", lido_em="2026-10-01")
    out = situacao.aplicar_situacao(_dim("vigente_na_fonte", "VIGENTE_NA_FONTE"), fut, None, HOJE)
    assert out.status == "vigente_na_fonte" and "REVOGACAO_POSTERIOR" in out.reason_code
    tr = situacao.aplicar_situacao_tr(TemporalResult("vigente_na_fonte", "r1", None), fut, None, HOJE)
    assert tr.status == "vigente_na_fonte" and "REVOGACAO_POSTERIOR" in tr.flags


def test_revogacao_futura_via_servico(svc):
    rw, path = _indexar_bcb(svc, _bcb_body(Revogado=True))
    situacao.gravar(svc.conn, WorkStatus(rw.work_id, "revogada", "x", None, "2999-01-01",
                                         rw.capture_id, rw.sha256, _agora()))
    out = svc.verificar_citacao(_cit(path))
    assert out["temporal"]["status"] == "vigente_na_fonte"
    assert "REVOGACAO_POSTERIOR" in out["temporal"]["reason_code"]


def test_revogado_ou_nao_existia_do_texto_sao_preservados():
    rev = _ws("revogada", lido_em="2026-10-01")
    for dim in (_dim("divergent", "REVOGADO"), _dim("not_found", "NAO_EXISTIA")):
        assert situacao.aplicar_situacao(dim, rev, "2020-01-01", HOJE) is dim
    il = _ws("ilegivel")
    assert situacao.aplicar_situacao(_dim("divergent", "REVOGADO"), il, None, HOJE).reason_code == "REVOGADO"


def test_ilegivel_e_desatualizada_rebaixam_so_vigente_ou_verified():
    il = _ws("ilegivel")
    assert situacao.aplicar_situacao(_dim("verified"), il, "2020-01-01", HOJE).reason_code == "SITUACAO_INDISPONIVEL"
    velha = _ws("vigente_declarada", lido_em="2026-01-01")
    out = situacao.aplicar_situacao(_dim("vigente_na_fonte"), velha, None, HOJE)
    assert out.status == "unknown" and out.reason_code.startswith("SITUACAO_")
    assert situacao.aplicar_situacao(_dim("unknown", "X"), il, None, HOJE).reason_code == "X"
    rv = _ws("revogada", lido_em="2026-01-01")  # revogação antiga continua valendo
    assert situacao.aplicar_situacao(_dim("vigente_na_fonte"), rv, None, HOJE).reason_code == "OBRA_REVOGADA_NA_FONTE"


@pytest.mark.parametrize("sit", ["nao_aplicavel", "vigente_declarada"])
def test_nao_aplicavel_e_vigente_declarada_nao_mudam_nada(sit):
    ws = _ws(sit, lido_em="2026-10-10")
    for d in (_dim("vigente_na_fonte"), _dim("verified"), _dim("unknown", "X"), _dim("divergent", "REVOGADO")):
        assert situacao.aplicar_situacao(d, ws, None, HOJE) is d
    assert situacao.aplicar_situacao(_dim("verified"), None, None, HOJE).status == "verified"


def test_nao_aplicavel_persistido_e_planalto_sem_situacao(verifica_populada):
    svc, rw, _doc = verifica_populada
    assert situacao.carregar(svc.conn, rw) is None
    situacao.gravar(svc.conn, WorkStatus(rw.work_id, "nao_aplicavel", lido_em=_agora()))
    assert situacao.carregar(svc.conn, rw).situacao == "nao_aplicavel"
    out = svc.verificar_citacao("Lei 6.404/1976, art. 254-A")
    assert out["temporal"]["reason_code"] not in {"OBRA_REVOGADA_NA_FONTE", "SITUACAO_INDISPONIVEL"}


# --- CVM --------------------------------------------------------------------

_PAGINA = """<html><head><meta charset="utf-8"></head><body><article><h2>{titulo}</h2>
<section class="pull-left contentArticle"><p><b>Tue Mar 29 09:30:00 BRT 2022</b></p>{extra}
<p>Dispõe sobre o registro e a prestação de informações periódicas e eventuais dos emissores.</p>
</section></article></body></html>"""


class _CvmFake:
    id = "cvm_normas"

    def __init__(self, body: bytes | None):
        self.body = body

    def fetch_situacao(self, cand):
        if self.body is None:
            raise Unavailable("http_503")
        return Response(cand.url, cand.url, 200, {}, self.body, hashlib.sha256(self.body).hexdigest(),
                        _agora(), [], "text/html")


def _indexar_cvm(svc):
    body = load_fixture("cvm_resol_080_consolid_docx")
    doc = parse_cvm_docx(body)
    rw = svc.indexar_obra(
        source_id="cvm_normas", work_key=WorkKey("cvm", "resolucao", "80", 2022), document=doc, body=body,
        url="https://conteudo.cvm.gov.br/legislacao/resolucoes/anexos/001/resol080consolid.docx",
        fetched_at=_agora(), work_date="2022-03-29", label="Resolução CVM 80")
    cand = Candidate("cvm_normas", "cvm:resolucoes:80", "Resolução CVM 80",
                     "https://conteudo.cvm.gov.br/legislacao/resolucoes/resol080.html")
    return rw, cand, next(p.path for p in doc.provisions if p.path.startswith("art"))


def test_cvm_pagina_revogada_marca_obra(svc):
    rw, cand, path = _indexar_cvm(svc)
    pagina = _PAGINA.format(titulo="Resolução CVM 80",
                            extra="<p>REVOGADA pela Resolução CVM 175, de 23 de dezembro de 2022.</p>")
    ws = situacao.registrar_cvm(svc.conn, svc.home, _CvmFake(pagina.encode()), cand, rw)
    assert (ws.situacao, ws.ato_revogador, ws.data_efeito) == ("revogada", "Resolução CVM 175", None)
    assert ws.captura_id and ws.captura_id != rw.capture_id  # a íntegra segue sendo a captura normativa
    out = svc.verificar_citacao(f"Resolução CVM 80/2022, {_art(path)}")
    assert out["temporal"]["reason_code"] == "OBRA_REVOGADA_NA_FONTE"
    assert any("REVOGADA pela" in (e["trecho_oficial"] or "") for e in out["temporal"]["evidence"])
    # a data do ato revogador nunca vira data de efeito
    passado = svc.verificar_citacao(f"Resolução CVM 80/2022, {_art(path)}", data="2022-06-01")
    assert passado["temporal"]["reason_code"] == "REVOGACAO_DATA_DESCONHECIDA"


def test_cvm_vigente_declarada_controle_positivo(svc):
    rw, cand, path = _indexar_cvm(svc)
    pagina = _PAGINA.format(titulo="Resolução CVM 80", extra="").encode()
    ws = situacao.registrar_cvm(svc.conn, svc.home, _CvmFake(pagina), cand, rw)
    assert ws.situacao == "vigente_declarada"
    out = svc.verificar_citacao(f"Resolução CVM 80/2022, {_art(path)}")
    assert out["temporal"]["status"] == "vigente_na_fonte"


@pytest.mark.parametrize("fonte", [None, b"<html>pagina quebrada</html>"])
def test_cvm_situacao_indisponivel_nao_vigente(svc, fonte):
    rw, cand, path = _indexar_cvm(svc)
    ws = situacao.registrar_cvm(svc.conn, svc.home, _CvmFake(fonte), cand, rw)
    assert ws.situacao == "ilegivel"
    out = svc.verificar_citacao(f"Resolução CVM 80/2022, {_art(path)}")
    assert out["temporal"]["status"] == "unknown"
    assert out["temporal"]["reason_code"] == "SITUACAO_INDISPONIVEL"


def test_cvm_sem_registro_de_situacao_nao_e_vigente(svc):
    rw, _, _ = _indexar_cvm(svc)
    assert situacao.carregar(svc.conn, rw).situacao == "ilegivel"


def test_pagina_nao_presume_vigente():
    doc = cvm_normas._parse_ato_html(b"<html><body><p>nada</p></body></html>",
                                     base_url="https://conteudo.cvm.gov.br/")
    assert "[situacao=vigente]" not in doc.text


def test_ressincronizar_situacao(svc, monkeypatch):
    rw, _, _ = _indexar_cvm(svc)
    monkeypatch.delenv("FV_OFFLINE")
    pagina = _PAGINA.format(titulo="Resolução CVM 80",
                            extra="<p>REVOGADA pela Resolução CVM 175, de 2022.</p>").encode()
    real = svc._get("cvm_normas")
    monkeypatch.setattr(real, "fetch_situacao", _CvmFake(pagina).fetch_situacao)
    out = svc.ressincronizar_situacao(fontes=("cvm_normas",))
    assert out["revogadas"] == 1
    assert situacao.carregar(svc.conn, rw, svc.home).situacao == "revogada"


# --- A4 / A9 / M2 / M3 ------------------------------------------------------

def _lista(titulos, total, base="/legislacao/resolucoes/"):
    arts = "".join(
        f'<article><h3><a href="{base}{h}">{t}</a></h3><div class="contentDesc">Ementa de ação</div>'
        f"<b>01/01/2022</b></article>" for t, h in titulos)
    html = f'<html><body><div class="orderResults"><span>{total} resultados encontrados</span></div>{arts}</body></html>'
    return html.encode("utf-8")  # sem meta charset: o lxml presumiria latin-1


def test_a4_consulta_acentuada_utf8_sem_mojibake():
    body = _lista([("Resolução CVM 175 – Fundos", "resol175.html")], 30)
    out = cvm_normas._parse_list_html(body, source_id="cvm_normas", tipo="resolucoes", limite=20,
                                      q="ação fiduciária")
    assert out[0].title == "Resolução CVM 175 – Fundos"
    assert out[0].snippet == "Ementa de ação"  # sem exigir a frase literal da consulta


def test_a4_total_positivo_sem_itens_legiveis_e_indisponivel():
    body = ('<html><body><div class="orderResults"><span>30 resultados encontrados</span></div>'
            "<article><p>x</p></article></body></html>").encode()
    with pytest.raises(Unavailable):
        cvm_normas._parse_list_html(body, source_id="cvm_normas", tipo="resolucoes", limite=20, q="x")


def test_a9_total_da_fonte_e_truncado_no_servico(svc, monkeypatch):
    body = _lista([(f"Resolução CVM {n}", f"resol{n:03d}.html") for n in (10, 11)], 175)
    cands = cvm_normas._parse_list_html(body, source_id="cvm_normas", tipo="resolucoes", limite=20, q="")
    assert (cands.total, cands.truncado) == (175, True)
    monkeypatch.delenv("FV_OFFLINE")

    class C:
        id = "cvm_normas"

        def search(self, q, **f):
            return cands

    monkeypatch.setattr(svc, "_get", lambda _id: C())
    monkeypatch.setattr(svc, "_index_candidate_legis", lambda c, cand: {"capture_id": "x", "trecho": ""})
    out = svc._buscar_normas("cvm_normas", "x", None)
    assert (out["total"], out["truncado"]) == (175, True)
    assert svc.buscar_legislacao("x", fonte="cvm_normas") is not None


def test_m3_um_item_por_ato_descarta_anexo_duplicado():
    body = _lista([("Resolução CVM 232 - Anexo A", "anexos/200/resol232A.html"),
                   ("Resolução CVM 232", "resol232.html"),
                   ("Resolução CVM 232 - Anexo B", "anexos/200/resol232B.html"),
                   ("Resolução CVM 233", "resol233.html")], 4)
    out = cvm_normas._parse_list_html(body, source_id="cvm_normas", tipo="resolucoes", limite=20, q="")
    assert [c.key for c in out] == ["cvm:resolucoes:232", "cvm:resolucoes:233"]
    assert out[0].title == "Resolução CVM 232"


def test_m2_especie_acompanha_o_numero(monkeypatch):
    vistos = []
    c = cvm_normas.CvmNormasConnector()
    monkeypatch.setattr(c, "resolve", lambda key: vistos.append(key))
    c.search("Instrução CVM 358")
    c.search("Resolução CVM 80")
    c.search("Parecer de Orientação CVM 35")
    assert vistos == [{"tipo": "instrucoes", "numero": 358}, {"tipo": "resolucoes", "numero": 80},
                      {"tipo": "pareceres-orientacao", "numero": 35}]


# --- M4 ---------------------------------------------------------------------

def test_m4_consulta_com_numero_aciona_lookup_exato(monkeypatch):
    urls = []
    corpo = load_fixture("bcb_busca_cmn_4966")

    def fake(url, **kw):
        urls.append(url)
        return Response(url, url, 200, {}, corpo, hashlib.sha256(corpo).hexdigest(), _agora(), [],
                        "application/json")

    monkeypatch.setattr(bcb, "connector_fetch", fake)
    out = bcb.BcbConnector().search("Resolução CMN 4.966")
    q = unquote(urls[0])
    assert "NumeroOWSNMBR:4966" in q and "Resolução CMN" in q
    assert (out.total, out.truncado) == (1, False)


def test_a9_bcb_total_da_fonte_maior_que_lido_e_truncado(monkeypatch):
    payload = json.loads(load_fixture("bcb_busca_cmn_4966"))
    payload["TotalRows"] = 175
    corpo = json.dumps(payload).encode()
    monkeypatch.setattr(bcb, "connector_fetch", lambda url, **kw: Response(
        url, url, 200, {}, corpo, hashlib.sha256(corpo).hexdigest(), _agora(), [], "application/json"))
    out = bcb.BcbConnector().search("Resolução CMN 4.966")
    assert (out.total, out.truncado) == (175, True)


# --- F03 --------------------------------------------------------------------

def _pdf(paginas: int) -> bytes:
    import io

    from pypdf import PdfWriter
    w = PdfWriter()
    for _ in range(paginas):
        w.add_blank_page(72, 72)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_f03_pdf_valido_roda_isolado():
    assert cvm_normas._parse_pdf(_pdf(2), source="x").profile == "cvm_pdf"


def test_f03_pdf_com_excesso_de_paginas_e_unavailable():
    with pytest.raises(Unavailable) as exc:
        cvm_normas._parse_pdf(_pdf(cvm_normas.PDF_MAX_PAGINAS + 1), source="x")
    assert "pdf_paginas_excedidas" in exc.value.reason


def test_f03_pdf_que_excede_o_tempo_e_unavailable(monkeypatch):
    monkeypatch.setattr(cvm_normas, "PDF_TIMEOUT_S", 0.01)
    with pytest.raises(Unavailable) as exc:
        cvm_normas._parse_pdf(_pdf(3), source="x")
    assert "timeout" in exc.value.reason


def test_f03_pdf_corrompido_nao_derruba_o_processo():
    with pytest.raises(Unavailable):
        cvm_normas._parse_pdf(b"%PDF-1.4\n" + b"\x00" * 200, source="x")


# --- rodada de ensaio real: DOCX isolado, equivalência, desempenho, busca limitada, obra revogada sem estrutura ---


def _docx_sintetico(n: int) -> bytes:
    import io
    import zipfile

    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           '<w:p><w:r><w:t>Art. 1. Abertura.</w:t></w:r></w:p>'
           + "".join(f"<w:p><w:r><w:t>continuação {i} do   texto</w:t></w:r></w:p>" for i in range(n))
           + "</w:body></w:document>")
    s = io.BytesIO()
    with zipfile.ZipFile(s, "w") as z:
        z.writestr("word/document.xml", xml)
    return s.getvalue()


def test_continuacao_docx_linear():
    import time

    t = time.monotonic()
    d = parse_cvm_docx(_docx_sintetico(20000))  # antes: minutos (renormalizava o acumulado a cada parágrafo)
    assert time.monotonic() - t < 15
    texto = d.provisions[0].redactions[0].text
    assert texto.endswith("continuação 19999 do texto") and "  " not in texto


@pytest.mark.parametrize("nome", ["044", "080", "160", "175"])
def test_continuacao_docx_texto_ja_normalizado(nome):
    from freoa_verifica.parsers.html_devices import _normalize_ws

    d = parse_cvm_docx(load_fixture(f"cvm_resol_{nome}_consolid_docx"))
    for p in d.provisions:
        for r in p.redactions:
            assert r.text == _normalize_ws(r.text)
    assert d.provisions


def test_docx_da_cvm_passa_por_processo_isolado(monkeypatch):
    chamados = []
    from freoa_verifica.parsers import isolated

    real = isolated.parse_isolated
    monkeypatch.setattr(isolated, "parse_isolated", lambda *a: chamados.append(a[0]) or real(*a))
    d = cvm_normas._parse_docx(_docx_sintetico(3))
    assert chamados == ["cvm_docx"] and d.provisions


def test_busca_indexa_no_maximo_n_e_declara_o_resto(svc, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE")
    cands = [Candidate("cvm_normas", f"cvm:resolucoes:{n}", f"Resolução CVM {n}", f"https://x/{n}") for n in range(12)]

    class C:
        id = "cvm_normas"

        def search(self, q, **f):
            return cands

    visto = []
    monkeypatch.setattr(svc, "_get", lambda _id: C())
    monkeypatch.setattr(svc, "_index_candidate_legis", lambda c, cand: visto.append(cand) or {"capture_id": "x", "trecho": ""})
    out = svc._buscar_normas("cvm_normas", "fato relevante", None)
    assert len(visto) == 5 and (out["indexados"], out["nao_indexados"], out["status"]) == (5, 7, "parcial")
    assert sum(1 for i in out["itens"] if i.get("nao_indexado")) == 7
    visto.clear()
    out = svc._buscar_normas("cvm_normas", "x", None, orcamento_s=0)  # esgotado já na busca inicial (rodada 5)
    assert not visto and out["status"] == "indisponivel" and out["motivo"] == "orcamento"


def test_obra_revogada_com_documento_sem_estrutura_aparece_revogada(svc):
    import io
    import zipfile

    s = io.BytesIO()
    with zipfile.ZipFile(s, "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   "<w:body><w:p><w:r><w:t>Resolução CVM nº 85, de 29 de março de 2022</w:t></w:r></w:p><w:p><w:r><w:t>Texto corrido sem artigos.</w:t></w:r></w:p></w:body></w:document>")
    body = s.getvalue()
    rw = svc.indexar_obra(
        source_id="cvm_normas", work_key=WorkKey("cvm", "resolucao", "85", 2022), document=parse_cvm_docx(body), body=body,
        url="https://conteudo.cvm.gov.br/legislacao/resolucoes/anexos/001/resol085.pdf",
        fetched_at=_agora(), work_date="2022-03-29", label="Resolução CVM 85")
    cand = Candidate("cvm_normas", "cvm:resolucoes:85", "Resolução CVM 85",
                     "https://conteudo.cvm.gov.br/legislacao/resolucoes/resol085.html")
    pagina = _PAGINA.format(titulo="Resolução CVM 85",
                            extra="<p>REVOGADA pela Resolução CVM 175, de 23 de dezembro de 2022.</p>")
    situacao.registrar_cvm(svc.conn, svc.home, _CvmFake(pagina.encode()), cand, rw)
    out = svc.verificar_citacao("art. 1º da Resolução CVM 85/2022")
    assert out["temporal"]["status"] == "divergent"
    assert out["temporal"]["reason_code"] == "OBRA_REVOGADA_NA_FONTE"
