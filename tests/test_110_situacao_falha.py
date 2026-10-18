"""1.1.0: falha transitória de releitura não sobrescreve leitura autêntica recente."""
from freoa_verifica import situacao
from freoa_verifica.situacao import WorkStatus
from tests.test_c2_situacao import _bcb_body, _indexar_bcb, svc  # noqa: F401


def _sit(svc, work_id):
    return svc.conn.execute("SELECT situacao FROM work_status WHERE work_id=?", (work_id,)).fetchone()[0]


def test_falha_preserva_leitura_autentica(svc):  # noqa: F811
    rw, _ = _indexar_bcb(svc, _bcb_body())
    ws = situacao._falha_de_leitura(svc.conn, WorkStatus(rw.work_id, "ilegivel", "bcb_indisponivel: http_400"), svc.home)
    assert ws.situacao == "vigente_declarada" and _sit(svc, rw.work_id) == "vigente_declarada"


def test_falha_sem_leitura_anterior_rebaixa(svc):  # noqa: F811
    rw, _ = _indexar_bcb(svc, _bcb_body())
    svc.conn.execute("DELETE FROM work_status WHERE work_id=?", (rw.work_id,))
    svc.conn.commit()
    ws = situacao._falha_de_leitura(svc.conn, WorkStatus(rw.work_id, "ilegivel", "bcb_indisponivel"), svc.home)
    assert ws.situacao == "ilegivel" and _sit(svc, rw.work_id) == "ilegivel"
