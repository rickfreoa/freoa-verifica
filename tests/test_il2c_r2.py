"""Inventários independentes do parecer r2; respostas públicas e bytes reais intactos."""
import re

import pytest
from lxml import html

from freoa_verifica.aliases import WorkKey
from freoa_verifica.service import Verifica
from tests.test_camara_legin import servidor, response
from tests.test_il2c_r1 import chamar, _conteudo  # noqa: F401

NORMS = {"lsa": ("lei", "6404", 1976), "lc": ("lei_complementar", "123", 2006),
         "lib": ("lei", "13874", 2019)}
FIX_NAMES = {"lsa": "lei6404", "lc": "lc123", "lib": "lei13874"}


@pytest.fixture(scope="module")
def acervo_r2(tmp_path_factory):
    # Replay em módulo: cada caso mantém seu próprio recibo; nenhuma chamada real.
    with pytest.MonkeyPatch.context() as patch:
        servidor.__wrapped__(patch, [])
        patch.setenv("FV_OFFLINE", "0")
        with Verifica(home=tmp_path_factory.mktemp("r2"), registro="completo") as svc:
            for kind, number, year in NORMS.values():
                for version in ("vigente", "publicacao_original"):
                    svc._capture_work(WorkKey("federal", kind, number, year), versao=version)
            patch.setenv("FV_OFFLINE", "1")
            yield svc


def cite(norm, path):
    from freoa_verifica.parsers.paths import int_to_roman
    kind, num, year = NORMS[norm]
    parts = path.split(".")
    label = "art. " + parts[0][3:]
    for part in parts[1:]:
        if part == "caput":
            label += ", caput"
        elif part == "parunico":
            label += ", parágrafo único"
        elif part.startswith("par"):
            label += ", parágrafo " + part[3:]
        elif part.startswith("inc"):
            label += ", inciso " + int_to_roman(int(part[3:]))
        elif part.startswith("ali-"):
            label += ", alínea " + part[4:]
        elif part.startswith("item"):
            label += ", item " + part[4:]
    return label + (" da Lei Complementar " if kind == "lei_complementar" else " da Lei ") + num + "/" + str(year)


def paths(spec):
    result = []
    for part in spec.split():
        if ".." in part:
            a, b = map(int, part.split(".."))
            result.extend("art" + str(n) for n in range(a, b + 1))
        else:
            result.append("art" + part)
    return result


# Listas integrais transcritas do parecer, sem seleção pela saída do parser.
CAPUT = {
    ("lsa", "vigente"): "2..5 8 10..11 13..18 22..31 34..51 53..55 57..58 61 63..68 70..75 77..82 84..88 92 95 97..101 103..104 106..109 111..113 116..119 121..127 129..138 142..144 146..150 152 154..159 162..176 178 184 186 189..190 193..197 200..202 204..206 208..211 213..216 219..229 231..233 235..237 239 243..244 246..253 256..259 261..262 264..265 267 269..272 275..279 281..282 285 287 289 291 295..298 4-A 110-A 136-A 294-A 294-B 299-B",
    ("lc", "vigente"): "2 5..8 10 14 16 20 22..23 25 28 30..33 38..39 43..45 47 51..52 55 62..65 70 73 75..77 3-A 18-B 18-C 18-E 18-F 25-B 38-A 38-B 49-A 60-A 61-A 61-F 67-A 79-C 85-A",
    ("lib", "vigente"): "1..2 4..5 16 18..20 4-A",
    ("lsa", "publicacao_original"): "2..5 8 10..11 13..18 22..48 50..51 53..55 57..68 70..75 77..82 84..88 92 95 97..101 103..104 106..113 115..119 122..126 129..138 140..144 146..150 152 154..159 161..179 182..190 193..197 200..202 204..206 208..211 213..216 219..233 235..237 239 243..244 246..259 261..262 264..265 267 269..272 275..279 281..282 285 287 289 291 293..298",
}


def raw_descendant(norm, version, path):
    """Leitura independente do HTML: parágrafos físicos, sem parser do produto."""
    key = "textos_" + ("original_" if version == "publicacao_original" else "atualizado_") + FIX_NAMES[norm]
    resp = response(key)
    # Espaços do arquivo não são quebras editoriais; br e p são.
    tree = html.fromstring(re.sub(r"\s+", " ", resp.body.decode("utf-8")))
    roots = tree.xpath('//*[@class="textoNorma"]')
    root = roots[0] if roots else tree
    for node in root.xpath(".//br|.//p|.//center|.//div"):
        node.text = "\n" + (node.text or "")
        node.tail = "\n" + (node.tail or "")
    article = None
    physical = root.text_content().split("\n")
    for line in physical:
        text = " ".join(line.split())
        start = re.match(r"Art\.\s*(\d+)[º°o]?(?:-([A-Z]))?[.\s]", text, re.I)
        if start:
            article = "art" + start[1] + ("-" + start[2].upper() if start[2] else "")
            # Alguns descendentes estão no mesmo parágrafo HTML.
            inline = re.split(r"(?<=[.!?])\s+(?=§\s*\d)", text, maxsplit=1)
            text = inline[1] if len(inline) == 2 else ""
        if article != path:
            continue
        child = re.match(r"(?:§\s*\d+[º°.]*|Parágrafo único[.]?|[IVXLCDM]+\s*[-–—]|[a-z]\)|\d+\.)\s*(.*)", text)
        if child:
            normative = re.split(r'\((?=[“"]?Caput|Artigo|Parágrafo|Inciso|Alínea|Vide|VETADO)', child[1])[0].strip()
            if len(normative) >= 35:
                return normative[:100].rsplit(" ", 1)[0]
    raise AssertionError((norm, version, path, "sem testemunha independente"))


@pytest.mark.parametrize("norm,version,path", [(n, v, p) for (n, v), spec in CAPUT.items() for p in paths(spec)])
def test_f10_todos_caputs_publicos(acervo_r2, norm, version, path):
    svc = acervo_r2
    key = WorkKey("federal", *NORMS[norm])
    rw = svc._resolve(key, versao=version)
    descendant = raw_descendant(norm, version, path)
    caput = rw.document.provision(path + ".caput").redactions[0]
    aggregate = rw.document.provision(path).redactions[0]
    assert descendant in " ".join(aggregate.text.split()), (path, descendant)
    assert descendant not in " ".join(caput.text.split()), (path, descendant)
    assert caput.span[0] == aggregate.span[0] and caput.span[1] < aggregate.span[1]
    out = svc.obter_dispositivo(work_id=rw.work_id, caminho=path + ".caput", versao=version)
    assert descendant not in (out.get("texto") or "")
    assert out["caminho"] == path + ".caput"
    if version == "vigente":
        result = svc.verificar_citacao(cite(norm, path + ".caput"), trecho=descendant)
        assert result["text"]["status"] != "verified"


ASSOCIATIONS = {
    "lsa": "art4-A.par4>art4-A art41.par3.inc2>art41.par3 art55.par2.inc2>art55.par2 art55.par3.inc2>art55.par3 art110-A.par14>art110-A art133.par6.inc4>art133.par6 art136-A.par2.inc2>art136-A art176.par5.inc4.ali-i>art176.par5 art177.par2.inc2>art177.par2 art254-A.par5>art254-A art294-A.inc5>art294-A art294-B.par2.inc2>art294-B art299-B.parunico>art299-B",
    "lc": "art2.par9.inc2>art2.par9 art3-A.parunico>art3-A art4.par4.inc2>art4.par4 art8.inc2.ali-b>art8.inc2 art8.par1.inc2>art8.par1 art17.inc10.ali-c.item4>art17.inc10.ali-c art18.par1.inc3>art18.par1 art18.par1-B.inc2>art18.par1-B art18.par4.inc7.ali-b>art18.par4.inc7 art18.par4-A.inc5>art18.par4-A art18.par5-M.inc2>art18.par5-M art18-F.inc3>art18-F art25-B.parunico>art25-B art38-B.parunico.inc2>art38-B art61-F.parunico>art61-F art67-A.parunico>art67-A art76.parunico>art76",
    "lib": "art4-A.par4.inc2>art4-A",
}


@pytest.mark.parametrize("norm,old,target", [(n, *pair.split(">")) for n, spec in ASSOCIATIONS.items() for pair in spec.split()])
def test_f11_associacoes_e_historico_publico(acervo_r2, norm, old, target):
    svc = acervo_r2
    rw = svc._resolve(WorkKey("federal", *NORMS[norm]))
    annotations = rw.document.provision(target).redactions[0].annotations
    assert annotations and all(a.target_path == target for a in annotations)
    assert not any(a.target_path == target for a in rw.document.provision(old).redactions[0].annotations)
    out = svc.obter_dispositivo(work_id=rw.work_id, caminho=target)
    assert any(a["target_path"] == target for a in out["anotacoes"])
    hist = svc.historico_dispositivo(cite(norm, target))
    assert hist["status"] == "unknown" and hist["needs_judgment"] is True
    assert hist["linha_do_tempo"] == [] and hist["flags"]
    note = annotations[0].raw
    verified = svc.verificar_citacao(cite(norm, target), trecho=note)
    assert verified["text"]["status"] != "verified"


AGGREGATES = {
    "lsa": "art110-A art136-A art136-A.par2 art138 art294-A art294-B art294-B.par2",
    "lc": "art2 art16 art18-C.par3 art18-E art22 art23 art23.par4 art25-B art31 art32 art33 art38-B art38-B.parunico art49-A art52 art61-F art65 art65.par4 art67-A art77",
    "lib": "art19 art20",
}


@pytest.mark.parametrize("norm,path", [(n, p) for n, spec in AGGREGATES.items() for p in spec.split()])
def test_f11_impedimentos_agregados(acervo_r2, norm, path):
    svc = acervo_r2
    rw = svc._resolve(WorkKey("federal", *NORMS[norm]))
    out = svc.obter_dispositivo(work_id=rw.work_id, caminho=path)
    assert out["vigencia"]["status"] == "unknown"
    hist = svc.historico_dispositivo(cite(norm, path))
    assert hist["status"] == "unknown" and hist["needs_judgment"]


VETO = {
    ("lsa", "vigente"): "art110-A.par10 art294-A.inc5",
    ("lc", "vigente"): "art15 art52.parunico art55.par2 art60 art69 art77.par3 art85",
    ("lib", "vigente"): "art19.inc4 art20.inc1",
    ("lc", "publicacao_original"): "art1.par2 art13.par4 art15 art17.par1.inc22 art17.par1.inc28 art17.par3 art52.parunico art55.par2 art60 art69 art77.par3",
    ("lib", "publicacao_original"): "art3.inc7 art3.inc11.ali-a art3.par9",
}


@pytest.mark.parametrize("norm,version,path", [(n, v, p) for (n, v), spec in VETO.items() for p in spec.split()])
def test_f12_pontuacao_nao_e_redacao(acervo_r2, norm, version, path):
    svc = acervo_r2
    rw = svc._resolve(WorkKey("federal", *NORMS[norm]), versao=version)
    prov = rw.document.provision(path)
    assert any(a.kind == "veto" for a in prov.redactions[0].annotations)
    assert any(i.code == "VETO" and i.path == path for i in rw.document.issues)
    out = svc.obter_dispositivo(work_id=rw.work_id, caminho=path, versao=version)
    assert out["status"] == "unknown" and out["texto"] is None
    assert out["anotacoes"]
    if version == "vigente":
        for punctuation in (".", ";"):
            result = svc.verificar_citacao(cite(norm, path), trecho=punctuation)
            assert result["text"]["status"] != "verified"


DUPLICATES = {"lsa": "art59 art59.par1", "lc": "art13 art13.par1 art13.par1.inc12 art13.par1.inc14 art18 art18.par1"}
PARTIAL = {
    "lsa": "art62 art110 art140 art177 art177.par2 art179 art182 art182.par1 art183 art187 art188 art255 art293",
    "lc": "art4 art17 art17.par1 art18 art18.par5 art18.par5-B art18.par5-C art18.par5-D art21 art26 art26.par1 art29",
    "lib": "art3",
}


@pytest.mark.parametrize("norm,path", [(n, p) for spec in (DUPLICATES, PARTIAL) for n, ps in spec.items() for p in ps.split()])
def test_f13_historico_se_abstem(acervo_r2, norm, path):
    out = acervo_r2.historico_dispositivo(cite(norm, path))
    assert out["status"] == "unknown" and out["linha_do_tempo"] == []
    assert out["needs_judgment"] and out["flags"]
    assert out["fundamento_temporal"] is None


@pytest.mark.parametrize("norm,path,trecho", [
    ("lsa", "art156.caput", "o administrador interessado será obrigado a transferir para a companhia as vantagens que dele tiver auferido."),
    ("lc", "art25-B", "Artigo acrescido"),
    ("lsa", "art110-A.par10", "."),
    ("lsa", "art59.par1", "texto"),
])
def test_r2_fachadas_e_resolver(acervo_r2, chamar, norm, path, trecho):
    citation = cite(norm, path)
    out = chamar(acervo_r2, "verificar_citacao", citacao=citation, trecho=trecho)
    assert out["text"]["status"] != "verified"
    out = chamar(acervo_r2, "obter_dispositivo", citacao=citation)
    assert trecho not in (_conteudo(out.get("texto")) or "")
    if not path.endswith("caput"):
        out = chamar(acervo_r2, "historico_dispositivo", citacao=citation)
        assert out["status"] == "unknown" and out["linha_do_tempo"] == []
    if path in ("art59.par1", "art110-A.par10"):
        out = chamar(acervo_r2, "resolver_citacao", citacao=citation)
        assert out["status"] == "unknown"


@pytest.mark.parametrize("stub", ["(VETADO)", "(VETADO).", "(VETADO);", "(VETADO) . ;"])
def test_f12_stub_sintetico_ate_saida(verifica_populada, monkeypatch, stub):
    from tests.test_camara_legin import sintetico
    from freoa_verifica.parsers.model import RevokedProvision
    svc, rw, _ = verifica_populada
    rw.document = sintetico("<p>Art. 1º " + stub + "</p>")
    rw.quarantined = rw.document.quarantined
    monkeypatch.setattr(svc, "_resolve", lambda *a, **kw: rw)
    with pytest.raises(RevokedProvision):
        rw.document.provision("art1").current_text()
    result = svc.verificar_citacao("art. 1 da Lei 1/2001", trecho=".")
    assert result["text"]["status"] != "verified"
    out = svc.obter_dispositivo("art. 1 da Lei 1/2001")
    assert out["texto"] is None and out["status"] == "unknown"


@pytest.mark.parametrize("subject,target", [
    ("Artigo", "art1"), ("Parágrafo", "art1.par1"),
    ("Inciso", "art1.par1.inc1"), ("Alínea", "art1.par1.inc1.ali-a"),
    ("“Caput” do artigo", "art1.caput"),
    ("“Caput” do parágrafo", "art1.par1.caput"),
    ("“Caput” do inciso", "art1.par1.inc1.caput"),
    ("“Caput” da alínea", "art1.par1.inc1.ali-a.caput"),
])
def test_f11_sujeito_completo_terminal(subject, target):
    from tests.test_camara_legin import sintetico
    doc = sintetico('<p>Art. 1º Regra.</p><p>§ 1º Parágrafo.</p><p>I - Inciso.</p>'
                    '<p>a) Alínea.</p><p>(' + subject + ' acrescido pela Lei nº 2, de 1/1/2020)</p>')
    annotations = doc.provision(target).redactions[0].annotations
    assert annotations and all(a.target_path == target for a in annotations)
    for prov in doc.provisions:
        assert all(a.target_path == prov.path for r in prov.redactions for a in r.annotations)


def test_f11_alvo_incerto_bloqueia_publicamente(verifica_populada, monkeypatch):
    from tests.test_camara_legin import sintetico
    svc, rw, _ = verifica_populada
    rw.document = sintetico('<p>Art. 1º Regra normativa. (Inciso acrescido pela Lei nº 2, de 1/1/2020)</p>')
    rw.quarantined = rw.document.quarantined
    monkeypatch.setattr(svc, "_resolve", lambda *a, **kw: rw)
    result = svc.verificar_citacao("art. 1 da Lei 1/2001", trecho="Regra normativa.")
    assert result["text"]["status"] == "unknown"
    assert result["identity"]["reason_code"] == "ALVO_NOTA_INCERTO"
    out = svc.obter_dispositivo("art. 1 da Lei 1/2001")
    assert out["texto"] is None and out["vigencia"]["status"] == "unknown"


@pytest.mark.parametrize("norm,path", [("lsa", "art59.par1"), ("lc", "art13.par1.inc12")])
def test_f13_busca_local_nao_reconstroi_vigencia(acervo_r2, norm, path):
    svc = acervo_r2
    rw = svc._resolve(WorkKey("federal", *NORMS[norm]))
    text = rw.document.provision(path).redactions[0].text
    query = " ".join(text.split()[:4]).replace('"', '')
    out = svc.buscar_legislacao(query, data="2025-01-01", limite=50)
    matches = [r for r in out["itens"] if r.get("caminho") == path]
    assert matches
    assert all(r["vigencia"]["status"] == "unknown" for r in matches)


@pytest.mark.parametrize("descendants", [False, True])
def test_f10_fallback_exige_caput_exclusivo(verifica_populada, monkeypatch, descendants):
    from freoa_verifica.parsers.model import ParsedDocument, Provision, Redaction
    svc, rw, _ = verifica_populada
    principal = "Regra principal com identidade própria."
    filho = "Texto reservado ao parágrafo descendente."
    rw.document = ParsedDocument("fixture", "r2", "Lei nº 6404, de 1976", None, principal,
        provisions=[Provision("art1", "Art. 1º", "", redactions=[Redaction(
            principal + ("\n§ 1º " + filho if descendants else ""), False, 0)])])
    if descendants:
        rw.document.provisions.append(Provision("art1.par1", "§ 1º", "", redactions=[Redaction(filho, False, 0)]))
    monkeypatch.setattr(svc, "_resolve", lambda *a, **kw: rw)
    out = svc.obter_dispositivo("art. 1, caput da Lei 6404/1976")
    assert (out.get("texto") == principal) is (not descendants)
    result = svc.verificar_citacao("art. 1, caput da Lei 6404/1976", trecho=filho if descendants else principal)
    assert (result["text"]["status"] == "verified") is (not descendants)
