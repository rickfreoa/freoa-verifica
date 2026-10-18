"""Estrutura inferida de PDF da CVM (1.1.0): artigos endereçáveis, cabeçalho fora só por geometria."""
import pytest

from freoa_verifica.parsers.html_devices import parse_html_devices
from freoa_verifica.parsers.model import ParsedDocument, RevokedProvision
from freoa_verifica.parsers.pdf_dispositivos import como_html, paragrafos, textos_de_corpo

CAB = "COMISSÃO DE VALORES MOBILIÁRIOS"


class _Pagina:
    """Página falsa: linhas (y, texto) entregues ao visitor como o pypdf faz."""

    def __init__(self, linhas, altura=842.0):
        self.linhas = linhas
        self.mediabox = type("MB", (), {"height": altura})()

    def extract_text(self, visitor_text=None):
        for y, t in self.linhas:
            visitor_text(t + "\n", [1, 0, 0, 1, 0, 0], [1, 0, 0, 1, 72, y], None, 12)
        return "".join(t + "\n" for _, t in self.linhas)


def _paginas(corpo_por_pagina, cabecalho=True, numero=True):
    out = []
    for n, corpo in enumerate(corpo_por_pagina, 1):
        linhas = [(800, CAB), (780, "Rua Sete de Setembro, 111 - Rio de Janeiro/RJ")] if cabecalho else []
        linhas += [(600 - 14 * i, l) for i, l in enumerate(corpo)]
        if numero:
            linhas.append((40, str(n)))
        out.append(_Pagina(linhas))
    return out


def test_cabecalho_e_numero_saem_por_posicao_e_repeticao():
    textos = textos_de_corpo(_paginas([["Art. 1º Texto um."], ["Art. 2º Texto dois."], ["Art. 3º Texto três."]]))
    assert all(CAB not in t and "Sete de Setembro" not in t for t in textos)
    assert paragrafos(textos) == ["Art. 1º Texto um.", "Art. 2º Texto dois.", "Art. 3º Texto três."]


def test_repeticao_no_corpo_nunca_e_descartada():
    # Reproduções do auditor: linha repetida em todas as páginas e número igual ao da página, no corpo.
    corpo = [[f"Art. {n}º O prazo fica limitado a", "cem dias corridos.", str(n), "dias."] for n in (1, 2, 3)]
    ps = paragrafos(textos_de_corpo(_paginas(corpo)))
    assert ps == [f"Art. {n}º O prazo fica limitado a cem dias corridos. {n} dias." for n in (1, 2, 3)]


def test_sem_cabecalho_repetido_nada_sai():
    corpo = [["Art. 1º Um."], ["Art. 2º Dois."], ["Art. 3º Três."]]
    pags = _paginas(corpo, cabecalho=False, numero=False)
    pags[0].linhas.insert(0, (800, "Texto no alto só desta página."))
    assert "Texto no alto só desta página." in textos_de_corpo(pags)[0]


def test_paragrafos_juntam_linhas():
    ps = paragrafos(["Art. 1º Esta Resolução\ndispõe sobre o teste.\nArt. 2º O emissor deve:\nI – divulgar fato\nrelevante; e",
                     "§ 1º O prazo é de sub-\nrogação."])
    assert ps == ["Art. 1º Esta Resolução dispõe sobre o teste.", "Art. 2º O emissor deve:",
                  "I – divulgar fato relevante; e", "§ 1º O prazo é de sub-rogação."]


def test_notas_da_cvm_viram_historico_e_citacao_nao_vira_dispositivo():
    paginas = [
        "Art. 1º Texto um.\nArt. 2º O prazo é de\n10 dias.\nArt. 2º O prazo é de\n20 dias.\n• Caput com redação dada pela Resolução CVM nº 181, de 28 de março de 2023.",
        "Parágrafo único. Texto antigo.\n• Parágrafo único revogado pela Resolução CVM nº 181, de 28 de março de 2023.\nArt. 3º A Resolução CVM nº 21 passa a vigorar com a seguinte\nredação:",
        "“Art. 1º Texto de outra norma.\n§ 1º Outro parágrafo.” (N.R.)\nArt. 4º Esta Resolução entra em vigor.",
    ]
    _t, _e, _txt, provs, iss, _am, _ed = parse_html_devices(como_html(paginas))
    doc = ParsedDocument("cvm_pdf", "t", "", None, "", provisions=provs, issues=iss)
    assert doc.current_text("art2").startswith("O prazo é de 20 dias.")
    with pytest.raises(RevokedProvision):
        doc.current_text("art2.parunico")
    assert doc.current_text("art1") == "Texto um."  # o “Art. 1º” citado não duplica o art. 1º
    assert not [i for i in iss if i.code == "DUPLICATE_CURRENT"]


def test_dispositivos_enderecaveis():
    paginas = ["Art. 1º Um.\nArt. 2º O emissor deve:\nI – divulgar; e\nII – manter.", "Art. 3º Vigência."]
    _t, _e, _txt, provs, _iss, _am, _ed = parse_html_devices(como_html(paginas))
    caminhos = {p.path for p in provs}
    assert {"art1", "art2", "art3"} <= {c.split(".")[0] for c in caminhos}
    assert any(".inc1" in c for c in caminhos)
