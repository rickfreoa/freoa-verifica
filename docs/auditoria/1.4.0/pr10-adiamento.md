# PR #10 — passe final com bloqueador; I1.2 adiado para I2

Data: 28/10/2026. Autor: supervisor (Opus), sob o D5 do plano 1.4.0 e o item 4 de
`pr10-reducao-escopo.md`.

## Fato

O passe final independente do Codex sobre `5a0bb1f` (escopo reduzido) terminou COM BLOQUEADOR:

- B1: com candidato único pelos metadados, a ementa do espelho citada em qualquer ponto do texto passa
  o filtro negativo e o vínculo se conclui com o documento de outro julgamento (prova da r1 reproduzida).
- B1, segunda forma: o campo `recurso` dos metadados omite graus intermediários (decisão 0044). Para
  um AgInt nos EDcl no REsp, os metadados dizem `AgInt` + `REsp`; a igualdade estrita de cadeia descarta
  o espelho correto e deixa o espelho do AgInt no REsp como candidato único. A unicidade depois do filtro
  não prova identidade.
- I1: as regressões de B1 testam metadados divergentes, não o candidato único da prova original.
- I2: o gerador do setor extensível declara tamanho de EOCD64 que o `zipfile` 3.14 recusa; com a
  construção válida, o leitor estrito recusou todos os casos antes de criar `ZipInfo`.
- I3: o plano ainda lista a segmentação em I1.2.

## Decisão

1. O I1.2 é adiado inteiro para I2 (item I2.6). O PR #10 não é incorporado; o ramo fica como base.
2. A 1.4.0a1 sai sem íntegras do STJ, com o adiamento no manifesto de aceite e no rótulo.
3. A afirmação de `pr10-reducao-escopo.md` de que "a cobertura cai; a confirmação indevida, não" não
   se sustentou e fica superada por este registro.

## O que a I2.6 precisa resolver antes de código

- Identidade sem inferência: verificar na S0 se o conjunto de espelhos do STJ traz identificador do
  documento que case com `SeqDocumento` (ou outro campo de ligação oficial). Se existir, o vínculo é por
  identidade documental e o texto não precisa ser lido.
- Sem esse campo: candidatos são todos os espelhos do registro e número cuja cadeia começa pelo recurso
  externo e termina pela classe base; mais de um candidato é `ambiguous`, sempre. A ementa só conta
  quando localizada na ementa própria, o que exige a segmentação tipada (D1) auditada antes.
- O que já está aprovado nas provas e deve ser preservado: leitor de ZIP estrito (sem ZIP64, disco único,
  disposição contígua), limites e confronto local × central, normalização de datas DJE/DJEN.
- Regressões obrigatórias: a prova original da r1 com candidato único; o par AgInt no REsp × AgInt nos
  EDcl no REsp; o setor extensível com tamanho declarado válido para o 3.14.
