# 0073 - Esquema de saída das ferramentas de paridade (C7) e das partes de `obter_decisao` (CH6)

Estado: aceita. Decisão do supervisor em 29/10/2026, sob o D5 (mudança de contrato público exige decisão formal) e
o requisito C7 de `docs/PARIDADE-1.4.md`, antes de qualquer código do I2.4. Revisão 3, depois dos pareceres do Codex
sobre o PR #21 (r1 e r2); revisão 4, redução de escopo pelo D5 depois do passe final com bloqueador (seção 8).

## Contexto

`docs/PARIDADE-1.4.md` fixou o que cada ferramenta de paridade entrega (I2.1). Dois pontos ficaram para decisão
formal: (a) a forma da resposta das cinco ferramentas novas, que entram no contrato 1 como `experimental` (C7);
(b) a forma da resposta de `obter_decisao` com `parte_idx` (CH6), que não pode alterar tipo, nulidade nem estados
de campo existente do contrato 1. No PR #13, a primeira rodada do Codex apontou LO2–LO4 e IJ6; a segunda e a
terceira, a forma de saída de CH6 (estado novo em campo fechado, depois colisão com o campo estável `parte`). Pelo
D5, o esquema de CH6 saiu daquele documento e veio para esta decisão (PARIDADE-1.4, seção 5).

## Decisão

### 1. Estágio e regra de promoção

1. `informativo_juridico`, `timeline_decisoes`, `listar_overruling_por_tema` e `listar_ramos_direito` entram no
   contrato 1 como **experimentais**, inteiras, na 1.4.0a2 (`listar_tribunais`: seção 8). São também
   experimentais os campos novos em ferramentas estáveis: `obter_decisao:particao`, `obter_decisao:alerta_situacao`,
   `pesquisar_jurisprudencia:itens[].alerta_situacao`, `pesquisar_jurisprudencia:resultados[].alerta_situacao` e
   `pesquisar_jurisprudencia:cobertura[].nao_filtraveis_por_ramo`.
2. Representação: ferramenta inteira por `"<ferramenta>:"` em `EXPERIMENTAL` de `freoa_verifica/contrato.py`. O
   comparador do teste de contrato (`tests/contrato/harness.py`) hoje só isenta caminho igual ou descendente por
   `.` ou `[]`; a implementação do I2.4 estende-o para que `"<ferramenta>:"` isente todo caminho da ferramenta, com
   teste negativo que prove (a) que todo campo das ferramentas novas fica isento e (b) que nenhum campo estável de
   outra ferramenta passa a ser isento.
3. Promoção a `stable`: respostas congeladas em `tests/contrato/esperado/` para os três adaptadores, casos de cada
   estado fechado, e nova decisão formal. Nenhuma promoção na 1.4.0a2.
4. Mudanças aditivas (regra 1 do contrato): `CONTRATO_VERSAO` continua "1". A seção 7 enfrenta a única com efeito
   sobre a navegação de uma ferramenta estável.

### 2. Envelope comum das ferramentas novas

| Campo | Tipo | Nulo | Significado |
|---|---|---|---|
| `status` | string | não | estado fechado, seção 3 |
| `itens` | array | não | itens principais (seção 4) |
| `total` | number | não | quantidade de `itens` desta página |
| `truncado` | bool | não | o `limite` cortou resultados |
| `cursor` | string | sim | próxima página; `null` sem mais páginas |
| `cobertura` | array | não | uma entrada por fonte, coleção ou tribunal considerado (seção 5) |
| `fontes_indisponiveis` | object | condicional | `{<fonte>: {motivo, categoria, evidencia_indisponibilidade?}}`, só em `parcial` e `indisponivel`; `categoria` segue a decisão 0045 (só com prova positiva; `null` sem prova) e `evidencia_indisponibilidade` aparece quando provada |
| `motivo` | string | condicional | só em `indisponivel` |

Listas auxiliares, quando a ferramenta as tem: `nao_classificadas` (`listar_overruling_por_tema`) e `informativos`
(`timeline_decisoes`, modo `recentes`). Chama-se **resultado** o conjunto de `itens` e das listas auxiliares.

Grafia: só português nos estados das ferramentas novas (`indisponivel`, nunca `unavailable`), para não ampliar a
inconsistência 1 do contrato. Exceção registrada à convenção das buscas do contrato 1: as ferramentas novas não
têm `resultados` sinônimo de `itens`.

### 3. Estados fechados das ferramentas novas (`status`)

A validação da entrada precede o estado: entrada fora do domínio, inclusive número CNJ com dígito verificador
inválido em `timeline_decisoes`, é `EntradaInvalida` (MCP: erro de ferramenta; REST: `problem+json` 4xx) e não produz
resposta com `status`. Os estados abaixo valem só para entrada válida.

**Fontes necessárias** são fixadas pela ferramenta, pelo modo e pelos filtros da chamada, **antes** de qualquer
consulta, pela tabela abaixo; uma fonte nunca deixa de ser necessária porque falhou. Para o estado, cada fonte
necessária está **lida** (consultada com sucesso: `resultado` `lida` ou `nao_confirmado_na_fonte` na `cobertura`) ou
**não lida** (falha, recusa ou `nao_consultada`, inclusive por modo offline), e toda fonte necessária não lida
aparece em `fontes_indisponiveis` com o motivo (`offline`, quando for o caso).

| Ferramenta e modo | Fontes necessárias |
|---|---|
| `informativo_juridico` | a coleção de informativos de cada tribunal no filtro (STF, STJ e TST sem filtro), no acervo local |
| `timeline_decisoes`, `processo` | DataJud, DJEN e acervo local |
| `timeline_decisoes`, `recentes` | as coleções de precedentes qualificados dos tipos e tribunais no filtro, no acervo local (temas de repercussão geral do STF, repetitivos do STJ, súmulas de STF, STJ e TST, IRDR e IAC do BNP); com `incluir_informativos`, também as de `informativo_juridico` |
| `listar_overruling_por_tema` | as coleções de situação de tema e súmula dos tribunais e tipos no filtro, no acervo local (STF RG, STJ repetitivos, BNP, súmulas por tribunal) |
| `listar_ramos_direito` | o acervo local e a tabela TPU versionada; nenhum portal |

| Literal | Condição |
|---|---|
| `indisponivel` | resultado vazio e ao menos uma fonte necessária não lida (C3; regra invariável 2): a ausência de itens não é afirmada, porque parte do recorte não foi lida |
| `parcial` | resultado não vazio e ao menos uma fonte necessária não lida; `fontes_indisponiveis` diz qual |
| `nenhum_no_recorte` | toda fonte necessária lida e resultado vazio; `cobertura` diz o que foi lido; nunca afirma inexistência fora do recorte (C4) |
| `ok` | toda fonte necessária lida e resultado não vazio |

Para entrada válida, toda fonte necessária está lida ou não lida, e todo resultado é vazio ou não: as quatro
condições são exaustivas e mutuamente exclusivas. `itens` pode estar vazio em `ok` ou `parcial` quando o
resultado está todo nas listas auxiliares (por exemplo, só temas `nao_classificada` em
`listar_overruling_por_tema`). `total` conta só `itens`.

Entrada fora do domínio (parâmetro inexistente, `limite` fora da faixa, janela acima do máximo, CNJ com dígito
verificador inválido) não é estado: é `EntradaInvalida`, como nas ferramentas atuais.

### 4. Itens por ferramenta

Os campos e enumerações são os de `docs/PARIDADE-1.4.md`; aqui se fixam nomes, tipos, nulidade e presença.

**Bloco de prova (C2), comum a todo item e a todo evento derivado de documento ou de metadado de fonte**:

| Campo | Tipo | Nulo | Regra |
|---|---|---|---|
| `proveniencia` | string | não | `captura` (derivado de documento oficial capturado) ou `metadado_de_fonte` (sem captura própria) |
| `url` | string | não | URL oficial do documento ou da fonte do metadado |
| `capture_id` | string | sim | não nulo se e só se `proveniencia` é `captura` |
| `sha256` | string | sim | hash dos bytes capturados; não nulo se e só se `proveniencia` é `captura` |
| `fetched_at` | string | sim | instante da captura; não nulo se e só se `proveniencia` é `captura` |

Item com `proveniencia: "metadado_de_fonte"` nunca é apresentado como `verified` nem como inteiro teor.

- **`informativo_juridico`** (IJ1–IJ5): bloco de prova; `tribunal` string; `numero_informativo` string;
  `data_divulgacao` string (data); `orgao` string|null; `processo` string|null; `tema` string|null; `ramo`
  string|null; `destaque` string (conteúdo oficial); `posicao` number; `decisao_id` string|null (IJ5: só com
  identidade tribunal + classe + número).
- **`timeline_decisoes`**, modo `processo` (TD1, TD3, TD4): topo com `modo: "processo"`, `numero_cnj` string e
  `atribuicao` array|null (C10, TD3: não nula quando há evento do DataJud). `itens` são eventos: bloco de prova;
  `data` string; `fonte` string (`datajud`, `djen`, `acervo`); `descricao` string (conteúdo oficial);
  `tipo_documental` string (`movimento`, `texto_publicado`, `ementa`, `inteiro_teor`; aberto); `decisao_id`
  string|null. Eventos do DataJud têm `proveniencia: "metadado_de_fonte"` e nunca `tipo_documental` de inteiro
  teor (TD1). A situação do processo em cada fonte vai na `cobertura` (seção 5, campo `resultado`), não no estado:
  processo em segredo ou ausente no DataJud é `resultado: "nao_confirmado_na_fonte"`, com `escopo`, nessa entrada
  (TD4); falha ou recusa do DataJud é `resultado: "indisponivel"`, nunca ausência. O estado agregado segue a
  seção 3: DataJud com `nao_confirmado_na_fonte` conta como fonte lida, mas não dispensa as outras duas. Exemplos:
  DataJud sem o processo, DJEN e acervo lidos e com eventos dão `ok`; os mesmos, com o DJEN não lido, dão `parcial`
  (há eventos) ou `indisponivel` (não há eventos); as três lidas e nenhum evento dão `nenhum_no_recorte`. Nenhuma
  resposta diz "processo inexistente".
  Modo `recentes` (TD2, TD2a, TD5): topo com `modo: "recentes"`. `itens` são precedentes: bloco de prova;
  `tribunal`; `tipo` (lista fechada de TD2); `numero` string; `tese` string|null (conteúdo oficial); `evento`
  string (`julgamento_merito`, `publicacao_tese`, `aprovacao_sumula`); `data_evento` string; `autoridade` object
  (o bloco do contrato 1). Lista auxiliar `informativos`, sempre presente (vazia sem `incluir_informativos`):
  itens de `informativo_juridico` acrescidos de `autoridade` object, a que a tabela `autoridade-1` lhes atribui
  (TD2a); nunca entram em `itens`.
- **`listar_overruling_por_tema`** (LO1–LO6): itens com bloco de prova; `tribunal`; `tipo`; `numero` string;
  `tese` string (conteúdo oficial); `situacao_oficial` string; `situacao` string (enumeração fechada de LO2);
  `data_situacao` string|null; `pertinencia` number|null. **Condicionais** (presentes só quando a fonte os declara;
  nunca preenchidos por inferência): `ato` string e `superada_por` string. Lista auxiliar `nao_classificadas`,
  sempre presente: mesmos campos, `situacao: "nao_classificada"`.
  LO6: campo `alerta_situacao` object `{tipo, numero, situacao, url}`, **condicional** (só quando o tema ou súmula
  está em estado alterado), em cada elemento de `itens[]` e de `resultados[]` de `pesquisar_jurisprudencia` (o
  mesmo objeto nas duas listas, que continuam idênticas) e no topo da resposta `encontrada` de `obter_decisao`.
  Não filtra nem reordena itens; não altera campo nem estado existente.
- **`listar_ramos_direito`** (LR1–LR4): itens com `ramo` string (nó de 1º nível da TPU), `codigo_tpu`
  string|null (nulo só no balde), `tpu_versao` string, `documentos` number, `por_tribunal` object `{<sigla>:
  number}`, `subramos` array (LR4, desejável; vazio sem implementação); o balde `ramo: "sem_assunto_oficial"` é
  sempre um item, com sua contagem. Itens de contagem não levam bloco de prova.
  LR3: `pesquisar_jurisprudencia` aceita `ramo` só na busca textual; cada elemento da `cobertura` (lista,
  experimental) ganha `nao_filtraveis_por_ramo` number|null (documentos do tribunal no recorte sem assunto oficial,
  que o filtro não pode alcançar; `null` sem filtro `ramo`). A variante estável em objeto da busca por classe e
  número não muda.

Campos de conteúdo oficial delimitados em MCP (Convenções do contrato): `destaque`, `descricao`, `tese`.

### 5. `cobertura` das ferramentas novas

Lista; cada entrada:

| Campo | Tipo | Nulo | Significado |
|---|---|---|---|
| `fonte` | string | não | fonte ou coleção (`informativos_stj`, `datajud`, `djen`, `acervo`, `bnp`…) |
| `tribunal` | string | sim | sigla, quando a entrada é de um tribunal |
| `resultado` | string | não | `lida` (consultada com sucesso), `nao_confirmado_na_fonte` (consultada com sucesso; o processo não consta ou está em segredo, TD4), `indisponivel` (falhou), `nao_consultada` (fora do recorte ou offline) |
| `escopo` | string | sim | o que a consulta alcança (por exemplo, "processos públicos indexados pelo DataJud") |
| `recorte` | object | sim | `{desde, ate}` das datas lidas |
| `primeiro_numero`, `ultimo_numero` | string | sim | IJ4: primeiro e último número ingeridos nas coleções numeradas (informativos); `null` nas demais |
| `lacunas` | array | não | IJ4: números faltantes na sequência; vazia quando a coleção não é numerada |
| `ultima_atualizacao` | string | sim | C11 |
| `indisponivel` | object | sim | `{motivo, categoria, evidencia_indisponibilidade?}` quando `resultado` é `indisponivel`; `categoria` pela decisão 0045 |

### 6. Adaptadores

| Operação | Python e MCP | REST |
|---|---|---|
| Informativos | `informativo_juridico` | `GET /v1/informativos` |
| Linha do tempo | `timeline_decisoes` | `GET /v1/timeline` (`modo` obrigatório) |
| Overruling | `listar_overruling_por_tema` | `GET /v1/overruling` |
| Ramos | `listar_ramos_direito` | `GET /v1/ramos` |

Paridade de adaptadores pelo C8, com a lista explícita de normalizações (delimitadores em MCP; envelopes de erro
REST).

### 7. Partes de `obter_decisao` (CH1–CH6)

Com `parte_idx`, a resposta é a forma `encontrada` do contrato 1, sem campo removido nem mudado de tipo, nulidade ou
estado, e com o mesmo significado de navegação:

- `texto`: o texto da parte; `offset`: início da parte (pontos de código); `max_chars`: `parte_tamanho`;
  `truncado`: `true` se a parte não termina no fim do texto; `cursor`: com `truncado: true`, o **fim** da parte
  (`intervalo[1]`, em string), isto é, onde o texto entregue acaba; `null` na última parte. Preserva-se o
  significado de continuação do contrato 1 (seguir por `cursor` no modo `offset` lê o restante); não se preserva a
  igualdade aritmética `cursor = offset + max_chars` do serviço atual, porque a parte pode terminar antes do limite
  pelo fim de parágrafo (CH4): `max_chars` é o limite máximo, e o tamanho entregue é `intervalo[1] - intervalo[0]`.
  Quem calcula a continuação por `offset + max_chars` em vez de ler o `cursor` pode saltar texto: a regra de
  navegação é ler o `cursor`, e a implementação a cobre em teste. Quem segue por `cursor` no modo de `offset` lê o restante sem perda nem repetição; quem segue por partes
  usa `parte_idx + 1`, cujo início é `intervalo[1] - sobreposicao`.
- Campo novo **`particao`** (experimental), objeto: `parte_idx` number, `partes_total` number, `parte_tamanho`
  number, `sobreposicao` number (200), `intervalo` [number, number] (início inclusivo, fim exclusivo, pontos de
  código sobre o texto canônico extraído), `sha256_parte` string, `sha256_texto` string (CH2: hexadecimal minúsculo
  dos bytes UTF-8), `segmentos` array de string (CH5; `["nao_identificado"]` sem segmentação tipada).
  O nome `particao` não coincide com nenhum campo do contrato 1 nem das respostas congeladas.
- Sem `parte_idx`, `particao` não aparece e o comportamento é o atual (CH1).
- `parte_idx` fora do intervalo, ou junto com `offset` diferente de 0 ou com `max_chars`: `EntradaInvalida`, com a
  mensagem informando `partes_total` quando conhecido (CH1, CH6). Nunca texto vazio nem estado novo.
- Estados de `parte_entregue` e de `status` não mudam: `parte_indisponivel` continua valendo quando a parte pedida
  não foi capturada, com ou sem `parte_idx`.

### 8. Fora desta decisão (redução pelo D5, 29/10/2026)

O passe final independente do PR #21 (`C:\dev\fv14-auditoria\parecer-pr21-final.md`, no computador do titular)
terminou COM BLOQUEADOR: conflito entre a seção 3 e LT4 em `listar_tribunais`, esquema incompleto de LT2/LT3, e
precedência não declarada de `formato_invalido`. Pelo D5, sem nova rodada, o escopo desta decisão foi reduzido:

1. `listar_tribunais` sai desta decisão. Seu esquema (itens com e sem sigla, matriz, `recorte_acervo`, estado de
   tribunal fora do escopo diante de fonte necessária não lida) será fixado em decisão própria, junto com a matriz
   de aceite do I3.7, que o LT1 exige como fonte única de verdade. Nenhum código de `listar_tribunais` antes dela.
2. `formato_invalido` deixa de ser estado das ferramentas novas: CNJ com dígito verificador inválido é
   `EntradaInvalida` (seção 3).
3. Fica para decisão anterior ao código de `timeline_decisoes` (modo `recentes`) e de `listar_overruling_por_tema`,
   que dependem do I2.3: como `limite` e `cursor` se aplicam às listas auxiliares (`informativos`,
   `nao_classificadas`), sem omissão nem repetição entre páginas.
4. Esclarecimento sem mudança de regra: os objetos de indisponibilidade seguem a decisão 0045 (seções 2 e 5).

## Consequências

- O I2.4 pode começar pelas partes de `obter_decisao` e por `listar_ramos_direito`, que não dependem de fonte nova;
  `informativo_juridico` e `timeline_decisoes` (modo `processo`) dependem das fontes já existentes ou do I2.3; o modo
  `recentes` e `listar_overruling_por_tema` esperam, além do I2.3, a decisão do item 3 da seção 8.
- O primeiro PR do I2.4 estende o comparador do teste de contrato para os prefixos de ferramenta inteira (seção 1,
  item 2), antes de qualquer ferramenta nova.
- Desvio desta forma no código é violação de requisito obrigatório fixado antes da implementação (D5).
