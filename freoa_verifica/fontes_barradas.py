"""Registro de recusas compartilhado pelo produto e pelo instrumento de captura."""

from types import MappingProxyType
from typing import Mapping

FONTES_BARRADAS: Mapping[str, str] = MappingProxyType({
    "senado_legislacao": "04/11/2026: robots.txt de legis.senado.leg.br: unavailable(http_403), recusa_identificado; barreira, sem nova tentativa",
    "dou": "04/11/2026: robots.txt de www.in.gov.br: unavailable(http_403), recusa_identificado; barreira, sem nova tentativa",
    "npl": "19/11/2026: GET com UA identificado pelo instrumento (sonda, transporte comum): unavailable(transporte_TransportError); TLS concluído e conexão reiniciada pelo servidor depois do pedido HTTP, em robots.txt, llms.txt e ato (l6404consol.htm); plano de testes NPL, T6; barreira, sem nova tentativa",
    "npl_classico": "19/11/2026: GET com UA identificado pelo instrumento (sonda, transporte comum): unavailable(transporte_TransportError); TLS concluído e conexão reiniciada pelo servidor depois do pedido HTTP, no ato l6404consol.htm; plano de testes NPL, T6; barreira, sem nova tentativa",
})
