"""B2-03: o `truncado`/`status` de topo agregam os cortes registrados em `cobertura` (decisão 0055)."""
from freoa_verifica.connectors.base import CandidateList
from freoa_verifica.service import Verifica
from tests.contrato.harness import semear
from tests.test_p1_cobertura import _cnj, _cob, svc, tjdft_conn  # noqa: F401


def test_textual_corte_no_limite_local_da_fonte_marca_o_topo(svc, tjdft_conn, monkeypatch):
    # fonte que não é "sempre ao vivo": a leitura para ao atingir o limite e o resto fica sem ler
    monkeypatch.setattr(type(tjdft_conn), "coverage",{"busca_textual": True, "busca_textual_ao_vivo": True})
    r = svc.pesquisar_jurisprudencia("sociedade", tribunais=["tjdft"], limite=1)
    c = _cob(r, "TJDFT")
    assert c["truncado_local"] is True
    assert r["truncado"] is True and r["status"] == "parcial"


def test_cnj_total_remoto_maior_que_lido_nao_e_negativa_categorica(svc, tjdft_conn, monkeypatch):
    monkeypatch.setattr(tjdft_conn, "search", lambda q, **kw: CandidateList([], total=50, total_exato=True))
    r = svc.pesquisar_jurisprudencia(_cnj("0713166", "2018", "807", "0000"))
    assert _cob(r, "TJDFT")["truncado_remoto"] is True
    assert r["truncado"] is True
    assert r["status"] == "nao_confirmado_no_acervo" and "truncada" in r["aviso"]


def test_cnj_leitura_completa_sem_resultado_continua_categorica(svc, tjdft_conn, monkeypatch):
    monkeypatch.setattr(tjdft_conn, "search", lambda q, **kw: CandidateList([], total=0, total_exato=True))
    r = svc.pesquisar_jurisprudencia(_cnj("0713166", "2018", "807", "0000"))
    assert r["truncado"] is False and r["status"] == "nao_encontrado_na_fonte"


def test_numero_agrega_a_cobertura(svc):
    semear(svc)
    r = svc.pesquisar_jurisprudencia("REsp 900.001")
    assert r["truncado"] is False
    corte = dict(r["cobertura"][0], truncado_local=True)
    assert Verifica._truncado_da_cobertura([corte]) is True
    assert Verifica._truncado_da_cobertura({"tribunais": []}) is False  # objeto legado do acervo
