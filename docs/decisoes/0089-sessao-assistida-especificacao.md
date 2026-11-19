# 0089 - Sessão assistida: especificação do mecanismo; emenda à 0067

**Situação: proposta, não vigente.** Versão 3, submetida à rodada 3 de 3 (D5). O titular escolheu em 19/11/2026 a
opção A da bifurcação da v2 (pendência 33): bytes recebidos pela conexão do próprio navegador, com validação
declarada e prova de origem de rede. A v1, a v2, os pareceres e o teste exploratório estão em
`docs/auditoria/0089/`. Não implementar antes do parecer da rodada 3.

19/11/2026. Supervisor (Opus), sob a autorização do titular (plano 1.4, seção 9, item 5) e a ordem da 0087
§2.1(a). Especifica o mecanismo que a 0067 §1 admitiu e emenda, só para a sessão assistida, o quarto item da regra
3 da 0067 (§2.1). Não altera as regras invariáveis 1 a 9, o critério de `verified`, a 0002, a 0060 a 0066 no fluxo
automático, a matriz, os pisos nem a reserva. A mudança de contrato é só aditiva (§2.10). A implementação toca
`transport` e exige auditoria própria (D5).

## 1. Fato e problema

As capacidades reprovadas da Porta L e o TJSP dependem de fontes que recusam o cliente automatizado: o Planalto
recusa o UA identificado (0048), normas.leg.br responde 403 com CAPTCHA (0085), o NPL reinicia a conexão de
clientes não navegador mesmo com UA de navegador, e o DOU em formato aberto desemboca em host barrado (estado de
19/11). A barreira do NPL discrimina o tipo de cliente, não o nome declarado.

Daí a bifurcação da v2. Toda arquitetura em que o transporte faz a requisição a montante ou é recusada por essa
barreira, ou precisa emprestar a identidade do navegador, o que a regra 3 veda (Codex r2, achado 9). Os bytes têm
de vir da conexão do próprio navegador. Mas a 0067 exige que a porta única aplique "as mesmas validações do fluxo
automático", e algumas delas pressupõem que o transporte é dono do soquete: framing estrito, conexão ao IP
resolvido pela ferramenta, taxa mínima de leitura, recusa de Content-Encoding (Codex r1, achados 1 e 2). Sem
emenda, a sessão assistida contrariaria a letra da 0067; com a emenda, cada validação passa a ter regra declarada.

O teste exploratório de 19/11 (`docs/auditoria/0089/teste-exploratorio-2026-11-19.md`) mostrou que o caminho é
viável: o navegador obteve Planalto, NPL e normas.leg.br sem desafio, e os eventos de rede do Chrome provaram
resposta a resposta que nada veio de cache, service worker ou prefetch. Mostrou também seis fatos que esta versão
incorpora: injeção variável do WAF F5 no Planalto; texto de normas.leg.br entregue por XHR; corpo decodificado
quando há compressão; política corporativa do navegador ativa no perfil dedicado; necessidade de filtrar antes de
gravar; e 502 do host clássico novo também ao navegador.

## 2. Decisão

### 2.1 Emenda à 0067

O quarto item da regra 3 da 0067 (regra 4 e porta única) passa a ter esta redação:

> regra 4: o navegador da sessão só é usado pelo humano; a captura entra no sistema exclusivamente pela porta única
> de `freoa_verifica.transport` (`transport.capturar_assistida`); nenhum conector ou parser lê bytes do navegador
> por outro caminho. Na sessão assistida, os bytes capturados são os recebidos pela conexão do próprio navegador
> dedicado, e a porta aplica a cada resposta a matriz de validação da 0089 §2.4: cada validação do fluxo
> automático é aplicada igual, aplicada sobre os metadados de rede do navegador, ou substituída por validação
> declarada, e a que não tiver dado suficiente causa recusa. Só vira captura resposta cuja origem de rede o
> navegador prove (nunca de cache, service worker, prefetch, 304 ou 206). A ferramenta não altera as requisições
> do navegador e nunca usa a identidade dele em requisição própria. No fluxo automático nada muda.

A 0067 recebe, no PR desta decisão, nota de topo que remete a esta emenda. A redação da regra 3 em `AGENTS.md`
(linha 20) não muda: já diz que, na sessão assistida, "a ferramenta captura os bytes".

### 2.2 Arquitetura: o navegador faz as trocas; a ferramenta observa

1. `fv sessao <fonte> [--alvo URL]` (CLI) é o único início. Exige terminal interativo; recusa execução sem TTY,
   agendada, por script de bateria ou pelo MCP. Antes de abrir, mostra a fonte, o alvo público sanitizado (§2.7)
   e o aviso da §2.8, e exige confirmação interativa para aquela sessão e aquele alvo.
2. **Navegador.** Chrome ou Edge **instalados**, lançados pelo adaptador com argumentos mínimos: perfil temporário
   novo (`--user-data-dir` no diretório da sessão, §2.7), sem sincronização, sem primeira execução, janela
   visível. Controle por pipe (`--remote-debugging-pipe`; no Windows, `--remote-debugging-io-pipes`). Porta TCP de
   depuração só se o teste do adaptador provar o pipe inviável no Windows; nesse caso, porta efêmera em
   127.0.0.1, com o risco declarado de que outro processo local pode anexar-se enquanto a sessão estiver aberta.
   Nunca: Playwright ou outro automatizador, `--enable-automation`, modo sem janela, `--ignore-certificate-errors`,
   exceção SPKI, proxy da ferramenta, extensão da ferramenta.
3. **Políticas de máquina.** Antes de mostrar o alvo, o adaptador lê as políticas efetivas na página interna
   `chrome://policy` (sem rede). Política que fixe proxy: a sessão não abre (o IP remoto seria o do proxy, não o
   da fonte). Política que force extensões ou páginas de início e de nova aba: a sessão abre, e o recibo da sessão
   registra só a existência da política e o identificador e a versão de cada extensão forçada; nenhum endereço ou
   valor de política é gravado. O teste exploratório mostrou que a política do escritório abre o SharePoint e o
   login corporativo em cada aba nova (achado 5); a §2.2(5) impede que isso entre em qualquer registro.
4. **Observação passiva.** Para cada alvo anexado (página, quadro, worker), o adaptador ativa os domínios
   `Network`, `Page` e `Target`, e só três comandos de configuração: `Network.setCacheDisabled(true)`,
   `Network.setBypassServiceWorker(true)` e `Browser.setDownloadBehavior(deny)`. Não altera requisição
   (`Fetch.continueRequest` com mudança, `Network.setExtraHTTPHeaders`, `Emulation.setUserAgentOverride` e afins
   ficam fora da lista fechada de métodos CDP permitidos), não navega, não injeta script, não clica.
5. **Filtro na origem.** Evento de host fora das origens da fonte (§2.11) é descartado em memória antes de qualquer
   gravação. Evento sem URL (cabeçalhos brutos) só é retido quando se associa, pelo `requestId`, a pedido de origem
   da fonte. Nada de terceiros (provedor de CAPTCHA, CDN alheia, analytics, SSO corporativo) é persistido, nem em
   log de depuração.
6. **Porta única.** O adaptador entrega a `transport.capturar_assistida` um evento de resposta com os dados da
   §2.4; só a porta decide se há captura. Conectores e parsers leem apenas capturas já aceitas.

### 2.3 O que vira captura

Vira captura só a resposta que cumprir, cumulativamente:

1. **Troca de rede provada pelo navegador:** `Network.responseReceived` com `fromDiskCache`, `fromServiceWorker` e
   `fromPrefetchCache` falsos; nenhum `Network.requestServedFromCache` para o pedido; `remoteIPAddress` e
   `securityDetails` presentes; `Network.loadingFinished` (não `loadingFailed`); alvo de página que não seja
   pré-renderização; status 200. 304, 206 e os demais status nunca viram captura.
2. Método `GET`; sem `Authorization` na requisição (lida em memória, nunca gravada). `POST` fica para decisão
   própria (§5).
3. **Recurso admitido pelo perfil** (§2.11): `Document` de quadro principal, ou recurso `XHR`/`Fetch` declarado
   para aquela fonte (normas.leg.br entrega o texto por XHR, achado 3 do teste); host, prefixo de caminho,
   parâmetros de query e padrão de cada valor conforme o perfil; fragmento descartado; esquema só `https`
   (`blob:`, `data:`, `filesystem:` e semelhantes recusados).
4. Media type declarado no perfil para aquele recurso.
5. Todas as linhas da matriz da §2.4 aprovadas.

**Vínculo.** A captura é atribuída à sua própria URL validada e aos seus próprios eventos, nunca ao alvo sugerido
nem à navegação anterior. Navegação iniciada por conteúdo (script, meta refresh, janela aberta pela página) é
navegação nova, validada por si; não herda cadeia nem atribuição de outra. O alvo sugerido só orienta o humano
(Terra r1, achado 2).

As demais respostas passam ao navegador sem interferência e nunca são persistidas. Recusa de captura é listada ao
humano com URL sanitizada e código.

### 2.4 Matriz de validação

Exaustiva quanto às validações do fluxo automático em `freoa_verifica/transport.py` (`35dd8bc`). "Igual" = mesma
regra e mesmo código de recusa; "metadados" = mesma regra aplicada a dado de rede do navegador; "declarada" =
regra substituta aprovada por esta emenda. Dado necessário ausente ou ambíguo causa recusa, nunca inferência
(Codex r1, achado 2; Terra r1, achado 10).

| # | Validação automática | Na sessão assistida | Dado do navegador (CDP) | Recusa |
|---|---|---|---|---|
| 1 | URL ASCII, `https`, host permitido, porta 443, caminho não ambíguo, prefixos (`validate_reference`, `_path_allowed`) | Igual, sobre a URL da resposta e de cada salto | `request.url`, `response.url` | `BlockedHost` |
| 2 | DNS pela ferramenta, só IP público unicast (`validate_url`, `_public_unicast`), conexão ao IP validado | Metadados: o IP efetivo da conexão que entregou os bytes deve ser público unicast pela mesma função. Declarada: a resolução é do navegador; a prova é o IP observado, não a resolução prévia | `remoteIPAddress`, `remotePort` = 443 | `BlockedHost` |
| 3 | TLS verificado pelo contexto padrão | Metadados: navegador sem exceção de certificado (§2.2(2)); exige `securityDetails` presente, protocolo TLS 1.2 ou 1.3 e `securityState` seguro | `securityDetails`, `securityState` | `RespostaInvalida` |
| 4 | Framing estrito (`_validar_framing`): sintaxe de campos, só `chunked`, Content-Length válido e único, sem conflito | Declarada: o parser HTTP do navegador recusa Content-Length múltiplo ou conflitante (vira `loadingFailed`); a porta confere nos cabeçalhos brutos, com multiplicidade, Content-Length único e numérico e Transfer-Encoding ausente ou `chunked`. Sintaxe da linha de status e dos campos não é observável; HTTP/2 e HTTP/3 têm framing próprio, aplicado pelo navegador; o protocolo vai ao recibo | `responseReceivedExtraInfo.headers`, `response.protocol` | `RespostaInvalida` |
| 5 | Content-Encoding ausente ou `identity`, em todo status (0060) | Declarada (emenda): admitidos ausente, `identity`, `gzip`, `deflate`, `br` e `zstd`, decodificados pelo navegador; outra codificação é recusada. A codificação original vai ao recibo; o hash é dos bytes decodificados (§2.5) | cabeçalhos brutos | `RespostaInvalida` |
| 6 | Content-Length declarado acima do limite; bytes acima do limite durante a leitura; corpo vazio | Metadados, antes e durante a expansão: a soma corrente de `dataReceived.dataLength` (decodificado) e de `encodedDataLength` é confrontada com `max_bytes`; excedido o limite, a carga é interrompida e não há leitura de corpo. O corpo só é lido depois de `loadingFinished`, com tamanho decodificado conhecido e dentro do limite. Corpo vazio, recusado | `dataReceived`, `loadingFinished.encodedDataLength` | `TooLarge`, `EmptyBody` |
| 7 | Corpo completo igual ao Content-Length | Sem Content-Encoding: tamanho do corpo igual ao Content-Length (assim no Planalto, 757.607 bytes). Com Content-Encoding: igualdade do Content-Length aos bytes codificados do corpo quando o navegador os expuser sem cabeçalhos; sem esse dado, a completude é a de `loadingFinished` (declarada) | idem | `RespostaInvalida` |
| 8 | Redirecionamentos: no máximo 3, `Location` presente, destino validado pela linha 1, 307 e 308 entre origens recusados, desafio no salto | Igual, salto a salto, pelos `redirectResponse` de `requestWillBeSent`. Redirecionamento interno do navegador (sem IP remoto) só se admite como HSTS para o mesmo host; qualquer outro interno, inclusive o produzido por extensão, causa recusa. A cadeia vai a `redirects` | `redirectResponse`, `request.url` | `BlockedHost` |
| 9 | Desafio (`detect_challenge`) em todo status, sobre amostra de 64 KiB | Igual, sobre status, cabeçalhos e os primeiros 64 KiB do corpo decodificado, como a 0060 §2 prevê para o caso de decodificação. Página de desafio nunca é captura | corpo decodificado | `HTTPStatusError` com desafio |
| 10 | Content-Type sintaticamente válido e media type na lista | Igual, sobre o Content-Type bruto da resposta; o `mimeType` inferido pelo navegador não é usado | cabeçalhos brutos | `RespostaInvalida` |
| 11 | Charset e interpretação textual (conectores) | Igual, sobre os bytes, pelo mesmo parser | corpo (§2.5) | código do conector |
| 12 | Prazo total da captura | Igual, medido entre `requestWillBeSent` e `loadingFinished` (carimbos do navegador) | `wallTime`, `timestamp` | `Timeout` |
| 13 | Taxa mínima de leitura (2 KiB/s em 30 s) | Declarada: não se aplica. Protege a ferramenta de leitura travada, e quem lê é o navegador; o prazo total (linha 12) continua | — | — |
| 14 | Limite de taxa e disjuntor por host | Declarada: não se aplicam às requisições, feitas pelo navegador por ação humana; aplica-se o teto de capturas por sessão do perfil | — | recusa de captura |
| 15 | Repetição automática (502 a 504, Retry-After) | Não há: a porta nunca pede nem repete; o humano recarrega se quiser | — | — |
| 16 | Identidade da requisição (método, URL canônica, cabeçalhos do chamador) | Método e URL sanitizada (§2.7); cabeçalhos do navegador, cookies inclusive, fora da identidade | — | — |
| 17 | Cookies da `Session` do transporte | Não existe: cookies ficam no perfil temporário do navegador e nunca são lidos pela porta | — | — |
| 18 | Cabeçalhos do recibo (`HEADER_NAMES`) | Igual | cabeçalhos brutos | — |
| 19 | `fetched_at` | Instante de `loadingFinished`, convertido para UTC pelo `wallTime` do pedido | `wallTime`, `timestamp` | — |

Além da matriz, a linha de proveniência da §2.3(1) (cache, service worker, prefetch, pré-renderização, 304, 206) é
exigência própria da sessão assistida, sem par no fluxo automático.

### 2.5 Bytes, hash e comparação entre capturas

1. **Objeto do hash.** O exemplar (0088) é o corpo como o navegador o entregou depois de decodificar o
   Content-Encoding; o SHA-256 é desses bytes. Sem compressão, coincidem com os bytes do fio (teste exploratório,
   Planalto). Com compressão, o hash não prova os bytes comprimidos da rede; o recibo registra a codificação
   original e, quando disponível, o tamanho codificado (Terra r1, achado 6).
2. **Sem reinterpretação de charset.** O adaptador obtém o corpo em bytes. Se a API do navegador o entregar como
   texto já decodificado por charset, só se aceita quando o charset efetivo da resposta for UTF-8 e o tamanho da
   reencodificação em UTF-8 for igual ao tamanho decodificado conhecido (soma de `dataReceived.dataLength`); fora
   disso, recusa. O aceite prova identidade de bytes contra origem controlada em UTF-8, ISO-8859-1 e
   windows-1252, com e sem compressão (§3.1).
3. **Conteúdo variável injetado.** O Planalto acrescenta, depois de `</html>`, um `<script id="f5_cspm">` com token
   por requisição; duas capturas da mesma página diferem só nele (achado 2), e o bloco já está nas capturas do
   fluxo automático. O hash bruto identifica o exemplar e nunca é usado para afirmar que duas capturas têm o
   mesmo conteúdo. Equivalência entre capturas, assistidas ou automáticas, só se afere sobre o texto extraído
   pelo parser, que descarta o bloco por lista fechada declarada no perfil da fonte. O bloco é conteúdo não
   normativo de terceiro e nunca entra no texto.

### 2.6 Proveniência, `verified` e frescor

1. A captura grava `procedencia: sessao_assistida` (0075) e, separadamente, `modalidade_acesso:
   sessao_assistida` (0067), que sobrevive à exportação e à instalação de snapshot (onde a procedência pública
   passa a `snapshot`, 0075). Grava ainda `sessao_id` aleatório, versão do navegador, protocolo, IP remoto e
   emissor do certificado; nunca dado derivado de cookie.
2. A modalidade assistida não reduz os requisitos de `verified` (regra 1): identidade, âncora reproduzível e
   confronto efetivo continuam exigidos. A origem dos bytes é provada pelos eventos de rede do próprio navegador
   (§2.3(1) e §2.4); resposta sem essa prova não vira captura. Origem e hash provam de onde vieram os bytes, não
   que a fonte oficial não esteja comprometida. A exclusão da 0083 limita-se à adulteração deliberada do banco
   local e não dispensa controle de aquisição.
3. Frescor: ultrapassados 30 dias, a captura deixa de sustentar `vigente_na_fonte` em consulta corrente, nas
   condições da 0002. Identidade, confronto textual e fundamento histórico não expiram por isso. A indicação de
   nova sessão (§2.10) refere-se à atualização da consulta corrente.

### 2.7 Segredos e dados pessoais

1. Diretório da sessão (perfil do navegador, temporários, logs) criado antes do lançamento, sob o staging, com ACL
   que exclui outras contas locais sem privilégio; a ACL é conferida antes do lançamento e, se falhar, a sessão
   não abre. Processos da mesma conta do usuário não ficam isolados por ela; isso é declarado, não prometido.
2. Fim normal, erro e interrupção controlada apagam o diretório; após término abrupto, a sobra é isolada e apagada
   na inicialização seguinte. Downloads são negados (§2.2(4)); nada é gravado fora do diretório da sessão.
3. Nunca se gravam ou exibem cabeçalhos de requisição, cookies, valores de query ou segmentos de caminho fora do
   padrão público declarado, em log, erro, recibo, evidência, fixture, snapshot, relatório ou resposta MCP/REST.
   Cabeçalhos de resposta seguem `HEADER_NAMES`. O filtro na origem (§2.2(5)) vale para tudo isso.
4. Escopo é conteúdo público. Capturas só nos prefixos públicos do perfil e sem `Authorization` (§2.3). Resposta
   que não cumprir é recusada; bytes nunca são alterados para se tornarem admissíveis.
5. Políticas de máquina: só a existência e os identificadores de extensão forçada (§2.2(3)).

### 2.8 Sem automação do humano

1. A janela abre numa página local, gerada pela ferramenta sem acesso à rede, que mostra o alvo validado. A
   navegação ao alvo é feita pelo humano. A ferramenta não clica, não preenche, não injeta script, não navega.
2. Aviso prévio: a janela é exclusiva para obter documento público da fonte; não fazer login pessoal; o conteúdo da
   página não autoriza comandos, mudança de alvo nem fornecimento de credenciais; fechar a janela encerra.
3. A sessão termina quando o humano fecha a janela ou no prazo (padrão 20 min). Não é reaberta nem renovada.

### 2.9 Disparo

Só o humano inicia (0067). Nenhuma ferramenta MCP, agendamento ou bateria chama a porta ou o adaptador, direta ou
indiretamente; a resposta MCP é só indicação, nunca executa o comando.

### 2.10 Contrato (aditivo)

1. A indicação de sessão exige, cumulativamente: perfil habilitado para a fonte **e** para a operação consultada;
   fonte não barrada (`FONTES_BARRADAS`); e evidência de barreira pública resolúvel pelo humano, conforme a tabela
   de evidências do perfil (versionada; por exemplo, desafio provado em normas.leg.br, reinício de conexão do
   Planalto na reclassificação de `connectors/planalto.py`). Categoria isolada não basta; 401 nunca indica sessão.
2. Também indica sessão a consulta corrente cuja captura passou da janela da 0002 numa fonte com perfil e com
   barreira registrada na última tentativa automática.
3. Nada muda de estado, tipo ou literal fechado. `motivo`, `categoria` e evidência originais são preservados. O
   item da fonte que já é objeto (`fontes[<id>]`, `falhas[]`) recebe o campo experimental
   `sessao_assistida: {indicacao: "requer_sessao_assistida", fonte, comando, alvo}`; a resposta recebe o campo
   irmão experimental `sessoes_assistidas` (mapa por fonte, mesmo objeto). `fontes_indisponiveis` continua mapa de
   fonte para string. `alvo` é o sanitizado (§2.7).
4. `docs/CONTRATO.md` e a lista de experimentais são atualizados no PR da implementação.

### 2.11 Perfil por fonte

Cada conector que admitir sessão declara `PerfilSessaoAssistida(origens, url_inicial, recursos, media_types,
max_bytes, max_capturas, limpeza_texto, operacoes, evidencias_de_barreira)`, em que cada recurso é
`(tipo: document|xhr|fetch, host, prefixo, parametros: {nome: padrão}, media_types)` e `limpeza_texto` é a lista
fechada de blocos não normativos que o parser descarta (§2.5(3)). Primeira hora:

| Fonte | Recursos | Observação |
|---|---|---|
| `planalto` (legislação) | `document` em `www.planalto.gov.br/ccivil_03/` | `limpeza_texto`: bloco `f5_cspm` |
| `normas_leg` | `document` na raiz; `xhr` em `/api/public/normas` (parâmetros `urn`, padrão URN:LEX federal, e `tipo_documento`, valores fechados) e em `/api/public/binario/<uuid>/texto` | o texto é o do recurso `binario`; o vínculo à norma vem do JSON de `/api/public/normas`, lido pelo parser a partir da captura |
| `tjsp` | só `document` (GET); pesquisa depende de `POST` (§5) | — |

A busca em `legis.senado.leg.br` não é recurso admitido (catálogo de descoberta, não texto). NPL e DOU
(`www.in.gov.br`) seguem barrados por decisão (pendências 28 e 31); a abertura deles à sessão exige decisão
própria. `listar_fontes` declara `sessao_assistida: disponivel|nao_aplicavel` (experimental).

### 2.12 Cobertura

A matriz e o bloco `cobertura` declaram o acesso (`automatico`, `assistido`) por fonte, nos três denominadores da
0067. Captura assistida nunca é somada à cobertura automática.

### 2.13 Dependência e distribuição

Sem Playwright. Com pipe, nenhuma dependência nova. Se o teste do adaptador exigir porta TCP (§2.2(2)),
`websocket-client` entra como extra opcional `[sessao]`, travado por hash em lock próprio. Sem o extra, quando
exigido, `fv sessao` sai com código 2; o resto não muda. O instalador oficial do Windows inclui o necessário, e o
teste de instalação o confere.

## 3. Aceite (o incremento só conclui com testes que provem)

1. **Adaptador real contra origem controlada.** Chrome instalado contra servidor HTTPS local de teste. A confiança
   na AC de teste e a admissão do IP de loopback vêm de parâmetros exclusivos do harness; um teste prova que o
   caminho de produto se recusa a lançar com eles. Casos: cada linha da §2.4 com o código de recusa esperado;
   `gzip`, `deflate`, `br`, `zstd` e codificação não admitida; bomba de compressão (interrupção antes de ler o
   corpo); Content-Length duplicado, conflitante e divergente; corpo truncado; 3 e 4 saltos, 307 entre origens,
   desafio no salto, redirecionamento interno não HSTS; 304 e 206; identidade de bytes em UTF-8, ISO-8859-1 e
   windows-1252, com e sem compressão.
2. **Proveniência.** Recarga com cache desligado vem da rede; service worker que sintetiza resposta, resposta de
   cache e pré-renderização não geram captura.
3. **Recusas de escopo.** `POST`, `Authorization`, caminho fora do prefixo, parâmetro ou valor não declarado,
   media type não declarado, página de desafio, terceiro em iframe, `blob:` e `data:`, download.
4. **Filtro na origem.** Sessão sintética com tráfego de terceiros, inclusive SSO simulado: nada fora das origens
   da fonte persiste, nem em log de depuração.
5. **Segredos.** Varredura sobre sessão sintética com cookies, `Authorization`, tokens em query e caminho; nada em
   log, erro, recibo, evidência, fixture, snapshot, relatório ou resposta MCP/REST.
6. **Diretório da sessão.** ACL conferida antes do lançamento (falha fecha a sessão); limpeza em fim normal, erro,
   interrupção e recuperação após término abrupto; pipe de controle ou, se porta, risco declarado no aviso.
7. **Políticas de máquina.** Com política de proxy simulada, a sessão não abre; com extensão forçada, o recibo a
   declara; nenhum valor de política é gravado.
8. **Passividade.** O tráfego CDP do adaptador, registrado no teste, contém só métodos da lista fechada da
   §2.2(4); conferência estática da mesma lista no código.
9. **Proveniência gravada.** `modalidade_acesso` e `procedencia` gravados; `modalidade_acesso` preservada em
   exportação e instalação de snapshot.
10. **Disparo.** Nenhum caminho MCP, agendado ou de bateria alcança porta ou adaptador, por importação ou chamada
    indireta (AST e teste de execução); sem confirmação interativa, nada é lançado.
11. **Contrato.** Indicação só nas condições da §2.10, nos três adaptadores; nenhum tipo existente muda.
12. **Conteúdo variável.** Duas capturas do Planalto com tokens `f5_cspm` distintos produzem o mesmo texto
    extraído, sem o bloco.
13. **Sessão manual registrada** no Windows (supervisor via WMI) com Planalto e normas.leg.br, antes da reapuração
    da Porta L. Fixtures seguem a regra 9.

## 4. O que não muda e alternativas rejeitadas

Não mudam: regras invariáveis, `verified`, 0002, 0060 a 0066 e transporte no fluxo automático (D5), reserva (D6).

Rejeitados: proxy do transporte que refaz as trocas (v2: recusado pela barreira por tipo de cliente, exigiria
emprestar a identidade do navegador contra a regra 3 e abria superfície de rede extensa); alterar as requisições do
navegador, inclusive forçar `Accept-Encoding: identity` por CDP (a ferramenta passaria a moldar o cliente que a
fonte vê); Playwright ou qualquer automatizador; reaproveitar cookies da sessão em requisições da ferramenta;
importar HAR ou cookies do navegador pessoal; extensão; capturar o DOM; instalar AC no sistema; modo sem janela;
OCR.

## 5. Questões abertas

1. `POST` (pesquisa do TJSP): identidade de requisição com corpo; decisão própria antes do TJSP.
2. Anexos em PDF: o visualizador interno os trata como `document` se o media type estiver declarado; download
   continua negado; fonte que só sirva download exige decisão própria.
3. Abertura de NPL e DOU à sessão (§2.11).
4. Pipe de depuração no Windows (§2.2(2)): confirmar no teste do adaptador.
5. Política corporativa: se a sessão no notebook do titular, sob as políticas do escritório, basta para produção,
   ou se convém navegador sem política de máquina (por exemplo, binário que leia outra chave de política); conferir
   na sessão manual do item 13 da §3.

## 6. Execução

Implementação pelo Codex (`workspace-write`, worktree e ramo próprios) em duas trilhas sequenciais, por regra de uma
trilha por vez em `transport.py`: (a) porta `capturar_assistida` com a matriz da §2.4; (b) adaptador CDP, CLI,
perfis e contrato. Revisão de fronteiras e segredos por Terra; auditoria por Codex somente leitura, sessão nova,
com os critérios da §3 fixados antes, inclusive a auditoria própria de `transport` (D5). A pendência 24
(reabertura de `normas_leg`) entra na mesma versão.

## 7. Histórico e correspondência com os pareceres

- v1 (captura por CDP, sem emenda): Codex r1 e Terra r1 BLOQUEADOR.
- v2 (proxy do transporte): Codex r2 e Terra r2 BLOQUEADOR; parada na bifurcação.
- 19/11/2026: titular escolhe a opção A; teste exploratório; esta v3.

| Parecer | Achado | Resposta na v3 |
|---|---|---|
| Codex r1 | 1. Content-Encoding contra a 0067 e a 0060 | emenda (§2.1); §2.4, linhas 5 a 7 e 9; §2.5(1) |
| Codex r1 | 2. Matriz exaustiva, dados por validação | §2.4, com dado, regra e código por linha; recusa sem dado |
| Codex r1 | 3. Abertura automática da página | §2.8(1) |
| Codex r1 | 4. Tipo de `fontes_indisponiveis` | §2.10(3) |
| Codex r1 | 5. Disparo por categoria | §2.10(1) e (2) |
| Codex r1 | 6. `verified` e 0083 | §2.6(2) |
| Codex r1 | 7. Frescor | §2.6(3) |
| Codex r1 | 8. Aceite insuficiente | §3, itens 1 a 13 |
| Terra r1 | 1. Cache, service worker, 304 | §2.2(4); §2.3(1); §3.2 |
| Terra r1 | 2. Vínculo de navegação | §2.3, "Vínculo" |
| Terra r1 | 3. Downloads | §2.2(4); §2.7(2) |
| Terra r1 | 4. Dados pessoais e conteúdo autenticado | §2.7(4); §2.8(2) |
| Terra r1 | 5. Segredos em URL | §2.7(3); §2.11 (parâmetros com padrão) |
| Terra r1 | 6. Limite durante a expansão; objeto do hash | §2.4, linha 6; §2.5(1) |
| Terra r1 | 7. ACL e término abrupto | §2.7(1) e (2) |
| Terra r1 | 8. Página hostil | §2.8(2); §2.6(2) |
| Terra r1 | 9. TTY não prova intenção | §2.2(1) |
| Terra r1 | 10. Cabeçalhos hostis, terceiros | §2.4, linhas 4 e 10; §2.2(5); §2.3(3) |
| Codex r2 e Terra r2 | regra 3, pilha TLS a montante, túnel, AC local, credencial do proxy | superados: não há proxy, AC nem túnel (§2.2(2); §4) |
| Terra r2 | QUIC e WebSocket; prefetch | HTTP/3 aceito com protocolo no recibo (§2.4, linha 4); WebSocket não é recurso admitido (§2.11); prefetch e pré-renderização recusados (§2.3(1)) |
| Teste exploratório | achados 1 a 6 | §1; §2.2(3) e (5); §2.4; §2.5; §2.11; §5.5 |
