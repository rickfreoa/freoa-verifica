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


def test_dispositivos_enderecaveis():
    _t, _e, _txt, provs, _iss, _am, _ed = parse_html_devices(como_html(PAGINAS))
    caminhos = {p.path for p in provs}
    assert {"art1", "art2", "art3"} <= {c.split(".")[0] for c in caminhos}
    assert any(c.startswith("art2.inc1") or ".inc1" in c for c in caminhos)
