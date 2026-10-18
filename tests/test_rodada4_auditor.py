"""Rodada 4 (auditor Codex, parecer sobre ee4ddbe): A7 retroativo, status parcial, orçamento da busca, continuação linear."""
from __future__ import annotations

import glob
import hashlib
import io
import time
import zipfile

import pytest

from freoa_verifica import derivados
from freoa_verifica.connectors.base import Candidate, CandidateList
from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.service import Verifica
from tests.test_fd_busca import _Cvm


def test_a7_home_pre_010_com_candidato_so_no_staging_nao_vira_canonico(tmp_path, monkeypatch):
    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path) as s:
        c = _Cvm()
        s._index_candidate_legis(c, c.search("zebrafish")[0])
        # reproduz o home gerado antes da 010: sem coluna/marca, versões 10 e 11 não aplicadas
        with s.conn:
            s.conn.execute("ALTER TABLE parsed_document DROP COLUMN candidato_ao_vivo")
            s.conn.execute("DELETE FROM schema_version WHERE version>=10")
        assert s.conn.execute("select count(*) from fts_staging").fetchone()[0] >= 1
    with Verifica(tmp_path) as s:  # migra 010 + 011
        assert s.conn.execute("select candidato_ao_vivo from parsed_document").fetchone()[0] == 1
        with s.conn:
            derivados.reindexar_fts(s.conn)  # `acervo reconstruir`
        assert s.conn.execute("select count(*) from fts_redaction where text like '%zebrafish%'").fetchone()[0] == 0
        assert s.conn.execute("select count(*) from fts_staging").fetchone()[0] >= 1
        assert s.buscar_legislacao("zebrafish", fonte="__somente_local__")["itens"] == []


def test_a7_011_idempotente_e_nao_marca_canonicas(tmp_path, monkeypatch):
    from tests.test_f_c_negativa_historico_recibo import _doc, _indexar

    monkeypatch.setenv("FV_OFFLINE", "1")
    with Verifica(tmp_path) as s:
        _indexar(s, _doc())
        with s.conn:
            s.conn.execute("DELETE FROM schema_version WHERE version=11")
    with Verifica(tmp_path) as s:
        assert s.conn.execute("select count(*) from parsed_document where candidato_ao_vivo=1").fetchone()[0] == 0


class _Cands:
    def __init__(self, n, total):
        self.itens = CandidateList([Candidate("cvm_normas", f"k{i}", f"R {i}", f"https://x/{i}") for i in range(n)], total=total)

    id = "cvm_normas"

    def search(self, q, **f):
        return self.itens


def test_busca_truncada_nao_volta_ok(tmp_path, monkeypatch):
    monkeypatch.delenv("FV_OFFLINE", raising=False)
    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s, "_get", lambda _id: _Cands(1, 50))
        monkeypatch.setattr(s, "_index_candidate_legis", lambda c, cand: {"capture_id": "x", "trecho": ""})
        out = s._buscar_normas("cvm_normas", "x", None)
        assert out["truncado"] is True and out["status"] == "parcial"


def test_orcamento_repassado_ao_parse_e_item_nao_indexado(tmp_path, monkeypatch):
    from freoa_verifica.parsers import isolated

    monkeypatch.delenv("FV_OFFLINE", raising=False)
    visto = []

    class Lento(_Cands):
        def fetch(self, cand):
            return None

        def parse(self, resp):
            visto.append(isolated.restante(60.0))
            time.sleep(0.4)  # parse lento: estoura o orçamento de 0,2 s
            from freoa_verifica.connectors.base import Unavailable
            raise Unavailable("docx_nao_processado: timeout")

    with Verifica(tmp_path) as s:
        monkeypatch.setattr(s, "_get", lambda _id: Lento(2, 2))
        out = s._buscar_normas("cvm_normas", "x", None, orcamento_s=0.2)
    assert visto and visto[0] <= 0.2 + 1e-6  # min(restante, timeout do perfil); folga de ponto flutuante
    assert [i.get("motivo") for i in out["itens"]] == ["orcamento", None]
    assert out["itens"][0]["nao_indexado"] and out["itens"][1]["nao_indexado"]
    assert out["status"] == "parcial" and out["nao_indexados"] == 2


def test_parse_isolado_respeita_orcamento_esgotado():
    from freoa_verifica.limites import PRAZO
    from freoa_verifica.parsers.isolated import parse_isolated

    tok = PRAZO.set(time.monotonic() - 1)
    try:
        assert parse_isolated("cvm_docx", b"x", 60.0).quarantined
    finally:
        PRAZO.reset(tok)


def _docx_continuacoes(n):
    ps = "<w:p><w:r><w:t>Art. 1º Fica vedado o ato.</w:t></w:r></w:p>" + "".join(
        f"<w:p><w:r><w:t>continuação {i} do texto</w:t></w:r></w:p>" for i in range(n))
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                   f"<w:body>{ps}</w:body></w:document>")
    return b.getvalue()


def test_continuacoes_escalam_linearmente():
    def t(n):
        raw = _docx_continuacoes(n)
        t0 = time.perf_counter()
        d = parse_cvm_docx(raw)
        return time.perf_counter() - t0, d

    t(500)  # aquecimento
    a, d = t(8000)
    b, _ = t(16000)
    assert d.provisions[0].redactions[0].text.count("continuação") == 8000
    assert b / a < 3.5  # linear dá ~2; quadrático daria ~4


def test_continuacao_fixtures_consolidadas_equivalentes():
    esperado = {  # hash de (path, texto, struck, span) medido antes da mudança (ee4ddbe)
        "044": "25f5148f4f555c7e", "080": "cbca927da10f740a", "160": "e1395c2fe88cdf6d", "175": "923074c4e0317e60"}
    import json
    for f in sorted(glob.glob("tests/fixtures/cvm_resol_*_consolid_docx.docx")):
        d = parse_cvm_docx(open(f, "rb").read())
        pv = [(p.path, [(r.text, r.struck, r.span) for r in p.redactions]) for p in d.provisions]
        h = hashlib.sha256(json.dumps(pv).encode()).hexdigest()[:16]
        assert h == esperado[f.split("resol_")[1][:3]]
