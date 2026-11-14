"""Perfil isolado normas.leg.br (0085); mesma leitura conservadora do HTML Câmara."""
from freoa_verifica.parsers.camara_legin import parse_camara_legin

PARSER_VERSION = "normas-leg-1"


def parse_normas_leg(data, *, base_url=None):
    doc = parse_camara_legin(data, base_url=base_url)
    doc.profile = "normas_leg"
    doc.parser_version = PARSER_VERSION
    return doc
