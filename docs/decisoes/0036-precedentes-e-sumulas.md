# 0036 - Precedentes qualificados do STJ e súmulas do STF no índice local

Data: 18/10/2026. Marco P5.

`fv sync stj` passa a ingerir `Temas.csv` e `Processos.csv` (CKAN `precedentes-qualificados`) e `fv sync stf` passa a ingerir o sumário e as páginas de súmula e súmula vinculante do portal. Tudo vai ao índice já usado por `pesquisar_jurisprudencia` (FTS do STJ; tabelas `decision` e FTS de decisões para ambos), sem nova tabela e sem novo rótulo.

- Autoridade: nenhuma regra de `authority.py` muda. Tema (repetitivo) e IAC chegam com classe "Tema Repetitivo"/"IAC" e saem B; súmula e súmula vinculante do STF saem A.
- Situação não rebaixa rótulo, mas é campo estruturado. O rótulo A/B mede espécie, não vigência. Cada item de `pesquisar_jurisprudencia` e o retorno de `obter_decisao` trazem `situacao_precedente = {valor, texto_oficial}` com `valor` em vigente|cancelada|superada|revisada|desconhecida. O campo é gravado em `decision.authority_attrs_json` (sem migração; sobrevive a reabrir o banco e a exportar/instalar snapshot) e atualizado a cada nova captura da mesma decisão. Quando o valor é cancelada, superada ou revisada, o item traz o alerta `PRECEDENTE_NAO_VIGENTE_NA_FONTE`. Ausência de situação é `desconhecida`, nunca vigente.
- Mapeamento STJ (campo `situacao` do CSV): contém "cancel" -> cancelada; "revis" -> revisada; "supera" -> superada; "Trânsito em Julgado" e "Acórdão Publicado..." -> vigente; qualquer outro (Afetado, Em Julgamento, Sobrestado, vazio) -> desconhecida, com o texto oficial preservado. STF: a observação do título ("cancelada", "superada") é o valor; súmula sem observação fica `desconhecida`, porque a ausência de marca na página não demonstra vigência.
- Linhas repetidas no CSV do STJ: a política é a mesma no sync e na releitura da captura (a última linha da chave vale). Se as linhas repetidas divergem em tese ou situação, o documento registra "Divergência na fonte" no texto e o item traz o alerta `LINHAS_DIVERGENTES_NA_FONTE`.
- Prova: o CSV (ou a página) capturado com hash é o documento; o texto indexado deriva só dele. Os processos paradigma vêm de `Processos.csv`, captura distinta, e não entram no texto probatório: ficam no payload do índice como `processosParadigmaNaoAutenticados` (metadado, ignorado pelo parser).
- Falha: recurso ausente, página fora do formato ou erro de rede viram `unavailable(motivo)` no `sync_state`; nenhum sumário vazio é aceito como "sem súmulas".
- Escopo STJ: só `Tema` e `IAC`. Controvérsia (ainda não é precedente), SIRDR e PUIL ficam de fora até decisão própria.
- A chave `stj_precedentes_qualificados` do corpus semente passa de `false` para `true`.
