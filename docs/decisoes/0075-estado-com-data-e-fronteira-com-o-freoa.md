# 0075. Estado com `data` referido a D e fronteira com o FREOA (IL.0)

Data: 03/11/2026. Autor: supervisor (Opus), sob a emenda IL do plano 1.4.0 (`docs/PLANO-1.4.0-EMENDA-IL.md`) e a autorização do titular de 03/11/2026. Regra 3 do contrato (estado falso) e regra 1 (evolução aditiva).

## 1. Verificação exigida pela emenda (seção 5, "Verificar no início do IL")

Pergunta: `verificar_citacao` com `data` atribui a data a partir da rasura, sem fundamento documental do período?

Resposta: sim. Prova no próprio repositório: `tests/test_verify.py::test_rcvm160_temporal_causal` exige `text.status == "verified"` e `temporal.status == "verified"` para o texto riscado da compilada da RCVM 160 em `data="2022-08-01"`. O mecanismo é geral (`temporal.select`, regras R2 a R4): a redação original (R3) começa na data da obra e termina na data do ato alterador seguinte, lida da anotação da compilada; sem flag impeditiva na redação escolhida, o estado é `verified`. O texto confrontado é o riscado da compilada, e o limite final é a data do ato alterador, que não é início de vigência (decisão 0002). Nenhuma das duas coisas é fundamento documental do período.

Conclusão: é estado falso no sentido da regra 3 do contrato. Corrige-se, e a correção prevalece sobre o congelado.

## 2. Regra corrigida (vale para toda obra, legislação, CVM e BCB)

Consulta com `data` diferente da data corrente em America/Sao_Paulo ("consulta histórica"):

1. Sem fundamento documental do período, `temporal.status` é `unknown`, com `reason_code` `sem_fundamento_do_periodo`, sempre que o modelo temporal selecionaria redação ou afirmaria `verified` ou `revogado` para D. A data do ato alterador e o texto riscado da compilada não são fundamento do período.
2. Na mesma condição, com trecho, `text.status` é `unknown`, com `reason_code` `sem_fundamento_do_periodo`. O confronto do trecho com as redações conhecidas vai no campo aditivo `correspondencia_textual`, nunca no estado.
3. Mantêm-se: `nao_existia` para D anterior à data da obra ou anterior à data do ato que incluiu o dispositivo (a data do ato nunca é posterior ao início de vigência, logo a inexistência em D anterior está demonstrada); `ambiguous`; `unknown` com os motivos já existentes; `not_found` de identidade.
4. Consulta corrente (sem `data`, ou `data` igual a hoje) não muda: `vigente_na_fonte` segue as regras da 1.3.0.
5. Fundamento do período só nasce de versão oficial identificada para a data (emenda, seção 5, item 1). Nenhuma fonte do acervo instalado o fornece hoje; por isso `fundamento_temporal` vem `null` em toda resposta até o IL.2. Quando vier, `verified` para D passa a exigir `fundamento_temporal` não nulo.

## 3. Nomes publicados (IL.0, emenda seção 8)

Todos aditivos, estágio `stable` salvo indicação, sem mudança de `CONTRATO_VERSAO`.

### 3.1 `verificar_citacao` (nível superior)

| Campo | Tipo | Nulo | Significado |
|---|---|---|---|
| `fundamento_temporal` | object | sim | `{tipo, capture_id, url, sha256, data}`; `tipo` em `versao_oficial_na_data` (aberto). `null` quando não há fundamento do período (sempre, até o IL.2) ou quando a consulta é corrente |
| `correspondencia_textual` | object | sim | só em consulta histórica com trecho e identidade verificada: `{resultado: "coincide"\|"parcial"\|"diverge", redaction_id: string\|null, riscada: bool\|null, origem: "rasura_compilada"\|"redacao_atual"}`. Descreve o confronto mecânico; não é estado nem afirma o texto em D |

### 3.2 Evidência (`evidence[]` das dimensões; `evidencia` de `obter_dispositivo`)

| Campo | Tipo | Nulo | Significado |
|---|---|---|---|
| `captured_at` | string | não | instante da captura (mesmo valor de `fetched_at`; nome estável para o FREOA) |
| `acervo_ate` | string | sim | data `AAAA-MM-DD` do corte do acervo congelado da fonte (hoje só `planalto`: última captura da fonte no acervo instalado); `null` em fonte viva |
| `source_kind` | string | não | espécie do ato: `lei`, `lei_complementar`, `decreto`, `decreto_lei`, `medida_provisoria`, `emenda_constitucional`, `constituicao`, `resolucao_cvm`, `instrucao_cvm`, `parecer_orientacao_cvm`, `resolucao_cmn`, `resolucao_bcb`, `circular_bcb` (aberto) ou `nao_identificado` |
| `natureza_texto` | string | não | `publicacao_original`, `consolidacao_oficial`, `reconstrucao_mecanica` ou `nao_identificado` |
| `procedencia` | string | não | `captura_direta`, `snapshot`, `cadeia_de_alteracoes`, `sessao_assistida` ou `nao_identificado` |
| `esfera` | string | não | `federal`, `estadual`, `municipal` ou `nao_identificado` (metadado) |

Nenhum eixo afirma vigência. Compilada do Planalto e documento consolidado da CVM são `consolidacao_oficial`; captura instalada pelo snapshot é `snapshot`.

### 3.3 `listar_fontes` (nível superior)

- `qualificacao` (array): um item por porta e escopo, `{porta: "L"|"A"|"stj_1_4_0", escopo: string, estado: "aprovada"|"reprovada"|"nao_apurada"|"suspensa", versao: string|null, manifesto: string|null, rotulo: string}`. `escopo` é a capacidade da Porta L (`texto_publicado`, `texto_consolidado_vigente`, `redacao_em_data`, `anexos`, `remissoes`) ou a sigla do tribunal. Rótulos distintos: "Porta L aprovada em (capacidades)", "STJ qualificado no escopo 1.4.0", "Porta A por tribunal". Informa; não liga nem desliga rota no FREOA. Fonte: `freoa_verifica/data/qualificacao.json`, versionado.
- `avisos_incidente` (array): `{id, data, versoes_afetadas: array, acao: "retirada"|"correcao", descricao, referencia}`. Fonte: `freoa_verifica/data/avisos_incidente.json` mais, se existir, `<home>/avisos_incidente.json` (mesma forma, validada; item inválido é descartado com aviso em log). Limite conhecido: a versão instalada só conhece avisos até a sua construção ou o que o operador gravou no home; a nota da release é o outro ponto público.

### 3.4 Ferramenta nova `obter_registro`

Registro local da operação de verificação. Entrada: `run_id` (string), `capture_ids` (array de string, opcional). Saída em `encontrada`: `{status, run_id, ferramenta, criado_em, politica, parametros, estado: {identity, text, temporal, support}, evidencias, fundamento_temporal, integridade: {algoritmo: "hmac-sha256", confere: bool|null}, confere_capturas: object|null}`. Em política `completo`, `parametros` e `evidencias` (`[{capture_id, sha256, url}]`) vêm como gravados. Em `sem_conteudo` (decisão 0040, mantida), `parametros` vem só com os HMAC já gravados, `evidencias` vem `null` e `confere_capturas` responde, para cada `capture_id` informado, se ele consta das evidências da operação (por HMAC); assim quem guardou a resposta prova a correspondência sem que o banco revele o que foi consultado. `integridade.confere` recalcula o HMAC do registro com a chave do home; `null` em registro anterior à 1.4.0a2. Em `inexistente`: `{status, run_id}`. Adaptadores: MCP `obter_registro`; REST `GET /v1/registros/{run_id}`; Python `obter_registro`.

A captura persistida já é recuperável por `capture_id` sem rede (`obter_evidencia`, que lê o blob local). Para fonte viva, o FREOA guarda `run_id` e `capture_id`; reexecução determinística só basta para acervo local.

### 3.5 Contrato do consumidor

`tests/contrato/consumidores/freoa.json` lista, por ferramenta, os caminhos e os literais de estado que o FREOA consome. A suíte falha se um caminho listado sumir de uma resposta congelada da ferramenta, se mudar de tipo, ou se um literal listado sair do conjunto de estados, salvo caminho em `DEPRECATED`. Mudança nesse arquivo exige auditoria.

## 4. Consequências

- Testes que exigiam `verified` para D histórico passam a exigir `unknown`/`sem_fundamento_do_periodo` e a `correspondencia_textual` correspondente; o congelado regravado traz esta decisão no commit.
- A capacidade (c) da Porta L parte deste estado: 100% dos casos sem fundamento da data devolvidos como não verificados para D, com motivo.
- O FREOA pode adotar os nomes e fixar a versão mínima 1.4.0a2.

## 5. Fora desta decisão

Versões oficiais por data, cadeia de atos alteradores e `sem_versao_oficial_na_data` (emenda, seção 5, item 3) entram com os adaptadores do IL.2. Reconstrução mecânica fica fora do IL.

## 6. Numeração das pré-releases

IL.0 e esta correção saem em pré-release própria, 1.4.0a2 (emenda, seção 5, IL.0). O IL qualificado pela Porta L sai em 1.4.0a3; o STJ, em 1.4.0a4. A 1.4.0 estável continua IL + STJ. Número de versão não é rótulo de substituição.
