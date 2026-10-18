# 0033 - Candidato por documento, falha de fonte e orçamento na busca inicial

Data: 18/10/2026. Rodada 5 do auditor.

- A7: a migração 012 (Python, idempotente) marca `candidato_ao_vivo` por `parsed_document`: candidato quando alguma redação não riscada do modelo está no `fts_staging` e não no `fts_redaction` (texto+path+rótulo). Só marca; não desmarca o que a 010/011 marcaram. O runner de migrações passou a aceitar módulos `.py` com `migrar(conn)`.
- Regra 2: `buscar_legislacao`, `buscar_normas_*` e `pesquisar_jurisprudencia` devolvem `parcial` quando alguma fonte consultada falhou e há itens, e `indisponivel` (com `motivo`) quando não há item. Nunca `ok` com zero por falha. Fonte `offline` declarada não conta como falha.
- Orçamento: a busca inicial do conector em `buscar_normas_*` roda sob o prazo (thread daemon com PRAZO propagado); estourado, `indisponivel/orcamento`. Limite: conector bloqueante é abandonado, não cancelado.
