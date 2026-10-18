"""Decisão 0035: data de efeito declarada em Atualizacoes do BCB."""
from datetime import datetime

import pytest

from freoa_verifica import situacao
from tests.test_c2_situacao import _bcb_body, _cit, _indexar_bcb, svc  # noqa: F401


@pytest.mark.parametrize("entrada,ato,efeito", [
    ("Resolução CMN nº 5.295/2026 - Revogação total a partir de 1º/6/2026.", "Resolução CMN nº 5.295/2026", "2026-06-01"),
    ("Resolução BCB nº 487/2025 - Revogação total.", "Resolução BCB nº 487/2025", None),
    ("Resolução BCB nº 450/2025, revogação total.", "Resolução BCB nº 450/2025", None),
    ("Resolução CMN nº 5.019/2022 - Nova redação: art. 76, caput.", None, None),
    ("Resolução CMN nº 1/2020 - Revogação total.;#Resolução CMN nº 2/2021 - Revogação total.", None, None),
    ("Resolução CMN nº 5.100/2023 - Revogação parcial a partir de 1º/10/2023.", None, None),
])
def test_revogacao_declarada(entrada, ato, efeito):
    assert situacao._revogacao_declarada(entrada) == (ato, efeito)


def test_data_anterior_ao_efeito_deixa_de_ser_unknown(svc):  # noqa: F811
    body = _bcb_body(Revogado=True, Atualizacoes="Resolução CMN nº 5.295/2026 - Revogação total a partir de 1º/6/2026.")
    rw, path = _indexar_bcb(svc, body)
    row = svc.conn.execute("SELECT ato_revogador, data_efeito FROM work_status WHERE work_id=?", (rw.work_id,)).fetchone()
    assert tuple(row) == ("Resolução CMN nº 5.295/2026", "2026-06-01")
    antes = svc.verificar_citacao(_cit(path), data="2025-01-10")["temporal"]
    depois = svc.verificar_citacao(_cit(path), data="2026-07-01")["temporal"]
    assert antes["status"] in {"verified", "vigente_na_fonte"} and "REVOGACAO_POSTERIOR" in str(antes)
    assert (depois["status"], depois["reason_code"]) == ("divergent", "OBRA_REVOGADA_NA_FONTE")


def test_anterior_compara_instantes():
    inicio = datetime.now().astimezone()
    assert situacao._anterior("2026-01-01T00:00:00+00:00", inicio)
    assert not situacao._anterior(datetime.now().astimezone().isoformat(), inicio.replace(year=2000))
    assert situacao._anterior(None, inicio)
