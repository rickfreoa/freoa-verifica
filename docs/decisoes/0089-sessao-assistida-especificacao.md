# 0089 - Sessão assistida: especificação do mecanismo; emenda à 0067

**Situação: vigente desde 19/11/2026.** Versão 5.2, aprovada depois da verificação final de Codex e Terra
(SEM_BLOQUEADOR) e da aprovação, pelo titular, da premissa sobre o operador (§2.2(3)(b')). Histórico, pareceres, testes
e laboratórios em `docs/auditoria/0089/`. A implementação segue a §6, com auditoria própria de `transport` (D5).

19/11/2026. Supervisor (Opus), sob a autorização do titular (plano 1.4, seção 9, item 5), a ordem da 0087 §2.1(a)
e as decisões do titular de 19/11 (opção A; decisões 1 a 6 da rodada 3, §7). Especifica o mecanismo que a 0067
§1 admitiu e emenda, só para a sessão assistida, a leitura da regra 4 e o quarto item da regra 3 da 0067 (§2.1).
Não altera o critério de `verified`, a 0002, a 0060 a 0066 no fluxo automático, a matriz, os pisos nem a reserva.
A mudança de contrato é só aditiva (§2.10). A implementação toca `transport` e exige auditoria própria (D5).

## 1. Fato e problema

As capacidades reprovadas da Porta L dependem de fontes que recusam o cliente automatizado: o Planalto recusa o
UA identificado (0048), normas.leg.br responde 403 com CAPTCHA (0085), o NPL reinicia a conexão de clientes não
navegador mesmo com UA de navegador. A barreira do NPL discrimina o tipo de cliente, não o nome declarado. Toda
arquitetura em que o transporte faz a requisição a montante ou é recusada por essa barreira, ou precisa emprestar
a identidade do navegador, o que a regra 3 veda (v2; Codex r2, achado 9). Os bytes têm de vir da conexão do
próprio navegador, e as validações que pressupõem que o transporte é dono do soquete precisam de regra declarada.

Dois testes com navegador dedicado e gravador CDP (`teste-exploratorio-2026-11-19.md`, `teste-normas-2026-11-19.md`)
mostraram: o navegador obtém Planalto, NPL e normas.leg.br sem desafio; os eventos de rede provam, resposta a
resposta, que nada veio de cache, service worker ou prefetch, mesmo sem alterar o comportamento de cache do
navegador; o Planalto injeta um script variável do WAF F5; o texto de normas.leg.br chega por XHR, com vínculo
determinístico entre o JSON-LD da norma e o binário do texto; a política corporativa do navegador abre o SSO do
escritório em cada aba nova; o filtro de hosts antes de gravar elimina esse tráfego dos registros.

O laboratório de 19/11 (`laboratorio-2026-11-19.md`, só `127.0.0.1`) mostrou ainda: `Network.streamResourceContent`
entrega os bytes do corpo sem interpretação de charset, onde `Network.getResponseBody` os altera; o inventário de
extensões pelo perfil independe de alvo CDP; a raiz de `Page.getFrameTree` identifica o quadro principal; e a política
do escritório instala no notebook do titular uma extensão com permissões de interceptação de rede.

## 2. Decisão

### 2.1 Emenda: regra 4 e 0067

1. **Leitura da regra 4 na sessão assistida** (decisão 6 do titular; Codex r3, achado 1). Exclusivamente na sessão
   assistida, a regra 4 ("toda requisição passa por `freoa_verifica.transport`") exige que **toda admissão de
   resposta como captura** passe por `transport.capturar_assistida`. As requisições do navegador dedicado não são
   emitidas nem encaminhadas pelo transporte. A exceção não alcança requisição alguma da ferramenta nem o fluxo
   automático. `AGENTS.md` (regra 4) e a 0001 recebem remissão a esta leitura no PR da implementação, que é quando a
   leitura passa a ter efeito; o PR desta decisão só altera documentos de decisão e auditoria.
2. **Quarto item da regra 3 da 0067**, nova redação:

   > regra 4: o navegador da sessão só é usado pelo humano; a captura entra no sistema exclusivamente pela porta
   > única de `freoa_verifica.transport` (`transport.capturar_assistida`); nenhum conector ou parser lê bytes do
   > navegador por outro caminho. Na sessão assistida, os bytes capturados são os recebidos pela conexão do próprio
   > navegador dedicado, e a porta aplica a cada resposta a matriz de validação da 0089 §2.4: cada validação do
   > fluxo automático é aplicada igual, aplicada sobre os metadados de rede do navegador, substituída por validação
   > declarada ou declarada inaplicável com razão; dado necessário ausente ou ambíguo causa recusa. Só vira captura
   > resposta cuja origem de rede o navegador prove (nunca de cache, service worker, prefetch, pré-renderização,
   > 304 ou 206). A ferramenta não envia ao navegador comando que altere requisição, cache ou service worker, e
   > nunca usa a identidade dele em requisição própria. No fluxo automático nada muda.

   A 0067 já tem nota de topo que remete a esta emenda.

### 2.2 Arquitetura: o navegador faz as trocas; a ferramenta só observa

1. **Início.** `fv sessao <fonte> [--alvo URL]` (CLI) é o único início. Exige terminal interativo do titular;
   recusa execução sem TTY, agendada, por script, por bateria, pelo MCP do produto ou por processo remoto (WMI,
   SSH). Antes de abrir, mostra a fonte, o alvo público sanitizado (§2.7) e o aviso da §2.8, e exige confirmação
   interativa para aquela sessão e aquele alvo.
2. **Navegador.** Chrome, Edge ou Brave **instalados**, lançados pelo adaptador com argumentos fechados:
   `--user-data-dir=<diretório da sessão>`, `--no-first-run`, `--no-default-browser-check`, `--disable-sync`,
   `--no-proxy-server`, `--disable-breakpad`, `--remote-debugging-pipe` (no Windows, com os identificadores de pipe
   herdados só pelo processo do navegador). Janela visível. Nunca: Playwright ou outro automatizador, `--load-extension`, `--enable-unsafe-extension-debugging`,
   `--enable-automation`, modo sem janela, porta TCP de depuração, `--ignore-certificate-errors`, exceção SPKI,
   proxy ou extensão da ferramenta. Se o pipe não puder ser estabelecido, a sessão não abre (decisão 3).
3. **Ambiente** (decisão 3; Codex r4, B2; Codex r5 e Terra r5; decisão do titular sobre componentes, §7).
   (a) **Antes do lançamento**, o adaptador lê, sem abrir página alguma, as políticas de máquina e de usuário do
   navegador escolhido no Registro do Windows (HKLM e HKCU; `Software\Policies\Google\Chrome`,
   `Software\Policies\Microsoft\Edge` ou `Software\Policies\BraveSoftware\Brave`). A sessão não abre se houver: política de
   proxy (`ProxySettings`, `ProxyMode`, `ProxyServer`, `ProxyPacUrl`); token de gerência em nuvem
   (`CloudManagementEnrollmentToken`), cujas políticas não são enumeráveis localmente; `ExtensionInstallForcelist` com
   qualquer item; ou `ExtensionSettings` com qualquer entrada cujo `installation_mode` seja `force_installed` ou
   `normal_installed`. Leitura do Registro que falhe impede a sessão.
   (b) **Vigilância contínua.** Antes do lançamento, o adaptador cria o diretório do perfil e liga sobre ele a notificação
   de mudanças do sistema de arquivos (ReadDirectoryChangesW), cobrindo `Default\Extensions`. Depois do lançamento, há
   um período de assentamento: candidatas só se tornam elegíveis quando o diretório `Default\Extensions` ficar 10 s sem
   mudança e o inventário da alínea (c) passar; o conjunto de caminhos e tamanhos nesse instante é a linha de base. Só é
   elegível pedido cujo `requestWillBeSent` seja posterior à linha de base. A partir dela, **qualquer** criação,
   alteração, renomeação ou remoção sob `Default\Extensions`, estouro do buffer de notificações ou falha do observador
   invalida todas as candidatas pendentes e encerra a sessão sem gravação. Antes da seleção e de novo antes da
   gravação, o adaptador estabelece uma barreira: grava um arquivo-sentinela dentro de `Default\Extensions` e só prossegue
   depois de receber a notificação dele, o que garante que todas as notificações anteriores foram processadas;
   notificação diferente do sentinela, perda de eventos ou barreira não estabelecida em 5 s invalida as candidatas. A
   vigilância é a prova de que nenhuma extensão foi instalada, ativada ou removida durante a sessão (laboratório de
   vigilância, `teste-brave-2026-11-19.md`: a instalação por política da Fortinet no Chrome foi captada aos 5 s, no
   instante da gravação dos arquivos).
   (b') **Extensões carregadas de fora do diretório** (Codex, conferência final). Extensão desempacotada é carregada do
   caminho escolhido, sem cópia para `Default\Extensions`. Os caminhos para isso são três, e cada um é tratado: (1) o
   argumento `--load-extension`, que o adaptador nunca passa (lista fechada da §2.2(2), que também exclui
   `--enable-unsafe-extension-debugging`); (2) o comando CDP `Extensions.loadUnpacked`, fora da lista fechada da §2.12 e
   disponível só com aquele argumento; (3) a ação manual do humano em `chrome://extensions`, com o modo de
   desenvolvedor. O terceiro é ação do operador da sessão, que o aviso da §2.8(2) proíbe; a ferramenta não escreve
   política para impedi-lo. Premissa declarada, da mesma natureza da §2.2(7): o humano que inicia e conduz a sessão é
   operador confiável quanto ao próprio navegador; carregar extensão durante a sessão viola o aviso e não é ameaça que a
   ferramenta prometa conter. Extensão com `location` 4 (desempacotada) presente no inventário da alínea (c) encerra a
   sessão sem capturas.
   (c) **Inventário** (evidência auxiliar, Codex r5): no fim do assentamento e imediatamente antes da seleção, o
   adaptador lê `extensions.settings` em `Secure Preferences` e `Preferences` do perfil da sessão e o `manifest.json` de
   cada extensão. **Extensão de componente** (`location` 5) cujo caminho absoluto esteja dentro do diretório de
   instalação do próprio navegador é parte do navegador e não entra na regra seguinte: vem com o binário, nenhuma
   política ou usuário a acrescenta, e o navegador já é a parte em que se confia para relatar os eventos de rede. Toda
   outra extensão, inclusive de componente externo (`location` 10), que tenha permissão de interceptação ou controle de
   rede (`webRequest`, `webRequestBlocking`, `webRequestAuthProvider`, `declarativeNetRequest`,
   `declarativeNetRequestWithHostAccess`, `proxy`, `debugger`) ou a chave `declarative_net_request` encerra a sessão sem
   capturas. Arquivo ausente, ilegível ou manifesto indisponível: nenhuma candidata. Alcance declarado do componente
   embutido: pode bloquear requisição (então não há candidata), redirecioná-la (recusado pela §2.4, linha 8) ou alterar
   cabeçalhos; a não alteração do corpo é premissa do navegador confiável, coerente com o contrato da API `webRequest`,
   e o teste realizado não a demonstra universalmente.
   (d) Nenhum valor de política é gravado; o recibo registra só que a conferência passou e o navegador usado.
   **Fatos verificados:** no notebook do titular, o Chrome e o Edge têm `ExtensionInstallForcelist` (Fortinet Privileged
   Access Agent, com `proxy`, `declarativeNetRequest`, `webRequest`): a sessão não abre neles. O Brave 1.100 (Chromium
   158), instalado na conta do usuário, não tem política; o perfil novo não recebe extensão instalada, só os componentes
   `Chrome PDF Viewer` e `Brave` (este com `webRequest` e `webRequestBlocking`, admitido pela regra do componente).
4. **Observação pura** (decisão 2; Codex r3, achado 2). O adaptador usa só a lista fechada de métodos CDP da §2.12;
   nenhum deles altera requisição, cache, service worker, cabeçalho ou identidade; o único de configuração nega
   downloads. Não navega, não injeta script, não clica, não interrompe carga. Cache e service worker do navegador ficam como estão; a porta recusa toda
   resposta que não prove origem de rede (§2.3(1)). Se a página vier do cache, o humano recarrega (Ctrl+F5) por
   ação própria.
5. **Filtro na origem.** Evento de alvo, requisição ou resposta fora das origens da fonte (§2.11) é descartado em
   memória antes de qualquer gravação, inclusive de diagnóstico. Evento sem URL só é retido quando se associa
   inequivocamente (§2.3, "Correlação") a salto de origem da fonte. O alcance da promessa: nada de terceiros entra
   nos registros, recibos, evidências e entregáveis da ferramenta; artefatos que o próprio navegador grave ficam
   no diretório protegido da sessão e são descartados (§2.7).
6. **Porta única.** O adaptador entrega a `transport.capturar_assistida` candidatas com os dados da §2.4; só a
   porta decide se há captura; o humano escolhe, entre as aceitas, as que entram (§2.3, "Seleção"). Conectores e
   parsers leem apenas capturas gravadas.
7. **Premissa de ameaça declarada.** Processo malicioso na mesma conta do Windows, com privilégios para anexar-se
   ao navegador ou ler sua memória, está fora do modelo: poderia igualmente adulterar o home. A ACL (§2.7(1))
   protege contra outras contas sem privilégio; não promete mais que isso.

### 2.3 O que vira captura

**Prontidão** (Codex r4, B3). A sequência é normativa: `Target.setDiscoverTargets`; `Target.setAutoAttach` com
espera pelo depurador; em cada alvo anexado, `Network.enable` e `Page.enable`, e só então
`Runtime.runIfWaitingForDebugger`. Só é elegível pedido cujo `requestWillBeSent` foi observado numa sessão que já
cumpriu essa sequência. A primeira navegação de aba aberta já com URL não é observada (laboratório, resultado 3) e,
por isso, nunca é candidata; o humano recarrega a página na aba já aberta.

**Candidata.** A porta aceita como candidata só a resposta que cumprir, cumulativamente:

1. **Troca de rede provada pelo navegador.** `Network.responseReceived` com `fromDiskCache`, `fromServiceWorker` e
   `fromPrefetchCache` **presentes e falsos** (ausência não vale como falso); nenhum
   `Network.requestServedFromCache` para o pedido; `remoteIPAddress`, `remotePort` e `securityDetails` presentes;
   `Network.responseReceivedExtraInfo` correspondente, com `statusCode` igual ao status da resposta (304 exposto como
   200 é recusado); `Network.loadingFinished` (não `loadingFailed`); alvo do tipo `page` sem subtipo de
   pré-renderização desde a criação; status 200. 304, 206 e os demais status nunca viram captura; a resposta final
   que suceda a um 103 é avaliada por si, e recurso iniciado por Early Hints nunca é candidato. Restauração de página
   sem troca nova (bfcache, histórico) não gera evento de resposta e nunca vira captura nem renova frescor.
2. Método `GET`; nenhum salto de rede na cadeia (§2.4, linha 8); sem `Authorization` e sem cookie enviado fora dos
   nomes declarados no perfil (§2.7(4)), lidos de `requestWillBeSentExtraInfo.associatedCookies` só entre os que não
   foram bloqueados; resposta sem `Cache-Control: private` e sem `Vary` que inclua `Cookie` ou `Authorization`.
3. **Recurso admitido pelo perfil** (§2.11): `Document` **do quadro principal**, provado por `frameId` do pedido igual
   ao `id` da raiz da árvore de quadros vigente no momento do pedido, obtida por `Page.getFrameTree` na anexação e mantida
   pelos eventos `Page.frameNavigated` e `Page.frameAttached` (quadro sem `parentId`; laboratório, resultado 4;
   `teste-brave-2026-11-19.md`, resultado 6), ou
   `XHR`/`Fetch` declarado, iniciado por documento do quadro principal da mesma aba; host, caminho e query conforme a
   gramática exata do recurso; fragmento descartado; esquema só `https`. WebSocket, Early Hints, iframes e recursos não
   declarados nunca são candidatos.
4. Media type declarado para aquele recurso.
5. **Corpo obtido por streaming** desde antes da chegada de dados (§2.5(2)).
6. Todas as linhas da matriz da §2.4 aprovadas.

**Correlação.** Toda associação de eventos usa a chave (sessão CDP, alvo, `requestId`, ordinal do salto). Evento fora
de ordem que não se associe sem ambiguidade, chave repetida, histórico incompleto ou perda da conexão CDP descartam a
candidata. Nenhum evento herda autorização de retenção de outro salto ou de outro alvo.

**Vínculo.** A candidata é atribuída à sua própria URL validada e aos seus próprios eventos, nunca ao alvo sugerido nem
à navegação anterior. Navegação iniciada por conteúdo é navegação nova, validada por si. Recurso dependente segue a
§2.11.

**Seleção** (decisão 4). Ao fechar a janela, a CLI resolve primeiro o grafo de vínculos de toda a sessão (§2.11) e só
depois lista as candidatas aceitas, cada uma com identidade pública (fonte, URN ou caminho, tipo, versão quando houver,
tamanho e hash curto), e, abaixo de cada documento, seus dependentes com os respectivos hashes. O humano marca os
documentos que entram; os dependentes seguem o documento marcado. As não marcadas são descartadas sem gravação. Sem
marcação, nada entra.

**Identidade da obtenção.** Cada candidata recebe identificador opaco único; não há cache nem reutilização por método e
URL. A identidade pública exibida e persistida é separada da URL operacional e nunca reúne destinos distintos.

Recusas são listadas ao humano com URL sanitizada e código. "Não examinado" nunca equivale a "sem desafio": resposta
que não chegou a ser examinada é recusada, não classificada.

### 2.4 Matriz de validação

Exaustiva quanto às validações e controles de `freoa_verifica/transport.py` (`35dd8bc`). **Igual**: mesma função ou
mesma regra, mesmo código. **Metadados**: mesma regra sobre dado de rede do navegador. **Declarada**: regra substituta
aprovada por esta emenda. **Inaplicável**: com a razão. Dado necessário ausente, opcional não presente ou ambíguo causa
recusa, nunca inferência. Recusa da porta não impede o navegador de exibir a página: só impede a captura.

| # | Controle automático (código) | Na sessão assistida | Dado (CDP) | Recusa |
|---|---|---|---|---|
| 1 | URL ASCII, `https`, host permitido, porta 443, caminho não ambíguo, prefixos (`validate_reference`, `_path_allowed`, 605–629, 507–530) | Igual, pela mesma função, sobre a URL da resposta, e gramática exata do recurso (§2.11). A URL `http` interna de um salto HSTS (linha 8) não é candidata e recebe só a validação estrutural da exceção; a URL `https` efetiva passa integralmente por esta linha | `request.url`, `response.url` | `BlockedHost` |
| 2 | DNS pela ferramenta com prazo e concorrência próprios; só IP público unicast; conexão ao IP validado (64, 665–719, 770–783) | Metadados: o IP efetivo da conexão passa por `_public_unicast`; porta 443. Declarada: a resolução é do navegador, lançado sem proxy (§2.2(2) e (3)); prazo e concorrência de DNS inaplicáveis porque a ferramenta não resolve; o tempo de resolução entra no prazo total (linha 12) | `remoteIPAddress`, `remotePort` | `BlockedHost` |
| 3 | TLS verificado pelo contexto padrão | Metadados: navegador sem exceção de certificado; `securityDetails` com protocolo TLS 1.2 ou 1.3 e `securityState` seguro | `securityDetails`, `securityState` | `RespostaInvalida` |
| 4 | Sintaxe estrita da linha de status e dos campos; `Transfer-Encoding` só `chunked` e único; `Content-Length` com até 20 dígitos e único; recusa de coexistência (`_campos_estritos`, `_validar_framing`, 323–378) | HTTP/1.x: **igual**, por `_campos_estritos` e `_validar_framing` aplicados a `headersText`, então obrigatório. HTTP/2 e HTTP/3: declarada; o framing é o do protocolo, aplicado pelo navegador; a porta confere nos cabeçalhos com multiplicidade (duplicatas separadas por `\n`, sem escolher um valor) `Content-Length` único com até 20 dígitos, ausência de `Transfer-Encoding` e recusa de coexistência. Protocolo vai ao recibo | `responseReceivedExtraInfo.headersText`, `.headers`, `response.protocol` | `RespostaInvalida` |
| 5 | Gramática e término dos chunks, trailers (243–320) | Declarada: o navegador recusa chunk malformado ou incompleto como erro de rede (`loadingFailed`), e a porta só aceita `loadingFinished`. Trailers não são observáveis nem usados. Diferença de aceitação admitida: o navegador pode tolerar extensão de chunk ou trailer que o transporte recusaria | `loadingFinished`, `loadingFailed` | recusa de candidata |
| 6 | Content-Encoding ausente ou `identity`, em todo status (0060, 1128–1136) | Declarada (emenda): admitidos ausente, `identity`, `gzip`, `deflate`, `br`, `zstd`, decodificados pelo navegador; outra codificação é recusada. A codificação original vai ao recibo; o hash é dos bytes decodificados (§2.5) | cabeçalhos com multiplicidade | `RespostaInvalida` |
| 7 | Tamanho declarado acima do limite; bytes acima do limite durante a leitura; confronto final do corpo com `Content-Length`; corpo vazio (1199–1203, 1238–1267) | Metadados: `Content-Length` acima de `max_bytes` recusa a candidata ao chegar `responseReceivedExtraInfo`. Contador decodificado: soma de `dataReceived.dataLength` contra `max_bytes`; excedido, o streaming é abandonado e a candidata descartada. Contador codificado: soma de `dataReceived.encodedDataLength` contra `max_bytes`, só onde o navegador o informa (em `XHR`/`Fetch`; em `Document` vem 0, laboratório, resultado 2). Confrontos finais: tamanho dos bytes do streaming igual à soma de `dataLength`, sempre; sem Content-Encoding, igual também ao `Content-Length`; com Content-Encoding em `XHR`/`Fetch`, `Content-Length` igual à soma de `encodedDataLength`; com Content-Encoding em `Document`, declarada a substituição pela completude de `loadingFinished`. Corpo vazio, recusado. Alcance declarado: o limite garante o que a ferramenta aceita e copia, não o consumo de memória do navegador | `dataReceived`, `loadingFinished`, cabeçalhos | `TooLarge`, `RespostaInvalida`, `EmptyBody` |
| 8 | Redirecionamentos: até 3, `Location`, destino validado, 307/308 entre origens recusados, desafio no corpo do salto (1137–1166, 1293) | Declarada: **nenhum salto de rede admitido**, porque o corpo do salto não é obtenível. Única exceção: redirecionamento interno HSTS, provado por `redirectResponse` com status 307, sem `remoteIPAddress`, com o cabeçalho `Non-Authoritative-Reason` de valor `HSTS` no mapa de cabeçalhos, e mudança só de `http` para `https` no mesmo host, caminho e query; não conta como salto. Outro redirecionamento interno, inclusive de extensão, recusa. Documento obtido por redirecionamento de rede é recusado; o humano abre a URL final | `redirectResponse` | `BlockedHost` |
| 9 | Desafio (`detect_challenge`) em todo status, amostra de 64 KiB (381–418) | Igual, sobre status, cabeçalhos e os primeiros 64 KiB dos bytes do streaming (decodificados), como a 0060 §2 prevê para decodificação. Página de desafio nunca é candidata; resposta não examinada é recusada, não declarada sem desafio | bytes do streaming | `HTTPStatusError` com desafio |
| 10 | Content-Type sintaticamente válido; media type na lista (1188–1197) | Igual, sobre o Content-Type bruto; único parâmetro admitido no valor persistido é `charset`; o `mimeType` inferido pelo navegador não é usado | cabeçalhos | `RespostaInvalida` |
| 11 | Charset e interpretação textual (conectores, `texto_resposta.py`) | Igual, sobre os bytes do streaming, com a mesma decodificação estrita | bytes | código do conector |
| 12 | Prazo total da chamada; classificação da falha pelo progresso: antes de qualquer byte de resposta `Timeout`, depois `RespostaInvalida` (941–983, 1063–1077, 1344–1345) | Igual em valor (30 s, padrão de `fetch`). Começa no `requestWillBeSent`; fiscalizado pelo relógio da porta, independentemente de eventos; inclui o streaming e a admissão. Declarada a diferença observacional: o primeiro sinal de resposta visível é `responseReceived` ou `responseReceivedExtraInfo` (cabeçalhos completos), não o primeiro byte. Sem nenhum dos dois no prazo: `Timeout`; com um deles e sem `loadingFinished`: `RespostaInvalida` | carimbos | `Timeout`, `RespostaInvalida` |
| 13 | Taxa mínima de leitura (2 KiB/s em 30 s) | Inaplicável: protege a ferramenta de leitura travada, e quem lê é o navegador; o prazo total continua | — | — |
| 14 | Limite de taxa e disjuntor por host (796–880) | Inaplicável às requisições, feitas pelo navegador por ação humana | — | — |
| 15 | Concorrência global de captura (65–66, 1346–1348) | Declarada: no máximo 4 candidatas em streaming simultâneo (o padrão de `FV_MAX_CONCURRENCY`); 32 candidatas pendentes por sessão; 64 MiB para todas as representações de corpo mantidas ao mesmo tempo pelo adaptador (mensagem JSON em processamento, texto base64, bytes decodificados e cópias), com reserva **antes** de cada alocação: o pipe entrega mensagens JSON delimitadas por caractere nulo, sem cabeçalho de tamanho, e o adaptador o lê em blocos de no máximo 1 MiB, cada bloco reservado contra o saldo antes da leitura; mensagem que, antes do delimitador, ultrapasse o saldo encerra a sessão sem gravação; fila de mensagens CDP não processadas limitada a 10.000 mensagens ou 32 MiB. Excedido limite de candidata, ela é descartada; excedida a fila ou a memória, a sessão encerra sem gravar candidatas pendentes. Memória interna do navegador excluída | — | recusa de candidata; encerramento |
| 16 | Repetição automática (502 a 504, Retry-After, 882–993) | Inaplicável: a porta nunca pede nem repete; o humano recarrega se quiser | — | — |
| 17 | Validação dos parâmetros da chamada (1325–1341) | Declarada: o perfil é validado ao carregar, com os mesmos limites (`max_bytes` ≤ `MAX_BYTES`, método só `GET`); media types contidos em `DEFAULT_ALLOWED_MIMES` mais `application/json`, este admitido só na sessão assistida e só para recurso que o declare; o fluxo automático não muda. Perfil inválido impede a sessão | perfil | erro de configuração |
| 18 | Cabeçalhos do chamador (429–447) e identidade da requisição (474–497) | Inaplicável: a porta não emite requisição nem recebe cabeçalhos de chamador. Identidade pública: §2.3, "Identidade da obtenção" | — | — |
| 19 | Cookies da `Session` do transporte (546–603) | Inaplicável: cookies ficam no perfil temporário; a porta só lê **nomes** dos cookies enviados, em memória, para a §2.3(2) | `requestWillBeSentExtraInfo.associatedCookies` | recusa de candidata |
| 20 | Revalidação de resposta reaproveitada (635–661) | Inaplicável: não há reaproveitamento | — | — |
| 21 | Metadados HTTP do recibo (`observe_http_response`, `HTTPMetadata`, 124–214) | Igual: a porta constrói o recibo pela mesma função, com os mesmos limites e descarte de duplicatas | cabeçalhos | `RespostaInvalida` |
| 22 | `fetched_at` (1277) | `wallTime` do `requestWillBeSent` + (`timestamp` de `loadingFinished` − `timestamp` do `requestWillBeSent`), do mesmo pedido, em UTC | `wallTime`, `timestamp` | — |

### 2.5 Bytes, hash e comparação entre capturas

1. **Objeto do hash.** O exemplar (0088) é o corpo como o navegador o recebeu depois de decodificar o
   Content-Encoding, antes de qualquer interpretação de charset; o SHA-256 é desses bytes. Sem compressão, coincidem
   com os bytes do fio. Com compressão, o hash não prova os bytes comprimidos da rede; o recibo registra a
   codificação original e, onde informada, a soma de `dataReceived.encodedDataLength`.
2. **Obtenção dos bytes** (Codex r4, B1; Terra r4, achado 2). O corpo é obtido **exclusivamente** por
   `Network.streamResourceContent`, chamado no `requestWillBeSent` do pedido elegível: os bytes são o `bufferedData`
   devolvido, seguido dos `dataReceived.data` subsequentes, todos em base64. `Network.getResponseBody` não é usado:
   no laboratório, ele devolveu texto reinterpretado e diferente dos bytes originais para BOM UTF-16 sob cabeçalho
   UTF-8 e para ISO-8859-1, e o campo `Response.charset` informou `utf-8` no primeiro caso; o streaming foi idêntico
   aos bytes originais em todos os dez casos (laboratório, resultado 1). Se o streaming falhar ou não estiver ativo
   antes do primeiro `dataReceived`, a candidata é recusada. Tamanho dos bytes diferente da soma de `dataLength`
   recusa (§2.4, linha 7).
3. **Conteúdo variável injetado** (Codex r4, R8; Terra r4, achado 6). O Planalto acrescenta, depois do último
   `</html>`, um script do WAF F5. O exemplar é guardado íntegro; o hash bruto nunca é usado para afirmar que duas
   capturas têm o mesmo conteúdo. O perfil do Planalto registra o **modelo literal** do bloco: a cauda do documento
   depois do último `</html>`, em que a única região variável é o valor de `f5_p`, gramática `[A-P]{128}`;
   substituído esse valor por `<TOKEN>`, a cauda tem 1.440 bytes e SHA-256
   `57e730d2a5f31c72f6d347d198d2e426eb7495188129242fe024c14961be4f3f`. Conferido em três fixtures do repositório
   (Leis 6.385, 6.404 e 10.303) e nas duas capturas do teste exploratório; as fixtures do CC e das Leis 14.195 e
   14.430 **não** casam o modelo (cauda diferente). Equivalência textual entre capturas só se afirma quando a cauda de
   todas casa exatamente o modelo; caso contrário, a equivalência não é afirmada e o caso vai ao humano. A
   equivalência é textual (texto extraído pelo parser, sem o bloco), não equivalência normativa integral. Mudança
   do modelo pela fonte é tratada como cauda diferente até registro de novo modelo.

### 2.6 Proveniência, `verified` e frescor

1. A captura grava `procedencia: sessao_assistida` (0075) e, separadamente, `modalidade_acesso:
   sessao_assistida` (0067), que sobrevive à exportação e à instalação de snapshot (onde a procedência pública
   passa a `snapshot`, 0075) e é publicada nas evidências dos adaptadores. Grava ainda `sessao_id` aleatório, o
   identificador da obtenção, versão do navegador, protocolo, IP remoto e emissor do certificado; nunca dado
   derivado de cookie.
2. A modalidade assistida não reduz os requisitos de `verified` (regra 1): identidade, âncora reproduzível e
   confronto efetivo continuam exigidos. A origem dos bytes é provada pelos eventos de rede do próprio navegador
   (§2.3 e §2.4); resposta sem essa prova não vira captura. Origem e hash provam de onde vieram os bytes, não que a
   fonte oficial não esteja comprometida. A 0083 trata da conferência de recibo gravado da Câmara e não é invocada
   aqui como modelo de ameaça.
3. Frescor: ultrapassados 30 dias, a captura deixa de sustentar `vigente_na_fonte` em consulta corrente, nas
   condições da 0002. Identidade, confronto textual e fundamento histórico não expiram por isso, preservadas as
   abstenções históricas da 0075.

### 2.7 Segredos, dados pessoais e artefatos

1. Diretório da sessão (perfil do navegador, temporários, logs) criado antes do lançamento, sob o staging, com ACL
   que exclui outras contas locais sem privilégio; a ACL é conferida antes do lançamento e, se falhar, a sessão
   não abre. Premissa de ameaça: §2.2(7).
2. Fim normal, erro e interrupção controlada apagam o diretório; após término abrupto, a sobra é isolada e apagada
   na inicialização seguinte. Downloads negados por `Browser.setDownloadBehavior(deny)`, comando de configuração do
   navegador que não altera requisição (§2.12). Relatórios de
   falha desligados (`--disable-breakpad`). O aceite inventaria os locais em que o navegador efetivamente grava
   durante a sessão; gravação fora do diretório da sessão que não possa ser evitada ou apagada impede a sessão.
3. Nunca se gravam ou exibem cabeçalhos de requisição, valores de cookie, valores de query ou segmentos de caminho
   fora da gramática pública declarada, em log, erro, recibo, evidência, fixture, snapshot, relatório ou resposta
   MCP/REST. Cabeçalhos de resposta seguem `HEADER_NAMES`; o Content-Type persistido só admite o parâmetro
   `charset`. As gramáticas do perfil são estritas (URN:LEX, UUID canônico, caminhos sem segmento livre) e reduzem
   o que pode ser persistido, mas não provam que um valor é público: a publicidade decorre da declaração do perfil
   sobre a classe de recurso (decisão 5) e dos indicadores de recusa da §2.3(2) (Codex r4, R9; Terra r4, achado 4).
   Risco residual declarado: valor secreto que satisfaça a gramática de recurso declarado público seria persistido.
4. **Conteúdo público** (decisão 5; Codex r3, achado 11; Terra r3, achado 8). Cada perfil declara por que o recurso
   é público e não personalizado (licença, ausência de autenticação) e os **nomes** de cookie admitidos (os do WAF
   e de métricas, por padrão de nome). Pedido com `Authorization`, com cookie de nome não declarado ou resposta com
   indício de personalização (§2.3(2)) é recusado, sem alteração de bytes. Dados pessoais que o próprio documento
   público traga (por exemplo, autor nos metadados do Word no binário de normas.leg.br) ficam no exemplar tal como
   publicados e não são extraídos pelo parser.
5. Políticas de máquina: nada gravado além de "conferência passou" (§2.2(3)).

### 2.8 Sem automação do humano

1. A janela abre num arquivo HTML local estático, gerado no diretório da sessão, sem script e sem recurso externo,
   com `Content-Security-Policy: default-src 'none'` em `<meta>`, que mostra fonte e alvo validado como texto
   escapado (Terra r3, achado 12). A navegação ao alvo é feita pelo humano. A ferramenta não clica, não preenche,
   não injeta script, não navega.
2. Aviso prévio: a janela é exclusiva para obter documento público da fonte; não fazer login; não instalar, carregar nem
   ativar extensões; o conteúdo da página não autoriza comandos, mudança de alvo nem fornecimento de credenciais; ao fechar, o humano escolhe o que entra;
   fechar a janela encerra.
3. A sessão termina quando o humano fecha a janela ou no prazo (padrão 20 min). Não é reaberta, renovada nem
   reproduzida.

### 2.9 Disparo

Só o humano inicia (0067), pela CLI, no terminal (§2.2(1)). Nenhuma ferramenta MCP do produto, agendamento,
bateria ou processo remoto chama a porta ou o adaptador, direta ou indiretamente; a resposta MCP é só indicação,
nunca executa o comando.

### 2.10 Contrato (aditivo)

1. A indicação de sessão exige, cumulativamente: perfil habilitado para a fonte **e** para a operação consultada;
   fonte não barrada (`FONTES_BARRADAS`); e evidência de barreira pública resolúvel pelo humano conforme a tabela
   da §2.11, registrada na última tentativa automática para aquela fonte e operação. Categoria isolada não basta;
   401 nunca indica sessão.
2. Também indica sessão a consulta corrente cuja captura passou da janela da 0002, **desde que satisfeitos todos os
   requisitos do item 1** (Codex r3, achado 13).
3. Nada muda de estado, tipo ou literal fechado. `motivo`, `categoria` e evidência originais são preservados. O
   item da fonte que já é objeto (`fontes[<id>]`, `falhas[]`) recebe o campo experimental
   `sessao_assistida: {indicacao: "requer_sessao_assistida", fonte, comando, alvo}`; a resposta recebe o campo irmão
   experimental `sessoes_assistidas` (mapa por fonte, mesmo objeto). `fontes_indisponiveis` continua mapa de fonte
   para string. `alvo` é o sanitizado (§2.7).
4. `docs/CONTRATO.md` e a lista de experimentais são atualizados no PR da implementação.

### 2.11 Perfis da primeira hora

`PerfilSessaoAssistida(origens, recursos, vinculos, cookies_admitidos, fundamento_publico, limpeza_texto,
max_bytes, max_capturas, operacoes, barreiras)`, validado ao carregar (§2.4, linha 17). Primeira hora: só
`planalto` e `normas_leg`. O `tjsp` depende do `POST` (§5) e fica para a decisão que o tratar.

**`planalto`** (operações de legislação)
- Origem: `www.planalto.gov.br:443`.
- Recurso: `document`, `GET`, caminho `^/ccivil_03/[A-Za-z0-9_\-/]+\.htm[l]?$` sem `..` nem segmento vazio, sem
  query; media type `text/html`.
- Cookies admitidos: padrões de nome do WAF F5 (`^TS[0-9a-f]{6,}$`, `^BIGipServer[\w.\-]+$`, `^f5avr\w+$`, `^f5_cspm$`; os dois últimos constam do próprio script
  do WAF, §2.5(3)). Nome
  diferente recusa a candidata; a correção do perfil é registrada.
- Fundamento público: compilação oficial publicada sem autenticação.
- `limpeza_texto`: cauda do WAF F5 no modelo literal da §2.5(3).
- `max_bytes`: `MAX_BYTES` (10 MiB). `max_capturas`: 50.
- Barreira: reinício de conexão (`transporte_TransportError`) depois do GET com o UA identificado, na
  reclassificação de `connectors/planalto.py`, ou recusa com UA identificado da 0048; validade de 30 dias.

**`normas_leg`** (operações de legislação)
- Origem: `normas.leg.br:443`.
- Recurso A (metadados): `xhr`, `GET`, caminho `/api/public/normas`, query exatamente
  `urn=<URN>&&tipo_documento=maior-detalhe` ou `urn=<URN>&tipo_documento=maior-detalhe`, com `<URN>` na gramática
  `^urn:lex:br:federal:[a-z]+(\.[a-z]+)*:\d{4}-\d{2}-\d{2};[0-9a-z]+([.\-][0-9a-z]+)*$`; media type
  `application/json`.
- Recurso B (texto): `xhr`, `GET`, caminho `^/api/public/binario/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/texto$`,
  sem query; media type `text/html`.
- **Vínculo B → A** (Terra r3, achado 3; Terra r4, achado 3; Codex r4, R7; dados reais em `teste-normas-2026-11-19.md`).
  O vínculo é resolvido sobre o conjunto completo das candidatas da sessão, ao fechar a janela, antes da seleção e de
  qualquer gravação. Uma candidata A vale para o vínculo se o JSON for válido, `legislationIdentifier` for igual à URN da
  query de A e cada elemento de `encoding[]` com `@type` `LegislationObject` tiver `contentUrl` na forma
  `https://normas.leg.br/api/binario/<uuid>/texto`, `version` em {`Original`, `Current`} e `@id` com a URN e, para
  `Current`, a expressão `@versao.atualizada`, para `Original`, a expressão `@<data>`; elemento fora disso invalida a A.
  Uma candidata B (UUID tirado do caminho `/api/public/binario/<uuid>/texto`, única equivalência de caminho admitida)
  liga-se à A cujo `encoding[]` contém o mesmo UUID. B é recusado se: nenhuma A válida o contém; o UUID aparece em mais
  de um elemento, em mais de uma URN ou em A com hashes diferentes para a mesma URN; há dois B do mesmo UUID com hashes
  diferentes (o grupo inteiro é recusado; B idênticos contam como um). Conflito detectado em qualquer momento da sessão
  invalida todas as candidatas que ele alcança. A captura B registra o identificador e o hash da captura A que a
  fundamenta, a URN, o UUID, o `version` e o `@id`; pela 0088, `Current` e `Original` são expressões distintas, ambas
  com `legislationLegalValue: UnofficialLegalValue`.
- Cookies admitidos: métricas por padrão de nome (`^_ga$`, `^_ga_[A-Z0-9]+$`, `^_gid$`, `^_gat\w*$`). A sessão de
  teste não registrou os nomes reais (redigidos); nome diferente recusa a candidata, e a correção do perfil é
  registrada.
- Fundamento público: API pública sem autenticação; licença CC BY 4.0 declarada no próprio JSON.
- `limpeza_texto`: nenhuma (binário estável entre obtenções).
- `max_bytes`: `MAX_BYTES`. `max_capturas`: 50.
- Barreira: 403 com desafio provado (0085); validade de 30 dias.

NPL e DOU (`www.in.gov.br`) seguem barrados (pendências 28 e 31); abri-los à sessão exige decisão própria.
`listar_fontes` declara `sessao_assistida: disponivel|nao_aplicavel` (experimental).

### 2.12 Métodos CDP admitidos (lista fechada)

Cada chamada leva exatamente os parâmetros indicados; parâmetro ausente, adicional ou com outro valor é recusado pelo
próprio adaptador antes do envio. Chamada a alvo vai com o `sessionId` da sessão anexada; chamada ao navegador vai sem
ele. Métodos sem parâmetros usam objeto vazio.

| Método e parâmetros | Natureza | Alvo |
|---|---|---|
| `Target.setDiscoverTargets` `{discover: true}` | observação de alvos e subtipos | navegador |
| `Target.setAutoAttach` `{autoAttach: true, waitForDebuggerOnStart: true, flatten: true}` | anexação antes de qualquer requisição do alvo | navegador |
| `Network.enable` `{}` | eventos de rede | `page` |
| `Page.enable` `{}` | eventos de quadro (`frameNavigated`, `frameAttached`) | `page` |
| `Runtime.runIfWaitingForDebugger` `{}` | liberar o alvo depois de `Network.enable` e `Page.enable` | cada alvo anexado |
| `Page.getFrameTree` `{}` | prova do quadro principal (§2.3(3)), somente leitura | `page` |
| `Network.streamResourceContent` `{requestId}` | bytes do corpo (§2.5(2)), só para pedido elegível, no `requestWillBeSent` | `page` |
| `Browser.getVersion` `{}` | versão para o recibo | navegador |
| `Browser.setDownloadBehavior` `{behavior: "deny"}` | negar downloads; não altera requisição | navegador |
| `Browser.close` `{}` | encerrar ao fim ou no prazo | navegador |

Nenhum desses métodos altera requisição, cache, service worker, cabeçalho ou identidade, nem navega. Alvos que não
sejam `page` (extensões, workers) são liberados com `Runtime.runIfWaitingForDebugger` e não recebem outro comando.

### 2.13 Cobertura

A matriz e o bloco `cobertura` declaram o acesso (`automatico`, `assistido`) por fonte, nos três denominadores da
0067. Captura assistida nunca é somada à cobertura automática.

### 2.14 Dependência e distribuição

Sem Playwright e sem dependência nova: o canal é o pipe do próprio navegador, lido pela biblioteca padrão. O
instalador oficial do Windows não muda; o teste de instalação confere que `fv sessao` existe.

## 3. Aceite (o incremento só conclui com testes que provem)

Cada item liga norma, cenário e resultado esperado (aceitação ou código de recusa); fixtures seguem a regra 9. O
laboratório de 19/11 (`laboratorio-2026-11-19.md`) antecipa parte dos itens 1 e 2, sem substituí-los.

1. **Adaptador real contra origem controlada.** Chrome instalado contra servidor HTTPS local. A confiança na AC de
   teste e a admissão do IP de loopback vêm de parâmetros exclusivos do harness; um teste prova que o caminho de
   produto se recusa a lançar com eles. Casos: as 22 linhas da §2.4; `headersText` com campo malformado,
   `Content-Length` com 21 dígitos, duplicado, conflitante, coexistência com `Transfer-Encoding`; chunk malformado e
   truncado; `gzip`, `deflate`, `br`, `zstd` e codificação não admitida; bomba de compressão (streaming abandonado,
   candidata descartada); `Content-Length` declarado acima do limite; confrontos finais da linha 7 (sem codificação,
   com codificação em `fetch`, com codificação em documento); corpo vazio; redirecionamento de rede (recusa), HSTS
   interno provado (aceito, sem que a URL `http` vire candidata) e interno sem prova (recusa); 304 exposto como 200;
   prazo sem cabeçalhos (`Timeout`), com cabeçalhos e sem término (`RespostaInvalida`) e com cabeçalho parcial;
   **identidade de bytes pelo streaming** em UTF-8, UTF-8 só no `<meta>`, UTF-8 inválido, sequência incompleta,
   U+FFFD literal, BOM UTF-16 sob cabeçalho UTF-8 (inclusive com tamanhos compensados), ISO-8859-1 e windows-1252;
   streaming iniciado tarde ou falho (recusa); eventos fora de ordem, `requestId` repetido entre alvos, alvo criado
   antes da anexação, aba aberta já com URL (primeiro documento não candidato), perda do canal; limites da linha 15.
2. **Proveniência.** Resposta de cache, de service worker que sintetiza resposta, de prefetch, de pré-renderização
   (inclusive em transição para página), restauração por bfcache, recurso iniciado por Early Hints: nenhuma vira
   candidata; resposta final depois de 103: avaliada por si; recarga forçada pelo humano vem da rede e vira.
3. **Escopo, quadro e vínculo.** `POST`, `Authorization`, cookie de nome não declarado, cookie bloqueado (não conta),
   `Cache-Control: private`, `Vary: Cookie`, caminho e query fora da gramática, media type não declarado, desafio,
   documento de iframe (inclusive no mesmo processo), `XHR` iniciado por iframe, `blob:` e `data:`, download,
   WebSocket. normas.leg.br: UUID trocado, URN divergente, UUID em dois elementos, B sem A, B de outra URN, **segunda A
   posterior que torna o UUID ambíguo** (invalida o B já aceito), dois B com hashes diferentes para o mesmo UUID
   (grupo recusado), dois B idênticos (um só), `version` ou `@id` incoerentes.
4. **Seleção.** Grafo resolvido antes da lista; sem marcação, nada é gravado; dependente segue o documento e é exibido
   com seu hash; candidata não marcada não deixa rastro.
5. **Filtro na origem.** Sessão sintética com tráfego de terceiros, SSO simulado, eventos extras antes e depois do
   evento principal, `requestId` coincidente entre terceiro e fonte, mudança de origem na cadeia: nada fora das
   origens persiste, nem em diagnóstico.
6. **Segredos e conteúdo público.** Varredura sobre sessão sintética com cookies, `Authorization`, tokens em query, em
   caminho **que satisfaça a gramática** (o valor é persistido só porque o perfil declara a classe de recurso pública;
   o teste documenta esse limite), em corpo e em parâmetros extras do Content-Type (recusados ou não persistidos, conforme
   a §2.7); documento público com dado pessoal publicado (preservado no exemplar, fora do texto extraído).
7. **Diretório e artefatos.** ACL conferida (falha fecha a sessão); acesso negado a outra conta sem privilégio;
   inventário dos locais de gravação do navegador durante e depois da sessão; limpeza em fim normal, erro, interrupção
   e recuperação após término abrupto.
8. **Ambiente.** Política de proxy simulada (HKCU), token de nuvem, `ExtensionInstallForcelist` com item e
   `ExtensionSettings` com `force_installed`: não abre. Vigilância: criação, alteração e remoção de arquivo sob
   `Default\Extensions` depois da linha de base, inclusive instalação e remoção entre duas leituras do inventário:
   candidatas invalidadas e sessão encerrada; estouro do buffer e falha do observador: idem; instalação durante o
   assentamento: linha de base adiada. Inventário: componente dentro da pasta do navegador com `webRequest` (como o
   `Brave`): admitido; componente externo (`location` 10) ou extensão comum com permissão vedada, inclusive só com regras
   estáticas `declarativeNetRequest` (instalada por mecanismo aceito pelo navegador de teste; §5.8): sessão encerrada;
   `Secure Preferences` ilegível: nenhuma candidata; pedido iniciado durante o assentamento: não candidato; barreira com
   sentinela atrasada além de 5 s: candidatas invalidadas; extensão desempacotada (`location` 4) no inventário: sessão
   encerrada; lançamento com `--load-extension` ou `--enable-unsafe-extension-debugging`: recusado pelo adaptador. Pipe indisponível: não abre. Cada navegador admitido (Chrome, Edge,
   Brave) passa pelos itens deste aceite.
9. **Passividade e prontidão.** Registro do tráfego CDP do adaptador: só métodos e parâmetros da §2.12, na sequência da
   §2.3; conferência estática da mesma lista; pedidos vistos pela origem de teste com e sem o adaptador anexado:
   iguais (cabeçalhos inclusive).
10. **Porta única.** Nenhum conector ou parser lê bytes do adaptador sem passar pela porta (AST e teste de execução
    com tentativa de contorno).
11. **`verified`, frescor e cobertura.** Captura assistida sem identidade, âncora ou confronto não ganha `verified`;
    regressões nos caminhos finais da 0075 (`verificar_texto`, `obter_dispositivo`), com histórico e juízo pendente;
    os 30 dias só afetam `vigente_na_fonte` em consulta corrente; cobertura assistida publicada à parte.
12. **Proveniência gravada.** `modalidade_acesso` e `procedencia` gravados, publicados nas evidências dos adaptadores;
    em snapshot instalado, procedência `snapshot` e `modalidade_acesso` preservada.
13. **Disparo e perfil pessoal.** Nenhum caminho MCP do produto, agendado, de bateria ou remoto alcança porta ou
    adaptador (AST e execução); sem TTY ou sem confirmação, nada é lançado; expiração, fechamento e queda do canal
    encerram sem reabertura, renovação ou repetição; nenhum acesso ao diretório de perfil pessoal do navegador
    (monitoramento de arquivos durante a sessão).
14. **Contrato.** Indicação só nas condições da §2.10, inclusive envelhecimento com todos os requisitos; sem barreira
    registrada, barreira expirada, 401, operação não habilitada e fonte barrada: não indica; motivo e categoria
    originais preservados; nenhum tipo muda.
15. **Conteúdo variável.** Planalto: cauda que casa o modelo da §2.5(3) com tokens distintos, mesmo texto; cauda
    diferente, bloco duplicado, deslocado, ausente, com texto inserido ou malformado: equivalência não afirmada.
16. **Instalação.** O teste de instalação do Windows confere que `fv sessao` existe e que, sem pipe disponível, sai com
    a recusa da §2.2(2).
17. **Sessão manual** pelo titular, no terminal, em máquina sem política que viole a §2.2(3), com Planalto e
    normas.leg.br, antes da reapuração da Porta L; o supervisor só lê os resultados. Complementa; não substitui.

## 4. O que não muda e alternativas rejeitadas

Não mudam: `verified`, 0002, 0060 a 0066 e transporte no fluxo automático (D5), reserva (D6). Regras invariáveis:
só a leitura da regra 4 na sessão assistida (§2.1(1)), por decisão do titular.

Rejeitados: proxy do transporte que refaz as trocas (v2); qualquer comando que altere requisição, cache ou service
worker do navegador, inclusive `Network.setCacheDisabled`, `Network.setBypassServiceWorker` e forçar
`Accept-Encoding: identity` (decisão 2); porta TCP de depuração; Playwright ou qualquer automatizador; aceitar
redirecionamento de rede sem corpo do salto; leitura de `chrome://policy` pelo adaptador (exigiria navegar);
reaproveitar cookies da sessão em requisições da ferramenta; importar HAR ou cookies do navegador pessoal; extensão
da ferramenta; capturar o DOM; instalar AC no sistema; modo sem janela; OCR.

## 5. Questões abertas

1. `POST` (pesquisa do TJSP): identidade de requisição com corpo; decisão própria antes do TJSP.
2. Anexos em PDF: o visualizador interno os trata como `document` se o media type estiver declarado no perfil;
   download continua negado; fonte que só sirva download exige decisão própria.
3. Abertura de NPL e DOU à sessão.
4. Pipe de depuração no Windows: confirmar no teste do adaptador; sem ele a sessão não existe (§2.2(2)), e a
   questão volta ao titular.
5. Nomes reais dos cookies do Planalto e de normas.leg.br: confirmar na sessão manual (§3.17); divergência corrige o
   perfil por registro, nunca por inferência em tempo de execução.
6. **Onde a sessão roda.** No notebook do titular, Chrome e Edge recebem a Fortinet por política e não admitem a sessão;
   o titular indicou o Brave instalado na própria conta, que não tem política nem extensão instalada (§2.2(3)). A
   compatibilidade desse uso com as regras de TI do escritório é do titular.
7. A versão `Original` de normas.leg.br como árbitro `texto_publicado` não oficial (teste de normas, achado 9):
   fora desta decisão.
8. Mecanismo de instalação de extensão no harness de teste (§3.8): o Chrome de marca 157 ignora `--load-extension`;
   usar política de teste em HKCU com pacote local ou navegador de teste que aceite extensão desempacotada.
9. **Streaming sem bytes em rajada.** Na sessão de teste no Brave, nove XHR de normas.leg.br, entre eles o binário da
   Lei 6.404, terminaram sem bytes de streaming e sem `responseReceivedExtraInfo`, sem erro do comando. Pela §2.3, são
   recusados; a causa (corrida ou pedido repetido pela página) deve ser isolada na implementação, porque afeta a
   utilidade, não a correção.

## 6. Execução

Implementação pelo Codex (`workspace-write`, worktree e ramo próprios) em duas trilhas sequenciais, por regra de uma
trilha por vez em `transport.py`: (a) porta `capturar_assistida` com a matriz da §2.4; (b) adaptador CDP, CLI,
perfis, seleção e contrato. Revisão de fronteiras e segredos por Terra; auditoria por Codex somente leitura, sessão
nova, com os critérios da §3 fixados antes, inclusive a auditoria própria de `transport` (D5). A pendência 24
(reabertura de `normas_leg`) entra na mesma versão.

## 7. Histórico e decisões do titular

- v1 (captura por CDP, sem emenda): Codex r1 e Terra r1 BLOQUEADOR.
- v2 (proxy do transporte): Codex r2 e Terra r2 BLOQUEADOR; bifurcação.
- 19/11: titular escolhe a opção A; teste exploratório; v3.
- v3: Codex r3 (16 achados) e Terra r3 (12 achados) BLOQUEADOR.
- 19/11, decisões do titular sobre a rodada 3: (1) exceção ao teto do D5 para a rodada 4, nas condições acima;
  (2) observação pura, sem comando que altere requisição, cache ou service worker; (3) sessão só abre com conexão
  direta, sem extensão com permissão de interceptação e com pipe de depuração; (4) seleção humana das capturas ao
  fechar a janela, com dependentes vinculados; (5) conteúdo público por declaração do perfil, com nomes de cookie
  admitidos; (6) leitura expressa da regra 4 na sessão assistida.
- 19/11: segunda sessão de teste (normas.leg.br); v4.

| Parecer r3 | Achado | Resposta na v4 |
|---|---|---|
| Codex | 1. Regra 4 | §2.1(1); decisão 6 |
| Codex | 2. Cache e service worker | §2.2(4); §2.12; decisão 2 |
| Codex | 3. Matriz incompleta | §2.4, linhas 4, 5, 7, 12, 15, 17 a 21 |
| Codex | 4. Contenção | §2.4, linhas 7 e 15 (alcance declarado) |
| Codex | 5. Charset | §2.5(2) |
| Codex | 6. Redirecionamentos e HSTS | §2.4, linha 8 (nenhum salto de rede; HSTS provado) |
| Codex | 7. Correlação | §2.3, "Correlação"; §2.2(5) |
| Codex | 8. Status, `headersText`, opcionais | §2.3(1); §2.4, linhas 4 e 7 |
| Codex | 9. Prazo e classificação | §2.4, linhas 12 e 22 |
| Codex | 10. Proxy efetivo e políticas | §2.2(2) e (3); decisão 3 |
| Codex | 11. Conteúdo público | §2.3(2); §2.7(3) e (4); decisão 5 |
| Codex | 12. Identidade e autorização | §2.3, "Identidade" e "Seleção"; decisão 4 |
| Codex | 13. Perfis e envelhecimento | §2.10(2); §2.11 |
| Codex | 14. Lista CDP | §2.12 |
| Codex | 15. Alcance do filtro | §2.2(5); §2.7(2) |
| Codex | 16. Aceite | §3, itens 1 a 16 |
| Terra | 1. Extensões forçadas | §2.2(3); §3.8 |
| Terra | 2. Canal DevTools | §2.2(2) e (7) |
| Terra | 3. Vínculo JSON-binário | §2.11 (`normas_leg`), com dados reais |
| Terra | 4. Origem e associação | §2.3(1) e "Correlação"; §3.2 |
| Terra | 5. Seleção humana | §2.3, "Seleção" |
| Terra | 6. Identidade de bytes | §2.5(2) |
| Terra | 7. Bomba e completude | §2.4, linhas 5 e 7 |
| Terra | 8. Captura privada | §2.3(2); §2.7(4) |
| Terra | 9. Segredos e artefatos | §2.7(2) e (3); §3.7 |
| Terra | 10. Bloco `f5_cspm` | §2.5(3); §3.15 |
| Terra | 11. Tráfego não controlado | §2.4, linha 15; premissa: o tráfego do navegador é o da navegação humana, fora do controle da ferramenta, e nada dele é capturado sem passar pela porta |
| Terra | 12. Página inicial | §2.8(1) |

- v4: Codex r4 (B1 a B3, R1 a R9) e Terra r4 (quatro bloqueadores, três ressalvas) BLOQUEADOR. Pelas condições da
  exceção, a especificação voltou ao titular.
- 19/11: o titular aprova a rodada 5 de escopo fechado, precedida de laboratório (`laboratorio-2026-11-19.md`); v5.

| Parecer r4 | Achado | Resposta na v5 |
|---|---|---|
| Codex | B1. Identidade de bytes (BOM UTF-16) | §2.5(2): só `streamResourceContent`; `getResponseBody` excluído; laboratório, resultado 1 |
| Codex | B2. Extensão sem alvo CDP | §2.2(3): inventário por `Secure Preferences`, antes de candidata e periódico; laboratório, resultado 5 |
| Codex | B3. Quadro principal e prontidão | §2.3, "Prontidão" e item 3; §2.12 (`Page.enable`, `Page.getFrameTree`); laboratório, resultados 3 e 4 |
| Codex | R1. `application/json` | §2.4, linha 17 |
| Codex | R2. Confrontos finais de tamanho | §2.4, linha 7; laboratório, resultado 2 |
| Codex | R3. "Resposta iniciada" | §2.4, linha 12 (diferença declarada) |
| Codex | R4. Fila e memória | §2.4, linha 15 (valores fixados) |
| Codex | R5. URL `http` do HSTS | §2.4, linhas 1 e 8 |
| Codex | R6. Parâmetros CDP | §2.12 (parâmetros exatos, `sessionId`) |
| Codex | R7. Grafo de vínculos | §2.3, "Seleção"; §2.11 (`normas_leg`) |
| Codex | R8. Bloco `f5_cspm` | §2.5(3): modelo literal com hash, token `[A-P]{128}` |
| Codex | R9. Publicidade por sintaxe | §2.7(3), com risco residual declarado |
| Terra | 1. Extensões | como B2 |
| Terra | 2. Identidade de bytes | como B1 |
| Terra | 3. Vínculo e seleção | como R7 |
| Terra | 4. Gramática e publicidade | como R9; decisão 5 mantida |
| Terra | 5. Cookies e personalização | §2.3(2) (cookies bloqueados não contam); §3.6; §5.5 |
| Terra | 6. `f5_cspm` | como R8 |
| Terra | 7. HSTS e lista CDP | §2.4, linha 8; §2.12; §3.1 e §3.9 |

- v5: Codex r5 e Terra r5 resolvem B1, B3, R1 a R3, R5 a R9 e Terra 2 a 7; resta, comum aos dois, B2 (inventário ao
  longo do tempo: o Chrome grava as preferências com atraso; extensão transitória entre leituras) e, do Codex, R4.
- 19/11: o titular aprova a correção de B2 e R4 com conferência final curta; indica o Brave; aprova que extensões de
  componente embutidas no navegador sejam tratadas como parte dele. Laboratório de vigilância e sessão de teste no
  Brave (`teste-brave-2026-11-19.md`): vigilância capta instalação por política aos 5 s; Brave sem política; 304
  apresentado como 200 detectado pelo `statusCode` bruto; bytes do binário de normas iguais entre Chrome e Brave. v5.1.

| Parecer r5 | Achado | Resposta na v5.1 |
|---|---|---|
| Codex e Terra | B2. Inventário ao longo do tempo | §2.2(3)(a) recusa prévia de extensão forçada por política; (b) vigilância contínua do diretório com linha de base e invalidação; (c) inventário como evidência auxiliar |
| Codex | R4. Contabilidade de memória | §2.4, linha 15 (todas as representações; reserva antes da alocação pelo tamanho do blocos de leitura do pipe) |
| Titular | Extensões de componente | §2.2(3)(c) |
| Titular | Brave | §2.2(2) e (3); §3.8; §5.6 |

- Conferência final curta da v5.1: Codex e Terra resolvem R4, a regra de componentes e a admissão do Brave; restam
  dois limites da vigilância (Terra: pedido iniciado no assentamento e notificações pendentes; Codex: extensão
  desempacotada carregada de fora do diretório). v5.2: §2.2(3)(b), barreira com sentinela e elegibilidade só após a
  linha de base; (b'), tratamento dos três caminhos de carga desempacotada, com premissa declarada sobre o operador;
  aviso da §2.8(2); §3.8.
- Verificação final (0070) sobre a v5.2: Codex e Terra SEM_BLOQUEADOR. 19/11: o titular aprova a premissa sobre o
  operador (§2.2(3)(b')). A 0089 torna-se vigente; as remissões em `AGENTS.md` e na 0001 passam ao PR da implementação.
