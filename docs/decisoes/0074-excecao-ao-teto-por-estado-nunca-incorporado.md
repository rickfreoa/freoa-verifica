# 0074 - Exceção ao teto do D5 por bloqueador restrito a estado de versão nunca incorporada

Estado: aceita. Decisão do titular (Ricardo Peres Freoa) em 29/10/2026, registrada pelo supervisor.

## Contexto

A rodada 3 do PR #20 (I2.7) terminou COM BLOQUEADOR por um único achado: a r3 passou a chavear o registro de
tentativas pela identidade canônica do recurso e deixou de reconhecer marcadores gravados no formato da r2 (chave
pelo SHA-256 da URL textual). Uma recusa registrada pela r2 poderia ser repetida pela r3. A r2 nunca foi
incorporada nem executada fora dos testes, que usam registro em pasta temporária; o supervisor verificou no notebook
do titular, em 29/10/2026, que o diretório padrão do registro (`~/.freoa-verifica/s0-tentativas`) não existe, que
`FV_S0_TENTATIVAS` não está definida e que não há marcadores da r1 (`*.tentativa.json`) em `C:\dev`. Pela letra do
D5, o item seria adiado; a decisão 0070 só cobre correção de registro.

## Decisão

1. Depois do teto do D5, admite-se uma única correção de código quando, cumulativamente: (a) o bloqueador diz
   respeito apenas a estado produzido por versão intermediária do próprio PR, nunca incorporada nem executada fora
   dos testes; (b) a ausência desse estado foi verificada e registrada; (c) a correção é conservadora (diante do
   estado anterior, recusa agir em vez de tentar interpretá-lo) e restrita ao achado.
2. O auditor faz uma conferência curta, que não conta como rodada: o delta toca só o achado (e os importantes e
   menores do mesmo parecer, se o supervisor os tratar) e a correção é conservadora. Responde "CORREÇÃO CONFERE" ou
   "CORREÇÃO NÃO CONFERE". Depois, o passe final independente do D5 continua exigido.
3. "NÃO CONFERE", delta além do permitido, ou passe final com bloqueador fazem valer o D5 sem exceção: o item é
   adiado.

## Aplicação ao PR #20

Antes de qualquer pedido, o orquestrador confere o registro de tentativas inteiro: toda entrada precisa estar no
formato atual (nome igual à chave canônica da URL registrada, campos `url`, `captura`, `inicio` e `identidade`). Se
houver entrada de formato anterior, ilegível ou vazia, nenhuma URL recebe pedido nesta execução e o relatório diz por
quê; a limpeza do registro é decisão humana.
