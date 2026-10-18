"""Regressões M3 — casos sintéticos da auditoria (itens 2–8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from freoa_verifica.aliases import WorkKey
from freoa_verifica.citation import DecisionKey, extract, parse_one
from freoa_verifica.parsers.model import (
    Annotation,
    Issue,
    ParsedDocument,
    Provision,
    Redaction,
)
from freoa_verifica.parsers.planalto import parse_planalto
from freoa_verifica.temporal import select
from freoa_verifica.textcmp import compare
from freoa_verifica.verify import MemoryResolver, ResolvedWork, verificar


# ---------------------------------------------------------------------------
# Item 2 — nota editorial não entra na redação
# ---------------------------------------------------------------------------


def test_item2_nota_editorial_separada():
    """Caso auditoria: <p>Nota editorial: venda dispensada de autorização.</p>"""
    html = (
        "<html><body>"
        "<p>LEI Nº 9.999, DE 1º DE JANEIRO DE 2020.</p>"
        "<p>Art. 1º A venda depende de autorização prévia.</p>"
        "<p>Nota editorial: venda dispensada de autorização.</p>"
        "</body></html>"
    )
    doc = parse_planalto(html)
    prov = doc.provision("art1")
    assert prov is not None
    text = prov.redactions[0].text
    assert "Nota editorial" not in text
    assert "venda depende" in text.lower()
    assert any(
        "Nota editorial" in b.text for b in doc.editorial_blocks
    ), doc.editorial_blocks


# ---------------------------------------------------------------------------
# Item 3 — verificador respeita bloqueios do parser
# ---------------------------------------------------------------------------


def _rw(
    *,
    path: str,
    redactions: list[Redaction],
    quarantined: bool = False,
    ambiguous: bool = False,
    fetched_at: str | None = None,
) -> ResolvedWork:
    issues = []
    if quarantined:
        issues.append(
            Issue("TRUNCATED", None, "quarentena sintética", blocking_scope="document")
        )
    prov = Provision(
        path=path,
        label="Art. 1",
        scope="",
        redactions=redactions,
        ambiguous=ambiguous,
    )
    doc = ParsedDocument(
        profile="test",
        parser_version="0",
        title="Lei teste",
        ementa=None,
        text=redactions[0].text if redactions else "",
        provisions=[prov],
        issues=issues,
    )
    now = datetime.now(timezone.utc).isoformat()
    return ResolvedWork(
        work_id="w1",
        work_key=WorkKey("federal", "lei", "9999", 2020),
        document=doc,
        work_date="2020-01-01",
        capture_id="c1",
        sha256="abc",
        url="https://example.test/lei",
        fetched_at=fetched_at or now,
        quarantined=doc.quarantined,
    )


def test_item3_ambiguous_never_verified():
    """Duas redações concorrentes ambiguous=True → identity/text/temporal ≠ verified."""
    reds = [
        Redaction(text="Redação A concorrente.", struck=False, order=0),
        Redaction(text="Redação B concorrente.", struck=False, order=1),
    ]
    rw = _rw(path="art1", redactions=reds, ambiguous=True)
    resolver = MemoryResolver()
    resolver.add(rw)
    res = verificar(
        "art. 1º da Lei 9.999/2020",
        trecho="Redação A concorrente.",
        data="2024-01-01",
        resolver=resolver,
    )
    assert res.identity.status == "ambiguous"
    assert res.text.status != "verified"
    assert res.temporal.status != "verified"


def test_item3_quarantined_never_verified():
    """Documento quarentenado → temporal/text nunca verified."""
    reds = [Redaction(text="Texto único vigente.", struck=False, order=0)]
    rw = _rw(path="art1", redactions=reds, quarantined=True)
    resolver = MemoryResolver()
    resolver.add(rw)
    res = verificar(
        "art. 1º da Lei 9.999/2020",
        trecho="Texto único vigente.",
        data=None,
        resolver=resolver,
    )
    assert res.identity.status != "verified"
    assert res.text.status != "verified"
    assert res.temporal.status != "verified"


# ---------------------------------------------------------------------------
# Item 4 — fim desconhecido ≠ intervalo aberto
# ---------------------------------------------------------------------------


def test_item4_ano_so_nao_seleciona_antiga():
    """Cadeia Texto antigo → Texto novo (ano só): em 2026 antiga ≠ verified."""
    prov = Provision(
        path="art1",
        label="Art. 1",
        scope="",
        redactions=[
            Redaction(text="Texto antigo", struck=True, order=0),
            Redaction(
                text="Texto novo",
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
    res = select(prov, "2026-01-01", work_date="1976-12-15")
    assert res.status == "unknown"
    # nunca selecionar a antiga como vigente
    if res.redaction_id is not None:
        red = next(r for r in prov.redactions if f"r{r.order}" == res.redaction_id)
        assert red.text != "Texto antigo" or red.struck is False


def test_item4_revogacao_sem_data_historica_unknown():
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
                        act_date=None,
                    )
                ],
            )
        ],
    )
    # data histórica → unknown
    res_h = select(prov, "2015-01-01", work_date="2010-01-01")
    assert res_h.status == "unknown"
    # data atual/omitida → revogado
    res_now = select(
        prov,
        None,
        work_date="2010-01-01",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    assert res_now.status == "revogado"


# ---------------------------------------------------------------------------
# Item 5 — R2/R3/R6 / vacatio / inclusão futura / omitida=hoje
# ---------------------------------------------------------------------------


def test_item5_vacatio_impede_verified():
    """Alteração 01/10/2026 com vacatio → verified em 02/10 bloqueado."""
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
                        raw="Redação dada pela Lei X, de 1º de outubro de 2026",
                        act_ref="Lei X",
                        act_date="2026-10-01",
                    )
                ],
            ),
        ],
    )
    res = select(prov, "2026-10-02", work_date="2010-01-01")
    assert "vacatio_nao_verificada" in res.flags
    assert res.status == "unknown"


def test_item5_inclusao_futura_nao_existia():
    """Inclusão em 2099 com data omitida (=hoje) → nao_existia."""
    prov = Provision(
        path="art1",
        label="Art. 1",
        scope="",
        redactions=[
            Redaction(
                text="incluído no futuro",
                struck=False,
                order=0,
                annotations=[
                    Annotation(
                        kind="incluido",
                        raw="Incluído pela Lei Futura",
                        act_ref="Lei Futura",
                        act_date="2099-01-01",
                    )
                ],
            )
        ],
    )
    res = select(
        prov,
        None,
        work_date="2020-01-01",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    assert res.status == "nao_existia"


def test_item5_revogado_2020_consulta_omitida():
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
                        raw="Revogado",
                        act_ref="Lei Z",
                        act_date="2020-01-01",
                    )
                ],
            )
        ],
    )
    res = select(
        prov,
        None,
        work_date="2010-01-01",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    assert res.status == "revogado"


# ---------------------------------------------------------------------------
# Item 6 — revogação parcial
# ---------------------------------------------------------------------------


def test_item6_revogacao_parcial_unknown():
    """Injetei revogacao_parcial datada: resultado unknown (não verified)."""
    prov = Provision(
        path="art1",
        label="Art. 1",
        scope="",
        redactions=[
            Redaction(
                text="texto parcial",
                struck=False,
                order=0,
                annotations=[
                    Annotation(
                        kind="revogacao_parcial",
                        raw="Revogação parcial pela Lei W, de 1º de janeiro de 2020",
                        act_ref="Lei W",
                        act_date="2020-01-01",
                    )
                ],
            )
        ],
    )
    res = select(prov, "2021-01-01", work_date="2010-01-01")
    assert res.status == "unknown"
    assert "revogacao_parcial" in res.flags


# ---------------------------------------------------------------------------
# Item 7 — fronteira lexical
# ---------------------------------------------------------------------------


def test_item7_match_dentro_de_numero():
    """Trecho '10 dias.' contra 'Prazo de 210 dias.' não é match."""
    cmp = compare("10 dias.", "Prazo de 210 dias.")
    assert cmp.status != "match"


def test_item7_match_com_fronteira():
    cmp = compare("210 dias.", "Prazo de 210 dias.")
    assert cmp.status == "match"


# ---------------------------------------------------------------------------
# Item 8 — 30 frases autorais de pareceres societários
# ---------------------------------------------------------------------------

# (frase, esperados) — esperados: predicados sobre extract()
AUDIT_PHRASES_30 = [
    # 1–6 exemplos da auditoria + variantes
    (
        "nos termos do art. 118, § 8º, da Lei das S.A.",
        lambda cs: any(
            c.path == "art118.par8" and c.work and c.work.number == "6404" for c in cs
        ),
    ),
    (
        "REsp 1.794.734/SP",
        lambda cs: any(
            c.decision and c.decision.court == "stj" and c.decision.number == "1794734"
            for c in cs
        ),
    ),
    (
        "Súmula 7 do STJ",
        lambda cs: any(
            c.kind == "sumula" and c.decision and c.decision.court == "stj" for c in cs
        ),
    ),
    (
        "Resolução CVM 80, art. 33, disciplina o registro de emissores",
        lambda cs: any(
            c.path == "art33" and c.work and c.work.number == "80" for c in cs
        )
        and not any(c.path and "inc501" in c.path for c in cs),
    ),
    (
        "Tema 1.046/STF",
        lambda cs: any(
            c.kind == "tema" and c.decision and c.decision.court == "stf" for c in cs
        ),
    ),
    (
        "Lei 14.195/21",
        lambda cs: any(
            c.work and c.work.number == "14195" and c.work.year == 2021 for c in cs
        ),
    ),
    # 7–12 tribunal contextual / TCU / LRF / CC-CF
    (
        "HC 234.567 do STJ",
        lambda cs: any(
            c.decision and c.decision.court == "stj" and c.decision.class_ == "HC"
            for c in cs
        ),
    ),
    (
        "HC 234.567/STJ",
        lambda cs: any(c.decision and c.decision.court == "stj" for c in cs),
    ),
    (
        "Acórdão 1.234/2020-TCU-Plenário",
        lambda cs: any(
            c.decision
            and c.decision.year == 2020
            and c.decision.organ
            and "Plen" in c.decision.organ
            for c in cs
        ),
    ),
    (
        "Acórdão 1.234/2021-TCU-Plenário",
        lambda cs: any(c.decision and c.decision.year == 2021 for c in cs),
    ),
    (
        "nos termos da LRF (LC 101/2000), art. 1º",
        lambda cs: any(
            c.work and c.work.kind == "lei_complementar" and c.work.number == "101"
            for c in cs
        )
        and not any(
            c.work and c.work.number == "11101" for c in cs
        ),
    ),
    (
        "LRF",
        lambda cs: len([c for c in cs if "alias_ambiguo" in c.flags]) == 2
        and all(c.confidence == "provavel" for c in cs if "alias_ambiguo" in c.flags),
    ),
    # 13–18 CC/CF e anexos
    (
        "CC: fulano de tal, CPF 000",
        lambda cs: not any(c.work and c.work.number == "10406" for c in cs),
    ),
    (
        "CF. página 12 do relatório",
        lambda cs: not any(
            c.work and c.work.kind == "constituicao" for c in cs
        ),
    ),
    (
        "art. 5º, II, da CF",
        lambda cs: any(
            c.work and c.work.kind == "constituicao" and c.path and "art5" in c.path
            for c in cs
        ),
    ),
    (
        "art. 1.228 do CC",
        lambda cs: any(
            c.work and c.work.number == "10406" and c.path == "art1228" for c in cs
        ),
    ),
    (
        "Anexo II, art. 3º da Resolução CVM 160",
        lambda cs: any(
            c.path == "anexo-ii/art3" and c.work and c.work.number == "160" for c in cs
        ),
    ),
    (
        "art. 1º do Anexo A da LSA",
        lambda cs: any(c.path == "anexo-a/art1" for c in cs),
    ),
    # 19–30 pareceres societários diversos
    (
        "Conforme o art. 254-A da Lei 6.404/76, a alienação de controle",
        lambda cs: any(c.path == "art254-A" for c in cs),
    ),
    (
        "nos termos do art. 116 da LSA",
        lambda cs: any(c.path == "art116" and c.work.number == "6404" for c in cs),
    ),
    (
        "Resolução CVM nº 80/2022, art. 33",
        lambda cs: any(c.path == "art33" and not (c.path or "").startswith("art33.inc") for c in cs),
    ),
    (
        "ADI 2.591 do STF",
        lambda cs: any(c.decision and c.decision.court == "stf" for c in cs),
    ),
    (
        "Súmula Vinculante 13",
        lambda cs: any(
            c.kind == "sumula" and c.decision and "Vinculante" in c.decision.class_
            for c in cs
        ),
    ),
    (
        "Tema Repetitivo 1.076/STJ",
        lambda cs: any(c.decision and c.decision.court == "stj" for c in cs),
    ),
    (
        "Parecer de Orientação CVM nº 35",
        lambda cs: any(
            c.work and c.work.kind == "parecer_orientacao" for c in cs
        ),
    ),
    (
        "arts. 116 e 117 da Lei das S.A.",
        lambda cs: {"art116", "art117"} <= {c.path for c in cs if c.path},
    ),
    (
        "inciso II do art. 1º da Lei 6.404/76",
        lambda cs: any(c.path == "art1.inc2" for c in cs),
    ),
    (
        "Lei Complementar 101/2000 (LRF)",
        lambda cs: any(
            c.work and c.work.number == "101" and c.work.kind == "lei_complementar"
            for c in cs
        )
        and not any(
            c.work and c.work.number == "11101" and "alias_ambiguo" not in c.flags
            for c in cs
            if c.raw == "LRF"
        ),
    ),
    (
        "o controle acionário, nos termos do art. 116, parágrafo único, da LSA",
        lambda cs: any(c.path == "art116.parunico" for c in cs),
    ),
    (
        "Acórdão TCU nº 500/2019 – 1ª Câmara",
        lambda cs: any(
            c.decision
            and c.decision.year == 2019
            and c.decision.number == "500"
            for c in cs
        ),
    ),
]


@pytest.mark.parametrize(
    "frase,pred",
    AUDIT_PHRASES_30,
    ids=[f"frase{i+1}" for i in range(len(AUDIT_PHRASES_30))],
)
def test_item8_trinta_frases_auditoria(frase, pred):
    cites = extract(frase)
    assert pred(cites), (frase, [(c.raw, c.path, c.work, c.decision, c.flags) for c in cites])


def test_item8_tcu_anos_chaves_distintas():
    a = parse_one("Acórdão 1.234/2020-TCU-Plenário")
    b = parse_one("Acórdão 1.234/2021-TCU-Plenário")
    assert a and b and a.decision and b.decision
    assert (a.decision.number, a.decision.year) != (b.decision.number, b.decision.year)
    assert a.decision.year == 2020 and b.decision.year == 2021


def test_item8_count_30():
    assert len(AUDIT_PHRASES_30) == 30


# ---------------------------------------------------------------------------
# vigente_na_fonte / captura desatualizada
# ---------------------------------------------------------------------------


def test_vigente_na_fonte_captura_fresca():
    prov = Provision(
        path="art1",
        label="Art. 1",
        scope="",
        redactions=[Redaction(text="vigente", struck=False, order=0)],
    )
    res = select(
        prov,
        None,
        work_date="2020-01-01",
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    assert res.status == "vigente_na_fonte"


def test_captura_desatualizada():
    prov = Provision(
        path="art1",
        label="Art. 1",
        scope="",
        redactions=[Redaction(text="vigente", struck=False, order=0)],
    )
    old = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    res = select(prov, None, work_date="2020-01-01", fetched_at=old)
    assert res.status == "unknown"
    assert res.reason == "CAPTURA_DESATUALIZADA"
