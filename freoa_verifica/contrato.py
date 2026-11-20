"""Contrato público de saída (docs/CONTRATO.md)."""

CONTRATO_VERSAO = "1"

# Estágios por campo: "<ferramenta>:<caminho>", com `[]` para listas; vale também para tudo sob o caminho.
# `deprecated` entra com aviso em `avisos_contrato` e no CHANGELOG, e sai da exigência do teste de contrato.
DEPRECATED: frozenset[str] = frozenset()
# `experimental` pode mudar sem aviso; fora da exigência do teste de contrato.
EXPERIMENTAL: frozenset[str] = frozenset({
    "listar_fontes:fontes[].sessao_assistida",
    "buscar_legislacao:sessoes_assistidas",
    "buscar_legislacao:fontes.*.sessao_assistida",
    "buscar_legislacao:falhas[].sessao_assistida",
    "verificar_citacao:sessoes_assistidas",
    "verificar_citacao:fontes.*.sessao_assistida",
    "verificar_citacao:falhas[].sessao_assistida",
    "verificar_texto:sessoes_assistidas",
    "verificar_texto:fontes.*.sessao_assistida",
    "verificar_texto:falhas[].sessao_assistida",
    "obter_dispositivo:sessoes_assistidas",
    "obter_dispositivo:fontes.*.sessao_assistida",
    "obter_dispositivo:falhas[].sessao_assistida",
    "listar_fontes:fontes[].cobertura",
    "listar_fontes:fontes[].ultimo_health",
    "listar_fontes:fontes[].capacidade",
    "listar_fontes:fontes[].recorte_acervo",
    "listar_fontes:fontes[].tipos_documento",
    "buscar_legislacao:tesauro",
    "pesquisar_jurisprudencia:tesauro",
    # Lista por tribunal (decisão 0055). `[]` deixa de fora o objeto `cobertura` de `nao_confirmado_no_acervo`, estável.
    "pesquisar_jurisprudencia:cobertura[]",
    "pesquisar_jurisprudencia:cobertura_por_tribunal",
    # Texto de captura lida sem Content-Type (decisão 0065); também em `evidence[]` de `verificar_citacao`.
    "obter_dispositivo:proveniencia",
    "obter_evidencia:proveniencia",
    # Partição de `obter_decisao` com `parte_idx` (decisão 0073, seção 7; PARIDADE-1.4, CH1–CH6).
    "obter_decisao:particao",
})
