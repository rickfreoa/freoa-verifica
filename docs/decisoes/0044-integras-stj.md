# 0044 — Íntegras do STJ

Estado: aceita para o parser; ligação ao acervo pendente (1.4.0).

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
   normalizados, até 400 conferidos) reproduzida na ementa PRÓPRIA da íntegra: o bloco que vai do
   marcador `EMENTA` da abertura até o título seguinte (RELATÓRIO, VOTO, ACÓRDÃO, DECISÃO ou PARECER).
   Ocorrência posterior (ementa citada como precedente) nunca vale; sem título que feche o bloco, o
   documento fica pendente (`sem_prova_do_julgamento`). Órgão e sessão sozinhos
   não individualizam o julgamento (Codex, 2ª rodada, B1). A fórmula, as datas e os marcadores são lidos numa visão textual (quebras `<br>`, `<p>`, CR/LF
   e espaços Unicode viram quebra ou espaço único; entidades como `&nbsp;` são resolvidas), sem
   alterar o texto bruto nem o hash. A fórmula só vale na abertura, o trecho que antecede o
   marcador `EMENTA` (até 3.000 caracteres; sem o marcador não há abertura); citação em outro
   ponto do texto não conta nem repete a fórmula. Sem a fórmula na abertura, ou com mais de uma, o
   documento fica pendente (`sem_prova_do_julgamento`). A sessão é uma data (`de DD/MM/AAAA`) ou um intervalo completo
   (`de DD/MM/AAAA a DD/MM/AAAA`); intervalo incompleto (`de X a`, `a 06/10`), data inexistente no
   calendário (também a do espelho) ou fim anterior ao início não recuam para o dia inicial e
   deixam o documento pendente pelo mesmo motivo, sem vincular. Candidatos sem compatibilidade de
   órgão e data dão `julgamento_divergente_do_espelho`. Nunca há recuo para o único espelho
   do registro.
4. Mais de um espelho com a mesma prova, ou duas íntegras do dia para a mesma identidade:
   `ambiguous`, sem escolha. Mesmo `SeqDocumento` com metadados divergentes: todos
   descartados; duplicata idêntica é contada.
5. Inteiro teor por declaração da coleção oficial (0038), nunca por comprimento. O hash da
   prova é dos bytes brutos do arquivo no ZIP. Texto que não é UTF-8 estrito (sem BOM alternativo) descarta o documento
   (`texto_nao_utf8`, contado), sem redecodificação; os metadados, que são corpo de resposta, passam
   pela interpretação única (0061 a 0064) e só UTF-8 vale (`metadados_nao_utf8` recusa o recurso); a limpeza de `<br>` serve só à leitura.
6. Contrato da fonte: item de metadados que não é objeto recusa o recurso; tipo de documento
   desconhecido tem motivo próprio, nunca é contado como monocrática. Decisões
   monocráticas ficam fora nesta versão e são contadas.
7. Limites do ZIP: 5.000 entradas, 200 MB lidos, 5 MB por entrada, razão 100. O fluxo é
   lido pelo cabeçalho local e descompactado sem confiar em tamanho ou CRC declarados
   (STORED exige tamanhos iguais; DEFLATE exige fim de fluxo sem sobra; tamanho e CRC reais
   devem coincidir com os declarados). O cabeçalho local é confrontado com o diretório central:
   flags, método, CRC, tamanhos, extra ZIP64 (tamanho original e comprimido; a sentinela
   0xFFFFFFFF sem extra diverge) e, com o bit 3, o data descriptor (com ou sem assinatura, 4 ou 8
   bytes por tamanho). Divergência recusa só aquela entrada, com motivo contado nos descartes
   (`zip_local_flags_divergente`, `zip_local_metodo_divergente`, `zip_local_crc_divergente`,
   `zip_local_tamanho_divergente`, `zip_zip64_divergente`, `zip_descriptor_divergente`,
   `zip_local_extra_invalido`). Nome fora de `[0-9]+.txt`, diretório, NUL no nome,
   nome local divergente do central, entrada cifrada ou método não suportado recusam o
   recurso inteiro. Os limites de entradas (5.000) e de tamanho do diretório central (2 MiB) são
   conferidos no EOCD (e no EOCD64) antes de instanciar `ZipFile` (`zip_entradas_excedidas`,
   `zip_diretorio_excedido`). Extra ZIP64 do diretório central, quando existe, tem de coincidir
   com os campos comuns e com o local, mesmo sem sentinela nos campos de 32 bits
   (`zip_zip64_divergente`).
8. A cobertura textual do ZIP é parcial; `texto_ausente_no_zip` é descarte esperado e não
   pode ser lido como falha da fonte.
9. Textos órfãos são contados em `Resultado.orfaos` e nunca vinculam: `texto_sem_metadado` (Seq do
   ZIP sem item nos metadados), `texto_sem_espelho` (acórdão cujo registro, classe e número não têm
   nenhum espelho candidato; também contado em `descartes` por documento) e, para entrada recusada
   do ZIP sem metadado, o motivo da recusa. Documento descartado cedo pelo metadado (tipo, registro,
   processo) cujo texto foi recusado pelo ZIP também tem o motivo da recusa em `orfaos`. Texto com candidato, mas sem prova do julgamento, fica
   nos descartes (`sem_prova_do_julgamento`, `julgamento_divergente_do_espelho`).

## Ligação pendente (1.4.0)

Capturar ZIP e metadados pelo transporte comum (recibo com sha256), gravar
`decision_document(kind='inteiro_teor', capture_id=<zip>)` na decisão do espelho, janela
padrão de 90 dias com checkpoint por recurso (0039), atualizar `coverage` do conector e
FONTES.md, e só então novo snapshot, após auditoria independente.

## Corrigidos antes da ligação (Codex, 2ª rodada: I2, I3, M1)

A delimitação da abertura, o intervalo e o calendário (I2), o confronto do cabeçalho local, do
descritor e do extra ZIP64 com o diretório central (I3) e a contagem de textos órfãos (M1) estão
nos itens 3, 7 e 9. A ligação ao acervo segue pendente de auditoria independente.

## Limites conhecidos

- A prova do julgamento é a fórmula de abertura; sessões presenciais e textos antigos podem
  usar outra redação, ou trazer a ementa antes do acórdão, e ficarão pendentes até serem medidos.
- A sessão não é conferida contra dia útil nem contra o intervalo de aquisição pedido; só contra o
  calendário e a data do espelho.
- Espelhos duplicados no índice com chaves distintas produzem `ambiguous`; deduplicar antes
  da ligação.
- Republicação com sha256 diferente deve ser tratada como conflito pelo chamador.
