# 0025 — Busca: número exato, staging ao vivo, pertinência e tesauro

Revisa a 0010 (a flexão mínima e os prefixos continuam; muda a regra "OR só com AND vazio").

- **Número exato (A6).** Consulta que é só classe e número (siglas ou "Recurso Especial nº ...") consulta a tabela de decisões confirmadas antes do FTS, com `_decision_evidence`. Achado: item com evidência; incidentes (`AgInt no REsp`, `EDcl no REsp`) do mesmo número em `relacionados`. Ausente: `nao_confirmado_no_acervo` com cobertura (tribunais, órgãos, período, registros) e nenhum outro processo. Consulta mista (texto e número) segue a busca textual. Bloco `resultados_textuais` fica vazio no modo número.
- **Staging (A7).** Candidatos capturados por `buscar_legislacao` (e `buscar_normas_*`) entram em `fts_staging`, nunca em `fts_redaction`. A busca consulta o staging somente quando consulta fontes ao vivo; itens saem com `candidato_ao_vivo`. Limite conhecido: se o candidato ao vivo é nova redação de obra já canônica, a redação nova fica só no staging até confirmação.
- **Fontes (A9, M7).** `nao_consultada` com motivo (`offline`, `somente_local`, `limite_atingido_no_acervo_local`, `busca_textual_nao_suportada`). Conector com `busca_textual: False` só é chamado para citação com obra identificável. `truncado` e `total` por fonte vêm de `cands.truncado`/`cands.total` quando o conector os expõe.
- **Fonte (M10).** `fonte` filtra no SQL, antes do limite.
- **Ranking (M5, M6).** Decisões: MATCH em `ementa` e `inteiro_teor`; bm25 com pesos 5 e 1. AND primeiro; com menos de `offset+limite` resultados, completa com OR (até 200 candidatos por bm25) acima do corte: até dois termos basta um; com três ou mais, dois terços (`hits*3 >= 2*n`). Cada item expõe `pertinencia` e `correspondencia` (`todos_os_termos` ou `parcial`); `modo_busca` continua `ampliada` só quando o AND deu zero. O corte de dois termos é desvio deliberado do "dois terços" literal: com dois terços, "acordos inexistente" (1/2) deixaria de recuperar o que a 0010 já recuperava.
- **Tesauro (`tesauro-1`).** 20 pares bidirecionais em arquivo versionado. A consulta vira `(Q) OR (Q')...` com um termo trocado por variante (máximo 12); pertinência é a da melhor variante. Resposta traz `tesauro: {versao, expansoes}`.

Não altera critério de `verified`: busca continua produzindo candidatos.
