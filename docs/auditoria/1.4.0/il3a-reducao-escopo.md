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

## Segunda redução (passe final, F1 e F2)

Supervisor (Opus), 07/11/2026, depois do passe final do PR #37 (`parecer-pr37-final.md`, COM BLOQUEADOR: F1 e F2). Esgotadas as rodadas do D5, aplica-se redução de escopo, seguida de conferência estreita, como no precedente do PR #36.

1. **F1 (conferência material da cadeia e do predecessor).** Nesta entrega o executor não confere materialmente o texto, a ação e o dispositivo atingido entregues em `ultima_versao_oficial_anterior` e em `cadeia_alteracoes`. Por isso, caso (c) do tipo `nao_verificado_para_D` com motivo `sem_versao_oficial_na_data`, cujo acerto depende dessa entrega (matriz IL.1, 1.1), nunca é contado como acerto: sai `parcial`, com motivo `conferencia_material_da_cadeia_nao_implementada`, no denominador e fora do numerador. A inspeção de confirmação indevida continua integral. A condição adicional de (c) (100% dos casos sem fundamento devolvidos como não verificados, com motivo) continua aferida pelos estados e motivos. Consequência declarada: a capacidade (c) tende a reprovar por acerto insuficiente enquanto a conferência material não existir; isso é abstenção do instrumento de medida, não aprovação.
2. **F2 (envio por socket preexistente).** No modo local, a CLI instala o gancho de auditoria como primeira instrução do processo, antes de importar o serviço ou qualquer módulo de rede, e recusa executar se houver descritor de socket aberto no processo no momento da instalação. Assim, antes da guarda nenhum socket nasce sem ser registrado pelo evento de criação, o que leva à recusa da execução no modo local; durante a guarda, a criação é barrada antes de existir descritor. (Precisão acrescentada pelo supervisor depois da conferência estreita do PR #37.) A garantia declarada passa a ser a do processo do executor iniciado pela CLI; chamadas de `send`/`sendall` sobre socket criado antes da guarda, fora desse processo, ficam expressamente fora da garantia (limitação documentada).
3. Nada disso altera matriz, pisos, reserva ou mutantes congelados.
