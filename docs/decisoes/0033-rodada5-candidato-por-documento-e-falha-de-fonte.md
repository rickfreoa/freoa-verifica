# 0033 - Candidato por documento, falha de fonte e orçamento na busca inicial

Data: 18/10/2026. Rodada 5 do auditor.

- A7: a migração 012 (Python, idempotente) marca `candidato_ao_vivo` por `parsed_document`: candidato quando alguma redação não riscada do modelo está no `fts_staging` e não no `fts_redaction` (texto+path+rótulo). Só marca; não desmarca o que a 010/011 marcaram. O runner de migrações passou a aceitar módulos `.py` com `migrar(conn)`.
- Regra 2: `buscar_legislacao`, `buscar_normas_*` e `pesquisar_jurisprudencia` devolvem `parcial` quando alguma fonte consultada falhou e há itens, e `indisponivel` (com `motivo`) quando não há item. Nunca `ok` com zero por falha. Fonte `offline` declarada não conta como falha.
- Orçamento: a busca inicial do conector em `buscar_normas_*` roda sob o prazo (thread daemon com PRAZO propagado); estourado, `indisponivel/orcamento`. Limite: conector bloqueante é abandonado, não cancelado.

## Rodada 6: acervo de versão não publicada, modelo canônico e orçamento por item

- Esquemas 8/9 só existiram em builds de desenvolvimento (a v1.0.2 publicada tem esquema 1..5, sem `fts_staging`). Nesses homes um candidato ao vivo com texto igual ou subconjunto do canônico não tem critério de conteúdo que o distinga. `schema_version` não guarda histórico além das versões aplicadas, então o critério é o estado: `fts_staging` com linhas e nenhuma captura marcada `candidato_ao_vivo=1` (verificado na 012, antes de marcar, e na 013 para homes já na 012) grava `meta.acervo_origem_nao_publicada=1`. Limite: um home v1.0.3 com falha entre a indexação e a marca teria o mesmo estado e seria sinalizado.
- Com a marca: `acervo reconstruir` e `snapshot install` recusam com `ACERVO_DE_VERSAO_NAO_PUBLICADA` (original intacto) e orientam instalar o snapshot em home novo; `doctor`/C7 incluem o mesmo motivo. A instalação de snapshot anexa ao banco local (não o substitui), por isso também recusa.
- `reindexar_fts` escolhe o modelo canônico de cada obra na captura mais recente não candidata; candidata nunca substitui obra que tem captura canônica (teste de regressão).
- Orçamento por item: cada indexação de candidato roda sob `_com_prazo`; ao estourar, o item vira `nao_indexado` motivo `orcamento` e um evento de cancelamento (`limites.CANCELADO`) faz a thread abandonada desfazer a transação do staging antes de confirmar. Limite: gravação já confirmada no instante do estouro não é desfeita.
- Limitação conhecida: homes v1.0.2 contaminados por buscas ao vivo antes desta versão (A7 original) não são descontaminados retroativamente. Recomendação: reinstalar o snapshot da v1.0.3 em home novo; `doctor` sugere isso quando o conjunto de obras diverge do manifesto (C7).
