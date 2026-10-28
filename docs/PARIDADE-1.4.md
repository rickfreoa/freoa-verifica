# Paridade funcional 1.4 — requisitos fixados antes da implementação (I2.1)

Estado: fixado pelo supervisor em 28/10/2026, antes de I2.2 a I2.4. Pelo D5 do plano 1.4.0, a violação
demonstrada de um requisito marcado **[O]** (obrigatório) bloqueia o merge, como achado alto. Requisito
**[D]** (desejável) não bloqueia. Mudar um [O] depois deste commit exige registro em `docs/decisoes/`
antes do código que o usa.

A referência funcional é o conjunto de usos que levava o titular a uma ferramenta externa de pesquisa.
A comparação nominal com essa ferramenta fica restrita a `tests/` e aos artefatos de bench (plano, seção 9,
item 3). Este documento descreve o que o FREOA Verifica entrega, não como outra ferramenta funciona.

## 1. Requisitos comuns às seis funções

| # | Requisito | Prova de aceite |
|---|---|---|
| C1 [O] | Toda requisição passa por `freoa_verifica.transport` (regra 4), com UA identificado (0048). | Teste estrutural: os módulos novos não importam `urllib`, `http.client`, `socket`, `requests` nem `httpx`. |
| C2 [O] | Item derivado de documento oficial traz `url` oficial, `capture_id`, `sha256` dos bytes capturados e `fetched_at`. Item sem captura própria declara `proveniencia: "metadado_de_fonte"` e nunca é `verified`. | Teste por ferramenta sobre fixture `captura_real` ou `sintetica` rotulada. |
| C3 [O] | Falha, desafio ou resposta inesperada viram `unavailable`/`indisponivel` com `motivo` e `categoria` (0045), ou `parcial` com `fontes_indisponiveis`; nunca lista vazia. | Teste de transporte falso para recusa, timeout, 403 e corpo inesperado em cada fonte. |
| C4 [O] | Resultado vazio de fonte consultada com sucesso vem com `cobertura` (tribunal, coleção, período efetivamente lido) e o estado `nenhum_no_recorte`; nunca afirma inexistência fora do recorte. | Teste de vazio. |
| C5 [O] | Nenhum modelo generativo; nenhum ranqueamento por embeddings nestas funções (são listagens e consultas por identidade, fora do plano de descoberta do D2). Ordenação determinística e documentada; desempate estável por identificador. | Teste de ordem com empate; teste estrutural sem import de runtime de modelo. |
| C6 [O] | Conteúdo oficial em MCP entre os delimitadores de documento (CONTRATO, Convenções). | Teste de contrato MCP. |
| C7 [O] | Ferramenta nova entra no contrato como `experimental` na 1.4.0a2 e só passa a `stable` com respostas congeladas em `tests/contrato/esperado/` e decisão formal (D5: mudança de contrato público). | Teste de contrato. |
| C8 [O] | Mesma resposta pelos três adaptadores (Python, MCP, REST), da fachada `service.py`. | Teste de paridade de adaptadores. |
| C9 [O] | p95 ≤ 5 s em consulta só local e ≤ 20 s com fonte ao vivo, medidos na bateria do snapshot (Porta A, D4). | Relatório da bateria. |
| C10 [D] | Atribuição de fonte no corpo da resposta quando a fonte exige (DataJud: CNJ e DataJud, Portaria 374/2026). Para o DataJud é [O]. | Teste do campo `atribuicao`. |

## 2. Requisitos por função

### 2.1 `informativo_juridico`

Uso coberto: ler o que os tribunais destacaram como relevante num período, por tribunal.

| # | Requisito |
|---|---|
| IJ1 [O] | Fontes: informativos oficiais de STF, STJ e TST, capturados do portal de cada tribunal. Cada item = um destaque do informativo, com `tribunal`, `numero_informativo`, `data_divulgacao`, `orgao`, `processo` (quando o informativo traz), `tema`/`ramo` como publicados, `destaque` (texto oficial) e `url` do informativo. |
| IJ2 [O] | Parâmetros: `tribunal` (opcional; sigla normalizada), `desde`/`ate` (datas; padrão últimos 365 dias; janela máxima 730 dias), `limite` (1–300, padrão 50), `cursor`. |
| IJ3 [O] | Ordenação: `data_divulgacao` decrescente, depois `tribunal`, `numero_informativo`, posição do destaque. Sem "balanceamento" entre tribunais; quem quiser equilíbrio filtra por tribunal. |
| IJ4 [O] | `cobertura` por tribunal: primeiro e último informativo ingeridos, data da última atualização e lacunas de numeração conhecidas. Informativo ausente na sequência aparece em `lacunas`, nunca é silenciado. |
| IJ5 [O] | Processo citado no destaque que exista no acervo vem ligado ao `id` da decisão; a ligação exige identidade (tribunal + classe + número), nunca semelhança de texto. |
| IJ6 [D] | Atualização p95 ≤ 72 h após a divulgação (coleção contínua, D4). |

### 2.2 `timeline_decisoes`

Dois usos distintos, separados por modo para não confundir prova processual com seleção de relevância.

| # | Requisito |
|---|---|
| TD1 [O] | `modo: "processo"` com `numero_cnj` (dígito verificador conferido): linha do tempo com movimentos do DataJud (`fonte: "datajud"`, `proveniencia: "metadado_de_fonte"`), comunicações do DJEN (`tipo_documental: "texto_publicado"`, 0047) e decisões do acervo do mesmo processo (com `capture_id`). Cada evento traz `data`, `fonte`, `descricao` como publicada e `tipo_documental`. Movimento nunca é apresentado como inteiro teor. |
| TD2 [O] | `modo: "recentes"` com `tribunal` opcional, `desde`/`ate` e `tipos` (lista fechada documentada: `tema_repetitivo`, `repercussao_geral`, `sumula`, `irdr`, `iac`, `informativo`): precedentes qualificados e destaques recentes, ordenados por data oficial do evento (julgamento de mérito, publicação da tese, aprovação da súmula), decrescente. Só entram itens com autoridade A ou B pela tabela pública `autoridade-1`; nada de seleção por popularidade. |
| TD3 [O] | Atribuição obrigatória quando houver evento do DataJud (C10). |
| TD4 [O] | Processo em segredo de justiça ou ausente no DataJud: `nao_confirmado_na_fonte` com `escopo`, nunca "processo inexistente". |
| TD5 [O] | Limites: `limite` 1–200 (padrão 50), janela máxima 730 dias no modo `recentes`. |

### 2.3 `listar_overruling_por_tema`

Uso coberto: saber se uma tese foi superada, cancelada ou revista, e por qual ato.

| # | Requisito |
|---|---|
| LO1 [O] | O estado vem só de declaração oficial: situação do tema de repercussão geral (STF), do tema repetitivo (STJ), do IRDR/IAC (BNP), súmula cancelada, revogada ou com redação alterada (STF, STJ, TST). Nunca se infere superação do texto de um acórdão. |
| LO2 [O] | Cada item: `tribunal`, `tipo` (tema_rg, tema_repetitivo, irdr, iac, sumula), `numero`, `tese` ou enunciado oficial, `situacao_oficial` (literal, como publicada), `situacao` normalizada (`cancelada`, `revisada`, `superada_declarada`, `em_revisao`, `vigente`), `data_situacao`, `ato` (processo ou ato que mudou a situação, só quando a fonte o declara) e `url`. `superada_por` só existe se a fonte o declarar. |
| LO3 [O] | Mapeamento `situacao_oficial` → `situacao` em tabela pública versionada; literal não mapeado vira `nao_classificada`, nunca `vigente`. |
| LO4 [O] | Busca por `query` lexical (FTS5) sobre tese, enunciado e assuntos oficiais; `apenas_alteradas` (padrão verdadeiro) filtra `situacao != vigente`; `limite` 1–30. Ordem: bm25, depois data da situação decrescente, depois identificador. |
| LO5 [O] | `cobertura`: coleções lidas (STF RG, STJ repetitivos, BNP, súmulas por tribunal) com data da última atualização de cada uma. |
| LO6 [O] | `obter_decisao` e `pesquisar_jurisprudencia` passam a anotar o item cujo tema ou súmula esteja em estado alterado (`alerta_situacao`), sem filtrar o item. |

### 2.4 `listar_tribunais`

| # | Requisito |
|---|---|
| LT1 [O] | Uma única fonte de verdade com `listar_fontes` e com a matriz de aceite (I3.7): o teste compara as duas saídas. |
| LT2 [O] | Sem sigla: lista dos tribunais do escopo (33 ao fim da 1.4) com `capacidade`, `tipos_documento`, contagem no acervo, período do acervo, estado na Porta A (`aprovado`, `em_avaliacao`, `nao_avaliado`) e exceção, se houver (`bloqueio_externo_documentado` com `revisar_em`). |
| LT3 [O] | Com sigla: matriz tribunal × coleção × órgão × período × modalidade documental (D1), com denominador quando confiável e `desconhecida` quando não. |
| LT4 [O] | Tribunal fora do escopo responde `capacidade: "nenhuma"`, nunca erro nem lista vazia. |

### 2.5 `listar_ramos_direito`

| # | Requisito |
|---|---|
| LR1 [O] | Ramo vem do assunto oficial do processo pela Tabela Processual Unificada (TPU) do CNJ: código de assunto publicado pela fonte (metadados do STJ, DataJud, portais) mapeado ao nó de primeiro nível da TPU, com a versão da tabela registrada. Nunca por palavra-chave nem por modelo. |
| LR2 [O] | Saída: por ramo, contagem de documentos no acervo, por tribunal; balde `sem_assunto_oficial` explícito com sua contagem. |
| LR3 [O] | `pesquisar_jurisprudencia` aceita filtro `ramo` (aditivo), que só filtra documentos com assunto oficial; os sem assunto aparecem em `cobertura` como não filtráveis. |
| LR4 [D] | Segundo nível da TPU como `subramo`. |

### 2.6 Partes (chunks) em `obter_decisao`

| # | Requisito |
|---|---|
| CH1 [O] | Parâmetros aditivos `parte_idx` (≥ 0) e `parte_tamanho` (500–10.000, padrão 2.000); sobreposição fixa de 200 caracteres. Os parâmetros atuais (`offset`, `max_chars`) continuam valendo. |
| CH2 [O] | Cada parte traz `parte_idx`, `partes_total`, `intervalo` [início, fim) sobre o texto canônico extraído, `sha256_parte`, `sha256_texto` (texto inteiro) e `capture_id`, e repete os metadados da decisão. |
| CH3 [O] | Reprodutibilidade: a mesma decisão, o mesmo `parte_idx` e o mesmo `parte_tamanho` devolvem os mesmos bytes; concatenar as partes sem a sobreposição reconstrói o texto com `sha256_texto` igual. |
| CH4 [O] | Corte nunca no meio de um caractere nem de um par substituto; preferência por fim de parágrafo dentro de uma janela de 200 caracteres, por regra determinística documentada. |
| CH5 [O] | Quando houver segmentação (I2.6), cada parte informa os segmentos que intersecta; sem segmentação, `segmentos: ["nao_identificado"]`. |
| CH6 [O] | `parte_idx` fora do intervalo: `status: "parte_inexistente"` com `partes_total`, nunca lista vazia. |

## 3. Fora do escopo

Pedidos de autos (plano, seção 9, item 4): dependem de acesso processual autenticado. O uso que os
justificava é atendido por `timeline_decisoes` (modo `processo`) e por `obter_decisao`.

## 4. Testes que fecham a paridade (I2.5)

O conjunto de desenvolvimento da Porta A inclui, por função, ao menos cinco casos de paridade com resposta
fixada pela fonte oficial, montados sem leitura do código: informativo de número conhecido; processo com
movimentos e publicação; tema repetitivo cancelado e súmula com redação alterada; tribunal com exceção;
decisão longa paginada e reconstruída por hash.
