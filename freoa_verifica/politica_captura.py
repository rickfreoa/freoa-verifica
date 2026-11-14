"""Fontes legislativas consultáveis e política comum para novas capturas."""

from freoa_verifica.connectors.base import Unavailable

LEGIS_CONNECTORS = ("planalto", "camara_legin", "normas_leg", "cvm_normas", "bcb", "senado")
LEGIS_NOVA_CAPTURA = frozenset(LEGIS_CONNECTORS) - {"planalto"}


def exigir_nova_captura(fonte: str) -> None:
    if fonte in LEGIS_CONNECTORS and fonte not in LEGIS_NOVA_CAPTURA:
        raise Unavailable("acervo_legado_sem_nova_captura")
