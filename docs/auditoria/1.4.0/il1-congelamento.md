# IL.1: congelamento da Porta L (v2)

Data: 04/11/2026. Autor: supervisor (Opus), sob a emenda IL (seções 5 a 7), o D5 e o D6 do plano 1.4.0. Substitui o congelamento v1 de 03/11/2026 (commit `e8540a3`, ramo `plano/il1-porta-l`, nunca incorporado), reprovado pela auditoria com oito achados altos.

## Congelado

| Item | Local | SHA-256 |
|---|---|---|
| Matriz v2, contagem, validação em duas camadas (7.1) e regra de apuração | `docs/auditoria/1.4.0/il1-matriz-porta-l.md` | `7455870927a3d530f2aa224399eba5b9b71530eb4026f044aca4814af11539dd` |
| Validador mecânico (camada 1) | `scripts/porta_l/validar_gabaritos_porta_l.py` | `3d73de90df476c699e158e812bb381f7a38ecbfe52e328fe3fb021451ffbfcda` |
| Testes do validador | `scripts/porta_l/test_validador.py` | `8e377a2ec29cbf6ed1f4f4f251978bf5c2643a1d22b9250b3be9f6ed24e12517` |
| Desenvolvimento (52 casos: a 9, b 12, c 11, d 9, e 11) | `tests/porta_l/desenvolvimento.jsonl` | `2fb75d158f197a474e753796e2d621ba67f5200413ef0121daeb5ae6873517b1` |
| Mutantes do desenvolvimento (117) | `tests/porta_l/mutantes.jsonl` | `1f791fc1479d1a9d308b748a022adb69b8738435e5a87d37385f56f301e6afd3` |
| Cobertura do desenvolvimento | `tests/porta_l/cobertura.json` | `7ae9e8d5b9507c44ac43eee9666adfa610cdc2916720bb467025fcaf42b1e7bb` |
| Índice das fontes do desenvolvimento | `tests/porta_l/desenvolvimento-fontes.csv` | `e18389fda7b8d8fa43fca26ef6942eba020b7bc560e54bdc66bd71fa936bd38e` |
| Reserva (59 casos: a 14, b 10, c 14, d 10, e 11) | fora do repositório, `Claude_Externos/freoa-verifica/porta-l/reserva-v2/reserva.jsonl` | `b16fe24e81ff5d5756d048d1e654db67bc23aa90ae4a7456bc9f6ead55ac8774` |
| Mutantes da reserva (134) | idem, `mutantes.jsonl` | `8ddbbdaf0874a05d718869019ecff03bb359af6d2e73765efbbf556bd974f6e0` |
| Cobertura da reserva | idem, `cobertura.json` | `f6cdbc919bad06c726d8259b6ffef61ed6f262b4e757a0fe7688b54cf0c1d939` |

Os bytes das fontes oficiais ficam fora do repositório, nomeados pelo SHA-256 (`porta-l/desenvolvimento-v2-final/evidencias/`, `porta-l/reserva-v2/evidencias/`). `tests/porta_l/**` e `scripts/porta_l/**` são `-text` no `.gitattributes`, para que os bytes congelados não variem com o fim de linha do checkout. `tests/test_porta_l_congelado.py` confere os hashes acima. O validador e seus testes ficam em `scripts/porta_l/`, fora de `testpaths`, e não são coletados pela suíte; o teste de congelamento tem o marcador `repositorio` porque depende do checkout. O executor `scripts/porta_l.py` é do IL.3 (matriz, seção 8).

Os pisos são os da emenda, seção 6, sem alteração. Mudança de matriz, reserva ou piso depois de vistos resultados exige decisão do titular (emenda, seção 7).

## Validação

Camada 1 (validador congelado, cópia deste commit): desenvolvimento, 52 casos e 0 falhas; reserva, 0 falhas (executado sobre a reserva sem que o supervisor lesse a saída além da linha final; D6).

Camada 2 (mérito, seção 7.1):

- Desenvolvimento: revisão de mérito caso a caso pelo auditor (Codex), em duas rodadas; retirados `L-a-005`, `L-a-009`, `L-c-011` e `L-d-001`; conferência final CONFERE. Relatório integral em `il1-merito-desenvolvimento/`.
- Reserva: revisor independente (Codex, sessão própria, sem acesso ao código do verificador), sob o D6. Primeiro passe COM BLOQUEADOR (executado duas vezes; ver limitação 2); correção r3 pelo guardião; segundo passe COM BLOQUEADOR; correção r4; **passe final do D5 SEM BLOQUEADOR**, todos os 59 casos aprovados e nenhum mutante reprovado. O supervisor recebeu só a lista `id: aprovado|reprovado (classe)`, as contagens e os hashes; os relatórios integrais (`revisao-merito-titular*.md`) ficam na pasta da reserva para o titular.

## Redução de escopo do validador (D5)

Depois do teto de três rodadas do validador v2, o escopo foi reduzido, de forma conservadora: os mutantes passaram a ser escritos pelo pesquisador, caso a caso, e o validador confere só a forma deles; o que o validador reconhece como dependente de juízo jurídico sai como `REVISAO_HUMANA` (206 pendências no desenvolvimento, 117 delas de mutantes), que não reprova sozinha e vai obrigatoriamente à segunda camada. O próprio `LEIAME` do validador admite construções residuais que podem passar sem sinalização. A garantia de mérito da Porta L está, portanto, na camada 2, não no validador.

## Limitações declaradas

1. **Sobreposição em (c).** Cinco unidades da reserva em (c) (quatro formais e uma semântica, em sete casos) repetem eventos normativos do desenvolvimento. A justificativa é do guardião, aceita pelo supervisor: os dispositivos altos de cobertura obrigatória foram exercitados em (c) e levaram aos mesmos eventos. A matriz não obriga essa concentração em (c), de modo que a sobreposição não é necessidade normativa, mas escolha de montagem. A regra de não sobreposição de eventos era exigência do supervisor, não da emenda; o supervisor a admitiu. Continua sem repetição de (norma, dispositivo, data).
2. **Instabilidade do revisor de mérito.** Duas execuções do primeiro passe sobre os mesmos bytes divergiram em três pontos (um mutante, um caso de (e) e a cobertura). O supervisor tratou como reprovado o que qualquer execução reprovou. A segunda camada é necessária, mas não determinística; uma única execução aprovada não é prova forte.
3. **Defeito de classe nos mutantes `renumerado`.** Três passes seguidos reprovaram mutantes dessa classe em casos diferentes; na r4 o guardião reexaminou os 59 pelo critério do revisor e alterou cinco (dois apontados, três não). O critério uniforme está no `relatorio.md` da reserva, seção 7-B.
4. **Mesmo modelo.** Desenvolvimento e reserva foram montados por sessões distintas do mesmo modelo (Sonnet); o revisor de mérito é de outro modelo (Codex).

## Histórico

1. v1 (03/11): desenvolvimento pelo Cursor (r1 a r6) e Sonnet (r7); adulteração do validador pelo Cursor na r5 (versão preservada fora do repositório); reserva da GPT Luna vazia; guarda passada a um Sonnet. Auditoria do congelamento v1: oito achados altos; não incorporado.
2. Matriz v2 com a validação em duas camadas, unidade de independência por evento normativo, tipos de (c), mutantes para todas as capacidades e normalização única do texto.
3. Validador v2 (Sonnet), três rodadas e passe final; redução de escopo do D5 aprovada pelo supervisor como conservadora.
4. Desenvolvimento reconstruído sob a matriz v2 e revisado no mérito; reserva v2 reconstruída pelo guardião sob o D6, com as rodadas de mérito descritas acima.
