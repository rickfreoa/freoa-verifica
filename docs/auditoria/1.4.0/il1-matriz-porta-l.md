# IL.1: matriz da Porta L, conjuntos e regra de apuração (congelada antes da implementação)

Versão 2 (03/11/2026), depois do parecer do Codex sobre a versão 1 (COM BLOQUEADOR, achados 1 a 17). Autor: supervisor (Opus), sob a emenda IL (seções 5 a 7) e a decisão 0075. Os pisos são os da emenda, seção 6, sem alteração; são escolhas de engenharia, não exigências demonstradas. Mudança de matriz, reserva ou piso depois de vistos resultados exige decisão do titular (emenda, seção 7).

## 1. Capacidades, chamada medida e acerto

Cada capacidade é medida por chamada pública fixa. Parâmetros e campos marcados "IL.2/IL.3" são nomes publicados aqui, aditivos, a implementar antes da apuração.

| Cap. | Escopo | Chamada | Acerto |
|---|---|---|---|
| (a) | texto publicado | `obter_dispositivo(citacao, versao="publicacao_original")` (IL.2) | `status: encontrada`; `evidencia.natureza_texto == "publicacao_original"`; `texto` igual ao gabarito |
| (b) | texto consolidado vigente | `obter_dispositivo(citacao)` | tipo `texto`: `status: encontrada`, `texto` igual ao gabarito, `truncado: false`; tipo `revogado_vigente`: `status: encontrada` e `vigencia.status == "revogado"` |
| (c) | redação em data D | `verificar_citacao(citacao, trecho=gabarito.texto ou caso.trecho, data=D)` | ver 1.1 |
| (d) | anexos | `obter_dispositivo(citacao_do_anexo)` | `status: encontrada`; `texto` igual ao gabarito (o recorte declarado do anexo) |
| (e) | remissões | `obter_dispositivo(citacao)`, campo `remissoes[]` (IL.3): `{texto, alvo: {obra, caminho}, resolvida: bool}` | o conjunto dos alvos com `resolvida: true` é exatamente o conjunto `alvos` do gabarito (cada alvo aceito também na forma listada em `alvos_equivalentes[alvo]`); nenhum faltante, nenhum excedente |

Semântica de `versao="publicacao_original"` em (a): o texto do dispositivo tal como publicado no Diário Oficial pelo ato que lhe deu a PRIMEIRA redação: a própria obra, se o dispositivo é original; o ato alterador, se foi incluído depois. O gabarito traz o dispositivo sem as aspas e sem a pontuação do comando alterador, e `fonte_oficial` é a publicação desse ato.

### 1.1 Tipos de gabarito em (c)

| Tipo | Acerto |
|---|---|
| `verificado_para_D` | `text.status == "verified"` e `temporal.status == "verified"`, com `trecho` igual ao texto INTEGRAL do dispositivo em D (gabarito); `fundamento_temporal` com `tipo == "versao_oficial_na_data"`, `capture_id` recuperável por `obter_evidencia` (status `encontrada`) cujo `sha256` confere, e `data` menor ou igual a D |
| `nao_verificado_para_D` | `text.status == "unknown"` e `temporal.status == "unknown"`, ambos com `reason_code` em `motivos_aceitos` (`sem_fundamento_do_periodo`, `sem_versao_oficial_na_data`); se o motivo for `sem_versao_oficial_na_data`, a resposta traz a última versão oficial anterior e a cadeia ordenada de atos alteradores (emenda, seção 5, item 3), conferidas contra `gabarito.cadeia` |
| `nao_existia_em_D` | `temporal.status == "not_found"` com `reason_code == "NAO_EXISTIA"` e `text.status != "verified"`. Só se admite nos dois casos da 0075, seção 2, item 3: D anterior à data da obra; ou D anterior à data do ato que INCLUIU o dispositivo (anotação de inclusão), sem anotação de vigência, produção de efeitos, veto ou revogação parcial no dispositivo, o que o caso documenta em `fundamento_data` |

## 2. Contagem

- Confirmação indevida (eliminatório, todas as capacidades e todos os mutantes): (i) `verified` em `text` ou `temporal` onde o gabarito não é `verificado_para_D`, ou com `fundamento_temporal` que não cumpra 1.1; (ii) `status: encontrada` com texto diferente do gabarito; (iii) em (e), alvo com `resolvida: true` fora de `alvos` e seus equivalentes; (iv) em mutante, qualquer resposta que o trate como o caso original (seção 3). Piso: 0.
- Unidade de independência: o EVENTO normativo que deu a redação do gabarito. Para redação original, o par (norma, `original`); para redação dada por ato posterior, o identificador canônico do ato alterador (`lei-10303-2001`), qualquer que seja a norma consultada (a alterada ou a alteradora). `familia_alteracao` é esse identificador ou `original`; o identificador da própria norma consultada nunca é família; sufixos e variantes (`-b`, `-2`, `-alt`) são vedados. Em compilada, a família é a do ato citado na anotação editorial do dispositivo (Redação dada pela…, Incluído pelo…), registrada em `familia_fundamento`.
- Denominador de cada capacidade: uma unidade por evento; havendo vários casos da mesma unidade, conta o de menor `id` em ordem lexicográfica (seleção determinística); os demais entram só no cômputo de confirmação indevida e de mutantes. Em cada capacidade, pelo menos 8 unidades em cada conjunto e pelo menos 4 normas distintas.
- `unavailable`, `indisponivel`, `parcial` nunca entram no numerador e ficam no denominador.
- Abstenção sistemática não aprova (c): pelo menos 40% dos casos (c) da reserva são `verificado_para_D`.
- (c), condição adicional: 100% dos casos sem fundamento da data devolvidos como não verificados para D, com motivo.

## 3. Mutantes (todas as capacidades)

Escritos pelo pesquisador, caso a caso, no próprio conjunto (`mutantes.jsonl`, com hash, junto de cada conjunto) e revisados na segunda camada (seção 7.1: todos os mutantes). O validador não gera os mutantes do conjunto (o `--gerar-mutantes` é só ajuda opcional que escreve um rascunho, nunca o arquivo congelado): confere a FORMA e a coerência mecânica (esquema; caso de origem existe; todos os casos têm os mutantes obrigatórios abaixo; `renumerado` com destino diferente do original e declarado na fonte do caso como dispositivo, sem julgar se é o conteúdo pedido; `caractere` diferindo do gabarito em exatamente um caractere; `data_trocada` com data ISO e referência à redação alternativa declarada no caso). Cada mutante traz `id`, `caso`, `tipo`, a chamada exata, os parâmetros, o destino declarado (no `renumerado`) e o resultado esperado:

| Mutante | Aplica-se a | Chamada | Esperado |
|---|---|---|---|
| `renumerado` | todas | a chamada da capacidade com a citação renumerada (`art. N` → `art. N+1`; se N+1 não existir na fonte do caso, `art. N-A`; anexos: número seguinte), escolhida entre dispositivos existentes na fonte | nenhum `encontrada` com o texto do original; nenhum `verified` |
| `caractere` | todas com texto | `verificar_citacao(citacao, trecho=texto com um caractere trocado na posição central, letra pela vizinha no alfabeto)` | `text.status != "verified"` |
| `data_trocada` | (b) e (c), quando o caso declara `data_mutante` | `verificar_citacao(citacao, trecho=gabarito, data=data_mutante)`, com `data_mutante` dentro do intervalo de outra redação documentada ou anterior à obra | `text.status != "verified"` e `temporal.status != "verified"` |

## 4. Desempenho

p95 por chamada sobre a reserva (mesmo n): uma passada de aquecimento descartada e três passadas medidas; p95 pelo método do posto mais próximo sobre todas as latências medidas; modo local com rede desligada (acervo ou snapshot instalado) ≤ 5 s; modo remoto (federação ao vivo) ≤ 20 s.

## 5. Conjuntos e cobertura

| Conjunto | Casos | Por capacidade | Guarda |
|---|---|---|---|
| Desenvolvimento | ≥ 40 | ≥ 8 unidades | `tests/porta_l/desenvolvimento.jsonl`, `mutantes.jsonl`, `cobertura.json`, com hash no manifesto |
| Reserva | ≥ 50 | ≥ 10 casos, ≥ 8 unidades | fora do repositório (`Claude_Externos/freoa-verifica/porta-l/reserva/`), só os hashes no repositório e no manifesto; regime do D6 |

Cada conjunto traz `cobertura.json`: para cada situação obrigatória, os casos que a exercitam, o evento e o resultado esperado. O validador confere só a forma (situações obrigatórias presentes; casos citados existem e foram aprovados na triagem); o vínculo documental de cada situação com os casos citados é revisado na segunda camada (seção 7.1), sem inferência por proximidade textual. Situações obrigatórias (emenda, IL.1): dispositivo alto de norma grande (LSA 156, 254-A, 289; CC 421 e 1.031; CTN 185, cada um em pelo menos um caso que confronte texto); redação anterior em D com rasura (a compilada mostra a redação anterior riscada) e sem rasura; revogação (tipo `revogado_vigente` ou caso (c) que dependa dela); MP reeditada (publicação de uma reedição, distinta da original); MP convertida (caso que distinga o texto da MP do texto da lei de conversão em D); anexo; remissão; data anterior à publicação.

## 6. Forma do caso (JSON Lines, UTF-8)

```json
{"id": "L-c-007", "conjunto": "desenvolvimento", "capacidade": "c", "familia_alteracao": "lei-10303-2001",
 "familia_fundamento": "anotação 'Incluído pela Lei nº 10.303, de 2001' na compilada da Câmara",
 "norma": {"especie": "lei", "numero": "6404", "ano": 1976}, "citacao": "art. 254-A da Lei 6.404/1976",
 "caminho": "art. 254-A", "data": "2002-01-15", "data_mutante": "1999-06-30", "trecho": null,
 "gabarito": {"tipo": "verificado_para_D",
              "texto": "...", "motivos_aceitos": [], "cadeia": [],
              "alvos": [{"obra": "Lei 6.404/1976", "caminho": "art. 4º, § 4º"}], "alvos_equivalentes": {},
              "fonte_oficial": {"url": "...", "sha256": "...", "capturado_em": "AAAA-MM-DDTHH:MM:SSZ", "orgao": "...",
                                "ato_no_documento": "cabeçalho do ato a que pertence o recorte", "pagina": 1},
              "fundamento_data": "..."},
 "norma_grande": true}
```

`gabarito.tipo` em `texto`, `revogado_vigente`, `verificado_para_D`, `nao_verificado_para_D`, `nao_existia_em_D` (os três últimos só em (c); `revogado_vigente` só em (b)). `norma_grande` é propriedade da norma (mais de 300 artigos), igual em todos os casos da mesma norma. `especie` em enum (`lei`, `lei_complementar`, `decreto`, `decreto_lei`, `medida_provisoria`, `emenda_constitucional`, `constituicao`, `resolucao_cvm`, `resolucao_cmn`).

Gabarito documental: o texto é exatamente o dispositivo pedido, inteiro (caput, parágrafos, incisos, alíneas, atravessando páginas), sem rubrica, título ou epígrafe do dispositivo seguinte, sem notas e sem anotação editorial de alteração; o recorte pertence ao ato declarado em `ato_no_documento`. Em (d), anexo é parte que o diploma publica sob a rubrica "Anexo" (tabela, quadro, regulamento aprovado como anexo), citada como tal. Em (e), `alvos` é a lista COMPLETA das remissões expressas no texto, no caminho mais profundo que o texto der (artigo, parágrafo, inciso), cada uma com obra explícita. `nao_verificado_para_D` traz as fontes consultadas e o limite que elas demonstram (um período sem versão oficial identificada, não a ausência de publicação num dia), com trecho normativo real, e, para `sem_versao_oficial_na_data`, a `cadeia` esperada. Fontes admitidas: Câmara (publicação original, texto atualizado), Senado (Dados Abertos, LexML), normas.leg.br, DOU; Planalto só no que o acervo congelado documenta. Sítio não oficial não é fonte.

## 7. Comparação textual (única para validador e apuração)

Normalização: NFC; sequências de espaço, tabulação, NBSP e quebra de linha viram um espaço, com aparas; aspas e apóstrofos tipográficos viram retos; `º` e `°` viram `o` (ordinal tipográfico, que as fontes oficiais grafam de um modo ou de outro). Nada além: nem caixa, nem pontuação, nem numeração. Anotações editoriais de alteração intercaladas na compilada saem da FONTE antes da busca do recorte, reconhecidas só por padrão completo (parêntese que começa por "Redação dada", "Incluído", "Incluída", "Acrescido", "Acrescentado", "Revogado", "Revogada", "Vide", "Vigência", "Produção de efeito", "Renumerado", "Vetado" seguido de referência a ato, ou o marcador "(NR)"); nunca saem do gabarito, que não pode contê-las. Texto riscado sai da fonte por elemento (`strike`, `s`, `del`, com ou sem atributos, ou estilo `line-through`). PDF é extraído página a página; extração indisponível ou inconclusiva reprova o caso.

## 7.1 Validação em duas camadas

O validador mecânico é condição necessária, não suficiente: ele confere forma, integridade dos bytes, recorte, identidade estrutural, esquema, famílias declaradas, independência e mutantes, e deve falhar fechado sempre que não puder decidir (extração inconclusiva, limite ou ato não identificado, padrão não reconhecido). Juízo jurídico que nenhum procedimento mecânico decide com segurança fica na segunda camada, obrigatória e registrada: (i) se o documento aceito é de fato a publicação original ou a versão oficial válida em D; (ii) se a lista de remissões está completa quando o texto contém remissão que o parser não reconhece; (iii) se a documentação de um gabarito histórico negativo demonstra o limite afirmado; (iv) se a família atribuída é o evento normativo correto. A segunda camada é a revisão de mérito de TODOS os casos (não só dos sinalizados), um a um, por revisor independente de quem montou o conjunto, contra as evidências gravadas, incluindo os mutantes gerados; por isso o falso negativo residual do validador não decide sozinho a validade de um caso: no desenvolvimento, o auditor (Codex), com relatório no repositório; na reserva, revisor independente em sessão própria, sob o D6, que comunica ao supervisor só aprovado ou reprovado por caso e entrega o relatório integral ao titular. Caso reprovado na segunda camada sai do conjunto ou é corrigido e revisado de novo. O validador sinaliza com `REVISAO_HUMANA` os casos que dependem de cada um desses juízos.

## 8. Apuração

Executor `scripts/porta_l.py --conjunto <jsonl> --mutantes <jsonl> --home <home> --modo local|remoto --saida <relatorio.json>`, implementado no IL.3, antes da apuração, pelos predicados das seções 1 a 4 (sem rede própria; chama o serviço público). Relatório por capacidade: denominador, acertos, confirmações indevidas, mutantes rejeitados, p95, aprovado ou reprovado por piso. Na reserva, o guardião executa e entrega ao supervisor só a tabela aprovado/reprovado; relatório integral ao titular.

## 9. Congelamento

Esta matriz, o validador, o conjunto de desenvolvimento com mutantes e cobertura, e os hashes da reserva, de seus mutantes e de sua cobertura entram juntos no repositório, antes do primeiro commit de implementação do IL.2, e são registrados no manifesto de aceite na release seguinte.
