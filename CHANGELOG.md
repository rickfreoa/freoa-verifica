# Histórico de versões

## Não lançado (1.4.0)

### Fontes

- Íntegras do STJ (decisão 0044): parser isolado do pacote oficial de íntegras, com vínculo ao espelho por registro, classe composta e número, prova do julgamento lida do texto (órgão, sessão e ementa do espelho), ambiguidade sem escolha, limites de ZIP e hash dos bytes brutos. Ainda não ligado ao acervo nem ao snapshot.
- Íntegras do STJ, abertos do PR #5: a fórmula de abertura só vale antes do marcador `EMENTA`; intervalo de sessão incompleto, data inexistente no calendário ou fim anterior ao início deixam o documento sem prova (I2). O ZIP confronta cabeçalho local, data descriptor e extra ZIP64 com o diretório central e recusa a entrada divergente com motivo contado (I3). Textos órfãos (sem metadado ou sem espelho) são contados em `Resultado.orfaos`, sem vincular (M1).
- Fixtures `tests/fixtures/stj_integras/*` registradas em `FIXTURES.json` como sintéticas (recorte da amostra de 08/10/2026; proveniência da captura original não documentada).

## 1.3.0 — 20/10/2026

Origem: plano `docs/PLANO-1.3.0.md` e comparativo com o juscraper (`docs/auditoria/2026-10-19-comparativo-juscraper.md`). Decisões 0045 a 0057.

### Evidência e contrato

- Indisponibilidade classificada (decisão 0045): `Unavailable` ganha `categoria` e `evidencia`; a saída JSON ganha `categoria` e `evidencia_indisponibilidade` (aditivo). Categorias por prova positiva: `ambiental_desafio`, `fonte_fora`, `recusa_identificado`, `resposta_inesperada` e `regressao`; sem prova, `categoria` é `null`. Testes live: desafio ambiental ou fonte fora, com evidência, viram xfail.
- Contrato JSON 1 (`docs/CONTRATO.md`): campos, estados, nulidade e mudanças aditivas. `CONTRATO_VERSAO = "1"` e campo `contrato` em `listar_fontes` (aditivo).
- Respostas da 1.2.0 congeladas em `tests/contrato/esperado/` (Python, MCP e REST), com teste de compatibilidade que normaliza só os campos voláteis documentados.
- Verificador de contrato compara campos por elemento de lista, tipo e nulidade (B2-05, B3-07).
- Captura reproduzível (decisão 0049): a busca do TJDFT tem origem única (`build_search_payload`); `captura.capturar` monta a requisição pelos `build_*` e a envia por `connector_fetch`; `scripts/capturar_fixture.py` é o caminho para nova captura.
- Fixtures com proveniência (decisão 0052): todo arquivo de `tests/fixtures/` consta de `FIXTURES.json`, com categoria `captura_real` ou `sintetica`.
- Bateria do snapshot (decisão 0057): `fv acervo conferir` confere o acervo em modo somente leitura (contagens por fonte, órgão e mês do STJ, recursos CKAN, pendências do `sync_state`, duplicatas, decisões sem captura, datas fora do recorte, derivados antigos) e compara com manifesto congelado (`--gravar-manifesto`, `--manifesto`; `--estrito` inclui pendências). Sai com 1 em qualquer divergência.
- Bateria, conteúdo × sincronização (decisão 0057, emenda): o manifesto separa `conteudo` (o que o snapshot carrega) e `origem` (`recursos_ckan`, do `sync_state` do produtor); `--pos-instalacao` confere só o conteúdo e exige acervo sem `sync_state`; `--manifesto` sem `sync_state` registra `origem: "nao_aplicavel_pos_instalacao"`. Manifesto antigo continua legível. Corrige a falha de `--manifesto` por `recursos_ckan` após `fv snapshot install`.
- Correções da auditoria do bloco 3: `fv acervo conferir` sem datas herda o recorte do manifesto (B3-02); `--gravar-manifesto` recusa destino dentro do acervo auditado e seus aliases, resolvido antes de abrir o banco (B3-03); a bateria confere existência, tamanho e sha256 dos blobs das capturas, e `--sem-blobs` deixa o resultado `parcial` (saída 2) (B3-04).

### Fontes

- TJDFT: texto integral pela API pública com `retornaInteiroTeor: true` (decisão 0046). Acórdãos passam a trazer a íntegra quando o campo vem preenchido; a regra do fecho decisório vale também para acórdãos.
- TJDFT: a íntegra exige o número CNJ do registro isolado e igual, de 20 dígitos, não substring (B3-06).
- TJDFT: data em `termosAcessorios` não é enviada, porque não há fixture da forma aceita (decisão 0053).
- Filtros de data propagados (decisão 0053): TJDFT filtra localmente, TJSP usa `dt_inicio`/`dt_fim`, STJ filtra em SQL. Cada conector declara em `filtros` o que aplica (`remoto` ou `local`); a resposta traz `filtros_nao_aplicados`.
- Comunica CNJ: não sondado nesta versão; conector previsto para a 1.4.0 (decisão 0047).
- Cobertura do STJ continua limitada ao que é adquirido: íntegras do STJ não estão implementadas (`docs/FONTES.md`).
- Auditoria final, rodada 4 (decisão 0059): o progresso de resposta vale para toda a cadeia de redirecionamentos (F-06, `saltos` na evidência); a semente tem guarda única por chave de requisição em todos os caminhos (F-08); `fontes_consultadas` acompanha as saídas de erro, com `categoria: "regressao"` para erro de programação (F-09); a confirmação CNJ reaproveita a resposta capturada e interrompe o TJSP diante de `Unavailable` (F-10).
- Auditoria final, rodada 5 (decisões 0045 e 0059, emendas FIX9): a classificação da falha de transporte é única (`_classificar` sobre `_EstadoChamada` por chamada lógica): qualquer status ou byte recebido em qualquer salto, inclusive em falha de DNS, validação ou prazo de salto posterior, é `resposta_inesperada`, sem repetição (F-06); erro de leitura ao examinar desafio propaga como `RespostaInvalida` em vez de virar "sem marcador" (F-13); falha de DNS é `fonte_fora`, não política. A semente deduplica a requisição pela identidade efetiva (método + URL normalizada + corpo) em todos os caminhos e não consulta de novo a fonte que desafiou ou recusou (F-08, F-11); os itens de uma ata do CVM Colegiado compartilham uma captura. README com instruções da 1.3.0 e a exigência de attestation (F-12).
- Auditoria final, rodada 6 (decisão 0059, emenda FIX10): a guarda usa a canonicalização de URL do transporte (`identidade_requisicao`: host sem ponto final, porta padrão, `%7E`, fragmento) (F-08); o bloqueio por fonte vale para o host de cada salto que desafiou ou recusou e o transporte consulta a guarda antes de cada salto (F-11); a amostra do corpo de erro é lida em laço até 64 KiB, com marcador entre blocos e framing validado (F-13); o indexador propaga sempre `Unavailable` e a pesquisa textual roda sob guarda por pesquisa, declarando a categoria em `cobertura[].indisponivel` e saindo de `ok` (F-14). README com a regra do `snapshot install` da decisão 0051 (F-12).
- Auditoria final, rodada 7 (decisão 0059, emenda FIX11): framing validado por função única em toda resposta, qualquer status, com leitura chunked estrita (F-13); a guarda registra o desfecho final do conector, depois da reclassificação do Planalto (F-11); a captura guardada é revalidada contra a política da chamada atual (host, caminho, MIME, `max_bytes`, redirecionamentos, desafio) antes de ser entregue (F-16).
- Fallback entre fontes (decisão 0058, revista): na mesma fonte só ausência explícita autoriza a requisição seguinte (F-05, F-07); entre fontes oficiais distintas (Planalto → Senado, TJSP → DataJud) qualquer `Unavailable` permite a próxima, com a indisponibilidade das anteriores em `fontes_consultadas` (aditivo, experimental) e proveniência da fonte que respondeu. Cada fonte é consultada uma vez; erro não-`Unavailable` interrompe. No CNJ, a confirmação pelo DataJud vale como confirmação do processo, nunca como texto do TJSP.
- Captura legada sem cabeçalho (decisão 0065 e emenda, FIX19/FIX19b): captura da 1.2.0 sem Content-Type é relida só dos bytes (`legado_sem_cabecalho`), com a decisão registrada no derivado (migração 015); `DERIVED_VERSION` 5 e `compativel` exige decisão registrada para toda captura reprocessável. Emenda: captura legada sem declaração nos bytes e inválida em UTF-8 admite uma codificação alternativa por fonte (`CODIFICACAO_LEGADA_POR_FONTE = {"planalto": "windows-1252"}`) só se o modelo relido for idêntico ao persistido (hash canônico de dispositivos, textos e rótulos); `legado_padrao_da_fonte_conferido`, com os dois hashes em `parsed_document.interpretacao_conferencia` (migração 016). Divergência ou ausência de modelo anterior: `interpretacao_indisponivel`. O relatório por fonte separa `reprocessadas_legadas_conferidas`; `proveniencia.interpretacao` (experimental) distingue os dois valores.
- Decisão de interpretação obrigatória com ou sem Content-Type (decisão 0066, FIX20/F-26): recibo com Content-Type e decisão nula torna os derivados incompatíveis; `indexar_obra` e `persist_parsed_document` recusam gravar modelo de fonte reprocessável sem decisão (`Unavailable("interpretacao_indisponivel")`, nada gravado); a decisão da releitura legada é gravada na mesma transação do modelo.

### Pesquisa e MCP

- `listar_fontes`: capacidade, recorte do acervo instalado e tipos de documento (decisão 0056).
- Instruções do servidor MCP com fluxo em quatro passos e descrições por ferramenta, com estados possíveis e recorte; testes do texto exposto (decisão 0056).
- Bloco `cobertura` em `pesquisar_jurisprudencia`, por tribunal, com truncamento remoto. `CandidateList.total` é `int | None` e `total_exato` declara se o total é exato, cota inferior ou desconhecido (decisão 0055).

### Saúde das fontes

- Os testes live gravam `saude-fontes.json` ao fim da sessão: `commit`, `inicio`, `fim`, `completa` e, por fonte, `estado` (`ok`, `unavailable`, `regressao`, `not_run`), `categoria`, `motivo` e testes (decisão 0054).
- Desafio ambiental ou fonte fora, com evidência, vira xfail; regressão e recusa ao identificado seguem como falha.
- O workflow semanal `saude-das-fontes` não mascara o resultado. A issue viva guarda `run_id` e início; execução posterior não grava sobre a anterior (B2-07, B2-08).

### Transporte

- User-Agent identificado em todos os conectores, sem exceção (decisão 0048): `freoa-verifica/<versão> (+https://github.com/rickfreoa/freoa-verifica)`, de fonte única. A string de navegador da 1.2.0 e o modo `navegador_1_2_0` foram removidos.
- Planalto: falha de transporte anterior a qualquer resposta vira `unavailable(recusa_identificado_planalto)`, categoria `recusa_identificado`, sem nova tentativa com outro UA. Respostas HTTP (5xx etc.) seguem a classificação geral.
- Timeout depois do status ou do primeiro byte do corpo é `resposta_inesperada`, não `fonte_fora` (B3-01). Falha de protocolo com resposta recebida (tipo inválido, framing, tamanho acima do limite) segue o mesmo caminho (decisão 0045, emenda FIX1). Prazo vencido depois do status 200 é `RespostaInvalida` (B3-01).
- `detect_challenge` não infere desafio por 202 com corpo vazio sem cabeçalho de borda ou assinatura (A11).

### Distribuição e CI

- Dependências de CI e de build vêm de locks com hashes (`requirements/ci.lock`, `build.lock`, `lint.lock`), instaladas com `--require-hashes`; a wheel entra com `--no-deps`. `scripts/atualizar_lock.{sh,ps1}` regeram os locks (decisão 0050).
- Matriz de testes em Python 3.11 a 3.14, em Ubuntu e Windows. Testes que leem o checkout são marcados `repositorio`. Ruff com baseline e catraca.
- `release.yml` cria a release como rascunho e não publica na PyPI; `pypi.yml` roda depois da publicação (decisão 0050).
- Instalador Windows: `-Versao` com padrão `1.3.0`; attestation obrigatória. `gh` ausente ou verificação falha aborta a instalação. `-SemAttestation` é explícito e grava `attestation_verificada: false`. Sucesso grava `instalacao.json` com versão, `sha256_wheel`, digest do snapshot e attestation (decisão 0051).
- `fv snapshot install` sem `--arquivo` consulta só a release `v<versão>`. Release ausente, rascunho ou sem o asset da versão falha com motivo explícito, sem busca em releases anteriores (decisão 0051).

### Mudanças incompatíveis e perdas declaradas

- Motivos de indisponibilidade: `desafio_http_403` passa a `http_403` (e `http_401` é novo); `desafio_corpo_vazio` passa a `corpo_vazio`. `desafio_<tipo>` fica só para assinatura identificada (decisão 0045).
- `CandidateList.total` desconhecido sai como `null`, não como o número de itens lidos (decisão 0055).
- **Planalto ao vivo indisponível:** o Planalto encerra a conexão do cliente identificado sem responder (decisão 0048). A atualização ao vivo da legislação federal fica indisponível até o Planalto aceitar o cliente identificado; a captura federal ao vivo passa ao Senado, que aceita o cliente identificado, com a recusa do Planalto declarada em `fontes_consultadas` (decisão 0058). O acervo instalado não foi alterado e continua atendendo consultas sem rede.
- Release passa a rascunho até a auditoria dos bytes publicados; a publicação na PyPI só ocorre depois da publicação da release (decisão 0050).
- Instalador exige attestation; a instalação sem verificação só ocorre com `-SemAttestation` explícito (decisão 0051).

## 1.2.0 (19/10/2026)

Responde à avaliação externa de 18/10/2026 (achados A1–A12; plano em `docs/PLANO-1.2.0.md`).

- A descrição da prova corresponde ao documento entregue (decisão 0038). `obter_decisao` nunca entrega outro documento sob o rótulo da parte pedida (`parte_indisponivel`, `parte_solicitada`, `parte_entregue`, `partes_disponiveis`); identificador oficial repetido em tribunais distintos é `ambiguous` e aceita `tribunal`; ausência no banco é `nao_encontrado_no_acervo` com `escopo: acervo_local`, nunca `inexistente`. Espécie declarada pela fonte prevalece (monocrática nunca rotulada como acórdão, inclusive no filtro `autoridade_min`); inteiro teor só por declaração do perfil, não por comprimento. `DERIVED_VERSION` 4: a reconstrução recalcula a autoridade gravada (Colegiado da CVM estava em D; passa a E) e tira o falso inteiro teor de súmulas.
- Conector TJDFT sobre a API pública oficial de jurisprudência (decisão 0041): ementa capturada de acórdãos; texto integral de decisões monocráticas e da presidência só quando traz o cabeçalho do mesmo processo; segredo de justiça descartado; semente temática societária.
- Parsers em processo isolado com limites em todos os perfis (decisão 0042): Planalto e BCB também passam pelo filho; Job Object no Windows (memória, CPU, sem descendentes), `RLIMIT` no POSIX, tetos de entrada e saída, grupo de processos próprio, `-P`; falha ao instalar limites é quarentena. Rede, sistema de arquivos e privilégios do filho não são contidos: serviço remoto exige contêiner (SECURITY.md).
- Snapshot vinculado ao pacote (decisão 0042): `data/snapshots-oficiais.json`; fora da lista só com `--aceitar-nao-vinculado`, e o acervo fica `vinculado: false` de forma permanente (`fv snapshot info`, `fv doctor`); `latest` escolhe o snapshot vinculado. `fv snapshot install` sai com código 1 em recusa.
- Reconhecimento de consultas (decisão 0043): número citado com UF acha registro sem UF (e declara `uf_citada_nao_conferida`); classe comparada sem acento ("Sumula" casa "Súmula"); número CNJ isolado devolve só o próprio processo, com dígito verificador conferido e consulta à API oficial do TJDFT; "<norma> art. N" sem vírgula, na citação avulsa, é exato; `verificar_citacao` de súmula, julgado ou CNJ usa a confirmação do acervo (antes, `not_found`).
- Busca temática: sigla de tribunal solta na consulta vira filtro (fora de aspas); raridade do termo (IDF) ordena a complementação OR; termos na ementa pesam mais que termos espalhados no inteiro teor; TJDFT pedido explicitamente é consultado ao vivo, com locuções jurídicas entre aspas (`locucoes-1`); resultado sem ementa mostra `trecho_inteiro_teor` em torno do termo, nunca sob o rótulo `ementa`.
- Comparativo com o JusRatio sobre conjunto-ouro independente de 42 casos (`docs/auditoria/comparativo-120/`): dentro do acervo, 34/35 contra 35/35; não temáticos 28/28 nos dois; resultados temáticos úteis 33/35 nos dois; nenhuma confirmação indevida.
- Cobertura do STJ declara só o que é adquirido (íntegras não implementadas). README e FONTES descrevem só o estado atual.
- Instalador Windows interrompe na etapa que falhar e só declara sucesso após conferir versão, acervo vinculado e `fv doctor`; verifica a attestation do wheel e do lock com `gh` (workflow de release, tag e runners hospedados) e registra quando não pôde verificar. Release: permissões mínimas na suíte, escrita só no build, tag conferida contra a versão, lock e `SHA256SUMS` atestados.
- Atualização sem limpar checkpoint (decisão 0039): recursos mensais do STJ são revalidados (dois meses mais recentes e capturas com mais de 30 dias; metadado CKAN alterado invalida o checkpoint), `fv doctor` informa `stj_atualizacao`; súmulas e SV do STF são recapturadas após 30 dias.
- REST e MCP HTTP sem token validam `Host` (127.0.0.1, localhost, [::1]) e `Origin` com parsing estrito; `Origin` externo é recusado também com token, salvo `FV_API_ORIGENS` (decisão 0040). Cliente local que envie outro `Host` (proxy, túnel) precisa usar token.
- Registro minimizado por padrão (decisão 0040): `sem_conteudo` passa a ser o padrão (`completo` só com `--registro-completo`/`FV_REGISTRO=completo`); hashes de entrada viram HMAC-SHA256 com segredo por home (`registro.key`, prefixo `hmac1:`); `fv runs purgar --apagar-original`. Execuções antigas gravadas em `completo` ficam até a purga.
- Correções da auditoria da decisão 0040: trava de home entre processos (purga, instalação de snapshot e reconstrução recusam com `HOME_EM_USO_POR_OUTRO_PROCESSO` se outro processo usa o home; checkpoint WAL ocupado também recusa); `access_log` do uvicorn desligado (citação na query string); `FV_API_ORIGENS` normalizada e validada (não é CORS); token não-ASCII responde 401; MCP HTTP e REST aceitam os mesmos `Host`; `registro.key` com cache, criação atômica e `CHAVE_REGISTRO_AUSENTE` em vez de regeneração silenciosa; `--apagar-original` grava o registro antes de apagar e devolve `apagados`/`falhas`; `X-Forwarded-For`/`Forwarded` conferidos em `fronteira.validar`.

## 1.1.0 (18/10/2026)

- Texto coletado é dado, nunca instrução (sanitização de saída): o envelope `DOCUMENTO OFICIAL` é sempre aplicado e os delimitadores que apareçam dentro do próprio documento são neutralizados (antes, um documento que contivesse o delimitador de abertura saía sem envelope e podia "fechá-lo"); toda resposta MCP e REST passa por triagem de padrões de prompt injection (portados do `freoa-document-sanitizer` do FREOA) e de caracteres invisíveis/bidi, sinalizados em `alertas_conteudo` sem alterar o texto oficial. Token REST comparado em tempo constante.
- PDFs de decisões do STF e do TJSP passam a ser lidos no processo isolado (antes, no processo do servidor); falha, excesso ou timeout viram `unavailable(pdf_nao_processado)`, nunca texto vazio.
- Normas da CVM em PDF ganham dispositivos endereçáveis (`cvm-pdf-2`): cabeçalho e rodapé saem por geometria e repetição (só o bloco contíguo a partir da borda da página), sumário é descartado, as notas "• ... com redação dada / incluído / revogado pela Resolução CVM nº X" viram anotações do dispositivo (redação vigente, anterior e revogação), e o texto que outra norma "passa a vigorar com a seguinte redação" até "(N.R.)" fica como citação. Dispositivo junto a margem descartada fica unknown/MARGEM_ADJACENTE; duplicidades remanescentes ficam `ambiguous`, sem `verified`. Issue `ESTRUTURA_INFERIDA_PDF`. Na Resolução CVM 175 (parte geral): 143 artigos, 801 dispositivos, 6 ambíguos.
- Data de efeito declarada pelo BCB (decisão 0035): entrada única "Revogação total a partir de D/M/AAAA" em `Atualizacoes` vira `data_efeito`; antes dela, o ato responde vigente com `REVOGACAO_POSTERIOR`; depois, `OBRA_REVOGADA_NA_FONTE`. Sem data declarada, registra-se só o ato revogador e a data continua desconhecida.
- Situação cadastral: falha de transporte na releitura não apaga leitura autêntica anterior (ela envelhece sozinha em 30 dias); `ressincronizar` informa `falhas_com_leitura_preservada`. Ritmo do BCB reduzido a 0,2 req/s por host (`FV_RATE_LIMIT_BCB`).
- Jurisprudência (decisão 0036): `fv sync` ingere os precedentes qualificados do STJ (Tema e IAC, autoridade B) e as súmulas e súmulas vinculantes do STF (portal oficial, autoridade A), com situação estruturada; precedente cancelado ou superado sai com `PRECEDENTE_NAO_VIGENTE_NA_FONTE`. Semente STJ ampliada a sete órgãos não criminais e 24 meses.
- `fv bench`: o caso pode declarar `data`; toda dimensão declarada em `expectativa` é confrontada sem apagar as obrigações das demais; indisponibilidade só conta como acerto quando esperada na própria dimensão.
- Publicação no PyPI por Trusted Publishing preparada no workflow de release (desligada até o cadastro do publicador e `PYPI_PUBLICAR=true`).

## 1.0.3 (18/10/2026)

- Monotonia estrutural (decisão 0034): captura de texto compilado que perde dispositivos do modelo canônico não é promovida (`PERDA_ESTRUTURAL` em `divergentes` de reprocessar, reconstruir e instalar snapshot); `pode_negar` não nega caminho de captura canônica anterior (`ESTRUTURA_DIVERGENTE_ENTRE_CAPTURAS`).
- ADCT com escopo próprio (`adct/artN`) no parser do Planalto (`parser_version` 1.2.3), sentinela `SCOPE_COLLISION` contra substituição entre escopos e extração de "art. N do ADCT" (decisão 0022).
- Negativa de dispositivo exige estrutura (decisão 0023): `pode_negar` único em todos os consumidores; obra não capturada é `COBERTURA`, documento cortado, em quarentena ou sem dispositivos estruturados (PDF da CVM) é `unknown` com motivo, nunca `inexistente`. "caput" usa a resolução canônica.
- Histórico ausente (decisão 0024): data sem redação selecionada não confronta nem devolve a redação atual como se fosse da data (`HISTORICO_ANTERIOR_AUSENTE`; `texto=null` e `texto_atual` rotulado); `redacoes_anteriores` exclui a vigente; `redacao_anterior_ausente_na_fonte`.
- `verificar_texto` lista remissões anafóricas como `referencia_nao_resolvida` e informa `total_detectado`, `total_processado` e `truncado` acima de 200 citações.
- Recibo final (decisão 0027): o recibo é gravado depois de todos os rebaixamentos e coincide com a resposta; `verificar_citacao` aplica o bloqueio de confiança de extração (corrige "Lei 6.404/1976: art. 117 do contrato" verified).
- Data do ato alterador extraída da epígrafe já capturada quando o Senado não fornece a data; só preenche a data completa, nunca inventa, e data inválida fica sem valor (M8).
- Coluna `rubrica` no índice FTS de redações (migração 006, preserva as linhas existentes); o parser do Planalto captura a rubrica (linha centrada antes do "Art.") em `Provision.rubrica` e ela alimenta a coluna: "dever de lealdade" acha o art. 155 da LSA. Modelos persistidos sem o campo continuam carregando (M11).
- Rótulos CVM com mojibake (UTF-8 lido como latin-1) são corrigidos ao gravar e ao instalar snapshot, só quando a reversão é UTF-8 válido e reduz caracteres suspeitos (M11).
- Situação da obra (C2, decisão 0021): tabela `work_status` alimentada pela página do ato CVM (sempre capturada) e pelos campos `Revogado`/`Cancelado` do BCB/CMN. Ato revogado ou cancelado deixa de sair `vigente_na_fonte` (`OBRA_REVOGADA_NA_FONTE`, inclusive em citação só da obra); data passada sem `data_efeito` é `unknown REVOGACAO_DATA_DESCONHECIDA`; revogação futura preserva a análise e marca `REVOGACAO_POSTERIOR`; situação ilegível ou com mais de 30 dias nunca é vigente. A página do ato CVM deixou de presumir vigência. `Verifica.ressincronizar_situacao()` relê o acervo.
- Busca CVM: decodificação UTF-8 correta (consultas acentuadas), sem exigir a frase literal, `unavailable` quando a fonte informa total > 0 e nada é lido, um item por ato (anexos duplicados descartados) e espécie acompanhando o número ("Instrução CVM 358"). Busca CVM/BCB informa `truncado` pelo total da fonte.
- BCB/CMN: "Resolução CMN 4.966" na consulta aciona o lookup exato por número.
- `fv acervo ressincronizar-situacao` relê a situação dos atos CVM/BCB/CMN. Conectores devolvem `CandidateList` com `total` e `truncado` reais (A9); `buscar_normas_*` e `buscar_legislacao` os repassam. Migrações em sequência: 006 rubrica, 007 `work_status`, 008 `fts_staging`.
- PDF da CVM roda em processo isolado com limites de tempo, memória, páginas e texto (decisão 0029).
- Busca (frente F-D, decisão 0025): consulta que é só classe e número (`REsp 2.210.785`, `Recurso Especial nº ...`) faz lookup exato no acervo; achado traz evidência, incidentes do mesmo processo vão em `relacionados` e ausência devolve `nao_confirmado_no_acervo` com a cobertura (tribunais, órgãos, período), sem outros processos.
- Candidatos de legislação indexados ao vivo ficam em `fts_staging` (migração 008), fora do FTS canônico; só a busca que consulta fontes ao vivo os vê, marcados `candidato_ao_vivo`.
- Fontes não consultadas (offline, limite atingido, sem busca textual como o Planalto) aparecem como `nao_consultada`; `truncado` e `total` por fonte são propagados quando o conector os informa.
- Filtro `fonte` da busca local de legislação é aplicado antes do limite.
- Ranking: MATCH de decisões restrito a ementa e inteiro teor, bm25 ponderado (ementa 5, inteiro teor 1), `pertinencia` e `correspondencia` em cada item, corte de dois terços dos termos e OR completando AND escasso (substitui "OR só com AND vazio" da 0010).
- Tesauro jurídico `tesauro-1` (20 pares determinísticos, `freoa_verifica/data/tesauro-1.json`) expande a consulta por OR; a versão e as expansões saem na resposta.
- Fronteiras remotas (decisão 0026): modo local/remoto explícito na API REST e no MCP HTTP; token obrigatório fora de loopback, verificado em toda requisição, inclusive ao carregar a fábrica ASGI diretamente.
- Validação de entrada compartilhada na fachada (tipos e tetos), corpo HTTP limitado antes da leitura integral, semáforo para operações caras; entrada inválida devolve 422, excesso de corpo 413, sobrecarga 503.
- Âncora textual: o intervalo devolvido é validado contra o trecho casado; sem prova, a âncora é recusada em vez de apontar caracteres errados (NFC, múltiplas composições).
- Conexões SQLite com dono registrado, fechamento coordenado e falhas registradas em log; a instalação de snapshot e a purga esperam as operações ativas.
- MCP: um serviço por home no mesmo processo.
- Política de registro `sem_conteudo` (`--sem-registro`) e `fv runs purgar --antes DATA` (decisão 0030).
- Snapshot publica identificadores das obras e das decisões e `derived_version`; `fv doctor`, o MCP e a API avisam `acervo_incompleto` quando o home está abaixo do manifesto instalado ou do mínimo embutido.
- Release só publica após a suíte completa no mesmo commit, sem substituição de assets, com `requirements-lock.txt` anexado. Actions fixadas por SHA de commit (tag em comentário).

- Derivados versionados (C6, decisão 0028): `DERIVED_VERSION` em `meta` (migração 009); home de versão anterior responde `indisponivel/ACERVO_DESATUALIZADO`; `fv acervo reconstruir [--com-situacao]` refaz modelo, dispositivos, redações e FTS numa cópia e troca o banco atomicamente; a instalação de snapshot com derivados mais novos substitui os modelos locais; o manifesto leva a `derived_version` real. Dispositivos novos de um modelo reprocessado passam a ser gravados e os antigos removidos.

- Purga de execuções em ordem segura (banco novo gravado em disco, original movido, novo instalado) com recuperação automática de troca interrompida (decisão 0030).

- Normas de série única citadas sem ano ("Resolução CMN 4.966", "Resolução BCB 428", "Resolução CVM 80", "Instrução CVM 358") são tratadas como exatas quando o acervo tem exatamente uma obra com o número; com zero ou mais de uma, ou para lei sem ano, seguem exigindo conferência (decisão 0031).

## 1.0.2

- Extração de citações em duas camadas: regras estruturais (numeração decimal de cláusulas, siglas coladas a números, pertença a instrumentos particulares, fronteiras de arquivo e de campo técnico) e confiança explícita `exata`/`provavel`. Em `verificar_texto`, citações `provavel` recebem `requer_conferencia`; só `exata` recebe `encontrada` ou `inexistente`. Nos oito corpora adversariais independentes (779 frases), falsos definitivos caíram de 250 para 0 e o recall subiu de 70,9% para 93,7%.
- Associação de dispositivo posterior exige vírgula ou travessão na mesma oração e rejeita dispositivos de instrumentos particulares; reconhece `Instr. CVM`, `Inst. CVM` e `IN CVM`.
- Corpus literal de 80 frases e controles de fronteira sintática cobrem as regressões de identidade.
- Staging de snapshots fica no diretório de dados, configurável por `FV_STAGING_DIR`, com testes isolados em `tmp_path`.
- Extração em prosa preserva o ponto de aliases como `Lei das S.A.`, aceita quebras de linha e dispositivos abreviados com `inc.` e `al.`.
- Artigos e preposições anteriores à norma não são tratados como alíneas isoladas; dispositivos após a norma, separados por vírgula, são associados corretamente.
- Trechos entre aspas após abreviações são confrontados, e listas de artigos verificam cada dispositivo extraído.
- Corpus independente de 118 frases sintéticas cobre pontuação, abreviações, listas, remissões não resolvidas e controles negativos.
- Instalação de snapshot mantém a seleção da última release que contenha esse asset, mesmo quando releases posteriores só distribuam o pacote.

- `FV_READ_ONLY=1` permite verificar normas no acervo instalado sem gravações no banco ou captura sob demanda.

## 1.0.1

- Pesquisa primeiro no acervo instalado de decisões de todos os tribunais, com FTS reconstruído na exportação/instalação, ranking bm25, desempate por autoridade/data e filtros SQL antes da paginação.

- Instalação de snapshots com download em fluxo, publicação atômica do arquivo e conferência de SHA-256 antes da extração; seleção da release mais recente com snapshot.
- `verificar_texto` preserva `formato_invalido` e exige evidência de negativa oficial para informar `inexistente`.

## 1.0.0

Primeira versão pública.

- Verificação de citações em quatro dimensões (identidade, texto, tempo, suporte), com evidência reproduzível: URL oficial, data de captura, SHA-256, caminho do dispositivo e trecho.
- Legislação federal (Planalto, com datas dos atos alteradores via Senado), normas da CVM (consolidados oficiais com redações anteriores e notas datadas) e do CMN/BCB.
- Jurisprudência e decisões administrativas: STJ (dados abertos), STF (portal de processos, decisões e Repercussão Geral), TJSP, TCU, Colegiado da CVM; metadados processuais pelo DataJud.
- `verificar_texto`: extrai todas as citações de um texto e informa, uma a uma, se existem.
- Motor temporal por eventos, com estados `verified`, `vigente_na_fonte`, `unknown`, `revogado`, `nao_existia` e `ambiguous`.
- Servidor MCP (stdio e streamable HTTP), CLI `fv` e API REST.
- Corpus semente distribuído como snapshot verificável.
