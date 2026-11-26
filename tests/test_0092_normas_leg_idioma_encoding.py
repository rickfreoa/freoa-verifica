"""0092, teste em Debian (colega): CF com três "Current" (pt, en, fr) e lei de versão única com `encoding` objeto.

Fixtures sintéticas geradas por payload()/html() de tests/test_normas_leg_0085.py; finalidade: contrato offline.
Não são capturas do portal; nenhuma requisição real.
"""
from __future__ import annotations

import pytest

from freoa_verifica import revalidacao as rev
from freoa_verifica.aliases import WorkKey
from freoa_verifica.connectors.base import Unavailable
from tests.test_normas_leg_0085 import KEY, TEXT, ambiente, payload

OUTRO = TEXT.replace("12345678", "87654321")
TERCEIRO = TEXT.replace("12345678", "11111111")


def _tres_idiomas():
    data = payload()
    base = data["encoding"][0]
    data["encoding"] = [{**base, "inLanguage": "en", "contentUrl": OUTRO.replace("/public/", "/")},
                        {**base, "inLanguage": "pt"},
                        {**base, "inLanguage": "fr", "contentUrl": TERCEIRO.replace("/public/", "/")}]
    return data


def test_current_em_tres_idiomas_escolhe_o_portugues(tmp_path):
    con, tr, _ = ambiente(tmp_path, data=_tres_idiomas())
    cand = con.resolve(KEY)
    assert [e["inLanguage"] for e in cand.metadata["encoding"]] == ["en", "pt", "fr"]  # idioma guardado
    doc = con.parse(con.fetch(cand))
    assert TEXT in tr.urls and OUTRO not in tr.urls and TERCEIRO not in tr.urls
    assert '"inLanguage": "pt"' in doc.editorial_blocks[-1].text


def test_dois_current_em_portugues_continua_ambiguo(tmp_path):
    data = _tres_idiomas()
    data["encoding"][0]["inLanguage"] = "pt"
    con, _, _ = ambiente(tmp_path, data=data)
    with pytest.raises(Unavailable, match="versao_ausente_ou_ambigua"):
        con.fetch(con.resolve(KEY))


def test_so_idiomas_estrangeiros_nao_escolhe_traducao(tmp_path):
    data = _tres_idiomas()
    data["encoding"] = [data["encoding"][0], data["encoding"][2]]
    con, tr, _ = ambiente(tmp_path, data=data)
    with pytest.raises(Unavailable, match="versao_ausente_ou_ambigua"):
        con.fetch(con.resolve(KEY))
    assert OUTRO not in tr.urls and TERCEIRO not in tr.urls


def test_encoding_objeto_unico_e_lido_como_lista(tmp_path):
    data = payload()
    data["encoding"] = data["encoding"][0]  # obra de versão única (ex.: Lei 15.177/2025)
    con, tr, _ = ambiente(tmp_path, data=data)
    cand = con.resolve(KEY)
    assert len(cand.metadata["encoding"]) == 1
    assert con.parse(con.fetch(cand)).provisions


@pytest.mark.parametrize("enc", ["texto", 3, [1]])
def test_encoding_de_outro_tipo_continua_recusado(tmp_path, enc):
    data = payload()
    data["encoding"] = enc
    con, _, _ = ambiente(tmp_path, data=data)
    with pytest.raises(Unavailable, match="resposta_inesperada"):
        con.resolve(KEY)


def test_revalidacao_aceita_encoding_objeto_e_le_o_sinal():
    lei = WorkKey("federal", "lei", "6404", 1976)
    meta = {"legislationIdentifier": "urn:lex:br:federal:lei:1976-12-15;6404", "dateModified": "2025-01-01",
            "encoding": {"version": "Current", "inLanguage": "pt",
                         "encodesCreativeWork": {"@id": "https://normas.leg.br/?urn=x@2024-10-01;versao.current"}}}
    assert rev._validar_metadados_obra(meta, lei) is None
    assert rev.sinal_de_metadados(meta)["date_modified"] == "2025-01-01"
    assert rev._validar_metadados_obra({**meta, "encoding": "texto"}, lei) == "metadados_invalidos"
