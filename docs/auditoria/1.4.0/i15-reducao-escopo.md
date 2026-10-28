# I1.5: redução de escopo pelo D5 (28/10/2026)

## Fato

As três rodadas do D5 sobre o PR #11 (manifesto de aceite, I1.5) terminaram COM BLOQUEADOR. O parecer da r3 apontou:

- B1: a saúde da bateria não era confrontada com o escopo nem com as contagens (saúde vazia, outra fonte, teste
  `not_run` com `completa: true` e `unavailable` com categoria `regressao` passavam; relatório "BATERIA NAO EXECUTADA"
  com contagens positivas passava).
- B2: `saude.commit` não era confrontado com o commit do recibo.
- Importantes: o ambiente da etapa 8 aceitava Linux e IP dos EUA; a decisão 0068 afirmava conferência de "forma e
  coerência" da saúde que não existia e falava em "núcleo e um por tribunal" quando o código aceita um pacote qualquer.

Não há rodada 4 (D5).

## Decisão

1. `bateria_live` (etapas 2 e 8) fica com `relatorio` e `saude_fontes` (caminho no repositório; sha256 calculado pelo
   `registrar` e reconferido no `validar`), `commit` (com as igualdades já existentes entre etapas) e `parecer_bateria`
   (caminho de parecer do auditor sobre esta bateria, com sha256 reconferido e última linha normalizada exatamente
   `SEM BLOQUEADOR`, mesma rotina do parecer da etapa 4). Saem do recibo e do código `aprovados`, `xfail`, `falhas`,
   `escopo`, `ambiente`, `falhas_fora_do_escopo` e a leitura semântica do `saude-fontes.json`. Não resta conferência
   parcial que pareça material: o validar só confere existência, hash e o parecer.
2. A `instalacao` (etapa 7) mantém os campos e passa a exigir `parecer_instalacao` (mesma rotina). O ambiente da etapa 8
   deixa de ser campo do recibo. `doctor` mantém `ok` e `alertas`.
3. `snapshot.pacotes` mantém lista com ao menos um pacote e digests; a documentação não afirma mais do que isso.
4. A decisão 0068 foi reescrita para dizer exatamente o que o código impõe e, em seção própria, o que é conferência
   material do auditor (execução e cobertura da bateria, commit da saúde, ambiente Windows e Brasil, completude dos
   pacotes, publicação no GitHub e na PyPI).

Os cenários B1 e B2 deixam de ser responsabilidade do validar. Os testes provam que, sem `parecer_bateria` válido
(ausente, inexistente, hash errado, última linha COM BLOQUEADOR, URL), o fechamento é recusado, inclusive com relatório
"BATERIA NAO EXECUTADA" e saúde vazia; o mesmo vale para `parecer_instalacao`.

## Consequência

Segue-se o passe final independente sobre o escopo reduzido. Se ele tiver bloqueador, o I1.5 é adiado e o I1 não fecha
pela seção 5 do plano até nova versão.
