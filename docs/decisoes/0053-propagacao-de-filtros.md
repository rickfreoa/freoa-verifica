# 0053 — Propagação de filtros e declaração do que a fonte não filtra

Data: 19/10/2026 · Versão: 1.3.0 · Origem: plano 1.3.0, E3

## Problema

O serviço repassava `desde`/`ate` a todo conector consultado ao vivo, mas o TJDFT os descartava, o TJSP esperava outros nomes (`dt_inicio`/`dt_fim`) e o STJ (índice local) usava só o limite. Nenhuma resposta dizia quais filtros a fonte tinha ignorado.

## Regras

1. Cada conector declara em `filtros` os filtros públicos que aplica na origem: `remoto` (parâmetro da fonte) ou `local` (no conector, sobre o recuperado). O que não consta não é aplicado.
2. TJDFT: a forma de data em `termosAcessorios` não tem fixture; **não se envia** parâmetro não comprovado. `desde`/`ate` são aplicados no conector sobre a data de julgamento (na falta, a de publicação); registro sem data não prova a janela e é descartado. `filtros: local`.
3. TJSP: `desde`/`ate` (AAAA-MM-DD) viram `dados.dtJulgamentoInicio`/`Fim` em `DD/MM/AAAA`; `dt_inicio`/`dt_fim` explícitos prevalecem.
4. STJ: `search` aplica `desde`/`ate` em SQL sobre `decision_date`, normalizando os três formatos presentes no índice; linha sem data reconhecível fica de fora.
5. A resposta de `pesquisar_jurisprudencia` traz `filtros_nao_aplicados` (lista de `{fonte, filtro, compensacao}`) e `fontes.<id>.filtros`. Campos **aditivos e experimentais**. A fonte que não filtra é consultada do mesmo modo; o SQL do serviço continua a filtrar o que foi recuperado, e a resposta diz isso (`compensacao`).

## Consequências

- Falha da fonte continua `unavailable`; filtro não aplicado nunca vira "zero resultados".
- `limite` e `cursor` não são repassados às fontes (a página consultada é a padrão); a matriz em `docs/FILTROS.md` registra isso como limitação.
- Quando uma sonda comprovar o campo de data do TJDFT, o filtro pode passar a `remoto` com fixture e teste novos.
