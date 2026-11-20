# 0089 - Exceção ao teto do D5 após a auditoria Codex r3 (decisão do titular, 20/11/2026)

## Fato

A auditoria Codex r3 (`docs/auditoria/0089/parecer-codex-r3.md`), terceira e última rodada admitida pelo D5, fechou os
três achados da r2 e apontou um único achado MÉDIO, com veredito BLOQUEADOR por regressão: evento CDP com campo de
prova ausente e campo presente malformado era classificado como simples ausência, com recusa só da candidata, quando
a malformação deveria encerrar a sessão. Não houve admissão indevida nem `verified` irregular.

## Decisão

Opção (A), aprovada pelo titular em 20/11/2026: exceção ao teto do D5, nos termos dos precedentes da própria 0089 e
das decisões 0074 e 0076.

1. A correção limita-se ao achado da r3: campos presentes malformados encerram a sessão antes de se classificar a falta
   de prova; ausência pura continua recusando só a candidata. `transport.py` não muda.
2. O auditor faz uma conferência curta, de escopo fechado nesse achado e nas regressões que a correção possa causar.
3. Novo bloqueador encerra a exceção, sem outra rodada; a decisão volta ao titular.
4. A exceção não dispensa a matriz da CI verde, o ensaio real nem os demais critérios da 0089, da 0090 e da nota de
   escopo da 1.4.0a6.
