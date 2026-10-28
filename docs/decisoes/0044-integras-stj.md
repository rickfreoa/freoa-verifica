# 0044 — Íntegras do STJ

Estado: aceita para o parser; segmentação e ligação ao acervo em I2.6.

## Contexto

O portal de dados abertos do STJ publica o pacote
`integras-de-decisoes-terminativas-e-acordaos-do-diario-da-justica` em pares diários:
`metadadosAAAAMMDD.json` e `textosAAAAMMDD.zip`, este com `<SeqDocumento>.txt` em UTF-8 e
quebras `<br>`. Amostra de 08/10/2026: 2.004 metadados (591 acórdãos), 37 textos no ZIP,
13 deles acórdãos. Os metadados não trazem órgão julgador, e `recurso` traz só o recurso
externo (`AgInt` + `REsp 123` pode ser AgInt nos EDcl no REsp). O texto é HTML livre (`<br>`,
entidades, comentários): três rodadas de auditoria mostraram que provar o julgamento pela
estrutura desse texto (fórmula de abertura, sessão, ementa própria) abre, a cada correção, nova
forma de delimitação ambígua. O vínculo deixou de interpretar o texto (redução de escopo do PR #10,
`docs/auditoria/1.4.0/pr10-reducao-escopo.md`).

## Decisão

1. Recorte por vínculo, não por órgão: a íntegra só é gravada quando vincula a um único
   espelho já presente no acervo, que carrega o órgão do recorte. O órgão vem sempre do espelho;
   nunca do texto nem do ministro.
2. A classe dos metadados é informação parcial, mas a cadeia tem de ser idêntica: recurso dos
   metadados (se houver) + classe base de `processo` == classe do espelho, nos mesmos tokens e na
   mesma ordem, sem graus intermediários livres (conectivos como `no`, `nos` e `em` são ignorados).
   `AgInt` nos metadados não vincula a `AgInt nos EDcl no REsp` no espelho.
3. Vínculo por identidade de metadados, sem ler o estrutural do texto. Candidato é o espelho do
   acervo que satisfaz todas as condições: (a) `numeroRegistro` igual; (b) cadeia de classe idêntica
   (item 2); (c) número do processo igual; (d) data de publicação do espelho, normalizada para ISO,
   igual a `dataPublicacao` dos metadados. O espelho do STJ traz a publicação como
   `DJEN       DATA:08/10/2026` ou `DJE        DATA:27/09/2024` (sigla, espaços de preenchimento, `DATA:`
   e dia/mês/ano), os metadados como `AAAA-MM-DD`. Só esses formatos, válidos no calendário, são
   normalizados; qualquer outro valor torna o espelho não candidato (`data_publicacao_espelho_ilegivel`)
   e nunca recua. Metadado ilegível: `data_publicacao_metadado_ilegivel`.
   Unicidade dupla: (i) exatamente um candidato no acervo; (ii) exatamente um acórdão nos metadados do
   dia com aquele `numeroRegistro` (qualquer classe; duplicata idêntica conta uma vez; o acórdão sem
   texto ou descartado também conta). Mais de um candidato: `ambiguous`. Falha de (ii): todas as
   íntegras daquele registro no dia ficam `ambiguous`, sem escolha. Zero candidatos com espelhos do
   registro no acervo: motivo específico, do espelho que foi mais longe (`classe_nao_identica`,
   `numero_divergente`, `data_publicacao_espelho_ilegivel`, `data_publicacao_divergente`), contado nos
   descartes. Sem espelho algum do registro: `texto_sem_espelho` em `orfaos`.
   A data de julgamento e o órgão do espelho não entram no vínculo, e o texto não é lido para nenhum
   dos dois.
   Filtro só negativo: a ementa do espelho (ao menos 120 caracteres normalizados; os primeiros 400 são
   conferidos) tem de ocorrer no texto normalizado; ausente, `ementa_ausente_no_texto`, sem vínculo. É
   condição necessária, nunca suficiente. A normalização é única, simples e idêntica nos dois lados:
   toda sequência `<...>` sem `<`/`>` internos vira espaço; entidades HTML são decodificadas uma vez;
   invisíveis (categoria Unicode Cf) e diacríticos saem (NFKD); casefold; espaços colapsados. Por ser fraca,
   só pode produzir falso negativo (perde vínculo); nunca cria vínculo, que depende dos metadados. Riscos
   residuais em "Limites conhecidos".
4. Duas íntegras do dia para o mesmo registro são `ambiguous`, sem escolha (item 3, unicidade (ii)).
   Mesmo `SeqDocumento` com metadados divergentes: todos descartados; duplicata idêntica é contada.
5. Inteiro teor por declaração da coleção oficial (0038), nunca por comprimento. O hash da
   prova é dos bytes brutos do arquivo no ZIP. Texto que não é UTF-8 estrito (sem BOM alternativo) descarta o documento
   (`texto_nao_utf8`, contado), sem redecodificação; os metadados, que são corpo de resposta, passam
   pela interpretação única (0061 a 0064) e só UTF-8 vale (`metadados_nao_utf8` recusa o recurso); `Integra.texto_limpo` (`<br>` em linhas) serve só à leitura humana.
6. Contrato da fonte: item de metadados que não é objeto recusa o recurso; tipo de documento
   desconhecido tem motivo próprio, nunca é contado como monocrática. Decisões
   monocráticas ficam fora nesta versão e são contadas.
7. ZIP estrito e limites. O leitor aceita uma só disposição, conferida sobre os bytes antes de instanciar
   `ZipFile` (que aloca um `ZipInfo` por registro); qualquer outra recusa o recurso inteiro com motivo
   contado `zip_estrutura_nao_suportada:<sub>`: (a) EOCD exatamente nos últimos 22 bytes, assinatura
   correta, comentário de comprimento 0 (`eocd_nao_final`: comentário, rabo ou ZIP concatenado); (b) sem
   ZIP64 (`zip64`): nenhuma assinatura de EOCD64 ou de localizador, nenhuma sentinela 0xFFFF/0xFFFFFFFF
   no EOCD ou nos registros central e local, nenhum extra de id 0x0001; extra malformado
   (`extra_invalido`); (c) disco único (`multidisco`): disco do EOCD e do diretório 0, entradas no disco
   iguais ao total, disco inicial de cada registro central 0; (d) diretório imediatamente antes do EOCD
   (`diretorio_nao_adjacente_ao_eocd`: deslocamento + tamanho == bytes anteriores ao EOCD); (e) primeiro
   cabeçalho local no byte 0 e cada membro (cabeçalho local, nome, extra, dados, descritor se bit 3)
   começando onde o anterior terminou, na ordem dos deslocamentos do diretório, o último terminando no
   diretório (`membros_nao_contiguos`). Com isso o percurso feito aqui e o do `zipfile` só podem ler o mesmo
   diretório, e os deslocamentos de um são conferidos contra os do outro (`zip_diretorio_divergente`).
   Limites: 5.000 entradas, 2 MiB de diretório, 200 MB lidos, 5 MB por entrada, razão 100;
   contagem e tamanho declarados são reconciliados com os percorridos (`zip_entradas_excedidas`,
   `zip_diretorio_excedido`, `zip_diretorio_divergente`). O limite de 2 MiB é restrição de compatibilidade e
   não foi validado contra pacotes oficiais; 5.000 nomes `<seq>.txt` ocupam cerca de 0,4 MB. A disposição
   estrita também não foi confrontada com um ZIP oficial real (a fixture é sintética): se o pacote oficial
   usar ZIP64, comentário ou outra disposição, o recurso será recusado, nunca lido de outro modo.
   O fluxo é lido pelo cabeçalho local e descompactado sem confiar em tamanho ou CRC declarados
   (STORED exige tamanhos iguais; DEFLATE exige fim de fluxo sem sobra; tamanho e CRC reais
   devem coincidir com os declarados). O cabeçalho local é confrontado com o diretório central:
   flags, método, CRC, tamanhos e, com o bit 3, o data descriptor (com ou sem assinatura, 4 bytes por
   campo). Divergência recusa só aquela entrada, com motivo contado nos descartes
   (`zip_local_flags_divergente`, `zip_local_metodo_divergente`, `zip_local_crc_divergente`,
   `zip_local_tamanho_divergente`, `zip_descriptor_divergente`). Nome fora de `[0-9]+.txt`, diretório, NUL
   no nome, nome local divergente do central, entrada cifrada ou método não suportado recusam o recurso
   inteiro.
8. A cobertura textual do ZIP é parcial; `texto_ausente_no_zip` é descarte esperado e não
   pode ser lido como falha da fonte.
9. Textos órfãos são contados em `Resultado.orfaos` e nunca vinculam: `texto_sem_metadado` (Seq do
   ZIP sem item nos metadados), `texto_sem_espelho` (acórdão cujo registro, classe e número não têm
   nenhum espelho no acervo; também contado em `descartes` por documento) e, para entrada recusada
   do ZIP sem metadado, o motivo da recusa. Documento descartado cedo pelo metadado (tipo, registro,
   processo) cujo texto foi recusado pelo ZIP também tem o motivo da recusa em `orfaos`. Texto cujo registro tem espelhos, mas nenhum candidato, fica
   nos descartes com o motivo específico do item 3; texto com candidato único mas sem a ementa do espelho,
   em `ementa_ausente_no_texto`.

## Fora desta decisão (I2.6)

Segmentação tipada do texto (D1) e ligação ao acervo: capturar ZIP e metadados pelo transporte comum
(recibo com sha256), gravar `decision_document(kind='inteiro_teor', capture_id=<zip>)` na decisão do
espelho, janela padrão de 90 dias com checkpoint por recurso (0039), atualizar `coverage` do conector e
FONTES.md, e só então novo snapshot, após auditoria independente.

## Histórico do método

O PR #10 passou por três rodadas do Codex (B1/B2 de ementa própria, sessão e terminadores; ZIP64) sem
chegar a aprovação. Pelo D5 do plano 1.4.0 o escopo foi reduzido: o vínculo passou a identidade de
metadados com filtro negativo da ementa, e o ZIP à disposição estrita (itens 3 e 7). Passe final
independente (Codex, sessão nova) sobre o PR reduzido; com bloqueador, o I1.2 é adiado inteiro para I2.

## Limites conhecidos

- Perda aceita: vínculos legítimos com cadeia de classe não idêntica (`AgInt` nos metadados para
  `AgInt nos EDcl no REsp` no espelho) não vinculam e são contados (`classe_nao_identica`). A cobertura
  cai; a confirmação indevida, não.
- Risco residual: metadado oficial errado (registro, processo ou data de publicação que identifiquem outro
  espelho) vincula o texto ao espelho errado. Mitigado pelo filtro da ementa (a ementa do espelho tem de
  estar no texto) e pela unicidade dupla (um candidato no acervo e um acórdão do registro no dia), não
  eliminado: texto que só cita a ementa de outro julgamento, com metadados que identifiquem o espelho,
  passa o filtro. A segmentação tipada que distingue ementa própria de citação fica para a I2.6.
- A relação entre a data de publicação do espelho (`DJEN`/`DJE`) e a de `dataPublicacao` dos metadados do
  pacote de íntegras não foi medida contra pares reais; se divergirem de modo sistemático (por exemplo,
  disponibilização × publicação), a cobertura cai a zero sem vínculo indevido (`data_publicacao_divergente`).
- Espelhos duplicados no índice com chaves distintas produzem `ambiguous`; deduplicar antes
  da ligação.
- Republicação com sha256 diferente deve ser tratada como conflito pelo chamador.
