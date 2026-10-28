# 0070 — Correção de registro depois do teto do D5

Estado: aceita. Decisão do titular (Ricardo Peres Freoa) em 28/10/2026, registrada pelo supervisor.

## Contexto

Os passes finais independentes dos PRs #11 e #13, feitos depois das três rodadas do D5 e da redução de escopo,
terminaram com bloqueador apenas por defeitos de registro: no #11, a redução do I1.5 não constava do manifesto
nem do rótulo; no #13, a seção 5 trazia histórico inexato das rodadas. Pela letra do D5, os dois seriam adiados.

## Decisão

1. Depois do teto do D5 (inclusive após o passe final), admite-se uma única correção restrita a registro:
   dados do manifesto de aceite, rótulo, notas, histórico, referências documentais e os testes que só conferem
   esse estado registrado.
2. A correção não altera código de produção, lógica de teste, requisito, critério de aceite nem escopo.
3. O auditor faz uma conferência curta, que não conta como rodada: (a) o delta toca só registro; (b) a correção
   corresponde ao achado do parecer. Responde "CORREÇÃO CONFERE" ou "CORREÇÃO NÃO CONFERE".
4. "NÃO CONFERE", ou delta além de registro, faz valer o D5 sem exceção: o item é adiado.
5. Correção de código, ainda que mecânica, não está coberta por esta decisão.

## Consequências

- Os PRs #11 e #13 recebem a correção de registro e a conferência curta.
- A regra se aplica aos incrementos seguintes do plano 1.4.0.
