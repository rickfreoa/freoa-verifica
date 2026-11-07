# IL.3-a: redução de escopo das remissões (D5)

Supervisor (Opus), 07/11/2026, depois da auditoria r3 do PR #37 (`C:\dev\fv14-auditoria\parecer-pr37-r3.md`, COM BLOQUEADOR), sob o D5 do plano 1.4 (três rodadas e passe final; teto não é aprovação; reduzir escopo ou adiar).

## Decisão

1. Nesta entrega, `obter_dispositivo` mantém o campo aditivo `remissoes[]`, mas **nenhuma remissão é devolvida com `resolvida: true`**. A resolução positiva fica desativada no ponto comum de emissão da fachada (Python, MCP e REST), por invariante testada.
2. `alvo` passa a ser leitura mecânica não verificada do texto emitido; não afirma obra nem dispositivo. A documentação do contrato diz isso expressamente.
3. A capacidade (e) da Porta L permanece `nao_apurada` em todas as rotas; nenhuma apuração de (e) pode ocorrer enquanto a resolução estiver desativada. A matriz, os pisos, a reserva e os mutantes congelados não mudam.
4. O extrator (`freoa_verifica/remissoes.py`) e seus negativos permanecem no repositório como base para a retomada; os 52 contraexemplos da r3 (R3-1 a R3-3, R3-6) entram como negativos independentes.

## Fundamento

Em três rodadas, cada correção eliminou as contraprovas anteriores, mas variantes de produções elementares continuaram a produzir `resolvida: true` com obra ou dispositivo diferentes do designado pelo texto (sigla posterior, obra em minúsculas, qualificador não consumido, token romano malformado). `resolvida: true` com alvo errado é confirmação indevida (matriz IL.1, seção 2, iii), eliminatória. O reconhecimento de 25/25 alvos do desenvolvimento com zero excedentes mostra base útil, mas não autoriza publicar a resolução. O auditor recomendou esta redução.

## Retomada

Nova trilha posterior ao IL.3: gramática de expressões completas, identificação de obra única e normalizada aplicada antes e depois do caminho, validação de tokens, consumo verificável até término comprovado, e os contraexemplos das rodadas r1–r3 como negativos. A retomada exige auditoria própria e só então a capacidade (e) pode ser apurada.
