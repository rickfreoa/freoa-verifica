"""Seleção temporal — RCVM 160 art. 2º, XVI e regras R1–R6."""

from __future__ import annotations

from freoa_verifica.parsers.cvm_docx import parse_cvm_docx
from freoa_verifica.parsers.model import Annotation, Provision, Redaction
from freoa_verifica.temporal import RULES, select
from tests.fixture_util import load_fixture

WORK_DATE_RCVM160 = "2022-07-13"


def _rcvm160_inc16():
    doc = parse_cvm_docx(load_fixture("cvm_resol_160_consolid_docx"))
    prov = doc.provision("art2.inc16")
    assert prov is not None
    return prov


def test_rules_documented():
    for key in ("R1", "R2", "R3", "R4", "R5", "R6"):
        assert key in RULES
        assert len(RULES[key]) > 20


def test_rcvm160_data_seleciona_riscada():
    """data 2022-08-01 → redação riscada (original, início 2022-07-13)."""
    prov = _rcvm160_inc16()
    res = select(prov, "2022-08-01", work_date=WORK_DATE_RCVM160)
    assert res.redaction_id is not None
    red = next(r for r in prov.redactions if f"r{r.order}" == res.redaction_id)
    assert red.struck is True
    assert res.interval is not None
    assert res.interval.start == WORK_DATE_RCVM160
    assert res.interval.end == "2022-11-29"
    assert res.status == "verified"


def test_rcvm160_data_seleciona_vigente():
    """data 2023-01-01 → redação vigente, mas vacatio impede verified."""
    prov = _rcvm160_inc16()
    res = select(prov, "2023-01-01", work_date=WORK_DATE_RCVM160)
    assert res.redaction_id is not None
    red = next(r for r in prov.redactions if f"r{r.order}" == res.redaction_id)
    assert red.struck is False
    assert res.interval is not None
    assert res.interval.start == "2022-11-29"
    assert res.interval.end is None
    assert "vacatio_nao_verificada" in res.flags
    assert res.status == "unknown"


def test_mudar_data_muda_redacao():
    prov = _rcvm160_inc16()
    a = select(prov, "2022-08-01", work_date=WORK_DATE_RCVM160)
    b = select(prov, "2023-01-01", work_date=WORK_DATE_RCVM160)
    assert a.redaction_id != b.redaction_id
    assert a.redaction_id is not None and b.redaction_id is not None


def test_temporal_verified_so_limites_conhecidos():
    """Sem data completa no ato → unknown."""
    prov = Provision(
        path="art1",
        label="Art. 1º",
        scope="",
        redactions=[
            Redaction(
                text="texto original",
                struck=True,
                order=0,
                annotations=[],
            ),
            Redaction(
                text="texto novo",
                struck=False,
                order=1,
                annotations=[
                    Annotation(
                        kind="redacao_dada",
                        raw="Redação dada pela Lei nº 10.303, de 2001",
                        act_ref="Lei nº 10.303, de 2001",
                        act_date=None,
                    )
                ],
            ),
        ],
    )
    res = select(prov, "2020-01-01", work_date="1976-12-15")
    # Sucessor só com ano → fim desconhecido → unknown (nunca verified na antiga)
    assert res.status == "unknown"
    # Mesmo antes de 2001: fim desconhecido impede verified
    res2 = select(prov, "1990-01-01", work_date="1976-12-15")
    assert res2.status == "unknown"
    assert "fim_desconhecido" in (res2.flags or []) or res2.reason == "FIM_DESCONHECIDO"


def test_r5_needs_judgment():
    prov = Provision(
        path="art1",
        label="Art. 1",
        scope="",
        redactions=[
            Redaction(
                text="x",
                struck=False,
                order=0,
                annotations=[
                    Annotation(kind="vide", raw="Vide Lei X", act_ref="Lei X"),
                ],
            )
        ],
    )
    res = select(prov, "2020-01-01", work_date="2010-01-01")
    assert res.needs_judgment is True
    assert res.status == "unknown"
    assert "R5" in res.rules_applied


def test_r6_vacatio_flag():
    prov = Provision(
        path="art1",
        label="Art. 1",
        scope="",
        redactions=[
            Redaction(text="a", struck=True, order=0),
            Redaction(
                text="b",
                struck=False,
                order=1,
                annotations=[
                    Annotation(
                        kind="redacao_dada",
                        raw="Redação dada pela Lei nº 1, de 1º de janeiro de 2020",
                        act_ref="Lei nº 1, de 1º de janeiro de 2020",
                        act_date="2020-01-01",
                    )
                ],
            ),
        ],
    )
    res = select(prov, "2021-01-01", work_date="2010-01-01")
    assert "vacatio_nao_verificada" in res.flags
    assert res.status == "unknown"


def test_r6_vigencia_na_publicacao():
    prov = Provision(
        path="art1",
        label="Art. 1",
        scope="",
        redactions=[
            Redaction(text="a", struck=True, order=0),
            Redaction(
                text="b",
                struck=False,
                order=1,
                annotations=[
                    Annotation(
                        kind="redacao_dada",
                        raw="Redação dada pela Lei Y",
                        act_ref="Lei Y",
                        act_date="2020-06-01",
                    )
                ],
            ),
        ],
    )
    res = select(
        prov,
        "2021-01-01",
        work_date="2010-01-01",
        amending_act_texts={
            "Lei Y": "Esta Lei entra em vigor na data de sua publicação."
        },
    )
    assert "publicacao_dou_nao_verificada" in res.flags
    assert "vacatio_nao_verificada" not in res.flags


def test_revogado():
    prov = Provision(
        path="art1",
        label="Art. 1",
        scope="",
        redactions=[
            Redaction(
                text="texto",
                struck=False,
                order=0,
                annotations=[
                    Annotation(
                        kind="revogado",
                        raw="Revogado pela Lei Z",
                        act_ref="Lei Z",
                        act_date="2022-01-01",
                    )
                ],
            )
        ],
    )
    res = select(prov, "2023-01-01", work_date="2010-01-01")
    assert res.status == "revogado"


def test_nao_existia():
    prov = _rcvm160_inc16()
    res = select(prov, "2020-01-01", work_date=WORK_DATE_RCVM160)
    assert res.status == "nao_existia"
