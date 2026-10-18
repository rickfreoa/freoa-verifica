"""Estrutura inferida de PDF da CVM (1.1.0): artigos endereçáveis, cabeçalhos fora."""
from freoa_verifica.parsers.html_devices import parse_html_devices
from freoa_verifica.parsers.pdf_dispositivos import como_html, paragrafos

CAB = "COMISSÃO DE VALORES MOBILIÁRIOS"
PAGINAS = [
    f"{CAB}\nRESOLUÇÃO CVM Nº 999, DE 1º DE JANEIRO DE 2030\nDispõe sobre teste.\nArt. 1º Esta Resolução\ndispõe sobre o teste.\n1",
    f"{CAB}\nArt. 2º O emissor deve:\nI – divulgar fato\nrelevante; e\nII – manter cadastro.\n2",
    f"{CAB}\n§ 1º O prazo é de sub-\nrogação.\nParágrafo único. Vale o\ndisposto.\nArt. 3º Esta Resolução entra em vigor.\nPágina 3 de 3",
]


def test_paragrafos_juntam_linhas_e_descartam_cabecalho():
    ps = paragrafos(PAGINAS)
    assert CAB not in ps and "1" not in ps
    assert "Art. 1º Esta Resolução dispõe sobre o teste." in ps
    assert "I – divulgar fato relevante; e" in ps
    assert "§ 1º O prazo é de sub-rogação." in ps


def test_numero_no_corpo_nunca_e_descartado():
    # Reprodução do auditor: o número repetido é conteúdo, não rodapé.
    paginas = [f"Art. {n}º O prazo fica limitado a\n100\ndias." for n in (1, 2, 3)]
    assert paragrafos(paginas) == [f"Art. {n}º O prazo fica limitado a 100 dias." for n in (1, 2, 3)]


def test_so_o_numero_da_propria_pagina_sai():
    paginas = ["Art. 1º Texto um.\n1", "Art. 2º Texto dois.\n7", "Art. 3º Texto três.\nPágina 3 de 3"]
    assert paragrafos(paginas) == ["Art. 1º Texto um.", "Art. 2º Texto dois. 7", "Art. 3º Texto três."]


def test_notas_da_cvm_viram_historico_e_citacao_nao_vira_dispositivo():
    from freoa_verifica.parsers.model import RevokedProvision
    import pytest
    cab = f"{CAB}\nRua Sete de Setembro, 111 - Rio de Janeiro/RJ"
    paginas = [
        f"{cab}\nArt. 1º Texto um.\nArt. 2º O prazo é de\n10 dias.\nArt. 2º O prazo é de\n20 dias.\n• Caput com redação dada pela Resolução CVM nº 181, de 28 de março de 2023.\n1",
        f"{cab}\nParágrafo único. Texto antigo.\n• Parágrafo único revogado pela Resolução CVM nº 181, de 28 de março de 2023.\nArt. 3º A Resolução CVM nº 21 passa a vigorar com a seguinte\nredação:\n2",
        f"{cab}\n“Art. 1º Texto de outra norma.\n§ 1º Outro parágrafo.” (N.R.)\nArt. 4º Esta Resolução entra em vigor.\n3",
    ]
    _t, _e, _txt, provs, iss, _am, _ed = parse_html_devices(como_html(paginas))
    from freoa_verifica.parsers.model import ParsedDocument
    doc = ParsedDocument("cvm_pdf", "t", "", None, "", provisions=provs, issues=iss)
    assert doc.current_text("art2").startswith("O prazo é de 20 dias.")
    with pytest.raises(RevokedProvision):
        doc.current_text("art2.parunico")
    assert doc.current_text("art1") == "Texto um."  # o “Art. 1º” citado não duplica o art. 1º
    assert not [i for i in iss if i.code == "DUPLICATE_CURRENT"]
    assert all("Sete de Setembro" not in p.current_redaction().text for p in provs if p.path != "art2.parunico")


def test_dispositivos_enderecaveis():
    _t, _e, _txt, provs, _iss, _am, _ed = parse_html_devices(como_html(PAGINAS))
    caminhos = {p.path for p in provs}
    assert {"art1", "art2", "art3"} <= {c.split(".")[0] for c in caminhos}
    assert any(c.startswith("art2.inc1") or ".inc1" in c for c in caminhos)
