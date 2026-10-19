# 0044 — Íntegras do STJ

Estado: aceita para o parser; ligação ao acervo pendente (1.3.0).

## Contexto

O portal de dados abertos do STJ publica o pacote
`integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica` em pares diários:
`metadadosAAAAMMDD.json` e `textosAAAAMMDD.zip`, este com `<SeqDocumento>.txt` em UTF-8 e
quebras `<br>`. Amostra de 08/10/2026: 2.004 metadados (591 acórdãos), 37 textos no ZIP,
13 deles acórdãos. Os metadados não trazem órgão julgador, e `recurso` traz só o recurso
externo (`AgInt` + `REsp 123` pode ser AgInt nos EDcl no REsp). O texto do acórdão abre com
fórmula fixa: "acordam os Ministros da QUARTA TURMA do Superior Tribunal de Justiça, em
Sessão Virtual de 29/09/2026 a 06/10/2026".

## Decisão

1. Recorte por vínculo, não por órgão: a íntegra só é gravada quando vincula a um único
   espelho já presente no acervo, que carrega o órgão do recorte. O órgão nunca é inferido
   pelo ministro.
2. A classe dos metadados é informação parcial. São candidatos os espelhos do mesmo
   registro e número cuja cadeia começa pelo recurso externo e termina pela classe base,
   com graus intermediários livres.
3. Entre os candidatos, o vínculo exige prova do julgamento individual lida do texto: órgão
   igual ao do espelho (abreviações CE, S1, S2, S3 normalizadas) e data de julgamento do
   espelho dentro da sessão declarada e a ementa do espelho (ao menos 120 caracteres
   normalizados, até 400 conferidos) reproduzida no texto da íntegra. Órgão e sessão sozinhos
   não individualizam o julgamento (Codex, 2ª rodada, B1). Sem a fórmula de abertura, ou com mais de uma, o
   documento fica pendente (`sem_prova_do_julgamento`); candidatos sem compatibilidade de
   órgão e data dão `julgamento_divergente_do_espelho`. Nunca há recuo para o único espelho
   do registro.
4. Mais de um espelho com a mesma prova, ou duas íntegras do dia para a mesma identidade:
   `ambiguous`, sem escolha. Mesmo `SeqDocumento` com metadados divergentes: todos
   descartados; duplicata idêntica é contada.
5. Inteiro teor por declaração da coleção oficial (0038), nunca por comprimento. O hash da
   prova é dos bytes brutos do arquivo no ZIP. Texto que não é UTF-8 descarta o documento
   (`texto_nao_utf8`, contado), sem redecodificação; a limpeza de `<br>` serve só à leitura.
6. Contrato da fonte: item de metadados que não é objeto recusa o recurso; tipo de documento
   desconhecido tem motivo próprio, nunca é contado como monocrática. Decisões
   monocráticas ficam fora nesta versão e são contadas.
7. Limites do ZIP: 5.000 entradas, 200 MB lidos, 5 MB por entrada, razão 100. O fluxo é
   lido pelo cabeçalho local e descompactado sem confiar em tamanho ou CRC declarados
   (STORED exige tamanhos iguais; DEFLATE exige fim de fluxo sem sobra; tamanho e CRC reais
   devem coincidir com os declarados). Nome fora de `[0-9]+.txt`, diretório, NUL no nome,
   nome local divergente do central, entrada cifrada ou método não suportado recusam o
   recurso inteiro.
8. A cobertura textual do ZIP é parcial; `texto_ausente_no_zip` é descarte esperado e não
   pode ser lido como falha da fonte.

## Ligação pendente (1.3.0)

Capturar ZIP e metadados pelo transporte comum (recibo com sha256), gravar
`decision_document(kind='inteiro_teor', capture_id=<zip>)` na decisão do espelho, janela
padrão de 90 dias com checkpoint por recurso (0039), atualizar `coverage` do conector e
FONTES.md, e só então novo snapshot, após auditoria independente.

## Abertos antes da ligação (Codex, 2ª rodada)

- I2: a fórmula de abertura é procurada nos 3.000 primeiros caracteres sem delimitar a
  abertura efetiva; intervalo incompleto recua para data única; datas não são validadas
  pelo calendário.
- I3: a leitura manual não confronta método, flags, CRC e tamanhos do cabeçalho local nem o
  data descriptor e o extra ZIP64 com o diretório central.
- M1: textos do ZIP sem metadado não são contados.

## Limites conhecidos

- A prova do julgamento é a fórmula de abertura; sessões presenciais e textos antigos podem
  usar outra redação e ficarão pendentes até serem medidos.
- Espelhos duplicados no índice com chaves distintas produzem `ambiguous`; deduplicar antes
  da ligação.
- Republicação com sha256 diferente deve ser tratada como conflito pelo chamador.
