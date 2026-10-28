# PR #10 — teto do D5 atingido; redução de escopo

Data: 28/10/2026. Autor: supervisor (Opus), sob o D5 do plano 1.4.0.

## Fato

A rodada 3 do Codex sobre `e793e0b` terminou COM BLOQUEADOR:

- B1: título canônico fragmentado (`RELAT<br>ÓRIO`) é absorvido no bloco da ementa e deixa vincular ementa
  citada no relatório.
- B2: vírgula como terminador faz intervalo incompleto (`29/09/2026, (a 06/10)`) recuar para data única.
- I1: ZIP64 com setor extensível faz o percurso manual e o `zipfile` lerem diretórios diferentes.
- I2: comentário HTML elimina vínculos legítimos.
- M1: campos de disco ignorados.

As três rodadas mostram o mesmo padrão: cada correção da leitura estrutural do texto abre nova
forma de delimitação ambígua. O defeito é do método (provar o julgamento pela estrutura de um HTML
livre), não de uma regex.

## Decisão (D5: reduz-se o escopo; o teto não equivale a aprovação)

1. O texto da íntegra deixa de ser interpretado para vincular. Saem a fórmula de abertura, a
   sessão, a ementa própria e a visão textual estrutural. O vínculo passa a exigir identidade de
   metadados (registro, cadeia de classe idêntica, número, data de publicação), unicidade dupla
   (no acervo e nos metadados do dia) e, como filtro só negativo, a presença da ementa do espelho
   no texto normalizado.
2. O leitor do ZIP aceita só a disposição estrita: sem ZIP64, disco único, EOCD nos últimos 22
   bytes sem comentário, diretório central imediatamente antes do EOCD, membros contíguos desde o
   byte 0. Fora disso, o recurso é recusado. Com isso o percurso manual e o `zipfile` só podem ler
   o mesmo diretório.
3. Saem do PR #10 e passam a I2.6: segmentação tipada (D1) e ligação ao acervo (captura pelo
   transporte, `decision_document`, cobertura, snapshot).
4. O PR #10 reduzido vai a um passe final independente (Codex, sessão nova). Se esse passe tiver
   bloqueador, o I1.2 é adiado inteiro para I2, com registro no manifesto de aceite e no rótulo da
   1.4.0a1.

## Interpretação do teto

O D5 fala em "3 rodadas por incremento". O supervisor conta o teto por delta submetido (PR), como a
sessão anterior já fazia: o PR #9 (plano) e o PR #10 (código) tiveram três rodadas cada. A leitura
literal (por incremento I1) esgotaria I1 antes de I1.4, I1.5 e S0 serem auditados. Questão aberta
para o titular.

## Perda aceita

Vínculos legítimos com cadeia de classe não idêntica (`AgInt` nos metadados para `AgInt nos EDcl no
REsp` no espelho) deixam de vincular e são contados (`classe_nao_identica`). A cobertura cai; a
confirmação indevida, não.
