# Filtros públicos: onde cada um é aplicado

Este documento diz, por filtro público e por conector, **onde** o filtro age: parâmetro da fonte (`remoto`), filtro no próprio conector ou em SQL local (`local`) ou nenhum (`não suportado`). A regra é a do AGENTS.md: o que a fonte não filtra é declarado na resposta, nunca silenciado (decisão 0053). Ver também `ARQUITETURA.md` (busca) e `FONTES.md` (cobertura).

## Contrato de resposta (experimental)

`pesquisar_jurisprudencia` ganhou, de forma aditiva e **experimental** (pode mudar na 1.x sem o ciclo de aviso de `stable`):

- Nos modos por identificador (número CNJ; classe e número), `desde`, `ate`, `autoridade_min` e `cursor` não se aplicam e entram em `filtros_nao_aplicados` como `{"filtro", "motivo": "modo_por_identificador"}` (sem `fonte`); `tribunais` restringe o resultado (tribunal do identificador fora do filtro: nada é consultado, `nao_confirmado_no_acervo`) e `limite` corta os itens, marcando `truncado_local` (B2-04).
- `filtros_nao_aplicados`: lista, sempre presente (vazia quando nada a declarar), de `{"fonte", "filtro", "compensacao"}`. Um item significa que a fonte consultada ao vivo não aplicou aquele filtro na origem; `compensacao: "filtro_local_sobre_o_recuperado"` diz que o serviço o aplica depois, em SQL, só ao que a fonte devolveu. A janela recuperada é finita (uma página da fonte), então **a ausência de um item no resultado não prova que a fonte não o tenha**.
- `fontes.<id>.filtros`: para cada filtro pedido, `"remoto"`, `"local"` ou `"nao_suportado"`.

(O `CONTRATO.md` da trilha P3 não existe nesta branch; ao ser criado, deve listar estes dois campos como `experimental`.)

## Jurisprudência (`pesquisar_jurisprudencia`)

Parâmetros públicos: `q`, `tribunais`, `desde`, `ate`, `autoridade_min`, `limite`, `cursor`. Não há parâmetros `orgao`, `classe`, `tribunal` (singular) nem `pagina`: `cursor` é opaco e é um deslocamento sobre o acervo local. `desde` e `ate` são datas `AAAA-MM-DD`, inclusivas, comparadas com a data de julgamento (na falta, a de publicação).

Em todo caso o acervo local é filtrado por SQL (`desde`, `ate`, `tribunais`, `autoridade_min`), inclusive o que acabou de ser indexado a partir de uma consulta ao vivo. A matriz abaixo trata da **consulta ao vivo** à fonte.

| Filtro | TJDFT | TJSP | STJ | TCU | CVM Colegiado | DataJud |
|---|---|---|---|---|---|---|
| `desde` / `ate` | local no conector (descarta antes de indexar; registro sem data é descartado) | remoto: `dados.dtJulgamentoInicio` / `dados.dtJulgamentoFim` em `DD/MM/AAAA` | busca ao vivo desligada no serviço (`busca_textual_ao_vivo: false`); `search` do conector filtra em SQL o índice local | não suportado | `desde`: remoto só pelo **ano**; `ate`: não suportado | não suportado |
| `tribunais` | seleciona o conector; SQL local | idem | idem | idem | idem | idem |
| `autoridade_min` | SQL local após indexar | idem | idem | idem | idem | idem |
| `limite` | truncamento no serviço; a página pedida à fonte é a padrão (20) | idem (padrão 20) | SQL local `LIMIT` | idem (padrão 20) | idem | idem |
| `cursor` | deslocamento local; a fonte é sempre consultada na página inicial | idem | idem | idem | idem | idem |
| `orgao`, `classe` | não existem na API pública do serviço | idem | idem | idem | idem | idem |

Limitações declaradas:

- **TJDFT**: a API pública tem o campo `termosAcessorios`, mas a forma exata para data de julgamento (por exemplo "entre DD/MM/AAAA e DD/MM/AAAA") não está comprovada por fixture. Por isso a data **não é enviada**; o filtro é local e declarado como `filtros.desde/ate: "local"`. Como o corte é feito sobre a página recuperada, uma janela estreita pode devolver menos itens que a fonte tem. Reavaliar quando uma sonda capturar o campo (plano 1.3.0, F1).
- **TJSP**: o formato `DD/MM/AAAA` do formulário e-SAJ não tem captura em `tests/fixtures`; vale o que o conector já enviava (`dt_inicio`/`dt_fim` explícitos continuam aceitos e prevalecem). O filtro SQL local confere o resultado de qualquer forma.
- **STJ**: o serviço nunca consulta o STJ ao vivo; a resposta vem do acervo local semeado (`fv sync stj`). `StjConnector.search` (uso direto do conector) aplica `desde`/`ate` em SQL, normalizando `AAAAMMDD`, `AAAA-MM-DD` e `DD/MM/AAAA`; linha sem data reconhecível fica fora de qualquer janela.
- **TCU, DataJud**: sem filtro de data na origem; entram em `filtros_nao_aplicados`. O TCU varre páginas em ordem e filtra por texto no conector.
- **CVM Colegiado**: `desde` seleciona o ano inteiro de `desde`; `ate` é declarado como não aplicado e o corte exato é do SQL local.
- A reordenação por pertinência e os limites de janela não são filtros e não aparecem aqui.

## Normas

| Função | Parâmetros | Como cada um age |
|---|---|---|
| `buscar_legislacao` | `q`, `fonte`, `data`, `limite`, `cursor` | `fonte`: SQL local (`source_id`); `data`: **não filtra** a busca, seleciona a redação vigente naquela data em cada resultado (aritmética temporal, decisão 0002); `limite`, `cursor`: deslocamento local. Sem `desde`/`ate`. |
| `buscar_normas_cvm` | `q`, `tipo` | `tipo`: pasta do índice da CVM (`resolucoes`, instruções etc.), remoto/conector; tipo desconhecido volta a `resolucoes`. Sem `desde`/`ate`, `limite` nem paginação (o serviço indexa até 5 candidatos e declara o restante como `nao_indexado`, decisão 0024). |
| `buscar_normas_bcb` | `q`, `tipo` | `tipo`: filtro da busca do BCB (`Resolução CMN`, `Resolução` etc.); tipo e número também são extraídos da própria consulta. Sem `desde`/`ate` nem paginação pública (o conector limita a 15 linhas). |

`desde`, `ate`, `orgao`, `classe`, `tribunal` e `pagina` **não existem** nessas funções; pedi-los não é possível pela interface pública, e por isso não há `filtros_nao_aplicados` nelas.
