# 0036 - Precedentes qualificados do STJ e súmulas do STF no índice local

Data: 18/10/2026. Marco P5.

`fv sync stj` passa a ingerir `Temas.csv` e `Processos.csv` (CKAN `precedentes-qualificados`) e `fv sync stf` passa a ingerir o sumário e as páginas de súmula e súmula vinculante do portal. Tudo vai ao índice já usado por `pesquisar_jurisprudencia` (FTS do STJ; tabelas `decision` e FTS de decisões para ambos), sem nova tabela e sem novo rótulo.

- Autoridade: nenhuma regra de `authority.py` muda. Tema (repetitivo) e IAC chegam com classe "Tema Repetitivo"/"IAC" e saem B; súmula e súmula vinculante do STF saem A.
- Situação não rebaixa rótulo. Tema cancelado ou revisado e súmula cancelada ou superada mantêm o rótulo da espécie, com a situação no texto indexado e em metadados. O rótulo mede espécie, não vigência; quem cita deve ler a situação. Alterar isso exige nova regra e nova versão de `RULES_VERSION`.
- Prova: o CSV (ou a página) capturado com hash é o documento; o texto indexado deriva dele. Exceção declarada: os processos paradigma de um tema vêm de `Processos.csv`, captura distinta registrada em `_processos_sha256`.
- Falha: recurso ausente, página fora do formato ou erro de rede viram `unavailable(motivo)` no `sync_state`; nenhum sumário vazio é aceito como "sem súmulas".
- Escopo STJ: só `Tema` e `IAC`. Controvérsia (ainda não é precedente), SIRDR e PUIL ficam de fora até decisão própria.
- A chave `stj_precedentes_qualificados` do corpus semente passa de `false` para `true`.
