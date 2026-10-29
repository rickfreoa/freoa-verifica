# 0073 - Esquema de saída das ferramentas de paridade (C7) e das partes de `obter_decisao` (CH6)

Estado: aceita. Decisão do supervisor em 29/10/2026, sob o D5 (mudança de contrato público exige decisão formal) e
o requisito C7 de `docs/PARIDADE-1.4.md`, antes de qualquer código do I2.4.

## Contexto

`docs/PARIDADE-1.4.md` fixou o que cada ferramenta de paridade entrega (I2.1). Dois pontos ficaram para decisão
formal: (a) a forma da resposta das cinco ferramentas novas, que entram no contrato 1 como `experimental` (C7);
(b) a forma da resposta de `obter_decisao` com `parte_idx` (CH6), que não pode alterar tipo, nulidade nem estados
de campo existente do contrato 1. O PR #13 tentou fixar (b) no próprio documento de paridade e foi reduzido pelo D5
depois de três rodadas: primeiro com estado novo em campo fechado, depois com colisão com o campo estável `parte`.

## Decisão

### 1. Estágio e regra de promoção

1. `informativo_juridico`, `timeline_decisoes`, `listar_overruling_por_tema`, `listar_tribunais` e
   `listar_ramos_direito` entram no contrato 1 como **experimentais**, inteiras, na 1.4.0a2: cada uma por prefixo
   `"<ferramenta>:"` em `EXPERIMENTAL` de `freoa_verifica/contrato.py`. O campo novo `particao` de `obter_decisao`
   (abaixo) entra do mesmo modo (`"obter_decisao:particao"`).
2. Promoção a `stable`: respostas congeladas em `tests/contrato/esperado/` para os três adaptadores, casos de cada
   estado fechado, e nova decisão formal. Nenhuma promoção na 1.4.0a2.
3. São mudanças aditivas (regra 1 do contrato): `CONTRATO_VERSAO` continua "1".

### 2. Envelope comum das cinco ferramentas novas

Campos sempre presentes, salvo indicação:

| Campo | Tipo | Nulo | Significado |
|---|---|---|---|
| `status` | string | não | estado fechado, seção 3 |
| `itens` | array | não | itens da ferramenta (seção 4); nunca vazio quando `status` é `ok` ou `parcial` |
| `total` | number | não | quantidade de `itens` desta página |
| `truncado` | bool | não | o `limite` cortou resultados |
| `cursor` | string | sim | próxima página; `null` sem mais páginas |
| `cobertura` | array | não | uma entrada por coleção ou tribunal lido (seção 5) |
| `fontes_indisponiveis` | object | condicional | `{<fonte>: {motivo, categoria}}`, só em `parcial` e `indisponivel` |
| `motivo` | string | condicional | só em `indisponivel` e `formato_invalido` |

Grafia: só português nos estados das ferramentas novas (`indisponivel`, nunca `unavailable`), para não ampliar a
inconsistência 1 do contrato. Não há `resultados` sinônimo de `itens` nas ferramentas novas.

### 3. Estados fechados das ferramentas novas (`status`)

| Literal | Significado |
|---|---|
| `ok` | consulta concluída, toda fonte consultada respondeu, há itens |
| `parcial` | há itens, mas alguma fonte falhou; `fontes_indisponiveis` diz qual (C3) |
| `nenhum_no_recorte` | fontes consultadas com sucesso e nada no recorte lido; `cobertura` diz o que foi lido; nunca afirma inexistência fora dele (C4) |
| `indisponivel` | nenhuma fonte necessária respondeu; `motivo` e `fontes_indisponiveis` (C3) |
| `formato_invalido` | entrada reconhecida e inválida no conteúdo (número CNJ com dígito verificador errado em `timeline_decisoes`); `motivo` |

Entrada fora do domínio (parâmetro inexistente, `limite` fora da faixa, janela acima do máximo) não é estado: é
`EntradaInvalida`, como nas ferramentas atuais (MCP: erro de ferramenta; REST: `problem+json` 4xx).

### 4. Itens por ferramenta

Os campos e enumerações são os de `docs/PARIDADE-1.4.md`; aqui se fixam nomes, tipos e nulidade.

- **`informativo_juridico`** (IJ1–IJ5): `tribunal` string; `numero_informativo` string; `data_divulgacao`
  string (data); `orgao` string|null; `processo` string|null; `tema` string|null; `ramo` string|null; `destaque`
  string (conteúdo oficial); `posicao` number; `decisao_id` string|null (IJ5: só com identidade tribunal + classe +
  número); `url` string; `capture_id` string; `sha256` string; `fetched_at` string.
- **`timeline_decisoes`**, modo `processo` (TD1, TD3, TD4): resposta com `modo: "processo"`, `numero_cnj` string,
  `atribuicao` array|null (C10: obrigatória quando houver evento do DataJud) e `itens` de eventos: `data` string;
  `fonte` string (`datajud`, `djen`, `acervo`); `descricao` string (conteúdo oficial); `tipo_documental` string
  (`movimento`, `texto_publicado`, `ementa`, `inteiro_teor`, aberto); `proveniencia` string
  (`metadado_de_fonte` ou `captura`); `decisao_id` string|null; `capture_id` string|null; `url` string|null. Processo
  em segredo ou ausente no DataJud: `status: "nenhum_no_recorte"` com `escopo` e `motivo_ausencia:
  "nao_confirmado_na_fonte"` (TD4); a resposta nunca diz "processo inexistente".
  Modo `recentes` (TD2, TD2a): `modo: "recentes"`; `itens` de precedentes: `tribunal`, `tipo` (lista fechada de
  TD2), `numero` string, `tese` string|null (conteúdo oficial), `evento` string (`julgamento_merito`,
  `publicacao_tese`, `aprovacao_sumula`), `data_evento` string, `autoridade` object (o bloco do contrato), `url`,
  `capture_id` string|null; `informativos` array (só com `incluir_informativos`; itens de `informativo_juridico`).
- **`listar_overruling_por_tema`** (LO1–LO6): itens com `tribunal`, `tipo`, `numero` string, `tese` string
  (conteúdo oficial), `situacao_oficial` string, `situacao` string (enumeração fechada de LO2), `data_situacao`
  string|null, `ato` string|null, `superada_por` string|null, `url`, `capture_id` string|null, `pertinencia`
  number|null; lista separada `nao_classificadas` (mesmos campos, `situacao: "nao_classificada"`), sempre presente.
  Anotação de LO6 em `obter_decisao` e `pesquisar_jurisprudencia`: campo aditivo `alerta_situacao`
  object|ausente `{tipo, numero, situacao, url}`, experimental (`"<ferramenta>:alerta_situacao"`).
- **`listar_tribunais`** (LT1–LT4): sem sigla, itens com `tribunal`, `capacidade`, `tipos_documento`,
  `decisoes_no_acervo` number, `recorte_acervo` object|null, `porta_a` string (`aprovado`, `em_avaliacao`,
  `nao_avaliado`), `excecao` object|null `{estado, revisar_em, registro}`. Com sigla, um item com `matriz` array de
  `{colecao, orgao, desde, ate, modalidade, documentos, denominador, cobertura}` (`denominador` number|null;
  `cobertura` number ou `"desconhecida"`). Tribunal fora do escopo: item com `capacidade: "nenhuma"` e `status:
  "ok"` (LT4).
- **`listar_ramos_direito`** (LR1–LR4): itens com `ramo` string (nome do nó de 1º nível da TPU), `codigo_tpu`
  string|null (null só no balde), `tpu_versao` string, `documentos` number, `por_tribunal` object `{<sigla>:
  number}`, `subramos` array (LR4, desejável; vazio sem implementação); o balde `ramo: "sem_assunto_oficial"` é
  sempre um item, com sua contagem.

Campos de conteúdo oficial delimitados em MCP (Convenções do contrato): `destaque`, `descricao`, `tese`.

### 5. `cobertura` das ferramentas novas

Lista; cada entrada: `colecao` string; `tribunal` string|null; `recorte` object|null `{desde, ate}`;
`ultima_atualizacao` string|null (C11); `lacunas` array (IJ4: números faltantes na sequência; vazia quando a
coleção não é numerada); `consulta` string (`acervo`, `ao_vivo`, `ambos`, `nenhuma`); `indisponivel`
object|null.

### 6. Adaptadores

| Operação | Python e MCP | REST |
|---|---|---|
| Informativos | `informativo_juridico` | `GET /v1/informativos` |
| Linha do tempo | `timeline_decisoes` | `GET /v1/timeline` (`modo` obrigatório) |
| Overruling | `listar_overruling_por_tema` | `GET /v1/overruling` |
| Tribunais | `listar_tribunais` | `GET /v1/tribunais` e `GET /v1/tribunais/{sigla}` |
| Ramos | `listar_ramos_direito` | `GET /v1/ramos` |

Paridade de adaptadores pelo C8, com a lista explícita de normalizações (delimitadores em MCP; envelopes de erro
REST).

### 7. Partes de `obter_decisao` (CH1–CH6)

Com `parte_idx`, a resposta é a forma `encontrada` do contrato 1, sem campo removido nem mudado de tipo, nulidade ou
estado:

- `texto`: o texto da parte; `truncado`: `true` se houver parte seguinte; `offset`: início da parte em pontos de
  código; `max_chars`: `parte_tamanho`; `cursor`: `null` (a navegação por partes é por `parte_idx`, não por
  `cursor`; o campo já é anulável no contrato 1).
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

## Consequências

- O I2.4 pode começar pelas partes de `obter_decisao`, por `listar_tribunais` e por `listar_ramos_direito`, que não
  dependem de fonte nova; `informativo_juridico`, o modo `recentes` de `timeline_decisoes` e
  `listar_overruling_por_tema` dependem dos dados do I2.3.
- O teste de contrato passa a listar os prefixos experimentais desta decisão; o teste de paridade de adaptadores
  (C8) cobre cada ferramenta nova.
- Desvio desta forma no código é violação de requisito obrigatório fixado antes da implementação (D5).
