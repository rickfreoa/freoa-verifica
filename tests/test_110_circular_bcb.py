"""1.1.0 (gold independente B06–B08): "Circular BCB nº N" e variantes são reconhecidas."""
import pytest

from freoa_verifica.citation import extract


@pytest.mark.parametrize("texto,kind,numero,ano,caminho", [
    ("Circular BCB 3.641/2013, art. 1º", "circular", "3641", 2013, "art1"),
    ("Circular do Banco Central do Brasil nº 3.978/2020, art. 2º", "circular", "3978", 2020, "art2"),
    ("Circular nº 3.641/2013", "circular", "3641", 2013, None),
    ("Carta-Circular BCB nº 4.001/2020", "carta_circular", "4001", 2020, None),
])
def test_circular_bcb(texto, kind, numero, ano, caminho):
    c = [c for c in extract(texto) if c.work][0]
    assert (c.work.authority, c.work.kind, c.work.number, c.work.year, c.path) == ("bcb", kind, numero, ano, caminho)


def _json(tipo, numero, texto):
    import json
    return json.dumps({"conteudo": [{"Titulo": f"{tipo} N° {numero}", "Tipo": tipo, "Numero": float(numero),
                                     "Data": "2017-02-23T21:33:00Z", "Revogado": False, "Cancelado": False,
                                     "Texto": texto}]}).encode("utf-8")


def test_resolucao_pre_2020_e_cmn_quando_o_preambulo_declara():
    from freoa_verifica.identity import declared_identity
    from freoa_verifica.parsers.bcb_json import parse_bcb_json
    cmn = parse_bcb_json(_json("Resolução", 4557, "<p>torna público que o Conselho Monetário Nacional, em sessão</p><p>Art. 1º Texto.</p>"))
    key, _ = declared_identity(cmn)
    assert (key.authority, key.kind, key.number, key.year) == ("cmn", "resolucao", "4557", 2017)
    outra = parse_bcb_json(_json("Resolução", 4557, "<p>A Diretoria Colegiada resolve:</p><p>Art. 1º Texto.</p>"))
    key2, _ = declared_identity(outra)
    assert key2 is None or key2.authority != "cmn"


def test_fetch_cai_para_tipo_resolucao_quando_cmn_vem_vazio(monkeypatch):
    from freoa_verifica.connectors import bcb
    from freoa_verifica.connectors.base import Candidate
    vistos = []

    def falso(url, **kw):
        vistos.append(url)
        body = b'{"conteudo": []}' if "CMN" in url else _json("Resolução", 4557, "<p>Conselho Monetário Nacional</p>")
        return type("R", (), {"body": body, "url": url})()

    monkeypatch.setattr(bcb, "connector_fetch", falso)
    c = bcb.BcbConnector() if hasattr(bcb, "BcbConnector") else next(v for v in vars(bcb).values()
                                                                      if isinstance(v, type) and getattr(v, "id", None) == "bcb")()
    r = c.fetch(Candidate("bcb", "bcb:Resolução CMN:4557", "x", metadata={"tipo": "Resolução CMN", "numero": "4557"}))
    assert len(vistos) == 2 and "p1=Resolu%C3%A7%C3%A3o&" in vistos[1] and b"4557" in r.body
