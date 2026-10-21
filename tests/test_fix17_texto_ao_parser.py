"""FIX17 (auditoria r13, F-22): todo parser recebe o texto da interpretação única do `Response`.

O Content-Type do `Response` decide; `<meta charset>` divergente no corpo, ou a regra fixa "JSON é UTF-8" de um
conector, não reinterpreta os bytes. Os bytes originais seguem só para captura e hash.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from freoa_verifica.connectors import cvm_normas, tjsp
from freoa_verifica.connectors.bcb import BcbConnector
from freoa_verifica.connectors.cvm_colegiado import CvmColegiadoConnector
from freoa_verifica.connectors.planalto import PlanaltoConnector
from freoa_verifica.connectors.senado import SenadoConnector
from freoa_verifica.connectors.tcu import TcuConnector
from freoa_verifica.connectors.tjdft import _load as tjdft_load
from freoa_verifica.parsers.isolated import parse_isolated
from freoa_verifica.transport import Response

CT_UTF8 = "text/html; charset=utf-8"
META_LATIN1 = '<meta charset="iso-8859-1">'


def _resposta(url: str, corpo: bytes, ctype: str, mime: str = "text/html") -> Response:
    return Response(url, url, 200, {}, corpo, hashlib.sha256(corpo).hexdigest(), "2026-10-20T00:00:00Z", [],
                    mime, content_type=ctype)


PLANALTO = (
    f"<html><head>{META_LATIN1}<title>Lei nº 1</title></head><body>"
    "<p>LEI Nº 1, DE 1 DE JANEIRO DE 2000</p><p>Art. 1º Ação de teste.</p></body></html>"
)


def test_planalto_subprocesso_real_usa_o_content_type_e_nao_o_meta():
    url = "https://www.planalto.gov.br/ccivil_03/leis/l1.htm"
    doc = PlanaltoConnector().parse(_resposta(url, PLANALTO.encode("utf-8"), CT_UTF8))
    textos = " ".join(r.text for p in doc.provisions for r in p.redactions)
    assert "Ação" in textos, textos
    assert "Ã" not in textos + doc.text


def test_planalto_meta_vale_quando_o_cabecalho_nao_declara():
    url = "https://www.planalto.gov.br/ccivil_03/leis/l1.htm"
    doc = PlanaltoConnector().parse(_resposta(url, PLANALTO.encode("iso-8859-1"), "text/html"))
    assert "Ação" in " ".join(r.text for p in doc.provisions for r in p.redactions)


def test_planalto_captura_relida_sem_content_type_usa_a_escada_declarada():
    """Sem Content-Type o Response não veio do transporte: captura relida (cp1252 sem meta, como a real da LSA)."""
    corpo = PLANALTO.replace(META_LATIN1, "").encode("cp1252")
    doc = PlanaltoConnector().parse(_resposta("https://www.planalto.gov.br/ccivil_03/leis/l1.htm", corpo, ""))
    assert "Ação" in " ".join(r.text for p in doc.provisions for r in p.redactions)
    assert "ENCODING_FALLBACK" in {i.code for i in doc.issues}


def test_filho_com_texto_nao_redetecta_charset():
    """`--texto`: o subprocesso recebe o texto decidido; o `<meta>` dentro dele não é reaplicado."""
    base = "https://www.planalto.gov.br/ccivil_03/leis/l1.htm"
    doc = parse_isolated("planalto", PLANALTO, 60.0, base_url=base)
    assert "Ação" in " ".join(r.text for p in doc.provisions for r in p.redactions)
    # Caminho anterior (bytes ao filho, sem Content-Type): o <meta> reinterpretava — é o que o teste acima exclui.
    legado = parse_isolated("planalto", PLANALTO.encode("utf-8"), 60.0, base_url=base)
    assert "AÃ§Ã£o" in " ".join(r.text for p in legado.provisions for r in p.redactions)


def test_cvm_colegiado_parse_com_meta_divergente():
    html = (f"<html><head>{META_LATIN1}</head><body><h2>Ata</h2><article><p class='text-uppercase'>"
            "PROC. 19957.000123/2024-11 Ação</p></article></body></html>").encode("utf-8")
    resp = _resposta("https://conteudo.cvm.gov.br/decisoes/2024/20240131_R05.html", html, CT_UTF8)
    assunto = CvmColegiadoConnector().parse(resp).metadata["decisoes"][0]["assunto"]
    assert "Ação" in assunto and "Ã" not in assunto


def test_cvm_normas_ato_html_com_meta_divergente():
    html = (f"<html><head>{META_LATIN1}</head><body><article><h2>Resolução CVM nº 1</h2>"
            "<section class='contentArticle'><p>Art. 1º Ação de teste.</p></section></article></body></html>"
            ).encode("utf-8")
    url = "https://conteudo.cvm.gov.br/legislacao/resolucoes/resol001.html"
    doc = cvm_normas.CvmNormasConnector().parse(_resposta(url, html, CT_UTF8))
    assert "Ã" not in doc.text + doc.title and "Ação" in doc.text and doc.title == "Resolução CVM nº 1"


def test_tjsp_resultados_com_meta_divergente():
    html = (f"<html><head>{META_LATIN1}</head><body>"
            '<input id="totalResultadoAbaRetornoFiltro-A" value="1">'
            '<table><tr class="fundocinza1"><td><a class="esajLinkLogin downloadEmenta" cdacordao="1">'
            "1000000-00.2024.8.26.0000</a></td><td>Ação de cobrança</td></tr></table></body></html>").encode("utf-8")
    resp = _resposta("https://esaj.tjsp.jus.br/cjsg/resultadoCompleta.do", html, CT_UTF8)
    texto = tjsp.texto_do_response(resp)
    assert "Ação" in texto and "Ã" not in texto


# --- JSON: o charset do cabeçalho vale também aqui, como na detecção de desafio --------------------------------

LATIN1_JSON = "application/json; charset=iso-8859-1"


def test_senado_parse_json_latin1_declarado():
    payload = {"documentos": {"documento": [{"normaNome": "Lei nº 1 - Ação", "ementa": "Ação de teste"}]}}
    corpo = json.dumps(payload, ensure_ascii=False).encode("iso-8859-1")
    url = "https://legis.senado.leg.br/dadosabertos/legislacao/lista"
    doc = SenadoConnector().parse(_resposta(url, corpo, LATIN1_JSON, "application/json"))
    assert doc.title == "Lei nº 1 - Ação" and doc.ementa == "Ação de teste"


def test_tcu_parse_json_latin1_declarado():
    item = [{"key": "AC-1-2024-P", "tipo": "ACÓRDÃO", "numeroAcordao": "1", "anoAcordao": "2024",
             "colegiado": "Plenário", "relator": "Fulano", "dataSessao": "01/01/2024",
             "sumario": "Ação de teste", "acordao": "Ação"}]
    corpo = json.dumps(item, ensure_ascii=False).encode("iso-8859-1")
    url = "https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos"
    dec = TcuConnector().parse(_resposta(url, corpo, LATIN1_JSON, "application/json"))
    assert "Ã" not in (dec.ementa or "") + dec.text and "Ação" in (dec.ementa or "") + dec.text


def test_tjdft_load_json_latin1_declarado():
    corpo = json.dumps({"registros": [], "ementa": "Ação"}, ensure_ascii=False).encode("iso-8859-1")
    data = tjdft_load(_resposta("https://jurisdf.tjdft.jus.br/api/v1/pesquisa", corpo, LATIN1_JSON,
                                "application/json"))
    assert data["ementa"] == "Ação"


def test_bcb_parse_subprocesso_recebe_texto():
    payload = {"conteudo": [{"Titulo": "Resolução CMN nº 1", "Tipo": "Resolução CMN", "Numero": 1,
                             "Data": "2024-01-01T00:00:00", "Texto": "<p>Art. 1º Ação de teste.</p>",
                             "Revogado": False, "Cancelado": False}]}
    corpo = json.dumps(payload, ensure_ascii=False).encode("iso-8859-1")
    url = "https://www.bcb.gov.br/api/conteudo/app/normativos/exibenormativo?p1=Resolução CMN&p2=1"
    doc = BcbConnector().parse(_resposta(url, corpo, LATIN1_JSON, "application/json"))
    assert "Ã" not in doc.text + doc.title and "Ação" in doc.text + doc.title
