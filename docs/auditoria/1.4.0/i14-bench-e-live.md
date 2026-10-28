# I1.4 — bench e bateria ao vivo (linha de base da 1.3.0)

Executor: supervisor (Opus), no notebook Windows do titular, IP brasileiro. Data: 27/10/2026.
Revisão 2 (após parecer do Codex sobre o PR #12): p95 corrigido, escopo das comparações declarado,
afirmações causais retiradas, evidências anexadas.

## Bateria ao vivo (`pytest -q -m live`)

Código: `7cf2b7c` (idêntico em código a `6a21865`; o delta é só `docs/PLANO-1.4.0.md`).
Evidências: `live-1.3.0-resumo.txt` (linhas de resultado e fecho do pytest, sem caminhos de máquina) e
`live-1.3.0-saude-fontes.json` (relatório do arnês, decisão 0054).
Resultado do pytest: 27 aprovados, 3 xfail, 4 falhas, em 128,09 s (linha final do resumo).

| Fonte | Resultado | Estado no arnês |
|---|---|---|
| BCB, CVM colegiado, CVM normas, DataJud, Senado, STF, STJ, TJDFT | aprovados | `ok` |
| TCU (positivo e documento) | aprovados | — |
| TJSP (positivo, negativo, documento) | xfail | `unavailable`, `ambiental_desafio:desafio_captcha`, com evidência |
| Planalto (positivo, negativo, documento) | falha | `regressao`, categoria `recusa_identificado`, motivo `recusa_identificado_planalto` |
| TCU (negativo) | falha | `regressao`, motivo `tcu_busca_incompleta_limite_de_varredura` |

Leitura: o arnês classifica as quatro falhas como `regressao`, e assim ficam. O traceback mostra que o
conector levantou indisponibilidade tipada (recusa do UA identificado no Planalto, decisão 0048; varredura
declarada incompleta no TCU), mas esta execução não isola a causa, e o registro não afirma que não sejam
regressões. No positivo e no documento do Planalto, o traceback mostra antes um `ConnectionResetError`;
uma execução não permite dizer se é transitório. O arnês não foi alargado: converter essas falhas em
xfail esconderia que a legislação está congelada desde a 1.3.0. Planalto e TCU ficam fora do escopo de I1
(a cascata Planalto é o I3.6) e entram no fechamento como falhas fora do escopo, a declarar no manifesto.

Defeito do arnês encontrado nesta leitura: `inicio` sai `null` no `saude-fontes.json`, porque o
`pytest_sessionstart` de `tests/live/conftest.py` não é chamado num conftest de subdiretório. Fica para
correção antes da bateria de fechamento do I1 (etapa 8).

## Bench (conjunto-ouro, `docs/auditoria/comparativo-120/gold.jsonl`)

Produto: 1.3.0 instalada pelo instalador oficial (attestation verificada, snapshot `b6921f68…`), com consulta
ao vivo onde o produto consulta. Comando: `python scripts/comparativo_ouro.py gold.jsonl freoa_raw.jsonl`.
Saída: `bench-1.3.0/freoa_raw.jsonl`. Foram executados os 44 casos do arquivo; o comparativo original pontua
42 (exclui F5 e F6, ver o README do comparativo).

Comparação com a 1.2.0 (`comparativo-120/freoa_raw.jsonl`), numa projeção declarada: para casos de
verificação, `status` e os estados das dimensões `identity` e `temporal`; para buscas, `status` e os
identificadores (`classe_numero` ou `id`) do top-5, em ordem. `segundos` é ignorado. Fora dessa projeção os
JSONs diferem em 16 casos (identificadores de captura, metadados de fontes), o que não é avaliado aqui.

| Medida | 1.3.0 |
|---|---|
| Casos iguais na projeção | 41 de 44 |
| Casos não temáticos alterados na projeção | 0 de 36 |
| Temáticos com top-5 alterado | 3 (D8, E4, E5): sai um acórdão do TJDFT e entra outro documento em cada caso |
| Itens novos no top-5, juiz cego (`bench-1.3.0/juiz-cego.json`) | E4: sim; D8: parcial; E5: parcial |
| Negativos plantados | nenhum com confirmação positiva nem com outro documento entregue como o pedido (conferido no jsonl) |
| Tempo por consulta (44 valores; mediana; p95 pelo posto mais próximo, ⌈0,95·44⌉ = 42º) | p50 2,1 s; p95 21,1 s; máximo 31,4 s |
| Consultas acima de 20 s | D7 (23,2 s), E4 (21,1 s), E5 (31,4 s) |

Leitura:

- A igualdade na projeção mostra que a 1.3.0 não mudou o resultado não temático da 1.2.0. Não é nova
  conferência de todas as identidades e capturas contra os originais.
- A ausência de confirmação indevida está demonstrada para os negativos plantados deste conjunto; não se
  estende além dele.
- As três mudanças temáticas coincidem com a saída de acórdãos do TJDFT, mas duas execuções não isolam a
  causa (busca ao vivo, ordem dos casos ou mudança no acervo).
- **O p95 de 21,1 s viola o piso do D4 (p95 ≤ 20 s em consulta federada).** O piso vale para a Porta A,
  medido sobre a avaliação estratificada; esta bateria não a substitui, mas sinaliza o risco.

Limites: o conjunto é o mesmo da 1.2.0 (sobreajuste declarado) e mede o acervo existente, não a pesquisa ampla
(plano, seção 1). Não autoriza desligar nada. O lado comparativo não foi refeito nesta rodada.
