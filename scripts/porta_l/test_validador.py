"""Regressões CAUSAIS do validador v2 da Porta L.

Cada teste parte de um conjunto-base VÁLIDO (fixtures sintéticas pequenas, geradas em diretório temporário externo ao
objeto: nada é gravado na pasta do validador) e aplica UMA mutação que reproduz um defeito dos pareceres (r1, r2 e r3 do
validador) ou da matriz (seções 1 a 7). O teste prova a causa: sem a mutação o validador não acusa nada; com ela, acusa a
falha específica. Rodar: pytest test_validador.py (a suíte completa é conferida contra cópias mutiladas por
mutacao_causal.py).
"""
import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, os.environ.get("VALIDADOR_DIR") or str(AQUI))  # VALIDADOR_DIR: cópia mutilada (prova causal)
import validar_gabaritos_porta_l as v  # noqa: E402

VALIDADOR = Path(v.__file__)
PY = sys.executable

# --------------------------------------------------------------------------------------------------------------
# Fixtures sintéticas
# --------------------------------------------------------------------------------------------------------------
HTML_PUB = """<html><head><title>Lei 9999</title><style>.antiga{text-decoration:line-through}</style></head><body>
<p>LEI Nº 9.999, DE 1º DE JANEIRO DE 2000</p>
<p>Dispõe sobre testes sintéticos.</p>
<p>Art. 1º Esta Lei dispõe sobre testes sintéticos do validador.</p>
<p>CAPÍTULO I</p>
<p>Da Administração</p>
<p>Art. 156. É vedado ao administrador intervir em operação social em que tiver interesse conflitante com o da companhia.</p>
<p>§ 1º Ainda que observado o disposto neste artigo, o administrador somente pode contratar em condições razoáveis.</p>
<p>§ 2º O negócio contratado com infração do disposto no § 1º é anulável.</p>
<p>Art. 156-A. O artigo cento e cinquenta e seis A trata de matéria distinta do artigo anterior.</p>
<p>Art. 157. O administrador deve declarar o seu impedimento (Inciso I integra a regra) à companhia.</p>
<p>Art. 158. Os administradores respondem pelos atos praticados, na forma do art. 4º, § 2º, desta Lei e do art. 5º da Lei nº 6.404, de 15 de dezembro de 1976.</p>
<p>Art. 159. Os administradores prestam contas na forma do estatuto social.</p>
<p>Art. 420. Se no contrato for estipulado o direito de arrependimento.</p>
<p>Art. 421. A liberdade contratual será exercida nos limites da função social do contrato.</p>
<p>Parágrafo único. Nas relações contratuais privadas, prevalecerão o princípio da intervenção mínima.</p>
<p>Art. 422. Os contratantes são obrigados a guardar os princípios de probidade.</p>
<p>Brasília, 1º de janeiro de 2000.</p>
</body></html>"""

HTML_COMP = """<html><head><style>.antiga{text-decoration:line-through}</style></head><body>
<p>LEI Nº 9.999, DE 1º DE JANEIRO DE 2000</p>
<p>Texto compilado</p>
<p>Art. 10. A sociedade responde pelos atos do administrador. (Redação dada pela Lei nº 7.777, de 31/10/2001)</p>
<p>Art. 11. A sociedade pode <strike class="antiga">revogar</strike> alterar o ato (Inciso I integra a regra) conforme o estatuto. (Incluído pela Lei nº 7.777, de 2001)</p>
<p>Art. 12. A deliberação é tomada por maioria. <s>Texto riscado com s.</s> <del>Texto riscado com del.</del> <span style="text-decoration:line-through">Texto riscado com estilo.</span> Fim do artigo doze. (Redação dada pela Lei nº 7.777, de 2001)</p>
<p>Art. 13. (Revogado pela Lei nº 7.777, de 31/10/2001)</p>
<p>Art. 14. A norma vale em todo o território. (Vide Lei nº 7.000, de 1990) O texto continua aqui. "(NR)"</p>
<p>Art. 15. Os prazos contam-se em dias corridos.</p>
<p>Art. 16. A matéria não alterada permanece.</p>
</body></html>"""

HTML_ALT = """<html><body>
<p>LEI Nº 8.000, DE 5 DE MARÇO DE 2001</p>
<p>Altera a Lei nº 9.999, de 1º de janeiro de 2000.</p>
<p>Art. 1º A Lei nº 9.999, de 1º de janeiro de 2000, passa a vigorar com a seguinte redação:</p>
<p>"Art. 157. O administrador deve declarar o seu impedimento à companhia, na forma do estatuto."</p>
<p>Art. 2º A Lei nº 9.999, de 1º de janeiro de 2000, passa a vigorar acrescida do seguinte artigo:</p>
<p>"Art. 158. Os administradores prestam contas na forma do estatuto social."</p>
<p>Art. 3º Esta Lei entra em vigor na data de sua publicação.</p>
</body></html>"""

PDF_COMP_PAGINAS = [
    ["Texto compilado - Página 1",
     "LEI Nº 9.999, DE 1º DE JANEIRO DE 2000",
     "Art. 420. Se no contrato for estipulado o direito de arrependimento.",
     "Art. 421. A liberdade contratual será exercida nos limites da função social do contrato.",
     "(Redação dada pela Lei nº 8.888, de 2005)"],
    ["Texto compilado - Página 2",
     "Parágrafo único. Nas relações contratuais privadas, prevalecerão o princípio da",
     "intervenção mínima. (Parágrafo único acrescido pela Lei nº 8.888, de 2005)",
     "Art. 422. Os contratantes são obrigados a guardar os princípios de probidade."],
    ["Texto compilado - Página 3",
     "Art. 423. Quando houver no contrato de adesão cláusulas ambíguas, adotar-se-á a interpretação mais favorável."],
]

PDF_DECRETOS_PAGINAS = [
    ["DECRETO Nº 100, DE 5 DE OUTUBRO DE 2021",
     "Aprova o Regulamento de Teste.",
     "Art. 1º Fica aprovado o Regulamento de Teste, na forma do Anexo.",
     "Art. 2º Este Decreto entra em vigor na data de sua publicação.",
     "ANEXO I",
     "REGULAMENTO DE TESTE",
     "Art. 1º Este Regulamento disciplina a matéria de teste.",
     "Art. 2º Compete ao órgão fiscalizar o cumprimento deste Regulamento.",
     "Art. 3º Os casos omissos serão resolvidos pelo órgão competente.",
     "ANEXO II",
     "REGULAMENTO COMPLEMENTAR",
     "Art. 1º Este Regulamento Complementar disciplina a matéria complementar.",
     "Art. 2º Compete ao órgão técnico fiscalizar o cumprimento do regulamento complementar.",
     "DECRETO Nº 101, DE 5 DE OUTUBRO DE 2021",
     "Dispõe sobre outra matéria.",
     "Art. 1º Este Decreto trata de outra matéria.",
     "Art. 2º Compete ao outro órgão fiscalizar a outra matéria."],
]


def pdf_bytes(paginas):
    """PDF mínimo (Helvetica, WinAnsi) com uma lista de linhas por página."""
    def esc(s):
        return s.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None,
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"]
    kids = []
    for linhas in paginas:
        conteudo = b"BT /F1 10 Tf 12 TL 40 800 Td " + b" ".join(b"(" + esc(l) + b") Tj T*" for l in linhas) + b" ET"
        n = len(objs) + 1
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> "
                    b"/Contents " + str(n + 1).encode() + b" 0 R >>")
        objs.append(b"<< /Length " + str(len(conteudo)).encode() + b" >>\nstream\n" + conteudo + b"\nendstream")
        kids.append(f"{n} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    out = b"%PDF-1.4\n"
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    out += b"".join(f"{x:010d} 00000 n \n".encode() for x in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


URLS = {
    "pub": "https://www2.camara.leg.br/legin/fed/lei/2000/lei-9999-1-janeiro-2000-1-publicacaooriginal-1-pl.html",
    "comp": "https://www2.camara.leg.br/legin/fed/lei/2000/lei-9999-1-janeiro-2000-1-normaatualizada-pl.html",
    "pdf": "https://www2.camara.leg.br/legin/fed/lei/2000/lei-9999-1-janeiro-2000-1-normaatualizada-pl.pdf",
    "dec": "https://www.in.gov.br/web/dou/-/decretos-100-101-2021",
    "alt": "https://www2.camara.leg.br/legin/fed/lei/2001/lei-8000-5-marco-2001-1-publicacaooriginal-1-pl.html",
}
CAPT = "2026-11-03T12:00:00Z"
ATO_LEI = "LEI Nº 9.999, DE 1º DE JANEIRO DE 2000"
ATO_DEC = "DECRETO Nº 100, DE 5 DE OUTUBRO DE 2021"
ATO_ALT = "LEI Nº 8.000, DE 5 DE MARÇO DE 2001"


@pytest.fixture(scope="session")
def amb(tmp_path_factory):
    """Fixtures geradas em temporário EXTERNO ao objeto (nada é regravado na pasta do validador)."""
    FIX = tmp_path_factory.mktemp("fix")
    EVID = FIX / "evidencias"
    EVID.mkdir(parents=True, exist_ok=True)
    arqs = {"pub": (HTML_PUB.encode("utf-8"), "html"), "comp": (HTML_COMP.encode("utf-8"), "html"),
            "pdf": (pdf_bytes(PDF_COMP_PAGINAS), "pdf"), "dec": (pdf_bytes(PDF_DECRETOS_PAGINAS), "pdf"),
            "alt": (HTML_ALT.encode("utf-8"), "html")}
    shas, linhas = {}, ["url,sha256,capturado_em,status,content-type,tamanho"]
    for k, (b, ext) in arqs.items():
        h = hashlib.sha256(b).hexdigest()
        (EVID / f"{h}.{ext}").write_bytes(b)
        shas[k] = h
        linhas.append(f"{URLS[k]},{h},{CAPT},200,text/{ext},{len(b)}")
    csv = FIX / "fontes.csv"
    csv.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return {"shas": shas, "csv": str(csv), "pasta": str(EVID), "fix": FIX}


def fonte(amb, k, ato, pagina=1):
    return {"url": URLS[k], "sha256": amb["shas"][k], "capturado_em": CAPT, "orgao": "Câmara dos Deputados",
            "ato_no_documento": ato, "pagina": pagina}


def base_casos(amb):
    N_LEI = {"especie": "lei", "numero": "9999", "ano": 2000}
    N_DEC = {"especie": "decreto", "numero": "100", "ano": 2021}

    def caso(id_, cap, cit, cam, fam, tipo, texto, k, ato, norma=N_LEI, **extra):
        g = {"tipo": tipo, "texto": texto, "motivos_aceitos": [], "cadeia": [], "alvos": [], "alvos_equivalentes": {},
             "fonte_oficial": fonte(amb, k, ato), "fundamento_data": "Texto extraído da fonte oficial indicada."}
        g.update(extra.pop("g", {}))
        c = {"id": id_, "conjunto": "desenvolvimento", "capacidade": cap, "familia_alteracao": fam,
             "familia_fundamento": "publicação original do ato" if fam == "original" else "anotação na compilada",
             "norma": dict(norma), "citacao": cit, "caminho": cam, "data": None, "data_mutante": None, "trecho": None,
             "gabarito": g, "norma_grande": False}
        c.update(extra)
        return c

    t156 = ("Art. 156. É vedado ao administrador intervir em operação social em que tiver interesse conflitante com o "
            "da companhia. § 1º Ainda que observado o disposto neste artigo, o administrador somente pode contratar "
            "em condições razoáveis. § 2º O negócio contratado com infração do disposto no § 1º é anulável.")
    t421 = ("Art. 421. A liberdade contratual será exercida nos limites da função social do contrato. Parágrafo único. "
            "Nas relações contratuais privadas, prevalecerão o princípio da intervenção mínima.")
    t158 = ("Art. 158. Os administradores respondem pelos atos praticados, na forma do art. 4º, § 2º, desta Lei e do "
            "art. 5º da Lei nº 6.404, de 15 de dezembro de 1976.")
    return [
        caso("L-a-001", "a", "art. 156 da Lei 9.999/2000", "art. 156", "original", "texto", t156, "pub", ATO_LEI),
        caso("L-a-003", "a", "art. 157 da Lei 9.999/2000", "art. 157", "lei-8000-2001", "texto",
             "Art. 157. O administrador deve declarar o seu impedimento à companhia, na forma do estatuto.",
             "alt", ATO_ALT),
        caso("L-a-002", "a", "art. 156-A da Lei 9.999/2000", "art. 156-A", "original", "texto",
             "Art. 156-A. O artigo cento e cinquenta e seis A trata de matéria distinta do artigo anterior.",
             "pub", ATO_LEI),
        caso("L-b-001", "b", "art. 11 da Lei 9.999/2000", "art. 11", "lei-7777-2001", "texto",
             "Art. 11. A sociedade pode alterar o ato (Inciso I integra a regra) conforme o estatuto.", "comp", ATO_LEI),
        caso("L-b-002", "b", "art. 421 da Lei 9.999/2000", "art. 421", "lei-8888-2005", "texto", t421, "pdf", ATO_LEI),
        caso("L-b-003", "b", "art. 13 da Lei 9.999/2000", "art. 13", "lei-7777-2001", "revogado_vigente", "",
             "comp", ATO_LEI),
        caso("L-c-001", "c", "art. 156 da Lei 9.999/2000", "art. 156", "original", "verificado_para_D", t156,
             "pub", ATO_LEI, data="2000-06-01", data_mutante="1999-06-30"),
        caso("L-c-002", "c", "art. 156 da Lei 9.999/2000", "art. 156", "original", "nao_existia_em_D", "",
             "pub", ATO_LEI, data="1999-12-31",
             g={"condicao_inexistencia": "anterior_a_obra",
                "fundamento_data": "A obra é de 1º/1/2000 (cabeçalho do ato); D é anterior."}),
        caso("L-c-003", "c", "art. 10 da Lei 9.999/2000", "art. 10", "lei-7777-2001", "nao_verificado_para_D", "",
             "comp", ATO_LEI, data="2001-06-01",
             trecho="A sociedade responde pelos atos do administrador.",
             g={"motivos_aceitos": ["sem_versao_oficial_na_data"],
                "cadeia": [{"ato": "lei-7777-2001", "data": "2001-10-31"}],
                "ultima_versao_anterior": {"ato": "original", "data": "2000-01-01"},
                "fontes_consultadas": [fonte(amb, "comp", ATO_LEI)],
                "fundamento_data": "Compilada traz a redação de 2001 e nenhuma versão oficial intermediária."}),
        caso("L-d-001", "d", "Art. 2º do Anexo I do Decreto 100/2021", "Anexo I, art. 2º", "original", "texto",
             "Art. 2º Compete ao órgão fiscalizar o cumprimento deste Regulamento.", "dec", ATO_DEC, norma=N_DEC),
        caso("L-e-001", "e", "art. 158 da Lei 9.999/2000", "art. 158", "original", "texto", t158, "pub", ATO_LEI,
             g={"alvos": [{"obra": "Lei 9.999/2000", "caminho": "art. 4º, § 2º"},
                          {"obra": "Lei 6.404/1976", "caminho": "art. 5º"}]}),
    ]


def rodar(casos, amb, pisos=False, fontes=True, cobertura=None):
    return v.validar(copy.deepcopy(casos), amb["pasta"], amb["csv"] if fontes else None, cobertura, pisos)


def falhas_de(res, cid=None):
    return [m for c, m in res.falhas if cid is None or c == cid]


def achar(casos, cid):
    return next(c for c in casos if c["id"] == cid)


def acusa(res, cid, trecho):
    ms = falhas_de(res, cid)
    assert any(trecho in m for m in ms), f"esperava falha com {trecho!r} em {cid}; houve: {ms}"


# --------------------------------------------------------------------------------------------------------------
# Linha de base e normalização
# --------------------------------------------------------------------------------------------------------------
def test_base_valida_sem_falhas(amb):
    res = rodar(base_casos(amb), amb)
    assert res.falhas == []


def test_normalizacao_unica_secao_7():
    assert v.norm("  Art. 1º “texto”  d’água\t\n°  ") == 'Art. 1o "texto" d\'água o'
    assert v.norm("Á") == "Á"  # NFC
    assert v.norm("Art. 1º.") != v.norm("art. 1º.")  # nada além: nem caixa
    assert v.norm("1.000") != v.norm("1000")  # nem numeração


def test_gabarito_com_ordinal_diferente_da_fonte_ainda_compara_pela_normalizacao(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["texto"] = achar(casos, "L-a-001")["gabarito"]["texto"].replace("§ 1º", "§ 1°")
    assert rodar(casos, amb).falhas == []


# --------------------------------------------------------------------------------------------------------------
# Esquema (seção 6)
# --------------------------------------------------------------------------------------------------------------
def test_ids_repetidos(amb):
    casos = base_casos(amb)
    for c in casos:
        c["id"] = "L-a-001"
    res = rodar(casos, amb)
    acusa(res, "L-a-001", "id repetido")
    assert sum("id repetido" in m for m in falhas_de(res)) == len(casos) - 1


def test_id_fora_do_padrao_e_conjunto_incoerente(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["id"] = "caso1"
    achar(casos, "L-a-002")["conjunto"] = "reserva"
    res = rodar(casos, amb)
    acusa(res, "caso1", "fora do padrão")
    acusa(res, "L-a-002", "incoerente com o id")


@pytest.mark.parametrize("campo", ["capturado_em", "orgao", "url", "sha256", "ato_no_documento", "pagina"])
def test_metadados_da_fonte_removidos(amb, campo):
    casos = base_casos(amb)
    del achar(casos, "L-a-001")["gabarito"]["fonte_oficial"][campo]
    assert falhas_de(rodar(casos, amb), "L-a-001"), campo


def test_familia_removida_e_campos_obrigatorios(amb):
    casos = base_casos(amb)
    del achar(casos, "L-a-001")["familia_alteracao"]
    del achar(casos, "L-a-002")["citacao"]
    del achar(casos, "L-b-001")["norma"]["ano"]
    res = rodar(casos, amb)
    acusa(res, "L-a-001", "familia_alteracao")
    acusa(res, "L-a-002", "citacao")
    acusa(res, "L-b-001", "norma.ano")


def test_enums_capacidade_tipo_especie(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["capacidade"] = "z"
    achar(casos, "L-a-002")["gabarito"]["tipo"] = "inventado"
    achar(casos, "L-b-001")["norma"]["especie"] = "portaria"
    res = rodar(casos, amb)
    acusa(res, "L-a-001", "capacidade fora do enum")
    acusa(res, "L-a-002", "gabarito.tipo fora do enum")
    acusa(res, "L-b-001", "norma.especie fora do enum")


def test_verificado_para_D_em_capacidade_a(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["tipo"] = "verificado_para_D"
    acusa(rodar(casos, amb), "L-a-001", "incompatível com a capacidade")


def test_tipo_de_c_em_capacidade_b_e_revogado_em_a(amb):
    casos = base_casos(amb)
    achar(casos, "L-b-001")["gabarito"]["tipo"] = "nao_existia_em_D"
    achar(casos, "L-a-002")["gabarito"]["tipo"] = "revogado_vigente"
    res = rodar(casos, amb)
    acusa(res, "L-b-001", "incompatível")
    acusa(res, "L-a-002", "incompatível")


@pytest.mark.parametrize("valor", ["ontem", "2026-13-01", "2026-02-30", "01/06/2000", "", 20000601])
def test_data_invalida(amb, valor):
    casos = base_casos(amb)
    achar(casos, "L-c-001")["data"] = valor
    assert falhas_de(rodar(casos, amb), "L-c-001"), valor


def test_data_mutante_invalida_ou_igual_a_data(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-001")["data_mutante"] = "amanhã"
    acusa(rodar(casos, amb), "L-c-001", "data_mutante não é data ISO")
    casos = base_casos(amb)
    achar(casos, "L-c-001")["data_mutante"] = achar(casos, "L-c-001")["data"]
    acusa(rodar(casos, amb), "L-c-001", "igual a data")


def test_capturado_em_formato_e_data_inexistente(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["capturado_em"] = "03/11/2026"
    achar(casos, "L-a-002")["gabarito"]["fonte_oficial"]["capturado_em"] = "2026-02-30T10:00:00Z"
    res = rodar(casos, amb)
    acusa(res, "L-a-001", "não é data e hora válidas")
    acusa(res, "L-a-002", "não é data e hora válidas")


def test_c_sem_data(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-001")["data"] = None
    acusa(rodar(casos, amb), "L-c-001", "exige `data`")


def test_positivo_historico_sem_data_trecho_e_fundamento(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-c-001")
    c["data"] = None
    c["trecho"] = None
    del c["gabarito"]["fundamento_data"]
    res = rodar(casos, amb)
    acusa(res, "L-c-001", "exige `data`")
    acusa(res, "L-c-001", "fundamento_data")


def test_verificado_para_D_com_D_anterior_ao_ato(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-001")["data"] = "1999-06-30"
    acusa(rodar(casos, amb), "L-c-001", "anterior à data do ato")


def test_norma_grande_incoerente_na_mesma_norma(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["norma_grande"] = True
    acusa(rodar(casos, amb), "L-a-001", "norma_grande diverge")


def test_caminho_incompleto_ou_incoerente_com_a_citacao(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["caminho"] = "156"
    achar(casos, "L-a-002")["caminho"] = "art. 157"
    achar(casos, "L-d-001")["caminho"] = "art. 2º"
    res = rodar(casos, amb)
    acusa(res, "L-a-001", "caminho incompleto")
    acusa(res, "L-a-002", "não corresponde ao artigo da citação")
    acusa(res, "L-d-001", "(d) exige caminho iniciado por Anexo")


def test_norma_inexistente(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["norma"]["numero"] = "123456"
    res = rodar(casos, amb)
    acusa(res, "L-a-001", "não corresponde à norma")
    acusa(res, "L-a-001", "não corresponde ao ato esperado")


def test_citacao_que_nao_identifica_a_norma(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["citacao"] = "art. 156 da lei das testemunhas"
    acusa(rodar(casos, amb), "L-a-001", "não identifica a norma")


def test_especie_incoerente_com_a_citacao(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["norma"]["especie"] = "decreto"
    acusa(rodar(casos, amb), "L-a-001", "não corresponde à norma")


# --------------------------------------------------------------------------------------------------------------
# Fonte
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url", ["https://example.invalid/falso", "https://www.planalto.gov.br.exemplo.com/x",
                                 "ftp://www2.camara.leg.br/x", "https://blog.exemplo.com.br/lei-9999"])
def test_url_fora_da_allowlist(amb, url):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["url"] = url
    acusa(rodar(casos, amb), "L-a-001", "fora da allowlist")


def test_url_em_host_oficial_mas_diferente_do_fontes_csv(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["url"] = "https://www2.camara.leg.br/outra/pagina.html"
    acusa(rodar(casos, amb), "L-a-001", "url não consta em fontes.csv")


def test_sha256_sem_arquivo_e_hash_nao_confere(amb, tmp_path):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["sha256"] = "0" * 64
    res = rodar(casos, amb, fontes=False)
    acusa(res, "L-a-001", "arquivo da evidência ausente")
    # arquivo adulterado: o nome continua sendo o sha antigo, mas os bytes mudaram
    pasta = tmp_path / "ev"
    pasta.mkdir()
    sha = amb["shas"]["pub"]
    (pasta / f"{sha}.html").write_bytes(HTML_PUB.replace("anulável", "nulo").encode("utf-8"))
    casos = [achar(base_casos(amb), "L-a-001")]
    res = v.validar(casos, str(pasta), None, None, False)
    acusa(res, "L-a-001", "sha256 não confere")


def test_metadados_divergentes_de_fontes_csv(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["capturado_em"] = "2026-11-03T13:00:00Z"
    acusa(rodar(casos, amb), "L-a-001", "capturado_em diverge de fontes.csv")
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["sha256"] = "a" * 64
    acusa(rodar(casos, amb), "L-a-001", "ausente de fontes.csv")


def test_sem_fontes_csv_vira_alerta(amb):
    res = rodar(base_casos(amb), amb, fontes=False)
    assert res.falhas == []
    assert any("sem --fontes" in m for _, m in res.alertas)


def test_planalto_so_com_alerta(amb, tmp_path):
    casos = base_casos(amb)
    fo = achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]
    fo["url"] = "https://www.planalto.gov.br/ccivil_03/leis/l9999.htm"
    res = rodar(casos, amb, fontes=False)
    assert not falhas_de(res, "L-a-001")
    assert any("Planalto" in m for c, m in res.alertas if c == "L-a-001")


# --------------------------------------------------------------------------------------------------------------
# Extração: HTML (riscado), PDF página a página, extração vazia
# --------------------------------------------------------------------------------------------------------------
def test_pdf_com_texto_inventado(amb):
    """Parecer 1: PDF escapava do confronto (23 de 40 casos); texto inventado passava com zero falhas."""
    casos = base_casos(amb)
    achar(casos, "L-b-002")["gabarito"]["texto"] = "Art. 421. Texto inteiramente inventado pelo auditor."
    acusa(rodar(casos, amb), "L-b-002", "não é trecho contínuo da fonte")


def test_pdf_continuidade_entre_paginas_e_cabecalho_de_pagina_removido(amb):
    casos = base_casos(amb)
    res = rodar(casos, amb)
    assert not falhas_de(res, "L-b-002")  # o art. 421 atravessa a página 1 -> 2 com rodapé/cabeçalho entre elas
    assert any("linhas de cabeçalho/rodapé removidas" in m for _, m in res.alertas)


def test_pdf_pagina_declarada_errada(amb):
    casos = base_casos(amb)
    achar(casos, "L-b-002")["gabarito"]["fonte_oficial"]["pagina"] = 2
    acusa(rodar(casos, amb), "L-b-002", "o recorte começa na página 1")


def test_extracao_de_pdf_vazio_e_inconclusiva_e_falha(amb, tmp_path):
    vazio = pdf_bytes([[""], [""]])
    sha = hashlib.sha256(vazio).hexdigest()
    pasta = tmp_path / "ev"
    pasta.mkdir()
    (pasta / f"{sha}.pdf").write_bytes(vazio)
    c = achar(base_casos(amb), "L-b-002")
    c["gabarito"]["fonte_oficial"].update(sha256=sha)
    res = v.validar([c], str(pasta), None, None, False)
    acusa(res, "L-b-002", "extração vazia ou inconclusiva")


def test_pdf_ilegivel_e_html_vazio_sao_falha(amb, tmp_path):
    pasta = tmp_path / "ev"
    pasta.mkdir()
    quebrado = b"%PDF-1.4\nlixo sem estrutura"
    vazio_html = b"<html><body><script>var x=1;</script></body></html>"
    res_all = []
    for b, ext in ((quebrado, "pdf"), (vazio_html, "html")):
        sha = hashlib.sha256(b).hexdigest()
        (pasta / f"{sha}.{ext}").write_bytes(b)
        c = achar(base_casos(amb), "L-a-001")
        c["gabarito"]["fonte_oficial"].update(sha256=sha)
        res_all.append(v.validar([c], str(pasta), None, None, False))
    assert any("PDF ilegível" in m or "extração" in m for m in falhas_de(res_all[0]))
    acusa(res_all[1], "L-a-001", "extração vazia ou inconclusiva")


@pytest.mark.parametrize("marca", ["<strike class=\"antiga\">", "<strike>", "<s>", "<del>",
                                   "<span style=\"text-decoration:line-through\">",
                                   "<font style='text-decoration: line-through; color:red'>",
                                   "<STRIKE style=\"x\">"])
def test_texto_riscado_e_removido_da_fonte_por_elemento_com_ou_sem_atributos(marca):
    fim = {"<span": "</span>", "<font": "</font>", "<p": "</p>"}.get(marca.split(" ")[0].rstrip(">"),
                                                                       f"</{marca[1:].split(' ')[0].rstrip('>').lower()}>")
    html = (f"<html><head><style>.antiga{{text-decoration:line-through}}</style></head><body>"
            f"<p>Art. 1º Texto vigente {marca}redação antiga{fim} continua. Mais texto para passar de duzentos "
            f"caracteres, repetindo-se algumas palavras para garantir tamanho suficiente à extração, sem riscado "
            f"algum nesta parte final do documento sintético de teste da extração de HTML riscado.</p></body></html>")
    f = v.carregar_fonte(html.encode("utf-8"))
    assert "redação antiga" not in f.clean, marca
    assert "Texto vigente continua." in f.clean
    assert any("redação antiga" in r for _, r in f.risc)


def test_gabarito_com_texto_riscado_reprova(amb):
    casos = base_casos(amb)
    achar(casos, "L-b-001")["gabarito"]["texto"] = (
        "Art. 11. A sociedade pode revogar alterar o ato (Inciso I integra a regra) conforme o estatuto.")
    acusa(rodar(casos, amb), "L-b-001", "texto riscado")


def test_todas_as_formas_de_riscado_do_art_12(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-b-001")
    c.update(citacao="art. 12 da Lei 9.999/2000", caminho="art. 12")
    c["gabarito"]["texto"] = "Art. 12. A deliberação é tomada por maioria. Fim do artigo doze."
    assert not falhas_de(rodar(casos, amb), "L-b-001")  # s, del e line-through saem da fonte
    c["gabarito"]["texto"] = "Art. 12. A deliberação é tomada por maioria. Texto riscado com del. Fim do artigo doze."
    acusa(rodar(casos, amb), "L-b-001", "texto riscado")


# --------------------------------------------------------------------------------------------------------------
# Anotações editoriais (seção 7)
# --------------------------------------------------------------------------------------------------------------
def test_parentese_normativo_e_preservado_na_fonte(amb):
    """Parecer 11: `(Inciso I integra a regra)` era apagado como se fosse anotação."""
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c.update(citacao="art. 157 da Lei 9.999/2000", caminho="art. 157")
    c["gabarito"]["texto"] = "Art. 157. O administrador deve declarar o seu impedimento (Inciso I integra a regra) à companhia."
    assert not falhas_de(rodar(casos, amb), "L-a-001")
    c["gabarito"]["texto"] = "Art. 157. O administrador deve declarar o seu impedimento à companhia."
    acusa(rodar(casos, amb), "L-a-001", "não é trecho contínuo")


def test_anotacao_editorial_so_sai_da_fonte_nunca_do_gabarito(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-b-001")
    c.update(citacao="art. 10 da Lei 9.999/2000", caminho="art. 10")
    c["gabarito"]["texto"] = "Art. 10. A sociedade responde pelos atos do administrador."
    assert not falhas_de(rodar(casos, amb), "L-b-001")
    c["gabarito"]["texto"] = ("Art. 10. A sociedade responde pelos atos do administrador. "
                              "(Redação dada pela Lei nº 7.777, de 31/10/2001)")
    acusa(rodar(casos, amb), "L-b-001", "anotação editorial")


@pytest.mark.parametrize("nota", ["(Redação dada pela Lei nº 8.000, de 2001)", "(Incluído pela Lei nº 8.000, de 2001)",
                                  "(Incluída pela Lei nº 8.000, de 2001)", "(Acrescido pela Lei nº 8.000, de 2001)",
                                  "(Acrescentado pelo Decreto nº 8.000, de 2001)", "(Revogado pela Lei nº 8.000, de 2001)",
                                  "(Revogada pela Lei nº 8.000, de 2001)", "(Vide Lei nº 8.000, de 2001)",
                                  "(Vigência: Lei nº 8.000, de 2001)", "(Produção de efeito conforme a Lei nº 8.000, de 2001)",
                                  "(Renumerado pela Lei nº 8.000, de 2001)", "(Vetado pela Mensagem nº 8, de 2001)",
                                  "(NR)", "(Parágrafo único acrescido pela Lei nº 8.000, de 2001)",
                                  "(Artigo acrescido pela Lei nº 8.000, de 2001)"])
def test_padroes_completos_de_anotacao_sao_reconhecidos(nota):
    assert v.tem_anotacao_editorial(nota)


@pytest.mark.parametrize("texto", ["(Inciso I integra a regra)", "(Parágrafo único deste artigo)", "(Vide o conceito)",
                                   "(Revogado o disposto anterior)", "(Incluído o prazo na contagem)",
                                   "(Artigo definido em regulamento)"])
def test_parenteses_normativos_nao_sao_anotacao(texto):
    assert not v.tem_anotacao_editorial(texto)


def test_vide_no_gabarito_e_so_alerta(amb, tmp_path):
    """Parecer 12: `vide` em qualquer contexto era rejeitado, inclusive remissão normativa legítima."""
    html = ("<html><body><p>LEI Nº 9.998, DE 1º DE JANEIRO DE 2000</p><p>Art. 1º Aplica-se o prazo, vide o conceito "
            "do contrato, e sobre ele não há dúvida alguma na prática dos atos de comércio. Texto adicional para "
            "passar do limite mínimo de duzentos caracteres de extração, repetindo palavras e frases do documento "
            "sintético de teste, apenas para garantir tamanho e dar contexto suficiente.</p><p>Art. 2º Fim.</p>"
            "</body></html>").encode()
    sha = hashlib.sha256(html).hexdigest()
    pasta = tmp_path / "ev"
    pasta.mkdir()
    (pasta / f"{sha}.html").write_bytes(html)
    c = achar(base_casos(amb), "L-a-001")
    c.update(norma={"especie": "lei", "numero": "9998", "ano": 2000}, citacao="art. 1º da Lei 9.998/2000",
             caminho="art. 1º")
    c["gabarito"]["fonte_oficial"].update(sha256=sha, ato_no_documento="LEI Nº 9.998, DE 1º DE JANEIRO DE 2000")
    c["gabarito"]["texto"] = (
        "Art. 1º Aplica-se o prazo, vide o conceito do contrato, e sobre ele não há dúvida alguma na prática dos atos "
        "de comércio. Texto adicional para passar do limite mínimo de duzentos caracteres de extração, repetindo "
        "palavras e frases do documento sintético de teste, apenas para garantir tamanho e dar contexto suficiente.")
    res = v.validar([c], str(pasta), None, None, False)
    assert res.falhas == []
    assert any("'vide'" in m for _, m in res.alertas)


# --------------------------------------------------------------------------------------------------------------
# Recorte
# --------------------------------------------------------------------------------------------------------------
def test_dispositivo_incompleto_art_421_sem_paragrafo_unico(amb):
    """Parecer 2: `L-b-005` pedia o art. 421 inteiro e trazia só o caput (norma grande)."""
    casos = base_casos(amb)
    achar(casos, "L-b-002")["gabarito"]["texto"] = (
        "Art. 421. A liberdade contratual será exercida nos limites da função social do contrato.")
    acusa(rodar(casos, amb), "L-b-002", "dispositivo incompleto")


def test_dispositivo_incompleto_sem_paragrafo_na_mesma_pagina_e_sem_inciso(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["texto"] = (
        "Art. 156. É vedado ao administrador intervir em operação social em que tiver interesse conflitante com o da "
        "companhia. § 1º Ainda que observado o disposto neste artigo, o administrador somente pode contratar em "
        "condições razoáveis.")
    acusa(rodar(casos, amb), "L-a-001", "dispositivo incompleto")


def test_recorte_de_ato_vizinho_na_mesma_pagina(amb):
    """Parecer 3: `L-d-008` tinha o art. 2º do corpo de outro decreto, publicado na mesma página do DOU."""
    casos = base_casos(amb)
    achar(casos, "L-d-001")["gabarito"]["texto"] = "Art. 2º Compete ao outro órgão fiscalizar a outra matéria."
    res = rodar(casos, amb)
    acusa(res, "L-d-001", "não é a do dispositivo")


def test_recorte_do_corpo_do_decreto_nao_e_anexo(amb):
    casos = base_casos(amb)
    achar(casos, "L-d-001")["gabarito"]["texto"] = "Art. 2º Este Decreto entra em vigor na data de sua publicação."
    acusa(rodar(casos, amb), "L-d-001", "não é a do dispositivo")


def test_ato_declarado_diferente_do_documento(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["ato_no_documento"] = "LEI Nº 9.998, DE 1º DE JANEIRO DE 2000"
    acusa(rodar(casos, amb), "L-a-001", "ato_no_documento")
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["ato_no_documento"] = "texto livre sem ato"
    acusa(rodar(casos, amb), "L-a-001", "não identifica um ato")


def test_art_156a_para_citacao_de_art_156(amb):
    """Parecer 11: o teste de início aceitava `Art. 156-A` para `art. 156`."""
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["texto"] = (
        "Art. 156-A. O artigo cento e cinquenta e seis A trata de matéria distinta do artigo anterior.")
    acusa(rodar(casos, amb), "L-a-001", "não é a do dispositivo")
    # e o inverso: `art. 156-A` não aceita o corpo de `Art. 156`
    casos = base_casos(amb)
    achar(casos, "L-a-002")["gabarito"]["texto"] = achar(casos, "L-a-001")["gabarito"]["texto"]
    acusa(rodar(casos, amb), "L-a-002", "não é a do dispositivo")


def test_limite_desconhecido_e_falha_nao_presuncao_de_integridade(amb):
    """Parecer 11: `PROX` aceitava qualquer `(` como limite; recorte antes de continuação entre parênteses passava."""
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c.update(citacao="art. 157 da Lei 9.999/2000", caminho="art. 157")
    c["gabarito"]["texto"] = "Art. 157. O administrador deve declarar o seu impedimento"
    acusa(rodar(casos, amb), "L-a-001", "limite desconhecido")


def test_recorte_que_invade_o_dispositivo_seguinte(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-002")["gabarito"]["texto"] += " Art. 157. O administrador deve declarar o seu impedimento (Inciso I integra a regra) à companhia."
    acusa(rodar(casos, amb), "L-a-002", "invade o dispositivo seguinte")


def test_recorte_que_termina_em_rotulo_ou_divisao(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c.update(citacao="art. 1º da Lei 9.999/2000", caminho="art. 1º")
    c["gabarito"]["texto"] = "Art. 1º Esta Lei dispõe sobre testes sintéticos do validador. CAPÍTULO I"
    res = rodar(casos, amb)
    ms = " | ".join(falhas_de(res, "L-a-001"))
    assert "divisão" in ms or "limite desconhecido" in ms
    c["gabarito"]["texto"] = "Art. 1º Esta Lei dispõe sobre testes sintéticos do validador."
    assert not falhas_de(rodar(casos, amb), "L-a-001")  # termina antes da divisão: correto


def test_recorte_de_divisao_e_rubrica_seguem_como_limite_valido(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c.update(citacao="art. 1º da Lei 9.999/2000", caminho="art. 1º")
    c["gabarito"]["texto"] = "Art. 1º Esta Lei dispõe sobre testes sintéticos do validador."
    assert not falhas_de(rodar(casos, amb), "L-a-001")  # logo depois vem "CAPÍTULO I Da Administração Art. 156"


def test_aspas_do_comando_alterador_no_gabarito(amb):
    """Parecer 9: `L-a-002` conservava a aspa final do bloco de alteração."""
    casos = base_casos(amb)
    achar(casos, "L-a-002")["gabarito"]["texto"] = (
        achar(casos, "L-a-002")["gabarito"]["texto"] + '"')
    res = rodar(casos, amb)
    assert falhas_de(res, "L-a-002")
    casos = base_casos(amb)
    achar(casos, "L-a-002")["gabarito"]["texto"] = '"' + achar(casos, "L-a-002")["gabarito"]["texto"]
    acusa(rodar(casos, amb), "L-a-002", "começa por aspas")


def test_tamanho_e_termos_suspeitos_sao_alerta_nao_falha(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c.update(citacao="art. 1º da Lei 9.999/2000", caminho="art. 1º")
    c["gabarito"]["texto"] = "Art. 1º Esta Lei dispõe sobre testes sintéticos do validador."
    res = rodar(casos, amb)
    assert not falhas_de(res, "L-a-001")
    # curto: alerta contextual
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c.update(citacao="art. 420 da Lei 9.999/2000", caminho="art. 420")
    c["gabarito"]["texto"] = "Art. 420. Se no contrato for estipulado o direito de arrependimento."
    res = rodar(casos, amb)
    assert not falhas_de(res, "L-a-001")


def test_gabarito_vazio_em_texto_e_falha(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["texto"] = ""
    acusa(rodar(casos, amb), "L-a-001", "exige gabarito.texto")


# --------------------------------------------------------------------------------------------------------------
# Famílias e independência (seção 2)
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("fam", ["original-2", "lei-9999-2000-b", "lei-7777-2001-alt", "lei-7777-2001-2", "Original",
                                 "lei 7777/2001", "", "lei-7777", "decreto", "mp-1-2019-x"])
def test_familia_com_sufixo_ou_fora_do_padrao(amb, fam):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["familia_alteracao"] = fam
    assert falhas_de(rodar(casos, amb), "L-a-001"), fam


def test_familia_equivalente_ao_proprio_ato_e_original_sao_a_mesma_unidade(amb):
    """Parecer 4: `lei-10406-2002` e `original` apareciam como famílias diferentes para a mesma norma."""
    casos = base_casos(amb)
    achar(casos, "L-a-001")["familia_alteracao"] = "lei-9999-2000"
    acusa(rodar(casos, amb), "L-a-001", "própria norma consultada")


def test_mp_com_familia_da_propria_mp(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c["norma"] = {"especie": "medida_provisoria", "numero": "9999", "ano": 2000}
    c["citacao"] = "art. 156 da Medida Provisória 9.999/2000"
    c["familia_alteracao"] = "mp-9999-2000"
    acusa(rodar(casos, amb), "L-a-001", "própria norma consultada")


def test_compilada_sem_anotacao_que_nomeie_o_ato_da_familia(amb):
    """Parecer 4: `L-b-004` com família `original` embora a compilada atribuísse a redação à LC 118/2005."""
    casos = base_casos(amb)
    achar(casos, "L-b-001")["familia_alteracao"] = "original"
    acusa(rodar(casos, amb), "L-b-001", "família 'original', mas a anotação editorial")
    casos = base_casos(amb)
    achar(casos, "L-b-001")["familia_alteracao"] = "lei-1111-1999"
    acusa(rodar(casos, amb), "L-b-001", "não consta das anotações do dispositivo")
    casos = base_casos(amb)
    del achar(casos, "L-b-001")["familia_fundamento"]
    acusa(rodar(casos, amb), "L-b-001", "familia_fundamento ausente")


def test_compilada_sem_anotacao_no_dispositivo_exige_original(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-b-001")
    c.update(citacao="art. 15 da Lei 9.999/2000", caminho="art. 15", familia_alteracao="lei-7777-2001")
    c["gabarito"]["texto"] = "Art. 15. Os prazos contam-se em dias corridos."
    acusa(rodar(casos, amb), "L-b-001", "não traz anotação editorial do dispositivo")
    c["familia_alteracao"] = "original"
    assert not falhas_de(rodar(casos, amb), "L-b-001")


def test_publicacao_de_ato_alterador_a_familia_e_o_ato_do_cabecalho(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c["familia_alteracao"] = "lei-7777-2001"  # a publicação é da Lei 9.999: o evento não é a Lei 7.777
    res = rodar(casos, amb)
    acusa(res, "L-a-001", "ato esperado")


def test_contagem_por_unidade_exige_8_unidades_e_4_normas(amb):
    res = rodar(base_casos(amb), amb, pisos=True)
    ms = falhas_de(res)
    assert any("unidades independentes válidas (mínimo 8)" in m for m in ms)
    assert any(c == "capacidade-a" for c, _ in res.falhas)


def test_contagem_unidade_e_o_evento_e_representante_e_o_menor_id():
    casos = []
    for i, (norma, fam) in enumerate([("1", "original"), ("1", "lei-100-1990"), ("2", "lei-100-1990"),
                                      ("3", "lei-100-1990"), ("4", "original"), ("5", "original"), ("6", "original"),
                                      ("7", "original"), ("8", "original"), ("9", "original")], 1):
        casos.append({"id": f"L-a-{i:03d}", "capacidade": "a", "familia_alteracao": fam,
                      "norma": {"especie": "lei", "numero": norma, "ano": 1990}})
    res = v.Resultado()
    v.contagem(casos, res, set())
    info = " ".join(res.info)
    # eventos: lei-1-1990 (original) | lei-100-1990 | lei-4..lei-9 (originais): 1 + 1 + 6 = 8 unidades; os três casos de
    # lei-100-1990 (consultada em normas diferentes) são UM evento
    assert "capacidade a: 8 unidades válidas de 8 (10 casos)" in info
    assert "L-a-002" in info and "L-a-003" not in info.split("representantes (menor id da unidade):")[1].split("capacidade b")[0]
    assert not [c for c, _ in res.falhas if c == "capacidade-a"]


def test_contagem_ignora_casos_com_falha(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["texto"] = "inventado"
    res = rodar(casos, amb, pisos=True)
    # L-a-001 e L-a-002 são o MESMO evento (lei-9999-2000, original): o representante é o menor id, fixado antes de
    # avaliar resultados; falhando L-a-001, a unidade não conta (não passa para L-a-002)
    assert "capacidade a: 1 unidades válidas de 2" in " ".join(res.info)  # só a unidade lei-8000-2001 (L-a-003)


# --------------------------------------------------------------------------------------------------------------
# (c) tipos históricos
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("motivos", [["porque sim"], ["sem_fundamento"], [], None, ["sem_versao_oficial_na_data", "x"]])
def test_motivos_arbitrarios_ou_ausentes(amb, motivos):
    casos = base_casos(amb)
    achar(casos, "L-c-003")["gabarito"]["motivos_aceitos"] = motivos
    assert falhas_de(rodar(casos, amb), "L-c-003"), motivos


def test_nao_verificado_trecho_generico_nao_e_trecho_normativo_real(amb):
    """Parecer 6/13: `L-c-005`–`008` usavam trechos genéricos de instrução ao avaliador."""
    casos = base_casos(amb)
    achar(casos, "L-c-003")["trecho"] = "Avalie a conformidade do dispositivo com a norma indicada."
    acusa(rodar(casos, amb), "L-c-003", "trecho não é texto do DISPOSITIVO citado")
    casos = base_casos(amb)
    achar(casos, "L-c-003")["trecho"] = None
    acusa(rodar(casos, amb), "L-c-003", "exige `trecho`")


def test_nao_verificado_sem_fontes_consultadas_e_sem_cadeia(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-003")["gabarito"]["fontes_consultadas"] = []
    achar(casos, "L-c-003")["gabarito"]["cadeia"] = []
    res = rodar(casos, amb)
    acusa(res, "L-c-003", "fontes_consultadas")
    acusa(res, "L-c-003", "`cadeia` não vazia")


def test_cadeia_mal_formada_ou_fora_de_ordem(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-003")["gabarito"]["cadeia"] = [{"ato": "lei-7777-2001", "data": "2001-10-31"},
                                                     {"ato": "lei-8888-2005", "data": "2001-01-01"}]
    acusa(rodar(casos, amb), "L-c-003", "não está ordenada")
    casos = base_casos(amb)
    achar(casos, "L-c-003")["gabarito"]["cadeia"] = ["a lei qualquer"]
    acusa(rodar(casos, amb), "L-c-003", "identificador canônico")


def test_nao_verificado_trecho_curto_e_alerta(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-003")["trecho"] = "A sociedade"
    res = rodar(casos, amb)
    assert not falhas_de(res, "L-c-003")
    assert any("trecho curto" in m for _, m in res.alertas)


def test_nao_verificado_com_texto_de_gabarito(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-003")["gabarito"]["texto"] = "Art. 10. A sociedade responde pelos atos do administrador."
    acusa(rodar(casos, amb), "L-c-003", "não admite gabarito.texto")


def test_nao_existia_exige_condicoes_da_secao_1_1(amb):
    casos = base_casos(amb)
    del achar(casos, "L-c-002")["gabarito"]["condicao_inexistencia"]
    acusa(rodar(casos, amb), "L-c-002", "condicao_inexistencia")
    casos = base_casos(amb)
    achar(casos, "L-c-002")["data"] = "2000-01-02"  # D depois da obra: o dispositivo existia
    acusa(rodar(casos, amb), "L-c-002", "não é anterior à data da obra")
    casos = base_casos(amb)
    achar(casos, "L-c-002")["data"] = "2000-01-01"  # mesmo dia: não é anterior
    acusa(rodar(casos, amb), "L-c-002", "não é anterior à data da obra")


def test_nao_existia_anterior_a_inclusao_exige_anotacao_e_ausencia_de_vigencia_veto_revogacao(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-c-002")
    c.update(citacao="art. 11 da Lei 9.999/2000", caminho="art. 11", familia_alteracao="lei-7777-2001", data="2001-10-30")
    c["gabarito"]["condicao_inexistencia"] = "anterior_a_inclusao"
    c["gabarito"]["fonte_oficial"] = fonte(amb, "comp", ATO_LEI)
    c["gabarito"]["fontes_consultadas"] = []
    # a anotação do art. 10 dá a data exata do ato 7.777 (31/10/2001): D=2001-10-30 é anterior; é inclusão sem ressalva
    assert not falhas_de(rodar(casos, amb), "L-c-002")
    c["data"] = "2001-11-01"
    acusa(rodar(casos, amb), "L-c-002", "não é anterior à data do ato que incluiu")


def test_nao_existia_inclusao_com_anotacao_de_revogacao_no_dispositivo_reprova(amb):
    # art. 13 só traz "(Revogado pela ...)": não é anotação de inclusão
    casos = base_casos(amb)
    c = achar(casos, "L-c-002")
    c.update(citacao="art. 13 da Lei 9.999/2000", caminho="art. 13", familia_alteracao="lei-7777-2001", data="2001-10-30")
    c["gabarito"]["condicao_inexistencia"] = "anterior_a_inclusao"
    c["gabarito"]["fonte_oficial"] = fonte(amb, "comp", ATO_LEI)
    res = rodar(casos, amb)
    ms = falhas_de(res, "L-c-002")
    assert any("não registra inclusão" in m or "revogação" in m for m in ms), ms


# --------------------------------------------------------------------------------------------------------------
# (b) revogado_vigente
# --------------------------------------------------------------------------------------------------------------
def test_revogado_vigente_exige_anotacao_de_revogacao_na_fonte(amb):
    casos = base_casos(amb)
    assert not falhas_de(rodar(casos, amb), "L-b-003")
    c = achar(casos, "L-b-003")
    c.update(citacao="art. 15 da Lei 9.999/2000", caminho="art. 15")
    acusa(rodar(casos, amb), "L-b-003", "anotação de revogação")
    c.update(citacao="art. 99 da Lei 9.999/2000", caminho="art. 99")
    acusa(rodar(casos, amb), "L-b-003", "não localizado na fonte oficial")


# --------------------------------------------------------------------------------------------------------------
# (d) anexos
# --------------------------------------------------------------------------------------------------------------
def test_d_citacao_sem_anexo(amb):
    casos = base_casos(amb)
    achar(casos, "L-d-001")["citacao"] = "Art. 2º do Decreto 100/2021"
    acusa(rodar(casos, amb), "L-d-001", "citação sem 'Anexo'")


def test_d_valido_no_anexo_do_ato_declarado(amb):
    assert not falhas_de(rodar(base_casos(amb), amb), "L-d-001")


def test_d_outro_artigo_do_mesmo_anexo_e_art_do_corpo_com_mesmo_numero(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-d-001")
    c["gabarito"]["texto"] = "Art. 1º Este Regulamento disciplina a matéria de teste."
    c.update(citacao="Art. 1º do Anexo I do Decreto 100/2021", caminho="Anexo I, art. 1º")
    assert not falhas_de(rodar(casos, amb), "L-d-001")
    c["gabarito"]["texto"] = "Art. 1º Fica aprovado o Regulamento de Teste, na forma do Anexo."
    acusa(rodar(casos, amb), "L-d-001", "não é a do dispositivo")


# --------------------------------------------------------------------------------------------------------------
# (e) remissões
# --------------------------------------------------------------------------------------------------------------
def test_e_valido(amb):
    assert not falhas_de(rodar(base_casos(amb), amb), "L-e-001")


def test_e_alvo_inventado_em_obra_falsa_com_caminho_ruim(amb):
    """Parecer 10: alvo `art. 999inventado` em obra falsa passava."""
    casos = base_casos(amb)
    achar(casos, "L-e-001")["gabarito"]["alvos"] = [{"obra": "Obra Falsa", "caminho": "art. 999inventado"}]
    res = rodar(casos, amb)
    acusa(res, "L-e-001", "obra do alvo não reconhecida")
    acusa(res, "L-e-001", "remissão expressa do texto ausente de `alvos`")


def test_e_alvo_incompleto_sem_o_paragrafo_que_o_texto_da(amb):
    casos = base_casos(amb)
    achar(casos, "L-e-001")["gabarito"]["alvos"][0]["caminho"] = "art. 4º"
    res = rodar(casos, amb)
    acusa(res, "L-e-001", "remissão expressa do texto ausente de `alvos`: lei-9999-2000 art. 4, § 2")
    acusa(res, "L-e-001", "não aparece como remissão expressa")


def test_e_remissao_omitida_lista_completa(amb):
    """Parecer 8: o resolvedor passava omitindo 21 de 30 alvos; a lista de alvos tem de ser COMPLETA."""
    casos = base_casos(amb)
    achar(casos, "L-e-001")["gabarito"]["alvos"] = achar(casos, "L-e-001")["gabarito"]["alvos"][:1]
    acusa(rodar(casos, amb), "L-e-001", "remissão expressa do texto ausente de `alvos`: lei-6404-1976 art. 5")


def test_e_alvos_vazio_e_alvo_sem_obra(amb):
    casos = base_casos(amb)
    achar(casos, "L-e-001")["gabarito"]["alvos"] = []
    acusa(rodar(casos, amb), "L-e-001", "`alvos` ausente ou vazio")
    casos = base_casos(amb)
    achar(casos, "L-e-001")["gabarito"]["alvos"][0] = {"caminho": "art. 4º, § 2º"}
    acusa(rodar(casos, amb), "L-e-001", "alvo sem obra ou caminho")


def test_e_alvo_repetido(amb):
    casos = base_casos(amb)
    al = achar(casos, "L-e-001")["gabarito"]["alvos"]
    al.append(dict(al[0]))
    acusa(rodar(casos, amb), "L-e-001", "alvo repetido")


def test_e_alvos_equivalentes_so_referenciam_alvos_existentes(amb):
    casos = base_casos(amb)
    achar(casos, "L-e-001")["gabarito"]["alvos_equivalentes"] = {"Lei 6.404/1976, art. 77": ["Lei 6.404/1976, art. 77, caput"]}
    acusa(rodar(casos, amb), "L-e-001", "alvos_equivalentes referencia alvo inexistente")
    casos = base_casos(amb)
    achar(casos, "L-e-001")["gabarito"]["alvos_equivalentes"] = {
        "Lei 6.404/1976, art. 5º": ["Lei 6.404/1976, art. 5º, caput", "Lei 6.404/1976, art. 5º, caput."]}
    res = rodar(casos, amb)
    assert not any("referencia alvo inexistente" in m for m in falhas_de(res, "L-e-001"))
    acusa(res, "L-e-001", "equivalente malformado")


def test_e_alvos_fora_de_e(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["alvos"] = [{"obra": "Lei 6.404/1976", "caminho": "art. 5º"}]
    acusa(rodar(casos, amb), "L-a-001", "alvos só se aplica a (e)")


@pytest.mark.parametrize("texto,esperado", [
    ("Art. 5º Nos termos do art. 4º, § 2º, desta Lei.", {("lei-1-2000", "4", (("par", "2"),))}),
    ("Art. 5º Conforme o inciso IV do caput do art. 1º, do parágrafo único do art. 170 e do caput do art. 174 da "
     "Constituição Federal.",
     {("constituicao-1988", "1", (("inc", "IV"),)), ("constituicao-1988", "170", (("par", "unico"),)),
      ("constituicao-1988", "174", (("caput", ""),))}),
    ("Art. 5º Aplica-se o art. 311, incisos II e III, do Código de Processo Civil.",
     {("lei-13105-2015", "311", (("inc", "II"),)), ("lei-13105-2015", "311", (("inc", "III"),))}),
    ("Art. 5º Vide arts. 4º e 5º da Lei nº 6.404, de 15 de dezembro de 1976.",
     {("lei-6404-1976", "4", ()), ("lei-6404-1976", "5", ())}),
    ("Art. 5º Conforme o art. 52, inciso I, alínea a, desta Lei.", {("lei-1-2000", "52", (("inc", "I"), ("ali", "a")))}),
    ("Art. 5º Sem remissão alguma.", set()),
])
def test_extracao_de_remissoes(texto, esperado):
    refs, incertos = v.extrair_remissoes(v.norm(texto), "lei-1-2000", "5")
    got = {(r["obra"], r["chave"][1], r["chave"][2]) for r in refs}
    assert got == esperado and not incertos


def test_caminho_completo_gramatica():
    ok = ["art. 4º", "art. 4º, § 4º", "art. 421, parágrafo único", "art. 52, inciso I, alínea a", "art. 1.031",
          "art. 254-A", "Anexo I, art. 2º", "Anexo", "art. 4º, caput"]
    ruim = ["", "4º", "art. 999inventado", "§ 4º", "art. 4º, §", "art. 4º, alínea", "artigo", "inciso II", None]
    assert all(v.parse_caminho(x) for x in ok)
    assert not any(v.parse_caminho(x) for x in ruim)
    assert v.chave_caminho("art. 4º, § 4º") != v.chave_caminho("art. 4º")


# --------------------------------------------------------------------------------------------------------------
# Cobertura (seção 5)
# --------------------------------------------------------------------------------------------------------------
def _cob(tmp_path, situacoes):
    p = tmp_path / "cobertura.json"
    p.write_text(json.dumps({"situacoes": situacoes}), encoding="utf-8")
    return str(p)


def test_cobertura_ausente_de_situacao_obrigatoria(amb, tmp_path):
    res = rodar(base_casos(amb), amb, cobertura=_cob(tmp_path, {}))
    for nome in ("lsa_156", "lsa_254a", "lsa_289", "cc_421", "cc_1031", "ctn_185", "rasura", "sem_rasura", "revogacao",
                 "mp_reeditada", "mp_convertida", "anexo", "remissao", "data_anterior_a_publicacao"):
        acusa(res, f"cobertura:{nome}", "situação obrigatória ausente")


def test_cobertura_so_forma_caso_inexistente_com_falha_e_campos_vazios(amb, tmp_path):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["texto"] = "inventado"
    sit = {
        "anexo": {"casos": ["L-x-999"], "evento": "e", "esperado": "x"},
        "remissao": {"casos": ["L-a-001"], "evento": "e", "esperado": "x"},
        "revogacao": {"casos": ["L-a-002"], "evento": "e", "esperado": "x"},
        "data_anterior_a_publicacao": {"casos": ["L-c-002"], "evento": "e", "esperado": "x"},
        "mp_reeditada": {"casos": ["L-a-002"], "evento": "", "esperado": "x"},
    }
    res = rodar(casos, amb, cobertura=_cob(tmp_path, sit))
    acusa(res, "cobertura:anexo", "caso citado inexistente")
    acusa(res, "cobertura:remissao", "tem falha de validação")
    acusa(res, "cobertura:mp_reeditada", "`evento` ausente ou vazio")
    # D5: o vínculo documental NÃO é conferido (sem inferência por proximidade textual): caso aprovado qualquer, em qualquer
    # situação, passa na forma e vai à revisão humana
    assert not falhas_de(res, "cobertura:revogacao") and not falhas_de(res, "cobertura:data_anterior_a_publicacao")
    assert any(c == "cobertura:revogacao" and cat == "(v)" for c, cat, _ in res.revisoes)


def test_cobertura_valida_na_forma_e_todo_vinculo_vai_a_revisao_humana(amb, tmp_path):
    casos = base_casos(amb)
    # o art. 421 da Lei 9.999/2000 não é o CC 10.406/2002: antes da D5 isso era FALHA por inferência; agora é da 2ª camada
    sit = {"anexo": {"casos": ["L-d-001"], "evento": "anexo do Decreto 100", "esperado": "texto do art. 2º"},
           "remissao": {"casos": ["L-e-001"], "evento": "remissões", "esperado": "alvos completos"},
           "revogacao": {"casos": ["L-b-003"], "evento": "art. 13 revogado", "esperado": "revogado_vigente"},
           "cc_421": {"casos": ["L-b-002"], "evento": "art. 421", "esperado": "texto integral"}}
    res = rodar(casos, amb, cobertura=_cob(tmp_path, sit))
    for nome in sit:
        assert not falhas_de(res, f"cobertura:{nome}"), nome
        assert any(c == f"cobertura:{nome}" and cat == "(v)" and "vínculo documental" in m for c, cat, m in res.revisoes)


def test_cobertura_nao_infere_vinculo_por_proximidade_textual():
    assert not hasattr(v, "_exercita")


def test_cobertura_ilegivel(amb, tmp_path):
    p = tmp_path / "cob.json"
    p.write_text("{não é json", encoding="utf-8")
    acusa(rodar(base_casos(amb), amb, cobertura=str(p)), "cobertura", "ilegível")


def test_cobertura_nao_informada_e_obrigatoria_no_congelamento(amb):
    res = rodar(base_casos(amb), amb, pisos=True)
    acusa(res, "cobertura", "obrigatório no congelamento")
    res = v.validar(copy.deepcopy(base_casos(amb)), amb["pasta"], amb["csv"], None, True, exploratorio=True)
    assert not falhas_de(res, "cobertura") and any("sem --cobertura" in m for m in res.incompleto)


# --------------------------------------------------------------------------------------------------------------
# Mutantes (seção 3)
# --------------------------------------------------------------------------------------------------------------
def test_gerar_mutantes_e_deterministico_e_escolhe_dispositivo_existente(amb, tmp_path):
    casos = base_casos(amb)
    a = tmp_path / "m1.jsonl"
    b = tmp_path / "m2.jsonl"
    m1, _, e1 = v.gerar_mutantes(copy.deepcopy(casos), amb["pasta"], str(a))
    m2, _, e2 = v.gerar_mutantes(copy.deepcopy(list(reversed(casos))), amb["pasta"], str(b))
    ra, rb = tmp_path / "m1.rascunho.jsonl", tmp_path / "m2.rascunho.jsonl"
    assert not a.exists() and not b.exists()  # nunca o arquivo pedido, só o rascunho
    assert ra.read_bytes() == rb.read_bytes() and m1 == m2 and e1 == e2
    por = {(m["caso"], m["tipo"]): m for m in m1}
    # art. 156 -> 157 existe no ato; 156-A também, mas N+1 tem precedência
    assert por[("L-a-001", "renumerado")]["chamada"]["parametros"]["citacao"] == "art. 157 da Lei 9.999/2000"
    assert por[("L-a-001", "renumerado")]["chamada"]["parametros"]["versao"] == "publicacao_original"
    assert por[("L-a-001", "renumerado")]["destino"]["caminho"] == "art. 157"
    assert por[("L-b-002", "renumerado")]["chamada"]["parametros"]["citacao"] == "art. 422 da Lei 9.999/2000"
    assert por[("L-e-001", "renumerado")]["chamada"]["parametros"]["citacao"] == "art. 159 da Lei 9.999/2000"


def _mini_html(tmp_path, html):
    b = html.encode("utf-8")
    sha = hashlib.sha256(b).hexdigest()
    pasta = tmp_path / "ev"
    pasta.mkdir(exist_ok=True)
    (pasta / f"{sha}.html").write_bytes(b)
    return str(pasta), sha


def test_renumerado_usa_n_mais_a_quando_n_mais_1_nao_existe(amb, tmp_path):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    html = ("<html><body><p>LEI Nº 9.997, DE 1º DE JANEIRO DE 2000</p><p>Art. 5º Texto cinco da lei de teste, com "
            "tamanho suficiente para a extração do documento sintético de teste do gerador de mutantes.</p>"
            "<p>Art. 5º-A. Texto cinco A da lei de teste, com tamanho suficiente para a extração do documento "
            "sintético de teste do gerador de mutantes.</p></body></html>")
    pasta, sha = _mini_html(tmp_path, html)
    c.update(norma={"especie": "lei", "numero": "9997", "ano": 2000}, citacao="art. 5º da Lei 9.997/2000", caminho="art. 5º")
    c["gabarito"]["fonte_oficial"].update(sha256=sha, ato_no_documento="LEI Nº 9.997, DE 1º DE JANEIRO DE 2000")
    c["gabarito"]["texto"] = ("Art. 5º Texto cinco da lei de teste, com tamanho suficiente para a extração do documento "
                              "sintético de teste do gerador de mutantes.")
    muts, _, erros = v.gerar_mutantes([c], pasta)
    m = [x for x in muts if x["tipo"] == "renumerado"][0]
    assert m["chamada"]["parametros"]["citacao"] == "art. 5º-A da Lei 9.997/2000" and m["alteracao"]["regra"] == "art. N-A"
    assert not erros


def test_mutante_caractere_troca_letra_central_pela_vizinha(amb):
    casos = base_casos(amb)
    muts, _, _ = v.gerar_mutantes(casos, amb["pasta"])
    m = next(x for x in muts if x["caso"] == "L-a-002" and x["tipo"] == "caractere")
    orig = v.norm(achar(casos, "L-a-002")["gabarito"]["texto"])
    novo = m["chamada"]["parametros"]["trecho"]
    diffs = [i for i in range(len(orig)) if orig[i] != novo[i]]
    assert len(diffs) == 1 and len(orig) == len(novo)
    i = diffs[0]
    assert abs(i - len(orig) // 2) <= 3
    assert ord(novo[i]) - ord(orig[i]) in (1, -1)
    assert m["chamada"]["funcao"] == "verificar_citacao"
    assert m["esperado"] == {"text.status": "!= verified"}


def test_mutante_data_trocada_so_com_data_mutante_em_b_e_c(amb):
    casos = base_casos(amb)
    muts, avisos, erros = v.gerar_mutantes(casos, amb["pasta"])
    dt = [m for m in muts if m["tipo"] == "data_trocada"]
    assert [m["caso"] for m in dt] == ["L-c-001"]
    p = dt[0]["chamada"]["parametros"]
    assert p["data"] == "1999-06-30" and p["trecho"] == v.norm(achar(casos, "L-c-001")["gabarito"]["texto"])
    assert dt[0]["esperado"] == {"text.status": "!= verified", "temporal.status": "!= verified"}
    assert any("L-b-001: sem data_mutante" in a for a in avisos)


def test_mutantes_cobrem_todas_as_capacidades(amb):
    """Sem a união artificial com `{e}`: (e) tem mutante renumerado de verdade (art. 158 -> 159 existe no ato)."""
    muts, _, erros = v.gerar_mutantes(base_casos(amb), amb["pasta"])
    caps = {m["caso"].split("-")[1] for m in muts if m["tipo"] in ("renumerado", "caractere")}
    assert caps == {"a", "b", "c", "d", "e"}
    assert not erros


def test_mutante_de_c_leva_data_e_trecho(amb):
    muts, _, _ = v.gerar_mutantes(base_casos(amb), amb["pasta"])
    m = next(x for x in muts if x["caso"] == "L-c-001" and x["tipo"] == "renumerado")
    assert m["chamada"]["funcao"] == "verificar_citacao"
    assert m["chamada"]["parametros"]["data"] == "2000-06-01" and m["chamada"]["parametros"]["trecho"]


# --------------------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------------------
def _cli(amb, casos, tmp_path, *extra):
    jl = tmp_path / "c.jsonl"
    jl.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in casos), encoding="utf-8")
    return subprocess.run([PY, "-I", "-X", "utf8", str(AQUI / "validar_gabaritos_porta_l.py"), str(jl), amb["pasta"],
                           "--fontes", amb["csv"], *extra], capture_output=True, text=True, encoding="utf-8")


def test_cli_codigo_de_saida_e_linha_final(amb, tmp_path):
    casos = base_casos(amb)
    p = _cli(amb, casos, tmp_path)
    linhas = p.stdout.strip().splitlines()
    assert linhas[-1].endswith(f"{len(casos)} casos, {len([l for l in linhas if l.startswith('FALHA')])} falhas")
    # com pisos, o conjunto de teste pequeno falha por contagem => código 1
    assert p.returncode == 1
    assert any(l.startswith("FALHA capacidade-a:") for l in linhas)
    assert any(l.startswith("ALERTA ") for l in linhas)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["url"] = "https://example.invalid/falso"
    p = _cli(amb, casos, tmp_path)
    assert "FALHA L-a-001: gabarito.fonte_oficial" not in p.stdout
    assert any(l.startswith("FALHA L-a-001: fonte_oficial.url fora da allowlist") for l in p.stdout.splitlines())


def test_cli_gerar_mutantes_grava_so_rascunho_e_nunca_o_congelado(amb, tmp_path):
    out = tmp_path / "mutantes.jsonl"
    p = _cli(amb, base_casos(amb), tmp_path, "--gerar-mutantes", str(out))
    rasc = tmp_path / "mutantes.rascunho.jsonl"
    assert rasc.exists() and not out.exists() and "rascunho de mutantes" in p.stdout
    linhas = [json.loads(l) for l in rasc.read_text(encoding="utf-8").splitlines()]
    assert linhas and all({"id", "caso", "tipo", "chamada", "esperado", "rascunho"} <= set(m) and m["rascunho"] for m in linhas)
    # gerar o rascunho não satisfaz a obrigação de mutantes do congelamento
    assert any(l.startswith("FALHA mutantes:") and "obrigatório" in l for l in p.stdout.splitlines())


def test_cli_json_invalido_e_falha(amb, tmp_path):
    jl = tmp_path / "c.jsonl"
    jl.write_text("{não é json\n", encoding="utf-8")
    p = subprocess.run([PY, "-I", "-X", "utf8", str(AQUI / "validar_gabaritos_porta_l.py"), str(jl), amb["pasta"]],
                       capture_output=True, text=True, encoding="utf-8")
    assert "JSON inválido" in p.stdout and p.returncode == 1


# ==============================================================================================================
# RODADA 2: contraexemplos e controles positivos do parecer-validador-v2-r1.md (achados 1 a 17)
# ==============================================================================================================
import types  # noqa: E402

LEI9990 = "LEI Nº 9.990, DE 1º DE JANEIRO DE 2000"
URL_PUB_MINI = "https://www2.camara.leg.br/legin/fed/lei/2000/mini-publicacaooriginal-1-pl.html"
URL_COMP_MINI = "https://www2.camara.leg.br/legin/fed/lei/2000/mini-normaatualizada-pl.html"
N9990 = {"especie": "lei", "numero": "9990", "ano": 2000}


def _doc(tmp_path, conteudo, ext="html"):
    b = conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8")
    sha = hashlib.sha256(b).hexdigest()
    pasta = tmp_path / "ev_mini"
    pasta.mkdir(exist_ok=True)
    (pasta / f"{sha}.{ext}").write_bytes(b)
    return str(pasta), sha


def _html(*paragrafos):
    return "<html><body>" + "".join(f"<p>{p}</p>" for p in paragrafos) + "</body></html>"


def _caso(sha, texto, cit, cam, ato=LEI9990, norma=None, cap="a", fam="original", url=URL_PUB_MINI, tipo="texto",
          id_=None, **g):
    gab = {"tipo": tipo, "texto": texto, "motivos_aceitos": [], "cadeia": [], "alvos": [], "alvos_equivalentes": {},
           "fonte_oficial": {"url": url, "sha256": sha, "capturado_em": CAPT, "orgao": "Câmara dos Deputados",
                             "ato_no_documento": ato, "pagina": 1},
           "fundamento_data": "Texto extraído da fonte oficial indicada."}
    gab.update(g)
    return {"id": id_ or f"L-{cap}-001", "conjunto": "desenvolvimento", "capacidade": cap, "familia_alteracao": fam,
            "familia_fundamento": "publicação original do ato" if fam == "original" else "anotação na compilada",
            "norma": dict(norma or N9990), "citacao": cit, "caminho": cam, "data": None, "data_mutante": None,
            "trecho": None, "gabarito": gab, "norma_grande": False}


def _val(caso, pasta, pisos=False):
    return v.validar([copy.deepcopy(caso)], pasta, None, None, pisos)


def _um(tmp_path, paragrafos, texto, cit, cam, **kw):
    pasta, sha = _doc(tmp_path, _html(*paragrafos))
    return _caso(sha, texto, cit, cam, **kw), pasta


# --------------------------------------------------------------------------------------------------------------
# Achado 1: publicação original e validade histórica documentadas
# --------------------------------------------------------------------------------------------------------------
def test_r2_a1_compilada_nao_prova_a_publicacao_original_em_a(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-b-001")
    c.update(id="L-a-009", capacidade="a")  # compilada de 2001 declarada como "publicação original"
    acusa(rodar(casos, amb), "L-a-009", "(a) exige a publicação")


def test_r2_a1_positivo_historico_exige_ato_do_evento_anterior_ou_igual_a_D(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-b-001")
    c.update(id="L-c-009", capacidade="c", data="1800-01-01")
    c["gabarito"]["tipo"] = "verificado_para_D"
    acusa(rodar(casos, amb), "L-c-009", "anterior à data do ato do evento")
    c["data"] = "2001-10-30"  # véspera do ato 7.777 (31/10/2001)
    acusa(rodar(casos, amb), "L-c-009", "anterior à data do ato do evento")
    c["data"] = "2001-10-31"
    assert not falhas_de(rodar(casos, amb), "L-c-009")
    c["data"] = "2002-01-01"
    res = rodar(casos, amb)
    assert not falhas_de(res, "L-c-009")
    assert any(cid == "L-c-009" and cat == "(i)" for cid, cat, _ in res.revisoes)


def test_r2_a1_data_do_ato_so_pelo_ano_nao_sustenta_D_dentro_do_ano(tmp_path):
    pasta, sha = _doc(tmp_path, _html(LEI9990, "Texto compilado", "Art. 5. Regra do quinto artigo da lei. "
                                      "(Redação dada pela Lei nº 7.777, de 2001)", "Art. 6. Regra do sexto artigo."))
    c = _caso(sha, "Art. 5. Regra do quinto artigo da lei.", "art. 5º da Lei 9.990/2000", "art. 5º", cap="c",
              fam="lei-7777-2001", url=URL_COMP_MINI, tipo="verificado_para_D", id_="L-c-001")
    c["data"] = "2001-06-01"
    acusa(_val(c, pasta), "L-c-001", "só é demonstrada pelo ano")
    c["data"] = "2002-01-01"
    assert not falhas_de(_val(c, pasta), "L-c-001")


def test_r2_revisao_humana_e_registrada_por_categoria(amb):
    res = rodar(base_casos(amb), amb)
    cats = {cat for _, cat, _ in res.revisoes}
    assert {"(i)", "(iii)", "(iv)"} <= cats
    assert not [m for c, m in res.alertas if "REVISAO_HUMANA" in m]  # nunca misturada com ALERTA


# --------------------------------------------------------------------------------------------------------------
# Achado 2: identidade do ato
# --------------------------------------------------------------------------------------------------------------
def test_r2_a2_norma_e_citacao_falsas_com_familia_de_outra_publicacao(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c.update(norma={"especie": "lei", "numero": "123456", "ano": 1900}, citacao="art. 156 da Lei 123456/1900",
             familia_alteracao="lei-9999-2000")
    acusa(rodar(casos, amb), "L-a-001", "não há relação documental entre ato alterador, norma alterada e dispositivo")


def test_r2_a2_publicacao_legitima_do_ato_alterador_e_aceita(amb):
    res = rodar(base_casos(amb), amb)
    assert not falhas_de(res, "L-a-003")  # Lei 8.000/2001 cita a Lei 9.999/2000 antes do art. 157 que inclui


def test_r2_a2_cabecalho_em_caixa_mista_separa_os_atos(tmp_path):
    c, pasta = _um(tmp_path, [LEI9990, "Art. 1º Primeira regra da lei nove nove nove zero.",
                              "Decreto nº 100, de 5 de outubro de 2021",
                              "Art. 2º Segunda regra, que pertence ao decreto e não à lei."],
                   "Art. 2º Segunda regra, que pertence ao decreto e não à lei.", "art. 2º da Lei 9.990/2000", "art. 2º")
    acusa(_val(c, pasta), "L-a-001", "cabeçalho de ato mais próximo")
    c1, pasta = _um(tmp_path, [LEI9990, "Art. 1º Primeira regra da lei nove nove nove zero.",
                               "Decreto nº 100, de 5 de outubro de 2021",
                               "Art. 2º Segunda regra, que pertence ao decreto e não à lei."],
                    "Art. 1º Primeira regra da lei nove nove nove zero.", "art. 1º da Lei 9.990/2000", "art. 1º")
    assert not falhas_de(_val(c1, pasta), "L-a-001")


def test_r2_a2_referencia_a_ato_no_meio_da_frase_nao_e_cabecalho(tmp_path):
    c, pasta = _um(tmp_path, [LEI9990, "Art. 1º Aplica-se a Lei nº 6.404, de 15 de dezembro de 1976, a todos.",
                              "Art. 2º Segunda regra da lei nove nove nove zero."],
                   "Art. 2º Segunda regra da lei nove nove nove zero.", "art. 2º da Lei 9.990/2000", "art. 2º")
    assert not falhas_de(_val(c, pasta), "L-a-001")


# --------------------------------------------------------------------------------------------------------------
# Achado 3: o caminho completo é vinculado à posição estrutural
# --------------------------------------------------------------------------------------------------------------
T156_P1 = "§ 1º Ainda que observado o disposto neste artigo, o administrador somente pode contratar em condições razoáveis."
T156_P2 = "§ 2º O negócio contratado com infração do disposto no § 1º é anulável."


def test_r2_a3_paragrafo_do_art_156_atribuido_ao_art_157(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c.update(citacao="§ 1º do art. 157 da Lei 9.999/2000", caminho="art. 157, § 1º")
    c["gabarito"]["texto"] = T156_P1
    acusa(rodar(casos, amb), "L-a-001", "não localizado estruturalmente")


def test_r2_a3_citacao_ao_par2_com_caminho_e_texto_do_par1(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c.update(citacao="§ 2º do art. 156 da Lei 9.999/2000", caminho="art. 156, § 1º")
    c["gabarito"]["texto"] = T156_P1
    acusa(rodar(casos, amb), "L-a-001", "não corresponde ao dispositivo citado")


def test_r2_a3_paragrafo_correto_da_cadeia_e_aceito(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    for cit, cam, t in (("§ 1º do art. 156 da Lei 9.999/2000", "art. 156, § 1º", T156_P1),
                        ("§ 2º do art. 156 da Lei 9.999/2000", "art. 156, § 2º", T156_P2)):
        c.update(citacao=cit, caminho=cam)
        c["gabarito"]["texto"] = t
        assert not falhas_de(rodar(casos, amb), "L-a-001"), cam


def test_r2_a3_artigo_inteiro_pedido_com_caminho_caput_e_so_o_caput(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-a-001")
    c["caminho"] = "art. 156, caput"
    c["gabarito"]["texto"] = ("Art. 156. É vedado ao administrador intervir em operação social em que tiver interesse "
                              "conflitante com o da companhia.")
    acusa(rodar(casos, amb), "L-a-001", "não corresponde ao dispositivo citado")
    c["citacao"] = "art. 156, caput, da Lei 9.999/2000"  # pedido do caput: recorte do caput é o pedido
    res = rodar(casos, amb)
    assert not falhas_de(res, "L-a-001")


def test_r2_a3_inicial_maiuscula_antes_do_artigo_nao_prova_rubrica(tmp_path):
    c, pasta = _um(tmp_path, [LEI9990, "Art. 1º Regra do primeiro artigo.", "Continuação normativa obrigatória",
                              "Art. 2º Regra do segundo artigo."],
                   "Art. 1º Regra do primeiro artigo.", "art. 1º da Lei 9.990/2000", "art. 1º")
    acusa(_val(c, pasta), "L-a-001", "limite desconhecido")
    c, pasta = _um(tmp_path, [LEI9990, "Art. 1º Regra do primeiro artigo.", "Da Administração",
                              "Art. 2º Regra do segundo artigo."],
                   "Art. 1º Regra do primeiro artigo.", "art. 1º da Lei 9.990/2000", "art. 1º")
    assert not falhas_de(_val(c, pasta), "L-a-001")


def test_r2_a3_gramatica_do_caminho_hierarquia_e_numerais():
    for ruim in ("art. 1, § 1, § 2", "art. 1, inciso III, § 1", "art. 1, inciso IIII", "art. 1, caput, caput",
                 "art. 1, alínea a, inciso II", "art. 1, § 0", "art. 0", "art. 1, inciso II, inciso III",
                 "art. 1, inciso II, alínea a, alínea b", "Anexo I, tabela, art. 1"):
        assert v.parse_caminho(ruim) is None, ruim
    for bom in ("art. 1, caput, inciso II", "art. 1, § 2, inciso IV, alínea c", "art. 1, parágrafo único, inciso I",
                "Anexo II, art. 3º, § 1º", "Anexo I, tabela", "art. 254-A"):
        assert v.parse_caminho(bom) is not None, bom


# --------------------------------------------------------------------------------------------------------------
# Achado 4: limpeza de PDF nunca apaga conteúdo normativo
# --------------------------------------------------------------------------------------------------------------
def test_r2_a4_limpeza_preserva_inciso_repetido_nas_bordas_e_remove_o_cabecalho_de_pagina():
    p1 = "Texto compilado - Página 1\nLEI Nº 9.990, DE 1º DE JANEIRO DE 2000\nArt. 1º Obrigação primeira:\nI - Dever obrigatório para todos."
    p2 = "Texto compilado - Página 2\nI - Dever obrigatório para todos.\nArt. 2º Segunda obrigação."
    p3 = "Texto compilado - Página 3\nI - Dever obrigatório para todos.\nArt. 3º Terceira obrigação."
    out, n = v.limpar_paginas_pdf([p1, p2, p3])  # a linha do inciso se repete no topo de 2 páginas
    assert [o.count("I - Dever obrigatório para todos.") for o in out] == [1, 1, 1]
    assert "Texto compilado" not in "".join(out) and n == 3


def test_r2_a4_inciso_repetido_nas_bordas_nao_vira_dispositivo_incompleto_aceito(tmp_path):
    paginas = [[LEI9990, "Art. 1º Obrigação primeira:", "I - Dever obrigatório para todos."],
               ["I - Dever obrigatório para todos.", "Art. 2º Segunda obrigação."],
               ["I - Dever obrigatório para todos.", "Art. 3º Terceira obrigação."]]
    pasta, sha = _doc(tmp_path, pdf_bytes(paginas), "pdf")
    c = _caso(sha, "Art. 1º Obrigação primeira:", "art. 1º da Lei 9.990/2000", "art. 1º")
    acusa(_val(c, pasta), "L-a-001", "dispositivo incompleto")
    c["gabarito"]["texto"] = ("Art. 1º Obrigação primeira: I - Dever obrigatório para todos. "
                              "I - Dever obrigatório para todos.")
    assert not falhas_de(_val(c, pasta), "L-a-001")


def test_r2_a4_linha_repetida_com_ponto_final_ou_marcador_nao_e_cabecalho():
    paginas = ["Repete esta regra normativa aqui.\nArt. 1º Texto um.", "Repete esta regra normativa aqui.\nArt. 2º Texto dois."]
    out, n = v.limpar_paginas_pdf(paginas)
    assert n == 0 and all("Repete esta regra" in o for o in out)


# --------------------------------------------------------------------------------------------------------------
# Achado 5: (d) identifica o anexo e aceita o anexo inteiro
# --------------------------------------------------------------------------------------------------------------
DEC7 = "DECRETO Nº 7, DE 1º DE JANEIRO DE 2020"
N_DEC7 = {"especie": "decreto", "numero": "7", "ano": 2020}
DOC_ANEXO_I = [DEC7, "Art. 1º Aprova o regulamento conforme ANEXO I.", "Art. 2º Regra do corpo do decreto.", "ANEXO I",
               "Art. 1º Primeira regra do anexo.", "Art. 2º Segunda regra do anexo."]


def test_r2_a5_anexo_inexistente_e_rejeitado(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-d-001")
    c.update(citacao="Art. 2º do Anexo IX do Decreto 100/2021", caminho="Anexo IX, art. 2º")
    acusa(rodar(casos, amb), "L-d-001", "não localizado estruturalmente")


def test_r2_a5_mencao_a_anexo_em_remissao_nao_e_rubrica_e_artigo_do_corpo_nao_e_do_anexo(tmp_path):
    kw = dict(cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    cit, cam = "Art. 2º do Anexo I do Decreto 7/2020", "Anexo I, art. 2º"
    c, pasta = _um(tmp_path, DOC_ANEXO_I, "Art. 2º Regra do corpo do decreto.", cit, cam, **kw)
    acusa(_val(c, pasta), "L-d-001", "não é a do dispositivo")
    c, pasta = _um(tmp_path, DOC_ANEXO_I, "Art. 2º Segunda regra do anexo.", cit, cam, **kw)
    assert not falhas_de(_val(c, pasta), "L-d-001")
    # sem rubrica de anexo, só a remissão "conforme ANEXO I": não há anexo algum
    c, pasta = _um(tmp_path, DOC_ANEXO_I[:3], "Art. 2º Regra do corpo do decreto.", cit, cam, **kw)
    acusa(_val(c, pasta), "L-d-001", "não localizado estruturalmente")


def test_r2_a5_anexo_inteiro_correto_e_aceito_e_incompleto_e_rejeitado(tmp_path):
    kw = dict(cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    cit, cam = "Anexo I do Decreto 7/2020", "Anexo I"
    inteiro = "ANEXO I Art. 1º Primeira regra do anexo. Art. 2º Segunda regra do anexo."
    c, pasta = _um(tmp_path, DOC_ANEXO_I, inteiro, cit, cam, **kw)
    assert not falhas_de(_val(c, pasta), "L-d-001")
    c, pasta = _um(tmp_path, DOC_ANEXO_I, "ANEXO I Art. 1º Primeira regra do anexo.", cit, cam, **kw)
    acusa(_val(c, pasta), "L-d-001", "anexo incompleto")
    c, pasta = _um(tmp_path, DOC_ANEXO_I, inteiro, "Anexo II do Decreto 7/2020", "Anexo II", **kw)
    acusa(_val(c, pasta), "L-d-001", "não localizado estruturalmente")


# --------------------------------------------------------------------------------------------------------------
# Achados 6 e 7: remissões e alvos equivalentes
# --------------------------------------------------------------------------------------------------------------
def _alvo(cam, obra="Lei 9.990/2000"):
    return {"obra": obra, "caminho": cam}


def _caso_e(tmp_path, corpo, alvos, eq=None):
    c, pasta = _um(tmp_path, [LEI9990, f"Art. 9. {corpo}", "Art. 10. Fim da lei de teste."], f"Art. 9. {corpo}",
                   "art. 9º da Lei 9.990/2000", "art. 9º", cap="e", id_="L-e-001", alvos=alvos,
                   alvos_equivalentes=eq or {})
    return c, pasta


def test_r2_a6_faixa_de_artigos_expande_todos_os_artigos(tmp_path):
    corpo = "Aplica-se o disposto nos arts. 10 a 12 desta Lei."
    c, pasta = _caso_e(tmp_path, corpo, [_alvo("art. 10"), _alvo("art. 11"), _alvo("art. 12")])
    assert not falhas_de(_val(c, pasta), "L-e-001")
    c["gabarito"]["alvos"] = [_alvo("art. 10"), _alvo("art. 12")]
    acusa(_val(c, pasta), "L-e-001", "ausente de `alvos`: lei-9990-2000 art. 11")


def test_r2_a6_remissao_interna_ao_paragrafo_do_proprio_artigo(tmp_path):
    corpo = "Observado o art. 4º desta Lei, aplica-se o disposto no § 1º deste artigo."
    completo = [_alvo("art. 4º"), _alvo("art. 9º, § 1º")]
    c, pasta = _caso_e(tmp_path, corpo, completo)
    assert not falhas_de(_val(c, pasta), "L-e-001")
    c["gabarito"]["alvos"] = [_alvo("art. 4º")]  # omitir a remissão interna
    acusa(_val(c, pasta), "L-e-001", "ausente de `alvos`: lei-9990-2000 art. 9, § 1")


def test_r2_a6_listas_de_incisos_e_paragrafos_antes_do_artigo(tmp_path):
    corpo = "Aplicam-se os incisos II e III do art. 5º e os §§ 1º e 2º do art. 6º desta Lei."
    completo = [_alvo("art. 5º, inciso II"), _alvo("art. 5º, inciso III"), _alvo("art. 6º, § 1º"), _alvo("art. 6º, § 2º")]
    c, pasta = _caso_e(tmp_path, corpo, completo)
    assert not falhas_de(_val(c, pasta), "L-e-001")
    c["gabarito"]["alvos"] = completo[:1] + completo[2:]
    acusa(_val(c, pasta), "L-e-001", "ausente de `alvos`: lei-9990-2000 art. 5, inciso III")


def test_r2_a6_caput_e_artigo_inteiro_sao_alvos_distintos(tmp_path):
    corpo = "Aplicam-se o art. 10, caput, e o art. 11 desta Lei."
    c, pasta = _caso_e(tmp_path, corpo, [_alvo("art. 10, caput"), _alvo("art. 11")])
    assert not falhas_de(_val(c, pasta), "L-e-001")
    c["gabarito"]["alvos"] = [_alvo("art. 10"), _alvo("art. 11")]
    res = _val(c, pasta)
    acusa(res, "L-e-001", "ausente de `alvos`: lei-9990-2000 art. 10, caput")
    acusa(res, "L-e-001", "não aparece como remissão expressa")


def test_r2_a6_construcao_nao_reconhecida_vai_a_revisao_humana_sem_reprovar_nem_aprovar(tmp_path):
    corpo = "Observados o artigo anterior e os arts. 3º a 5º-A desta Lei."
    completo = [_alvo("art. 3º"), _alvo("art. 4º"), _alvo("art. 5º"), _alvo("art. 5º-A")]
    c, pasta = _caso_e(tmp_path, corpo, completo)
    res = _val(c, pasta)
    assert not falhas_de(res, "L-e-001")  # a lista documentalmente completa não é reprovada
    assert any(cat == "(ii)" for _, cat, _ in res.revisoes)  # e também não é aprovada em silêncio
    c["gabarito"]["alvos"] = [_alvo("art. 5º-A")]  # o que o parser reconhece e falta continua reprovando
    acusa(_val(c, pasta), "L-e-001", "ausente de `alvos`: lei-9990-2000 art. 3")


def test_r2_a7_equivalente_arbitrario_e_alvo_distinto_e_reprova(tmp_path):
    corpo = "Aplica-se o disposto no art. 4º, § 2º, desta Lei."
    c, pasta = _caso_e(tmp_path, corpo, [_alvo("art. 4º, § 2º")],
                       {"Lei 9.990/2000, art. 4º, § 2º": ["Lei 999999/1900, art. 999"]})
    acusa(_val(c, pasta), "L-e-001", "alvo DISTINTO")
    c["gabarito"]["alvos_equivalentes"] = {"Lei 9.990/2000, art. 4º, § 2º": ["Lei 9.990/2000, art. 4º, § 3º"]}
    acusa(_val(c, pasta), "L-e-001", "alvo DISTINTO")


def test_r2_a7_equivalente_em_outra_grafia_do_mesmo_alvo_e_aceito(tmp_path):
    corpo = "Aplica-se o disposto no art. 4º, § 2º, desta Lei."
    c, pasta = _caso_e(tmp_path, corpo, [_alvo("art. 4º, § 2º")],
                       {"Lei 9.990/2000, art. 4º, § 2º": ["Lei nº 9.990, de 1º de janeiro de 2000, art. 4º, § 2º"]})
    assert not falhas_de(_val(c, pasta), "L-e-001")


# --------------------------------------------------------------------------------------------------------------
# Achado 8: independência por evento sem inflação
# --------------------------------------------------------------------------------------------------------------
def _cm(i, norma, fam, cap="a", ano=2000, tipo="texto"):
    return {"id": f"L-{cap}-{i:03d}", "capacidade": cap, "familia_alteracao": fam,
            "norma": {"especie": "lei", "numero": str(norma), "ano": ano}, "gabarito": {"tipo": tipo}}


def test_r2_a8_publicacao_da_alteradora_e_redacao_que_ela_deu_sao_um_so_evento():
    casos = [_cm(1, 100, "original"), _cm(2, 1, "lei-100-2000")] + [_cm(i, i * 10, "original") for i in range(3, 9)]
    res = v.Resultado()
    v.contagem(casos, res, set())
    assert "capacidade a: 7 unidades válidas de 7 (8 casos)" in " ".join(res.info)  # sete eventos, não oito
    assert any(c == "capacidade-a" for c, _ in res.falhas)
    res = v.Resultado()
    v.contagem(casos + [_cm(9, 90, "original")], res, set())
    assert "capacidade a: 8 unidades válidas de 8" in " ".join(res.info)
    assert not [c for c, _ in res.falhas if c == "capacidade-a"]


def test_r2_a8_grafias_diferentes_do_mesmo_ato_sao_um_evento():
    casos = [_cm(1, 1, "lei-07777-2001"), _cm(2, 2, "lei-7777-2001"), _cm(3, 3, "lei-007777-2001")]
    res = v.Resultado()
    v.contagem(casos, res, set())
    assert "capacidade a: 1 unidades válidas de 1 (3 casos)" in " ".join(res.info)
    assert v.canon_fam("mp-02183-056-2001") == "mp-2183-56-2001"


def test_r2_a8_vide_nao_da_redacao_e_nao_pode_ser_familia(tmp_path):
    pasta, sha = _doc(tmp_path, _html(LEI9990, "Texto compilado", "Art. 5. Regra do quinto artigo da lei. "
                                      "(Redação dada pela Lei nº 7.777, de 31/10/2001) (Vide Lei nº 8.888, de 2005)",
                                      "Art. 6. Regra do sexto artigo."))
    c = _caso(sha, "Art. 5. Regra do quinto artigo da lei.", "art. 5º da Lei 9.990/2000", "art. 5º", cap="b",
              fam="lei-8888-2005", url=URL_COMP_MINI, id_="L-b-001")
    acusa(_val(c, pasta), "L-b-001", "não consta das anotações do dispositivo que dão a redação")
    c["familia_alteracao"] = "lei-7777-2001"
    assert not falhas_de(_val(c, pasta), "L-b-001")


def test_r2_a8_anotacao_sem_ano_nao_e_reconhecida_nem_aceita_como_familia(tmp_path):
    assert not v.tem_anotacao_editorial("(Redação dada pela Lei nº 7.777)")
    assert v.atos_das_anotacoes(["(Redação dada pela Lei nº 7.777)"]) == set()
    pasta, sha = _doc(tmp_path, _html(LEI9990, "Texto compilado", "Art. 5. Regra do quinto artigo da lei. "
                                      "(Redação dada pela Lei nº 7.777)", "Art. 6. Regra do sexto artigo."))
    c = _caso(sha, "Art. 5. Regra do quinto artigo da lei.", "art. 5º da Lei 9.990/2000", "art. 5º", cap="b",
              fam="lei-7777-2001", url=URL_COMP_MINI, id_="L-b-001")
    res = _val(c, pasta)
    assert falhas_de(res, "L-b-001")  # nada é adivinhado: sem ano, o ato não vira família
    acusa(res, "L-b-001", "não traz anotação editorial do dispositivo que dê a redação")


def test_r2_a16_representante_da_unidade_e_o_menor_id_antes_de_avaliar_resultados():
    casos = [_cm(1, 1, "original"), _cm(2, 1, "original")] + [_cm(i, i, "original") for i in range(3, 10)]
    res = v.Resultado()
    v.contagem(casos, res, {"L-a-001"})  # 001 falho: a unidade (norma 1) NÃO passa para 002
    info = " ".join(res.info)
    assert "capacidade a: 7 unidades válidas de 8" in info and "L-a-001" in info and "L-a-002" not in info.split(
        "representantes (menor id da unidade):")[1].split("capacidade b")[0]
    assert any(c == "capacidade-a" for c, _ in res.falhas)


# --------------------------------------------------------------------------------------------------------------
# Achado 9: históricos negativos documentados
# --------------------------------------------------------------------------------------------------------------
def test_r2_a9_cadeia_e_ultima_versao_ficticias_reprovam(amb):
    casos = base_casos(amb)
    g = achar(casos, "L-c-003")["gabarito"]
    g["cadeia"] = [{"ato": "lei-123456-1900", "data": "1900-01-01"}]
    g["ultima_versao_anterior"] = {"ato": "lei-123456-1900", "data": "1900-01-01"}
    res = rodar(casos, amb)
    acusa(res, "L-c-003", "cadeia: o ato 'lei-123456-1900' não está documentado")
    acusa(res, "L-c-003", "ultima_versao_anterior: o ato 'lei-123456-1900' não está documentado")
    g["ultima_versao_anterior"] = "mentira"  # tipo errado: falha de esquema, não processada como texto livre
    acusa(rodar(casos, amb), "L-c-003", "gabarito.ultima_versao_anterior deve ser dict")


def test_r2_a9_ultima_versao_anterior_ausente_ou_com_data_errada_e_falha(amb):
    casos = base_casos(amb)
    g = achar(casos, "L-c-003")["gabarito"]
    del g["ultima_versao_anterior"]
    acusa(rodar(casos, amb), "L-c-003", "exige `ultima_versao_anterior`")
    g["ultima_versao_anterior"] = {"ato": "original", "data": "1990-01-01"}
    acusa(rodar(casos, amb), "L-c-003", "não confere com a data documentada")
    g["ultima_versao_anterior"] = {"ato": "original", "data": "2000-01-01"}
    g["cadeia"] = [{"ato": "lei-7777-2001", "data": "2001-10-30"}]
    acusa(rodar(casos, amb), "L-c-003", "não confere com a data documentada")


def test_r2_a9_cabecalho_da_lei_nao_e_trecho_normativo_do_dispositivo(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-003")["trecho"] = "LEI Nº 9.999, DE 1º DE JANEIRO DE 2000"
    acusa(rodar(casos, amb), "L-c-003", "trecho não é texto do DISPOSITIVO")
    casos = base_casos(amb)
    achar(casos, "L-c-003")["trecho"] = "Os prazos contam-se em dias corridos."  # texto de OUTRO artigo (art. 15)
    acusa(rodar(casos, amb), "L-c-003", "trecho não é texto do DISPOSITIVO")


def test_r2_a9_ressalva_de_vigencia_sem_ato_no_dispositivo_incluido_reprova(tmp_path):
    def caso(paren):
        pasta, sha = _doc(tmp_path, _html(LEI9990, "Texto compilado", f"Art. 20. Texto do vigésimo artigo da lei.{paren} "
                                          "(Incluído pela Lei nº 7.777, de 31/10/2001)", "Art. 21. Fim."))
        c = _caso(sha, "", "art. 20 da Lei 9.990/2000", "art. 20", cap="c", fam="lei-7777-2001", url=URL_COMP_MINI,
                  tipo="nao_existia_em_D", id_="L-c-001", condicao_inexistencia="anterior_a_inclusao")
        c["data"] = "2001-06-01"
        return c, pasta
    c, pasta = caso("")
    assert not falhas_de(_val(c, pasta), "L-c-001")
    c, pasta = caso(" (Vigência)")
    acusa(_val(c, pasta), "L-c-001", "ressalva de vigência/efeito/veto/revogação")


# --------------------------------------------------------------------------------------------------------------
# Achado 10: revogação parcial; casos sem texto com todos os controles
# --------------------------------------------------------------------------------------------------------------
DOC_REV = [LEI9990, "Texto compilado", "Art. 30. Caput vigente do artigo trinta. § 1º (Revogado pela Lei nº 7.777, de 31/10/2001)",
           "Art. 31. (Revogado pela Lei nº 7.777, de 31/10/2001)", "Art. 32. Fim."]


def _rev(tmp_path, cit, cam):
    pasta, sha = _doc(tmp_path, _html(*DOC_REV))
    return _caso(sha, "", cit, cam, cap="b", fam="lei-7777-2001", url=URL_COMP_MINI, tipo="revogado_vigente",
                 id_="L-b-001"), pasta


def test_r2_a10_revogacao_parcial_nao_e_revogacao_do_artigo_inteiro(tmp_path):
    c, pasta = _rev(tmp_path, "art. 30 da Lei 9.990/2000", "art. 30")
    acusa(_val(c, pasta), "L-b-001", "revogação parcial")
    c, pasta = _rev(tmp_path, "§ 1º do art. 30 da Lei 9.990/2000", "art. 30, § 1º")
    assert not falhas_de(_val(c, pasta), "L-b-001")  # o § 1º, esse sim, está inteiro revogado
    c, pasta = _rev(tmp_path, "art. 31 da Lei 9.990/2000", "art. 31")
    assert not falhas_de(_val(c, pasta), "L-b-001")


def test_r2_a10_revogado_com_familia_ficticia_e_ato_de_outro_decreto_reprova(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-b-003")
    c["familia_alteracao"] = "lei-123456-1900"
    c["gabarito"]["fonte_oficial"]["ato_no_documento"] = ATO_DEC
    res = rodar(casos, amb)
    acusa(res, "L-b-003", "família 'lei-123456-1900' não consta das anotações")
    acusa(res, "L-b-003", "ato_no_documento")


def test_r2_a10_nao_existia_e_nao_verificado_passam_por_ato_pagina_e_familia(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-002")["gabarito"]["fonte_oficial"]["ato_no_documento"] = ATO_DEC
    achar(casos, "L-c-003")["gabarito"]["fonte_oficial"]["pagina"] = 7
    achar(casos, "L-c-003")["familia_alteracao"] = "lei-8888-2005"
    res = rodar(casos, amb)
    acusa(res, "L-c-002", "ato_no_documento")
    acusa(res, "L-c-003", "família 'lei-8888-2005'")


# --------------------------------------------------------------------------------------------------------------
# Achado 11: mutantes só com expectativas válidas; falta de mutante obrigatório é falha
# --------------------------------------------------------------------------------------------------------------
def test_r2_a11_data_mutante_sem_outra_redacao_documentada_e_invalida(amb):
    casos = base_casos(amb)
    achar(casos, "L-c-001")["data_mutante"] = "2000-06-02"  # texto original vale em 2000-06-01: sem outra redação
    acusa(rodar(casos, amb), "L-c-001", "não é anterior à obra")
    muts, _, erros = v.gerar_mutantes(casos, amb["pasta"])
    assert any("L-c-001" in e and "data_mutante inválida" in e for e in erros)
    assert not any(m["caso"] == "L-c-001" and m["tipo"] == "data_trocada" for m in muts)


def test_r2_a11_destino_de_anexo_inexistente_ou_de_outro_ato_nao_vira_mutante(tmp_path):
    kw = dict(cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    # só o Anexo I (arts. 1 e 2): não existe Anexo II nem art. 3 no anexo
    c, pasta = _um(tmp_path, DOC_ANEXO_I[:1] + DOC_ANEXO_I[3:], "Art. 2º Segunda regra do anexo.",
                   "Art. 2º do Anexo I do Decreto 7/2020", "Anexo I, art. 2º", **kw)
    muts, _, erros = v.gerar_mutantes([c], pasta)
    assert not [m for m in muts if m["tipo"] == "renumerado"]
    assert any("mutante obrigatório ausente" in e for e in erros)
    # com o Anexo II no ato, o destino é o anexo seguinte (regra dos anexos tem precedência)
    doc2 = DOC_ANEXO_I[:1] + DOC_ANEXO_I[3:] + ["ANEXO II", "Art. 1º Primeira regra do segundo anexo.",
                                                "Art. 2º Segunda regra do segundo anexo."]
    c, pasta = _um(tmp_path, doc2, "Art. 2º Segunda regra do anexo.", "Art. 2º do Anexo I do Decreto 7/2020",
                   "Anexo I, art. 2º", **kw)
    muts, _, erros = v.gerar_mutantes([c], pasta)
    m = next(x for x in muts if x["tipo"] == "renumerado")
    assert "Anexo II" in m["chamada"]["parametros"]["citacao"] and not erros
    # o art. 2 que existe só em OUTRO ato do mesmo documento não é destino do art. 1 do primeiro
    c, pasta = _um(tmp_path, [DEC7, "Art. 1º Primeira regra do primeiro decreto.", "DECRETO Nº 8, DE 1º DE JANEIRO DE 2020",
                              "Art. 1º Regra um do segundo decreto.", "Art. 2º Regra dois do segundo decreto."],
                   "Art. 1º Primeira regra do primeiro decreto.", "art. 1º do Decreto 7/2020", "art. 1º",
                   norma=N_DEC7, ato=DEC7, id_="L-a-001")
    muts, _, erros = v.gerar_mutantes([c], pasta)
    assert not [m for m in muts if m["tipo"] == "renumerado"] and any("renumerado" in e for e in erros)


def test_r2_a11_falta_de_mutante_obrigatorio_reprova_no_cli(amb, tmp_path):
    casos = base_casos(amb)
    achar(casos, "L-e-001")["gabarito"]["fonte_oficial"]["ato_no_documento"] = ATO_LEI
    html = HTML_PUB.replace("<p>Art. 159. Os administradores prestam contas na forma do estatuto social.</p>\n", "")
    pasta = tmp_path / "ev"
    pasta.mkdir()
    sha = hashlib.sha256(html.encode("utf-8")).hexdigest()
    (pasta / f"{sha}.html").write_bytes(html.encode("utf-8"))
    for c in casos:
        if c["gabarito"]["fonte_oficial"]["sha256"] == amb["shas"]["pub"]:
            c["gabarito"]["fonte_oficial"]["sha256"] = sha
    for k, b in (("comp", HTML_COMP), ("pdf", None), ("dec", None), ("alt", HTML_ALT)):
        origem = Path(amb["pasta"]) / f"{amb['shas'][k]}.{'html' if b else 'pdf'}"
        (pasta / origem.name).write_bytes(origem.read_bytes())
    jl = tmp_path / "c.jsonl"
    jl.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in casos), encoding="utf-8")
    out = tmp_path / "mut.jsonl"
    p = subprocess.run([PY, "-I", "-X", "utf8", str(VALIDADOR), str(jl), str(pasta), "--gerar-mutantes", str(out)],
                       capture_output=True, text=True, encoding="utf-8")
    # D5: o gerador é só rascunho; o que ele não consegue gerar vira ALERTA do rascunho, não FALHA do conjunto
    assert any(l.startswith("ALERTA rascunho-mutantes:") and "L-e-001" in l and "renumerado" in l
               for l in p.stdout.splitlines())
    assert not out.exists() and (tmp_path / "mut.rascunho.jsonl").exists()


# --------------------------------------------------------------------------------------------------------------
# Achado 12: obrigações globais da matriz sempre conferidas
# --------------------------------------------------------------------------------------------------------------
def _reserva(n_por_cap=10, tipo_c="verificado_para_D"):
    casos = []
    for cap in "abcde":
        for i in range(1, n_por_cap + 1):
            c = _cm(i, 100 + i, "original", cap=cap, tipo=tipo_c if cap == "c" else "texto")
            c["id"] = f"R-{cap}-{i:03d}"
            c["conjunto"] = "reserva"
            casos.append(c)
    return casos


def test_r2_a12_reserva_sintetica_sem_positivos_historicos_reprova():
    res = v.Resultado()
    v.contagem(_reserva(tipo_c="nao_verificado_para_D"), res, set(), "reserva")
    assert any("0 de 10 casos (c) da reserva são verificado_para_D" in m for _, m in res.falhas)


def test_r2_a12_reserva_valida_passa_e_o_limite_de_40_por_cento_e_exato():
    res = v.Resultado()
    v.contagem(_reserva(), res, set(), "reserva")
    assert res.falhas == []
    casos = _reserva(tipo_c="nao_verificado_para_D")
    for c in [x for x in casos if x["capacidade"] == "c"][:4]:
        c["gabarito"]["tipo"] = "verificado_para_D"
    res = v.Resultado()
    v.contagem(casos, res, set(), "reserva")
    assert res.falhas == []  # 4 de 10 = 40%
    for c in [x for x in casos if x["capacidade"] == "c"][:1]:
        c["gabarito"]["tipo"] = "nao_verificado_para_D"
    res = v.Resultado()
    v.contagem(casos, res, set(), "reserva")
    assert any("3 de 10" in m for _, m in res.falhas)  # 30%


def test_r2_a12_composicao_minima_dos_conjuntos():
    res = v.Resultado()
    v.contagem(_reserva(n_por_cap=9), res, set(), "reserva")
    ms = " | ".join(m for _, m in res.falhas)
    assert "45 casos (mínimo 50 no conjunto de reserva)" in ms and "9 casos na reserva (mínimo 10 por capacidade)" in ms
    dev = [x for x in _reserva(n_por_cap=8)]
    res = v.Resultado()
    v.contagem(dev, res, set(), "desenvolvimento")
    assert any("40 casos" not in m and "(mínimo 40" in m for _, m in res.falhas) is False  # 40 casos: o piso está cumprido
    res = v.Resultado()
    v.contagem(dev[:-1], res, set(), "desenvolvimento")
    assert any("39 casos (mínimo 40" in m for _, m in res.falhas)


def test_r2_a12_mutantes_e_cobertura_sao_obrigatorios_no_congelamento(amb, tmp_path):
    p = _cli(amb, base_casos(amb), tmp_path)
    linhas = p.stdout.splitlines()
    assert any(l.startswith("FALHA cobertura:") for l in linhas) and any(l.startswith("FALHA mutantes:") for l in linhas)
    p = _cli(amb, base_casos(amb), tmp_path, "--exploratorio")
    linhas = p.stdout.splitlines()
    assert not any(l.startswith(("FALHA cobertura:", "FALHA mutantes:")) for l in linhas)
    assert any(l.startswith("INCOMPLETO sem --cobertura") for l in linhas)
    assert any(l.startswith("INCOMPLETO sem --mutantes") for l in linhas)


def test_r2_a12_codigo_de_saida_2_quando_so_incompleto(amb, tmp_path, monkeypatch):
    r = v.Resultado()
    r.incompleto.append("sem --cobertura")
    monkeypatch.setattr(v, "validar", lambda *a, **k: r)
    jl = tmp_path / "c.jsonl"
    jl.write_text("", encoding="utf-8")
    assert v.main([str(jl), amb["pasta"], "--exploratorio"]) == 2


def test_r2_a12_conjunto_incoerente_com_o_campo_dos_casos(amb):
    res = v.validar(copy.deepcopy(base_casos(amb)), amb["pasta"], amb["csv"], None, False, conjunto="reserva")
    acusa(res, "conjunto", "incoerente com o campo `conjunto`")


# --------------------------------------------------------------------------------------------------------------
# Achado 13: anotação só com referência identificável a ato
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("paren", ["(Vide Lei)", "(Incluído no Regulamento interno)", "(Redação dada pelo Regulamento)",
                                   "(Vide Lei nº 8.000)", "(Revogado pelo Código)"])
def test_r2_a13_parentese_sem_ato_identificavel_nao_e_anotacao(paren):
    assert not v.tem_anotacao_editorial(paren)


@pytest.mark.parametrize("paren", ["(Vide Lei nº 8.000, de 2001)", "(Incluído pela Lei nº 8.000/2001)",
                                   "(Redação dada pela Lei de 12 de março de 1990)",
                                   "(Revogado pelo Decreto nº 8.000, de 12/3/1990)", "(Vetado pela Mensagem nº 8, de 2001)"])
def test_r2_a13_parentese_com_ato_identificavel_e_anotacao(paren):
    assert v.tem_anotacao_editorial(paren)


def test_r2_a13_parentese_normativo_com_palavra_de_anotacao_fica_na_fonte(tmp_path):
    corpo = "Art. 1º Regra principal (Incluído no Regulamento interno) obrigatória."
    c, pasta = _um(tmp_path, [LEI9990, corpo, "Art. 2º Fim."], corpo, "art. 1º da Lei 9.990/2000", "art. 1º")
    assert not falhas_de(_val(c, pasta), "L-a-001")
    c["gabarito"]["texto"] = "Art. 1º Regra principal obrigatória."
    acusa(_val(c, pasta), "L-a-001", "não é trecho contínuo")


# --------------------------------------------------------------------------------------------------------------
# Achado 14: esquema robusto diante de tipos inválidos
# --------------------------------------------------------------------------------------------------------------
def test_r2_a14_tipos_invalidos_viram_falha_tipada_sem_traceback(amb):
    for campo, valor, msg in (("citacao", 123, "citacao deve ser texto"), ("caminho", ["art. 156"], "caminho deve ser texto"),
                              ("familia_alteracao", 7, "familia_alteracao deve ser texto"), ("norma", "lei", "norma deve ser objeto"),
                              ("gabarito", [], "gabarito deve ser objeto")):
        casos = base_casos(amb)
        achar(casos, "L-a-001")[campo] = valor
        res = rodar(casos, amb)
        assert any(msg in m for m in falhas_de(res, "L-a-001")), campo
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["texto"] = 99
    achar(casos, "L-a-002")["gabarito"]["fonte_oficial"]["url"] = 123
    achar(casos, "L-b-001")["id"] = 5
    res = rodar(casos, amb)
    acusa(res, "L-a-001", "gabarito.texto deve ser texto")
    acusa(res, "L-a-002", "fonte_oficial.url ausente, vazio ou não é texto")
    assert not any("erro interno" in m for _, m in res.falhas)


def test_r2_a14_capturado_em_com_hora_invalida(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["gabarito"]["fonte_oficial"]["capturado_em"] = "2026-11-03T99:99:99Z"
    acusa(rodar(casos, amb), "L-a-001", "não é data e hora válidas")


def test_r2_a14_citacao_sem_dispositivo_reprova_mesmo_com_caminho(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["citacao"] = "Lei 9.999/2000"
    acusa(rodar(casos, amb), "L-a-001", "citação sem dispositivo")


def test_r2_a14_erro_interno_nunca_vira_traceback(amb, monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("falha simulada")
    monkeypatch.setattr(v, "validar_caso", explode)
    res = rodar(base_casos(amb), amb)
    acusa(res, "L-a-001", "erro interno ao validar o caso")


# --------------------------------------------------------------------------------------------------------------
# Achado 15: sem falso positivo na extração; Constituição
# --------------------------------------------------------------------------------------------------------------
def test_r2_a15_lei_curta_e_integral_nao_reprova_por_tamanho(tmp_path):
    corpo = "Art. 1º Texto curto."
    c, pasta = _um(tmp_path, [LEI9990, corpo], corpo, "art. 1º da Lei 9.990/2000", "art. 1º")
    assert not falhas_de(_val(c, pasta), "L-a-001")


def test_r2_a15_constituicao_tem_cabecalho_e_ato_no_documento(tmp_path):
    pasta, sha = _doc(tmp_path, _html("CONSTITUIÇÃO DA REPÚBLICA FEDERATIVA DO BRASIL DE 1988",
                                      "Art. 1º A República Federativa do Brasil constitui-se em Estado Democrático.",
                                      "Art. 2º São Poderes da União."))
    c = _caso(sha, "Art. 1º A República Federativa do Brasil constitui-se em Estado Democrático.",
              "art. 1º da Constituição Federal", "art. 1º", ato="Constituição Federal de 1988",
              norma={"especie": "constituicao", "numero": "1988", "ano": 1988})
    assert not falhas_de(_val(c, pasta), "L-a-001")
    c["gabarito"]["fonte_oficial"]["ato_no_documento"] = "Constituição Federal de 1967"
    acusa(_val(c, pasta), "L-a-001", "ato_no_documento")


# --------------------------------------------------------------------------------------------------------------
# Achado 17: documentação do fallback da extração de PDF
# --------------------------------------------------------------------------------------------------------------
def _fake_pypdf(layout, simples):
    class Pag:
        def extract_text(self, extraction_mode=None):
            return layout if extraction_mode == "layout" else simples

    class Rd:
        def __init__(self, _):
            self.pages = [Pag()]
    return types.SimpleNamespace(PdfReader=Rd)


def test_r2_a17_fallback_para_o_modo_simples_vale_com_layout_nao_vazio_e_curto(monkeypatch):
    longo = "Art. 1º Texto simples bem mais longo do que o layout devolveu nesta página sintética de teste."
    monkeypatch.setattr(v, "pypdf", _fake_pypdf("Art. 1º Texto", longo))  # layout NÃO vazio, mas < 60% do simples
    assert v.extrair_pdf(b"%PDF-1")[0] == longo
    monkeypatch.setattr(v, "pypdf", _fake_pypdf(longo, longo[:-10]))  # layout >= 60%: vale o layout
    assert v.extrair_pdf(b"%PDF-1")[0] == longo
    monkeypatch.setattr(v, "pypdf", _fake_pypdf("", longo))  # layout vazio: vale o simples
    assert v.extrair_pdf(b"%PDF-1")[0] == longo


def test_r2_a17_leiame_descreve_a_condicao_real_do_fallback():
    texto = (AQUI / "LEIAME.md").read_text(encoding="utf-8")
    assert "menos de 60%" in texto and "layout devolve página vazia" not in texto


def test_r2_cli_imprime_linhas_revisao_humana_separadas_dos_alertas(amb, tmp_path):
    p = _cli(amb, base_casos(amb), tmp_path)
    linhas = p.stdout.splitlines()
    assert any(l.startswith("REVISAO_HUMANA L-a-001: (i)") for l in linhas)
    assert any(l.startswith("INFO revisao_humana:") for l in linhas)
    assert not any(l.startswith("ALERTA") and "REVISAO_HUMANA" in l for l in linhas)


# ==============================================================================================================
# RODADA 3: contraexemplos e controles positivos do parecer-validador-r2.md (achados 1 a 15)
# ==============================================================================================================
def _revs(res, cid=None, cat=None):
    return [(c, k, m) for c, k, m in res.revisoes if (cid is None or c == cid) and (cat is None or k == cat)]


def _renum(c, pasta):
    muts, _, erros = v.gerar_mutantes([c], pasta)
    return [m for m in muts if m["tipo"] == "renumerado"], erros


# --------------------------------------------------------------------------------------------------------------
# Achado 6 (prioridade): mutante renumerado resolve e compara o DESTINO COMPLETO da chamada
# --------------------------------------------------------------------------------------------------------------
PAR_IGUAL = "§ 1º Parágrafo idêntico nos dois artigos."


def test_r3_a6_paragrafo_de_destino_com_texto_identico_ao_original_nao_gera_mutante(tmp_path):
    doc = [LEI9990, "Art. 1º Texto do primeiro artigo.", PAR_IGUAL, "Art. 2º Texto do segundo artigo.", PAR_IGUAL]
    c, pasta = _um(tmp_path, doc, PAR_IGUAL, "art. 1º, § 1º da Lei 9.990/2000", "art. 1º, § 1º")
    muts, erros = _renum(c, pasta)
    assert not muts and any("mutante obrigatório ausente" in e for e in erros)


def test_r3_a6_controle_paragrafo_de_destino_diferente_gera_mutante_com_caminho_completo(tmp_path):
    doc = [LEI9990, "Art. 1º Texto do primeiro artigo.", PAR_IGUAL, "Art. 2º Texto do segundo artigo.",
           "§ 1º Parágrafo próprio do segundo artigo."]
    c, pasta = _um(tmp_path, doc, PAR_IGUAL, "art. 1º, § 1º da Lei 9.990/2000", "art. 1º, § 1º")
    muts, erros = _renum(c, pasta)
    assert not erros and len(muts) == 1
    m = muts[0]
    assert m["chamada"]["parametros"]["citacao"] == "art. 2º, § 1º da Lei 9.990/2000"
    assert m["destino"]["caminho"] == "art. 2º, § 1º"


def test_r3_a6_destino_sem_o_subdispositivo_nao_existe_e_nao_gera_mutante(tmp_path):
    doc = [LEI9990, "Art. 1º Texto do primeiro artigo.", PAR_IGUAL, "Art. 2º Texto do segundo artigo sem parágrafos."]
    c, pasta = _um(tmp_path, doc, PAR_IGUAL, "art. 1º, § 1º da Lei 9.990/2000", "art. 1º, § 1º")
    muts, erros = _renum(c, pasta)
    assert not muts and erros


def test_r3_a6_destino_n_mais_a_com_o_subdispositivo(tmp_path):
    doc = [LEI9990, "Art. 1º Texto do primeiro artigo.", PAR_IGUAL, "Art. 2º Texto do segundo artigo sem parágrafos.",
           "Art. 1º-A Texto do artigo um A.", "§ 1º Parágrafo do artigo um A."]
    c, pasta = _um(tmp_path, doc, PAR_IGUAL, "art. 1º, § 1º da Lei 9.990/2000", "art. 1º, § 1º")
    muts, erros = _renum(c, pasta)
    assert not erros and muts[0]["alteracao"]["regra"] == "art. N-A"
    assert muts[0]["destino"]["caminho"].endswith("§ 1º")


ANEXO_A = ["Art. 1º Regra do anexo.", "Art. 2º Segunda regra do anexo."]


def test_r3_a6_anexos_com_artigos_identicos_nao_geram_mutante(tmp_path):
    doc = [DEC7, "Art. 1º Aprova os anexos."] + ["ANEXO I"] + ANEXO_A + ["ANEXO II"] + ANEXO_A
    c, pasta = _um(tmp_path, doc, "Art. 2º Segunda regra do anexo.", "Art. 2º do Anexo I do Decreto 7/2020",
                   "Anexo I, art. 2º", cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    muts, erros = _renum(c, pasta)
    assert not muts and any("mutante obrigatório ausente" in e for e in erros)


def test_r3_a6_anexo_unico_nao_troca_o_artigo_no_lugar_do_anexo_seguinte(tmp_path):
    doc = [DEC7, "Art. 1º Aprova o anexo.", "ANEXO", "Art. 1º Regra do anexo único.", "Art. 2º Segunda regra do anexo único."]
    c, pasta = _um(tmp_path, doc, "Art. 1º Regra do anexo único.", "Art. 1º do Anexo do Decreto 7/2020", "Anexo, art. 1º",
                   cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    muts, erros = _renum(c, pasta)
    assert not muts and erros  # nenhuma chamada com `art. 2` do anexo único: a matriz manda o número seguinte do anexo


def test_r3_a6_destino_de_anexo_tem_o_mesmo_caminho_completo_no_anexo_seguinte(tmp_path):
    doc = [DEC7, "Art. 1º Aprova os anexos.", "ANEXO I"] + ANEXO_A + ["ANEXO II", "Art. 1º Regra do segundo anexo.",
                                                                       "Art. 2º Outra regra do segundo anexo."]
    c, pasta = _um(tmp_path, doc, "Art. 2º Segunda regra do anexo.", "Art. 2º do Anexo I do Decreto 7/2020",
                   "Anexo I, art. 2º", cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    muts, erros = _renum(c, pasta)
    assert not erros and muts[0]["destino"]["caminho"] == "Anexo II, art. 2º"
    assert "Anexo II" in muts[0]["chamada"]["parametros"]["citacao"]


# --------------------------------------------------------------------------------------------------------------
# Achado 7 (prioridade): data_trocada só com redação alternativa do PRÓPRIO dispositivo
# --------------------------------------------------------------------------------------------------------------
LEI_7777 = "(Redação dada pela Lei nº 7.777, de 31/10/2001)"
DOC_ALT = [LEI9990, "Texto compilado", "Art. 1º Texto permanente do primeiro artigo da lei.",
           "Art. 2º <s>Redação antiga do segundo artigo da lei.</s> Redação nova do segundo artigo da lei. " + LEI_7777,
           "Art. 3º Fim da lei de teste."]
ALT_2 = {"ato": "original", "inicio": "2000-01-01", "fim": "2001-10-30",
         "fundamento": "O art. 2º tinha outra redação antes da Lei 7.777/2001 (riscada na compilada).",
         "texto": "Art. 2º Redação antiga do segundo artigo da lei."}


def _caso_c_alt(tmp_path, art, texto, alt, dm, fam="lei-7777-2001", d="2002-01-01"):
    c, pasta = _um(tmp_path, DOC_ALT, texto, f"art. {art} da Lei 9.990/2000", f"art. {art}", cap="c", fam=fam,
                   url=URL_COMP_MINI, tipo="verificado_para_D", id_="L-c-001")
    c["data"], c["data_mutante"] = d, dm
    c["gabarito"]["redacao_alternativa"] = alt
    return c, pasta


def test_r3_a7_anotacao_de_outro_artigo_nao_documenta_a_redacao_alternativa(tmp_path):
    alt = {"ato": "lei-7777-2001", "inicio": "2001-10-31", "fim": None, "fundamento": "Lei 7.777/2001 alterou o dispositivo",
           "texto": "Art. 1º Outra redação inventada do primeiro artigo da lei."}
    c, pasta = _caso_c_alt(tmp_path, "1º", "Art. 1º Texto permanente do primeiro artigo da lei.", alt, "2002-01-01",
                           fam="original", d="2000-06-01")
    acusa(_val(c, pasta), "L-c-001", "nenhuma fonte do caso traz, no próprio dispositivo")
    muts, _, erros = v.gerar_mutantes([c], pasta)
    assert not [m for m in muts if m["tipo"] == "data_trocada"]
    assert any("data_mutante inválida" in e for e in erros)


def test_r3_a7_alternativa_sem_texto_ou_com_o_texto_do_gabarito_e_invalida(tmp_path):
    alt = {"ato": "lei-7777-2001", "inicio": "2001-10-31", "fim": None, "fundamento": "Lei 7.777/2001"}
    c, pasta = _caso_c_alt(tmp_path, "1º", "Art. 1º Texto permanente do primeiro artigo da lei.", alt, "2002-01-01",
                           fam="original", d="2000-06-01")
    acusa(_val(c, pasta), "L-c-001", "redacao_alternativa sem `texto`")
    c["gabarito"]["redacao_alternativa"]["texto"] = c["gabarito"]["texto"]
    acusa(_val(c, pasta), "L-c-001", "igual ao texto do gabarito")


def test_r3_a7_controle_alternativa_do_proprio_dispositivo_com_texto_riscado_e_valida(tmp_path):
    c, pasta = _caso_c_alt(tmp_path, "2º", "Art. 2º Redação nova do segundo artigo da lei.", dict(ALT_2), "2000-06-01")
    res = _val(c, pasta)
    assert not falhas_de(res, "L-c-001"), falhas_de(res)
    assert _revs(res, "L-c-001", "(i)")
    muts, _, erros = v.gerar_mutantes([c], pasta)
    m = next(x for x in muts if x["tipo"] == "data_trocada")
    assert m["base"] == "redacao_alternativa" and not erros


def test_r3_a7_alternativa_com_texto_que_nao_consta_do_dispositivo_reprova(tmp_path):
    alt = dict(ALT_2, texto="Art. 2º Redação antiga que a fonte não traz.")
    c, pasta = _caso_c_alt(tmp_path, "2º", "Art. 2º Redação nova do segundo artigo da lei.", alt, "2000-06-01")
    acusa(_val(c, pasta), "L-c-001", "nenhuma fonte do caso traz, no próprio dispositivo")


def test_r3_a7_fonte_consultada_sem_o_dispositivo_testado_nao_basta(amb):
    casos = base_casos(amb)
    c = achar(casos, "L-c-001")
    c["data_mutante"] = "2002-01-01"
    c["gabarito"]["fontes_consultadas"] = [fonte(amb, "comp", ATO_LEI)]  # a compilada não tem o art. 156
    c["gabarito"]["redacao_alternativa"] = {"ato": "lei-7777-2001", "inicio": "2001-10-31", "fim": None,
                                            "fundamento": "Lei 7.777/2001", "texto": "Art. 156. Outra redação."}
    acusa(rodar(casos, amb), "L-c-001", "nenhuma fonte do caso traz, no próprio dispositivo")


# --------------------------------------------------------------------------------------------------------------
# Achado 1: cabeçalho não reconhecido nunca é atribuído ao ato anterior
# --------------------------------------------------------------------------------------------------------------
CAB_VARIANTES = [
    ("minuscula", ["Decreto nº 7, de 1º de janeiro de 2020", "dispõe sobre outra matéria."]),
    ("data_numerica", ["Decreto nº 7, de 1/1/2020", "Dispõe sobre outra matéria."]),
    ("so_o_ano", ["Decreto nº 7, de 2020", "dispõe sobre outra matéria."]),
]


@pytest.mark.parametrize("nome,cab", CAB_VARIANTES)
def test_r3_a1_cabecalho_de_outro_ato_nao_reconhecido_reprova(tmp_path, nome, cab):
    doc = [LEI9990, "Dispõe sobre testes.", "Art. 1º Primeira regra da lei.", "Art. 2º Esta Lei entra em vigor."] + cab + [
        "Art. 1º Regra do decreto estranho à lei."]
    c, pasta = _um(tmp_path, doc, "Art. 1º Regra do decreto estranho à lei.", "art. 1º da Lei 9.990/2000", "art. 1º")
    acusa(_val(c, pasta), "L-a-001", "não corresponde ao ato esperado")


def test_r3_a1_cabecalho_sem_ponto_antes_do_segundo_ato_reprova(tmp_path):
    doc = [LEI9990, "Art. 1º Primeira regra da lei.", "Art. 2º Esta Lei entra em vigor na data de sua publicação "
           "Decreto nº 7, de 1º de janeiro de 2020 dispõe sobre outra matéria.", "Art. 1º Regra do decreto estranho à lei."]
    c, pasta = _um(tmp_path, doc, "Art. 1º Regra do decreto estranho à lei.", "art. 1º da Lei 9.990/2000", "art. 1º")
    acusa(_val(c, pasta), "L-a-001", "não corresponde ao ato esperado")


def test_r3_a1_controle_dispositivo_do_proprio_ato_passa_e_citacao_no_meio_da_frase_nao_e_cabecalho(tmp_path):
    doc = [LEI9990, "Dispõe sobre testes.", "Art. 1º Primeira regra da lei, na forma da Lei nº 5.172, de 25 de outubro de "
           "1966, e do Decreto nº 7, de 1º de janeiro de 2020, quando couber.", "Art. 2º Esta Lei entra em vigor."]
    c, pasta = _um(tmp_path, doc, "Art. 2º Esta Lei entra em vigor.", "art. 2º da Lei 9.990/2000", "art. 2º")
    assert not falhas_de(_val(c, pasta), "L-a-001")
    c["gabarito"]["texto"] = ("Art. 1º Primeira regra da lei, na forma da Lei nº 5.172, de 25 de outubro de 1966, e do "
                              "Decreto nº 7, de 1º de janeiro de 2020, quando couber.")
    c["citacao"], c["caminho"] = "art. 1º da Lei 9.990/2000", "art. 1º"
    assert not falhas_de(_val(c, pasta), "L-a-001")


# --------------------------------------------------------------------------------------------------------------
# Achado 2: o término do recorte não ultrapassa o dispositivo
# --------------------------------------------------------------------------------------------------------------
DOC_FIM = [LEI9990, "Art. 1º Disposição geral da lei:", "I - primeiro inciso;", "II - segundo inciso.", "§ 1º Primeiro parágrafo "
           "do primeiro artigo.", "§ 2º Segundo parágrafo do primeiro artigo.", "Da Administração",
           "Art. 2º Segunda regra da lei."]


@pytest.mark.parametrize("texto,cit,cam,trecho", [
    ("§ 1º Primeiro parágrafo do primeiro artigo. § 2º Segundo parágrafo do primeiro artigo.", "art. 1º, § 1º da Lei 9.990/2000",
     "art. 1º, § 1º", "ultrapassa o dispositivo"),
    ("I - primeiro inciso; II - segundo inciso.", "art. 1º, inciso I da Lei 9.990/2000", "art. 1º, inciso I",
     "ultrapassa o dispositivo"),
    ("Art. 1º Disposição geral da lei: I - primeiro inciso; II - segundo inciso. § 1º Primeiro parágrafo do primeiro "
     "artigo. § 2º Segundo parágrafo do primeiro artigo. Da Administração", "art. 1º da Lei 9.990/2000", "art. 1º",
     "rubrica"),
])
def test_r3_a2_recorte_que_ultrapassa_o_dispositivo_reprova(tmp_path, texto, cit, cam, trecho):
    c, pasta = _um(tmp_path, DOC_FIM, texto, cit, cam)
    acusa(_val(c, pasta), "L-a-001", trecho)


def test_r3_a2_artigo_com_o_artigo_seguinte_sem_pontuacao_antes_de_art(tmp_path):
    doc = [LEI9990, "Art. 1º Regra da lei e Art. 2º Segunda regra da lei.", "Art. 3º Terceira regra."]
    c, pasta = _um(tmp_path, doc, "Art. 1º Regra da lei e Art. 2º Segunda regra da lei.", "art. 1º da Lei 9.990/2000",
                   "art. 1º")
    acusa(_val(c, pasta), "L-a-001", "início de outro dispositivo")


def test_r3_a2_controle_recortes_exatos_passam(tmp_path):
    for texto, cit, cam in [
            ("§ 1º Primeiro parágrafo do primeiro artigo.", "art. 1º, § 1º da Lei 9.990/2000", "art. 1º, § 1º"),
            ("I - primeiro inciso;", "art. 1º, inciso I da Lei 9.990/2000", "art. 1º, inciso I"),
            ("Art. 1º Disposição geral da lei: I - primeiro inciso; II - segundo inciso. § 1º Primeiro parágrafo do "
             "primeiro artigo. § 2º Segundo parágrafo do primeiro artigo.", "art. 1º da Lei 9.990/2000", "art. 1º")]:
        c, pasta = _um(tmp_path, DOC_FIM, texto, cit, cam)
        assert not falhas_de(_val(c, pasta), "L-a-001"), (cam, falhas_de(_val(c, pasta)))


# --------------------------------------------------------------------------------------------------------------
# Achado 3: limpeza de PDF nunca apaga texto normativo
# --------------------------------------------------------------------------------------------------------------
CONT = "observar sempre os requisitos legais"


def test_r3_a3_continuacao_normativa_repetida_na_borda_e_preservada():
    p1 = f"LEI Nº 9.990, DE 1º DE JANEIRO DE 2000\nArt. 1º Obrigação primeira, devendo\n{CONT}"
    p2 = f"{CONT}\nArt. 2º Segunda obrigação."
    p3 = f"{CONT}\nArt. 3º Terceira obrigação."
    out, n = v.limpar_paginas_pdf([p1, p2, p3])
    assert n == 0 and [o.count(CONT) for o in out] == [1, 1, 1]


def test_r3_a3_pdf_com_continuacao_repetida_integral_passa_e_truncado_reprova(tmp_path):
    paginas = [[LEI9990, "Art. 1º Obrigação primeira, devendo", CONT], [CONT, "Art. 2º Segunda obrigação."],
               [CONT, "Art. 3º Terceira obrigação."]]
    pasta, sha = _doc(tmp_path, pdf_bytes(paginas), "pdf")
    integral = f"Art. 1º Obrigação primeira, devendo {CONT} {CONT}"
    c = _caso(sha, integral, "art. 1º da Lei 9.990/2000", "art. 1º")
    c["gabarito"]["fonte_oficial"]["url"] = "https://www2.camara.leg.br/legin/fed/lei/2000/mini-publicacaooriginal-1-pl.pdf"
    assert not falhas_de(_val(c, pasta), "L-a-001")
    c["gabarito"]["texto"] = "Art. 1º Obrigação primeira, devendo"
    acusa(_val(c, pasta), "L-a-001", "limite desconhecido")


def test_r3_a3_linha_de_borda_com_contador_de_pagina_continua_removida():
    p = ["Texto compilado - Página {n}\nArt. {n}º Regra número {n}."]
    out, n = v.limpar_paginas_pdf([p[0].format(n=i) for i in (1, 2, 3)])
    assert n == 3 and "Texto compilado" not in "".join(out)


def test_r3_a3_numero_sozinho_so_sai_na_linha_mais_externa():
    p1 = "LEI Nº 9.990, DE 1º DE JANEIRO DE 2000\nArt. 1º Valores:\n2\n3"
    out, n = v.limpar_paginas_pdf([p1, "4\nArt. 2º Segunda regra."])
    assert out[0].endswith("\n2") and n == 2  # o `3` (última linha) e o `4` (primeira) saem; o `2`, antes da última, fica


# --------------------------------------------------------------------------------------------------------------
# Achado 4: limite inconclusivo é FALHA mecânica
# --------------------------------------------------------------------------------------------------------------
DOC_TAB = [DEC7, "Art. 1º Aprova o anexo.", "ANEXO I", "TABELA DE VALORES", "Primeira obrigacao. Segunda obrigacao."]


def test_r3_a4_frase_interior_nao_e_tabela_do_anexo(tmp_path):
    c, pasta = _um(tmp_path, DOC_TAB, "Segunda obrigacao.", "Tabela do Anexo I do Decreto 7/2020", "Anexo I, tabela",
                   cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    acusa(_val(c, pasta), "L-d-001", "o início do recorte não é o início do corpo do anexo")
    c["gabarito"]["texto"] = "Primeira obrigacao."
    acusa(_val(c, pasta), "L-d-001", "o recorte termina antes do fim do anexo")


def test_r3_a4_controle_corpo_inteiro_do_anexo_passa_com_revisao(tmp_path):
    c, pasta = _um(tmp_path, DOC_TAB, "Primeira obrigacao. Segunda obrigacao.", "Tabela do Anexo I do Decreto 7/2020",
                   "Anexo I, tabela", cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    res = _val(c, pasta)
    assert not falhas_de(res, "L-d-001"), falhas_de(res)
    assert _revs(res, "L-d-001", "(v)")


DOC_CAPUT = [LEI9990, "Art. 1º Para os fins desta lei:", "I - primeiro item;", "II - segundo item.", "Art. 2º Segunda regra."]


def test_r3_a4_caput_terminado_em_dois_pontos_sem_os_incisos_reprova(tmp_path):
    c, pasta = _um(tmp_path, DOC_CAPUT, "Art. 1º Para os fins desta lei:", "art. 1º, caput da Lei 9.990/2000",
                   "art. 1º, caput")
    acusa(_val(c, pasta), "L-a-001", "caput incompleto")
    c, pasta = _um(tmp_path, DOC_CAPUT, "Art. 1º Para os fins desta lei: I - primeiro item; II - segundo item.",
                   "art. 1º da Lei 9.990/2000", "art. 1º")
    assert not falhas_de(_val(c, pasta), "L-a-001")


# --------------------------------------------------------------------------------------------------------------
# Achado 5: remissões sem omissão silenciosa; lista correta não reprova
# --------------------------------------------------------------------------------------------------------------
HOST = "lei-9990-2000"


@pytest.mark.parametrize("trecho", [
    "art 5 desta Lei", "o artigo subsequente", "o inciso precedente", "o art. 4 e seguintes",
    "conforme o Anexo I", "o item 3 do Anexo", "o parágrafo segundo do art. 5", "os §§ 1º a 3º do art. 5",
    "o artigo seguinte", "a alínea anterior"])
def test_r3_a5_construcao_residual_vai_para_a_revisao_nunca_e_omitida(trecho):
    refs, incertos = v.extrair_remissoes(v.norm(f"Art. 8º Observado o art. 4º desta Lei e {trecho}."), HOST, "8")
    if trecho == "art 5 desta Lei":  # lida: `art` sem ponto é artigo e entra na lista exigida
        assert {r["chave"][1] for r in refs} == {"4", "5"}
        return
    assert incertos, trecho
    assert all(r["chave"][1] in ("4", "8") for r in refs), [r["chave"] for r in refs]  # nenhum alvo superficial imposto


def test_r3_a5_ate_e_expandido_como_faixa():
    refs, incertos = v.extrair_remissoes(v.norm("Art. 8º Aplicam-se os arts. 5º até 7º desta Lei."), HOST, "8")
    assert {r["chave"][1] for r in refs} == {"5", "6", "7"}


def _caso_e3(tmp_path, texto, alvos):
    doc = [LEI9990, "Art. 4º Regra quatro da lei.", "Art. 5º Regra cinco da lei.", "§ 2º Parágrafo do artigo cinco.", texto]
    c, pasta = _um(tmp_path, doc, texto, "art. 8º da Lei 9.990/2000", "art. 8º", cap="e", id_="L-e-001",
                   alvos=[{"obra": "Lei 9.990/2000", "caminho": a} for a in alvos])
    return c, pasta


def test_r3_a5_texto_com_remissao_nao_resolvida_nao_passa_sem_revisao_ii(tmp_path):
    for sufixo in ("o artigo subsequente", "o inciso precedente", "o art. 4 e seguintes",
                   "os arts. 4º, 6º e o Anexo I"):
        c, pasta = _caso_e3(tmp_path, f"Art. 8º Observado o art. 4º desta Lei e {sufixo}.", ["art. 4º"])
        res = _val(c, pasta)
        assert _revs(res, "L-e-001", "(ii)"), sufixo


def test_r3_a5_lista_correta_com_paragrafo_segundo_nao_reprova_e_vai_a_revisao(tmp_path):
    c, pasta = _caso_e3(tmp_path, "Art. 8º Observado o art. 4º e o parágrafo segundo do art. 5 desta Lei.",
                       ["art. 4º", "art. 5º, § 2º"])
    res = _val(c, pasta)
    assert not falhas_de(res, "L-e-001"), falhas_de(res)
    assert _revs(res, "L-e-001", "(ii)")


def test_r3_a5_faixa_de_paragrafos_nao_vira_remissao_ao_proprio_artigo(tmp_path):
    c, pasta = _caso_e3(tmp_path, "Art. 8º Observado o art. 4º e os §§ 1º a 3º do art. 5º desta Lei.", ["art. 4º", "art. 5º"])
    res = _val(c, pasta)
    assert not falhas_de(res, "L-e-001"), falhas_de(res)
    assert _revs(res, "L-e-001", "(ii)")
    refs, _ = v.extrair_remissoes(v.norm("Art. 8º Observado o art. 4º e os §§ 1º a 3º do art. 5º desta Lei."), HOST, "8")
    assert all(r["chave"][1] != "8" for r in refs)


def test_r3_a5_controle_lista_completa_e_resolvida_nao_exige_revisao(tmp_path):
    c, pasta = _caso_e3(tmp_path, "Art. 8º Observado o art. 4º e o art. 5º, § 2º, desta Lei.", ["art. 4º", "art. 5º, § 2º"])
    res = _val(c, pasta)
    assert not falhas_de(res, "L-e-001") and not _revs(res, "L-e-001", "(ii)")


# --------------------------------------------------------------------------------------------------------------
# Achado 8: HTML sem cascata CSS; classe de rasura conhecida só com revisão humana
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("css", [".x{text-decoration:line-through}\n.x{text-decoration:none}",
                                 ".x{text-decoration:line-through}.x{text-decoration-line:none !important}"])
def test_r3_a8_cascata_de_folha_de_estilo_nao_apaga_texto_vigente(css, tmp_path):
    html = (f"<html><head><style>{css}</style></head><body><p>{LEI9990}</p>"
            f"<p>Art. 1º Texto <span class='x'>vigente na cascata</span> da regra um.</p><p>Art. 2º Segunda regra.</p>"
            f"</body></html>")
    f = v.carregar_fonte(html.encode("utf-8"))
    assert "Texto vigente na cascata da regra um." in f.clean
    pasta, sha = _doc(tmp_path, html)
    c = _caso(sha, "Art. 1º Texto vigente na cascata da regra um.", "art. 1º da Lei 9.990/2000", "art. 1º")
    res = _val(c, pasta)
    assert not falhas_de(res, "L-a-001"), falhas_de(res)
    assert any("classe de rasura conhecida" in m for _, _, m in _revs(res, "L-a-001", "(i)"))


def test_r3_a8_texto_com_classe_de_rasura_fica_na_fonte_e_vai_a_revisao_humana(tmp_path):
    html = ("<html><head><link rel='stylesheet' href='externa.css'></head><body><p>" + LEI9990 + "</p>"
            "<p>Art. 1º Texto <span class='tachado'>possivelmente riscado</span> da regra um.</p></body></html>")
    f = v.carregar_fonte(html.encode("utf-8"))
    assert "possivelmente riscado" in f.clean and f.classe_rasura == ["possivelmente riscado"]
    pasta, sha = _doc(tmp_path, html)
    c = _caso(sha, "Art. 1º Texto possivelmente riscado da regra um.", "art. 1º da Lei 9.990/2000", "art. 1º")
    assert _revs(_val(c, pasta), "L-a-001", "(i)")


def test_r3_a8_controle_texto_sem_classe_de_rasura_nao_gera_revisao_de_classe(tmp_path):
    c, pasta = _um(tmp_path, [LEI9990, "Art. 1º Texto simples da regra um."], "Art. 1º Texto simples da regra um.",
                   "art. 1º da Lei 9.990/2000", "art. 1º")
    assert not any("classe de rasura" in m for _, _, m in _revs(_val(c, pasta)))


@pytest.mark.parametrize("estilo,riscado", [
    ("text-decoration:line-through", True), ("text-decoration:line-through; text-decoration:none", False),
    ("text-decoration:none; text-decoration:line-through", True),
    ("text-decoration-line:line-through !important; text-decoration-line:none", True),
    ("text-decoration:underline", False), ("color:red", False)])
def test_r3_a8_estilo_inline_efetivo(estilo, riscado):
    html = f"<html><body><p>Art. 1º Texto <span style='{estilo}'>marcado</span> final.</p></body></html>"
    f = v.carregar_fonte(html.encode("utf-8"))
    assert ("marcado" not in f.clean) is riscado


def test_r3_a8_elemento_strike_continua_sendo_riscado_mesmo_com_classe():
    html = ("<html><head><style>.k{text-decoration:none}</style></head><body><p>Art. 1º Texto <strike class='k'>"
            "antigo</strike> final.</p></body></html>")
    assert "antigo" not in v.carregar_fonte(html.encode("utf-8")).clean


# --------------------------------------------------------------------------------------------------------------
# Achado 9: (iv) em todo caso com família, inclusive `original`, por capacidade
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cap", ["a", "b", "c", "d", "e"])
def test_r3_a9_revisao_iv_em_todos_os_casos_de_cada_capacidade_inclusive_familia_original(amb, cap):
    casos = base_casos(amb)
    res = rodar(casos, amb)
    do_cap = [c for c in casos if c["capacidade"] == cap and c["gabarito"]["tipo"] != "nao_existia_em_D"]
    assert do_cap
    for c in do_cap:
        assert _revs(res, c["id"], "(iv)"), (cap, c["id"], c["familia_alteracao"])
    assert any(c["familia_alteracao"] == "original" for c in casos if c["capacidade"] == cap) or cap == "b"


def test_r3_a9_caso_aceito_com_familia_original_em_compilada_sem_anotacao_vai_a_revisao_iv(tmp_path):
    c, pasta = _um(tmp_path, [LEI9990, "Texto compilado", "Art. 5. Regra do quinto artigo.", "Art. 6. Regra do sexto."],
                   "Art. 5. Regra do quinto artigo.", "art. 5º da Lei 9.990/2000", "art. 5º", cap="b", fam="original",
                   url=URL_COMP_MINI)
    res = _val(c, pasta)
    assert not falhas_de(res, "L-b-001")
    assert any("'original'" in m for _, _, m in _revs(res, "L-b-001", "(iv)"))


@pytest.mark.parametrize("cap,cat", [("a", "(i)"), ("c", "(i)"), ("c", "(iii)")])
def test_r3_a9_categorias_i_e_iii_presentes_por_caso(amb, cap, cat):
    casos = base_casos(amb)
    res = rodar(casos, amb)
    alvo = [c for c in casos if c["capacidade"] == cap and (
        (cat == "(iii)" and c["gabarito"]["tipo"] == "nao_verificado_para_D") or
        (cat == "(i)" and (cap == "a" or c["gabarito"]["tipo"] == "verificado_para_D")))]
    assert alvo and all(_revs(res, c["id"], cat) for c in alvo)


# --------------------------------------------------------------------------------------------------------------
# Achado 10: conversão de MP exige identidade completa, vínculo de conversão e distinção em D
# --------------------------------------------------------------------------------------------------------------
def _conv(tmp_path, mencao, d_mp="2001-06-01", d_lei="2010-06-01"):
    pasta, sha = _doc(tmp_path, _html("LEI Nº 12.000, DE 1º DE JANEIRO DE 2010", mencao, "Art. 1º Texto da lei de teste."))
    fo = {"sha256": sha}
    mp = {"id": "L-c-001", "capacidade": "c", "norma": {"especie": "medida_provisoria", "numero": "2183-56", "ano": 2001},
          "data": d_mp, "familia_alteracao": "original", "gabarito": {"tipo": "verificado_para_D", "fonte_oficial": fo}}
    lei = {"id": "L-c-002", "capacidade": "c", "norma": {"especie": "lei", "numero": "12000", "ano": 2010}, "data": d_lei,
           "familia_alteracao": "original", "gabarito": {"tipo": "verificado_para_D", "fonte_oficial": fo}}
    return v._exercita("mp_convertida", [mp, lei], v.Contexto(pasta, None, v.Resultado()))


# --------------------------------------------------------------------------------------------------------------
# Achado 11: citação inequívoca e integralmente interpretada
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("cit", ["art. 1 e art. 2 da Lei 9.990/2000", "art. 1, item 2 da Lei 9.990/2000",
                                 "art. 1º da Lei 9.990/2000 ou da Lei 8.000/2001", "art. 1º e seguintes da Lei 9.990/2000",
                                 "art. 1º da Lei 9.990/2000, na redação vigente em 2010"])
def test_r3_a11_citacao_com_dispositivo_adicional_ou_qualificador_nao_suportado_reprova(cit):
    assert v.confere_citacao_caminho(cit, "art. 1º"), cit


def test_r3_a11_controle_citacoes_unicas_passam():
    assert v.confere_citacao_caminho("art. 1º da Lei 9.990/2000", "art. 1º") is None
    assert v.confere_citacao_caminho("art. 4º, § 2º, inciso II da Lei 9.990/2000", "art. 4º, § 2º, inciso II") is None
    assert v.confere_citacao_caminho("Art. 2º do Anexo I do Decreto 7/2020", "Anexo I, art. 2º") is None
    assert v.confere_citacao_caminho("art. 421 do Código Civil", "art. 421") is None


def test_r3_a11_citacao_com_dois_artigos_reprova_no_caso(amb):
    casos = base_casos(amb)
    achar(casos, "L-a-001")["citacao"] = "art. 156 e art. 157 da Lei 9.999/2000"
    acusa(rodar(casos, amb), "L-a-001", "mais de um artigo")


# --------------------------------------------------------------------------------------------------------------
# Achado 12: cobertura malformada reprova com diagnóstico, sem exceção
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("casos_cob", [[{}], [[]], [None], [1], "L-a-001", [["L-a-001"]]])
def test_r3_a12_cobertura_com_ids_malformados_reprova_sem_excecao(amb, tmp_path, casos_cob):
    sit = {n: {"casos": ["L-a-001"], "evento": "e", "esperado": "x"} for n in list(v.SITUACOES) + list(v.OUTRAS_SITUACOES)}
    sit["lsa_156"]["casos"] = casos_cob
    cob = tmp_path / "cob.json"
    cob.write_text(json.dumps({"situacoes": sit}), encoding="utf-8")
    res = v.validar(copy.deepcopy(base_casos(amb)), amb["pasta"], amb["csv"], str(cob), False)
    assert any(c == "cobertura:lsa_156" for c, _ in res.falhas), res.falhas[:3]


def test_r3_a12_cobertura_nao_objeto_e_erro_interno_viram_falha(amb, tmp_path, monkeypatch):
    cob = tmp_path / "cob.json"
    cob.write_text("[1, 2]", encoding="utf-8")
    res = v.validar(copy.deepcopy(base_casos(amb)), amb["pasta"], amb["csv"], str(cob), False)
    assert any(c == "cobertura" for c, _ in res.falhas)

    def explode(*a, **k):
        raise RuntimeError("falha simulada")
    monkeypatch.setattr(v, "validar_cobertura", explode)
    res = v.validar(copy.deepcopy(base_casos(amb)), amb["pasta"], amb["csv"], str(cob), False)
    assert any(c == "cobertura" and "erro ao conferir a cobertura" in m for c, m in res.falhas)


def test_r3_a12_cli_com_cobertura_malformada_termina_em_reprovacao_diagnosticada(amb, tmp_path):
    sit = {n: {"casos": [{}], "evento": "e", "esperado": "x"} for n in list(v.SITUACOES) + list(v.OUTRAS_SITUACOES)}
    cob = tmp_path / "cob.json"
    cob.write_text(json.dumps({"situacoes": sit}), encoding="utf-8")
    p = _cli(amb, base_casos(amb), tmp_path, "--cobertura", str(cob))
    assert "Traceback" not in p.stderr and p.returncode == 1
    assert any(l.startswith("FALHA cobertura:") for l in p.stdout.splitlines())


# --------------------------------------------------------------------------------------------------------------
# Achado 14: anexo em caixa mista
# --------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("rubrica", ["ANEXO I", "Anexo I"])
def test_r3_a14_anexo_correto_em_caixa_alta_ou_mista_passa(tmp_path, rubrica):
    doc = [DEC7, "Art. 1º Aprova o anexo.", rubrica, "Art. 1º Primeira regra do anexo.", "Art. 2º Segunda regra do anexo."]
    c, pasta = _um(tmp_path, doc, "Art. 2º Segunda regra do anexo.", "Art. 2º do Anexo I do Decreto 7/2020",
                   "Anexo I, art. 2º", cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    assert not falhas_de(_val(c, pasta), "L-d-001")
    c["gabarito"]["texto"] = "Art. 2º Segunda regra do corpo do decreto."  # artigo do corpo não é artigo de anexo
    assert falhas_de(_val(c, pasta), "L-d-001")


def test_r3_a14_remissao_em_caixa_mista_no_corpo_nao_e_rubrica(tmp_path):
    doc = [DEC7, "Art. 1º Aprova o regulamento constante do Anexo I.", "Art. 2º Regra do corpo, conforme Anexo I da norma.",
           "ANEXO I", "Art. 1º Primeira regra do anexo.", "Art. 2º Segunda regra do anexo."]
    c, pasta = _um(tmp_path, doc, "Art. 2º Regra do corpo, conforme Anexo I da norma.", "art. 2º do Decreto 7/2020",
                   "art. 2º", cap="b", norma=N_DEC7, ato=DEC7, id_="L-b-001")
    assert not falhas_de(_val(c, pasta), "L-b-001")


def test_r3_a14_anexo_de_rubrica_mista_inexistente_ainda_reprova(tmp_path):
    doc = [DEC7, "Art. 1º Aprova o anexo.", "Anexo I", "Art. 1º Primeira regra do anexo.", "Art. 2º Segunda regra do anexo."]
    c, pasta = _um(tmp_path, doc, "Art. 2º Segunda regra do anexo.", "Art. 2º do Anexo II do Decreto 7/2020",
                   "Anexo II, art. 2º", cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    assert falhas_de(_val(c, pasta), "L-d-001")


# --------------------------------------------------------------------------------------------------------------
# Achado 15: a descrição dos testes reflete o local real das fixtures
# --------------------------------------------------------------------------------------------------------------
def test_r3_a15_docstring_nao_informa_o_local_antigo_das_fixtures():
    assert "./fixtures" not in (__doc__ or "") and "temporário" in (__doc__ or "")


def test_r3_a7_D_dentro_do_intervalo_alternativo_e_ato_nao_documentado_reprovam(tmp_path):
    c, pasta = _caso_c_alt(tmp_path, "2º", "Art. 2º Redação nova do segundo artigo da lei.", dict(ALT_2), "2000-06-01",
                           d="2000-12-01")
    acusa(_val(c, pasta), "L-c-001", "dentro do intervalo da redação alternativa")
    c, pasta = _caso_c_alt(tmp_path, "2º", "Art. 2º Redação nova do segundo artigo da lei.", dict(ALT_2, ato="lei-123456-1900"),
                           "2000-06-01")
    acusa(_val(c, pasta), "L-c-001", "não confere com a data documentada do ato")


def test_r3_a5_art_sem_ponto_e_lido_e_exigido_em_alvos(tmp_path):
    c, pasta = _caso_e3(tmp_path, "Art. 8º Observado o art. 4º desta Lei e art 5 desta Lei.", ["art. 4º"])
    acusa(_val(c, pasta), "L-e-001", "remissão expressa do texto ausente de `alvos`: lei-9990-2000 art. 5")


def test_r3_a13_artigo_de_anexo_nao_vale_como_artigo_do_corpo_do_decreto(tmp_path):
    """Isola a causa: só o artigo do ANEXO é apresentado como se fosse o art. 2º do corpo; o corpo existe e é outro texto."""
    doc = [DEC7, "Art. 1º Aprova o anexo.", "Art. 2º Regra do corpo do decreto.", "ANEXO I", "Art. 1º Primeira regra do anexo.",
           "Art. 2º Segunda regra do anexo."]
    c, pasta = _um(tmp_path, doc, "Art. 2º Segunda regra do anexo.", "art. 2º do Decreto 7/2020", "art. 2º", cap="b",
                   norma=N_DEC7, ato=DEC7, id_="L-b-001")
    acusa(_val(c, pasta), "L-b-001", "não é a do dispositivo")
    c["gabarito"]["texto"] = "Art. 2º Regra do corpo do decreto."
    assert not falhas_de(_val(c, pasta), "L-b-001")


# ==============================================================================================================
# Redução D5: mutantes escritos pelo pesquisador (o validador confere forma), cobertura só na forma e as cinco
# verificações rebaixadas de FALHA a REVISAO_HUMANA
# ==============================================================================================================
def _mutantes_escritos(amb, casos=None):
    """Conjunto de mutantes como o pesquisador o escreveria: o rascunho do gerador, revisado (sem `rascunho`)."""
    muts, _, erros = v.gerar_mutantes(copy.deepcopy(casos or base_casos(amb)), amb["pasta"])
    assert not erros
    for m in muts:
        m.pop("rascunho", None)
    return muts


def _conferir_mutantes(amb, tmp_path, muts, casos=None, nome="mutantes.jsonl"):
    p = tmp_path / nome
    p.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in muts), encoding="utf-8")
    res = v.Resultado()
    n = v.validar_mutantes(str(p), copy.deepcopy(casos or base_casos(amb)), set(), v.Contexto(amb["pasta"], None, res), res)
    return res, n


def _mut(muts, caso, tipo):
    return next(m for m in muts if m["caso"] == caso and m["tipo"] == tipo)


def test_d5_mutantes_escritos_validos_passam_na_forma_e_todos_vao_a_revisao_humana(amb, tmp_path):
    muts = _mutantes_escritos(amb)
    res, n = _conferir_mutantes(amb, tmp_path, muts)
    assert n == len(muts) and not res.falhas, res.falhas[:3]
    rev = {c for c, cat, _ in res.revisoes if cat == "(vi)"}
    assert rev == {f"mutantes:{m['id']}" for m in muts}  # TODO mutante é revisado na segunda camada


def test_d5_nenhum_caminho_do_validador_grava_o_mutantes_jsonl_congelado(amb, tmp_path):
    destino = tmp_path / "mutantes.jsonl"
    v.gerar_mutantes(base_casos(amb), amb["pasta"], str(destino))
    assert not destino.exists() and (tmp_path / "mutantes.rascunho.jsonl").exists()
    assert v.caminho_rascunho("x/mutantes.jsonl").name == "mutantes.rascunho.jsonl"
    assert v.caminho_rascunho("x/m.rascunho.jsonl").name == "m.rascunho.jsonl"
    p = _cli(amb, base_casos(amb), tmp_path, "--gerar-mutantes", str(destino))
    assert not destino.exists(), p.stdout
    assert any(l.startswith("FALHA mutantes:") and "obrigatório" in l for l in p.stdout.splitlines())


def test_d5_rascunho_nao_e_aceito_como_arquivo_congelado(amb, tmp_path):
    muts = _mutantes_escritos(amb)
    res, _ = _conferir_mutantes(amb, tmp_path, muts, nome="mutantes.rascunho.jsonl")
    acusa(res, "mutantes", "é um rascunho")
    res, _ = _conferir_mutantes(amb, tmp_path, [dict(m, rascunho=True) for m in muts])
    assert any("marcado `rascunho`" in m for _, m in res.falhas)


def test_d5_cli_confere_o_mutantes_jsonl_do_pesquisador(amb, tmp_path):
    muts = _mutantes_escritos(amb)
    arq = tmp_path / "mutantes.jsonl"
    arq.write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in muts), encoding="utf-8")
    p = _cli(amb, base_casos(amb), tmp_path, "--mutantes", str(arq))
    linhas = p.stdout.splitlines()
    assert not any(l.startswith("FALHA mutantes") for l in linhas)
    assert any(l.startswith("INFO mutantes:") and "conferidos" in l for l in linhas)
    assert sum(1 for l in linhas if l.startswith("REVISAO_HUMANA mutantes:")) == len(muts)


@pytest.mark.parametrize("alterar,trecho", [
    (lambda m, ms: m.update(caso="L-x-999"), "caso de origem inexistente"),
    (lambda m, ms: m.update(tipo="reescrito"), "`tipo` inválido"),
    (lambda m, ms: m.update(esperado={}), "`esperado`"),
    (lambda m, ms: m.update(chamada={"funcao": "x", "parametros": {}}), "`chamada` deve ter"),
    (lambda m, ms: m.update(id=ms[1]["id"]), "id de mutante repetido"),
])
def test_d5_mutante_malformado_reprova(amb, tmp_path, alterar, trecho):
    muts = _mutantes_escritos(amb)
    alterar(muts[0], muts)
    res, _ = _conferir_mutantes(amb, tmp_path, muts)
    assert any(trecho in m for _, m in res.falhas), (trecho, res.falhas[:4])


@pytest.mark.parametrize("caso,tipo", [("L-a-001", "renumerado"), ("L-b-002", "caractere"), ("L-c-001", "data_trocada")])
def test_d5_mutante_obrigatorio_ausente_reprova(amb, tmp_path, caso, tipo):
    muts = [m for m in _mutantes_escritos(amb) if not (m["caso"] == caso and m["tipo"] == tipo)]
    res, _ = _conferir_mutantes(amb, tmp_path, muts)
    assert any(f"mutante obrigatório ausente (seção 3): {tipo}" in m and c == f"mutantes:{caso}" for c, m in res.falhas)
    assert not any("obrigatório ausente" in m for c, m in res.falhas if c != f"mutantes:{caso}")


def test_d5_conjunto_sem_mutantes_reprova_todos_os_obrigatorios(amb, tmp_path):
    res, _ = _conferir_mutantes(amb, tmp_path, [])
    assert sum(1 for _, m in res.falhas if "obrigatório ausente" in m) >= len(base_casos(amb))


def test_d5_renumerado_destino_igual_ao_original_ou_ausente_da_fonte_reprova(amb, tmp_path):
    muts = _mutantes_escritos(amb)
    m = _mut(muts, "L-a-001", "renumerado")
    m["destino"]["caminho"] = "art. 156"
    m["destino"]["citacao"] = "art. 156 da Lei 9.999/2000"
    m["chamada"]["parametros"]["citacao"] = "art. 156 da Lei 9.999/2000"
    res, _ = _conferir_mutantes(amb, tmp_path, muts)
    assert any("é o mesmo dispositivo do original" in x for _, x in res.falhas)
    assert any("a citação do destino é igual à do caso" in x for _, x in res.falhas)
    muts = _mutantes_escritos(amb)
    m = _mut(muts, "L-a-001", "renumerado")
    m["destino"] = {"citacao": "art. 999 da Lei 9.999/2000", "caminho": "art. 999"}
    m["chamada"]["parametros"]["citacao"] = "art. 999 da Lei 9.999/2000"
    res, _ = _conferir_mutantes(amb, tmp_path, muts)
    assert any("não aparece como dispositivo na fonte do caso" in x for _, x in res.falhas)
    assert not [x for c, x in res.falhas if c != "mutantes:L-a-001#renumerado"]


def test_d5_renumerado_citacao_da_chamada_diverge_do_destino_declarado(amb, tmp_path):
    muts = _mutantes_escritos(amb)
    _mut(muts, "L-a-001", "renumerado")["chamada"]["parametros"]["citacao"] = "art. 158 da Lei 9.999/2000"
    res, _ = _conferir_mutantes(amb, tmp_path, muts)
    assert any("citação da chamada difere da citação do destino" in x for _, x in res.falhas)


def test_d5_validador_nao_julga_se_o_destino_e_o_conteudo_pedido(amb, tmp_path):
    """Destino existente e diferente do original: o validador não decide se é o conteúdo pedido (isso é REVISAO_HUMANA
    (vi)), logo não há FALHA."""
    res, _ = _conferir_mutantes(amb, tmp_path, _mutantes_escritos(amb))
    assert not res.falhas
    assert all(cat == "(vi)" for c, cat, _ in res.revisoes if c.startswith("mutantes:"))


@pytest.mark.parametrize("trecho_novo,ok", [
    (lambda t: t[:10] + ("x" if t[10] != "x" else "y") + t[11:], True),
    (lambda t: t[:10] + "xy" + t[12:], False),
    (lambda t: t, False),
    (lambda t: t + "x", False),
])
def test_d5_caractere_difere_em_exatamente_um_caractere(amb, tmp_path, trecho_novo, ok):
    muts = _mutantes_escritos(amb)
    texto = v.norm(achar(base_casos(amb), "L-a-002")["gabarito"]["texto"])
    _mut(muts, "L-a-002", "caractere")["chamada"]["parametros"]["trecho"] = trecho_novo(texto)
    res, _ = _conferir_mutantes(amb, tmp_path, muts)
    assert (not res.falhas) is ok, res.falhas[:3]
    if not ok:
        assert any("exatamente um caractere" in x for _, x in res.falhas)


def test_d5_data_trocada_exige_data_iso_igual_a_do_caso_e_referencia_a_alternativa(amb, tmp_path):
    for campo, valor, trecho in [("data_mutante", "ontem", "data ISO válida"),
                                 ("data_mutante", "1999-01-01", "difere da declarada"),
                                 ("base", "x", "informe `base: anterior_a_obra`")]:
        muts = _mutantes_escritos(amb)
        _mut(muts, "L-c-001", "data_trocada")[campo] = valor
        res, _ = _conferir_mutantes(amb, tmp_path, muts)
        assert any(trecho in x for _, x in res.falhas), (campo, res.falhas[:3])
    muts = _mutantes_escritos(amb)
    _mut(muts, "L-c-001", "data_trocada")["chamada"]["parametros"]["data"] = "1999-07-01"
    res, _ = _conferir_mutantes(amb, tmp_path, muts)
    assert any("`data` da chamada difere" in x for _, x in res.falhas)


def test_d5_data_trocada_com_redacao_alternativa_declarada_exige_a_referencia(amb, tmp_path):
    casos = base_casos(amb)
    achar(casos, "L-c-001")["gabarito"]["redacao_alternativa"] = {
        "ato": "lei-8000-2001", "inicio": "2001-03-05", "fim": None, "fundamento": "x", "texto": "Art. 156. Outra."}
    muts = _mutantes_escritos(amb)  # o rascunho é gerado do caso sem alternativa; a referência é escrita pelo pesquisador
    m = _mut(muts, "L-c-001", "data_trocada")
    m.pop("base", None)
    m["redacao_alternativa"] = {"ato": "lei-8000-2001"}
    res, _ = _conferir_mutantes(amb, tmp_path, muts, casos)
    assert not any("redacao_alternativa" in x or "referência" in x for _, x in res.falhas), res.falhas[:3]
    for ref in ({"ato": "lei-1-2001"}, None):
        m["redacao_alternativa"] = ref
        res, _ = _conferir_mutantes(amb, tmp_path, muts, casos)
        assert any("falta a referência" in x for _, x in res.falhas)


def test_d5_data_trocada_em_caso_que_nao_a_declara_reprova(amb, tmp_path):
    muts = _mutantes_escritos(amb)
    ex = dict(_mut(muts, "L-c-001", "data_trocada"), caso="L-a-001", id="L-a-001#data_trocada")
    res, _ = _conferir_mutantes(amb, tmp_path, muts + [ex])
    assert any("só se aplica a (b) e (c)" in x for _, x in res.falhas)


def test_d5_mutantes_json_invalido_e_arquivo_ausente_viram_falha(amb, tmp_path):
    p = tmp_path / "mutantes.jsonl"
    p.write_text("{não é json\n[]\n", encoding="utf-8")
    res = v.Resultado()
    v.validar_mutantes(str(p), base_casos(amb), set(), v.Contexto(amb["pasta"], None, res), res)
    assert any("JSON inválido" in m for _, m in res.falhas) and any("não é objeto" in m for _, m in res.falhas)
    res = v.Resultado()
    v.validar_mutantes(str(tmp_path / "nao-existe.jsonl"), base_casos(amb), set(), v.Contexto(amb["pasta"], None, res), res)
    assert any("ilegível" in m for _, m in res.falhas)


# --- as cinco verificações rebaixadas de FALHA a REVISAO_HUMANA ----------------------------------------------
def test_d5_remissao_com_anexo_na_lista_correta_nao_reprova_e_vai_a_revisao(tmp_path):
    texto = "Art. 8º Aplicam-se o art. 4º e o Anexo I desta Lei."
    doc = [LEI9990, "Art. 4º Regra quatro da lei.", texto]
    for alvos in ([{"obra": "Lei 9.990/2000", "caminho": "art. 4º"}, {"obra": "Lei 9.990/2000", "caminho": "Anexo I"}],
                  [{"obra": "Lei 9.990/2000", "caminho": "art. 4º"},
                   {"obra": "Lei 9.990/2000", "caminho": "Anexo I, art. 1º"}]):
        c, pasta = _um(tmp_path, doc, texto, "art. 8º da Lei 9.990/2000", "art. 8º", cap="e", alvos=alvos)
        res = _val(c, pasta)
        assert not falhas_de(res, "L-e-001"), falhas_de(res)
        assert any("alvo de anexo" in m for _, _, m in _revs(res, "L-e-001", "(ii)"))


def test_d5_remissao_com_alvo_de_caminho_invalido_continua_falha(tmp_path):
    texto = "Art. 8º Aplicam-se o art. 4º e o Anexo I desta Lei."
    c, pasta = _um(tmp_path, [LEI9990, "Art. 4º Regra quatro da lei.", texto], texto, "art. 8º da Lei 9.990/2000",
                   "art. 8º", cap="e", alvos=[{"obra": "Lei 9.990/2000", "caminho": "art. 4º"},
                                              {"obra": "Lei 9.990/2000", "caminho": "Anexo I, inciso"}])
    acusa(_val(c, pasta), "L-e-001", "caminho do alvo incompleto ou inválido")


@pytest.mark.parametrize("frase", ["Observado o Art. 2º desta Lei", "Aplica-se o disposto no Art. 2º desta Lei",
                                    "Nos termos do Art. 2º desta Lei"])
def test_d5_art_maiusculo_em_remissao_nao_reprova_e_vai_a_revisao(tmp_path, frase):
    texto = f"Art. 1º {frase}, aplica-se a regra um."
    c, pasta = _um(tmp_path, [LEI9990, texto, "Art. 2º Segunda regra da lei."], texto, "art. 1º da Lei 9.990/2000",
                   "art. 1º")
    res = _val(c, pasta)
    assert not falhas_de(res, "L-a-001"), falhas_de(res)
    assert any("lido como remissão" in m for _, _, m in _revs(res, "L-a-001", "(v)"))


def test_d5_art_maiusculo_que_abre_outro_dispositivo_continua_falha(tmp_path):
    doc = [LEI9990, "Art. 1º Regra da lei e Art. 2º Segunda regra da lei.", "Art. 3º Terceira regra."]
    c, pasta = _um(tmp_path, doc, "Art. 1º Regra da lei e Art. 2º Segunda regra da lei.", "art. 1º da Lei 9.990/2000",
                   "art. 1º")
    acusa(_val(c, pasta), "L-a-001", "início de outro dispositivo")


def _pdf_tabela(tmp_path, ultima):
    return _doc(tmp_path, pdf_bytes([[LEI9990, "ANEXO I", "TABELA DE VALORES", "Valor devido", ultima]]), "pdf")


def test_d5_celula_numerica_em_pdf_nao_reprova_e_vai_a_revisao(tmp_path):
    pasta, sha = _pdf_tabela(tmp_path, "100")
    c = _caso(sha, "Valor devido 100", "Tabela do Anexo I da Lei 9.990/2000", "Anexo I, tabela", cap="d")
    res = _val(c, pasta)
    assert not falhas_de(res, "L-d-001"), falhas_de(res)
    assert any("linhas só de número" in m for _, _, m in _revs(res, "L-d-001", "(v)"))


def test_d5_pdf_com_texto_inventado_continua_falha_mesmo_com_leitura_alternativa(tmp_path):
    pasta, sha = _pdf_tabela(tmp_path, "100")
    c = _caso(sha, "Valor devido 999", "Tabela do Anexo I da Lei 9.990/2000", "Anexo I, tabela", cap="d")
    acusa(_val(c, pasta), "L-d-001", "não é trecho contínuo da fonte")


@pytest.mark.parametrize("estilo", ["text-decoration:none!important;text-decoration:line-through ! important",
                                    "text-decoration:none!important;text-decoration:line-through/**/!important",
                                    "text-decoration:line-through !IMPORTANT;text-decoration:none"])
def test_d5_prioridade_inline_nao_reprova_gabarito_correto_e_vai_a_revisao(tmp_path, estilo):
    html = (f"<html><body><p>{LEI9990}</p><p>Art. 1º Texto <span style='{estilo}'>antigo</span> vigente da regra."
            f"</p></body></html>")
    pasta, sha = _doc(tmp_path, html)
    c = _caso(sha, "Art. 1º Texto vigente da regra.", "art. 1º da Lei 9.990/2000", "art. 1º")
    res = _val(c, pasta)
    assert not falhas_de(res, "L-a-001"), falhas_de(res)
    assert any("prioridade" in m for _, _, m in _revs(res, "L-a-001", "(v)"))
    # a leitura alternativa (outra resolução da prioridade) também é aceita, com a mesma revisão, em vez de FALHA
    c["gabarito"]["texto"] = "Art. 1º Texto antigo vigente da regra."
    res = _val(c, pasta)
    assert not falhas_de(res, "L-a-001"), falhas_de(res)
    assert any("prioridade" in m for _, _, m in _revs(res, "L-a-001", "(v)"))


def test_d5_estilo_inline_sem_prioridade_nao_gera_leitura_alternativa():
    html = "<html><body><p>Art. 1º Texto <span style='text-decoration:line-through'>antigo</span> final.</p></body></html>"
    f = v.carregar_fonte(html.encode("utf-8"))
    assert f.alternativas == [] and "antigo" not in f.clean


def test_d5_rubrica_de_anexo_seguida_de_titulo_minusculo_nao_reprova_e_vai_a_revisao(tmp_path):
    doc = [DEC7, "Art. 1º Aprova o anexo.", "Anexo I", "regulamento dos deveres.", "Art. 1º Primeira regra do anexo.",
           "Art. 2º Segunda regra do anexo."]
    c, pasta = _um(tmp_path, doc, "Art. 2º Segunda regra do anexo.", "Art. 2º do Anexo I do Decreto 7/2020",
                   "Anexo I, art. 2º", cap="d", norma=N_DEC7, ato=DEC7, id_="L-d-001")
    res = _val(c, pasta)
    assert not falhas_de(res, "L-d-001"), falhas_de(res)
    assert any("título que começa por minúscula" in m for _, _, m in _revs(res, "L-d-001", "(v)"))
    c["citacao"], c["caminho"] = "Art. 2º do Anexo II do Decreto 7/2020", "Anexo II, art. 2º"  # anexo inexistente: FALHA
    assert falhas_de(_val(c, pasta), "L-d-001")


def test_d5_nenhuma_outra_falha_foi_rebaixada(amb):
    """Os controles que não são os cinco continuam FALHA (amostra: ato vizinho, texto inventado)."""
    casos = base_casos(amb)
    achar(casos, "L-d-001")["gabarito"]["texto"] = "Art. 2º Compete ao outro órgão fiscalizar a outra matéria."
    achar(casos, "L-a-001")["gabarito"]["texto"] = "Art. 156. Texto inventado."
    res = rodar(casos, amb)
    assert falhas_de(res, "L-d-001") and falhas_de(res, "L-a-001")


# --- item 13: API direta com registro que não é objeto -------------------------------------------------------
@pytest.mark.parametrize("registro", [None, [], 5, "abc"])
def test_d5_api_direta_com_registro_nao_objeto_vira_falha_controlada(amb, registro):
    res = v.validar([registro], amb["pasta"], None, None, False)
    assert any(c == "registro-1" and "não é objeto JSON" in m for c, m in res.falhas)
    res = v.validar([registro] + copy.deepcopy(base_casos(amb)), amb["pasta"], amb["csv"], None, False)
    assert any(c == "registro-1" for c, _ in res.falhas) and not falhas_de(res, "L-a-001")
