# 0089 - Sessão assistida: especificação do mecanismo; emenda à 0067

**Situação: proposta, não vigente.** Versão 4, submetida à rodada 4 por **exceção ao teto do D5 aprovada pelo
titular em 19/11/2026**, nas condições da 0074 e da 0076: a v4 incorpora todos os achados da rodada 3; a exceção
fica registrada antes de qualquer merge; novo BLOQUEADOR encerra esta especificação na forma atual e devolve a
questão ao titular. Histórico, pareceres e testes em `docs/auditoria/0089/`. Não implementar antes do parecer.

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

## 2. Decisão

### 2.1 Emenda: regra 4 e 0067

1. **Leitura da regra 4 na sessão assistida** (decisão 6 do titular; Codex r3, achado 1). Exclusivamente na sessão
   assistida, a regra 4 ("toda requisição passa por `freoa_verifica.transport`") exige que **toda admissão de
   resposta como captura** passe por `transport.capturar_assistida`. As requisições do navegador dedicado não são
   emitidas nem encaminhadas pelo transporte. A exceção não alcança requisição alguma da ferramenta nem o fluxo
   automático. `AGENTS.md` (regra 4) e a 0001 recebem, no PR desta decisão, remissão a esta leitura.
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
2. **Navegador.** Chrome ou Edge **instalados**, lançados pelo adaptador com argumentos fechados:
   `--user-data-dir=<diretório da sessão>`, `--no-first-run`, `--no-default-browser-check`, `--disable-sync`,
   `--no-proxy-server`, `--disable-breakpad`, `--remote-debugging-pipe` (no Windows, com os identificadores de pipe
   herdados só pelo processo do navegador). Janela visível. Nunca: Playwright ou outro automatizador,
   `--enable-automation`, modo sem janela, porta TCP de depuração, `--ignore-certificate-errors`, exceção SPKI,
   proxy ou extensão da ferramenta. Se o pipe não puder ser estabelecido, a sessão não abre (decisão 3).
3. **Ambiente** (decisão 3; Terra r3, achado 1; Codex r3, achado 10). Antes do lançamento, o adaptador lê as
   políticas de máquina e de usuário no Registro do Windows (`Software\Policies\Google\Chrome` ou
   `Software\Policies\Microsoft\Edge`, em HKLM e HKCU), sem abrir página alguma. A sessão não abre se houver: política
   de proxy (`ProxySettings`, `ProxyMode`, `ProxyServer`, `ProxyPacUrl`); token de gerência em nuvem
   (`CloudManagementEnrollmentToken`), cujas políticas não são enumeráveis localmente. Depois do lançamento, a cada extensão que apareça como alvo, o adaptador lê o `manifest.json` no
   diretório da sessão; extensão com permissão de interceptação ou controle de rede (`webRequest`,
   `webRequestBlocking`, `webRequestAuthProvider`, `declarativeNetRequest`, `declarativeNetRequestWithHostAccess`,
   `proxy`, `debugger`) encerra a sessão sem capturas. Extensões de componente embutidas no próprio navegador são
   parte dele. Nenhum valor de política é gravado; o recibo da sessão registra só que a conferência passou.
   Consequência declarada: no notebook do titular, se a política do escritório forçar extensão ou proxy, a sessão
   não abre ali.
4. **Observação pura** (decisão 2; Codex r3, achado 2). O adaptador usa só a lista fechada de métodos CDP da §2.12;
   nenhum deles altera requisição, cache, service worker, cabeçalho ou identidade; o único de configuração nega
   downloads. Não navega, não injeta script,
   não clica, não interrompe carga. Cache e service worker do navegador ficam como estão; a porta recusa toda
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

**Candidata.** A porta aceita como candidata só a resposta que cumprir, cumulativamente:

1. **Troca de rede provada pelo navegador.** `Network.responseReceived` com `fromDiskCache`, `fromServiceWorker` e
   `fromPrefetchCache` **presentes e falsos** (ausência não vale como falso); nenhum
   `Network.requestServedFromCache` para o pedido; `remoteIPAddress`, `remotePort` e `securityDetails` presentes;
   `Network.responseReceivedExtraInfo` correspondente, com `statusCode` igual ao status da resposta (304 exposto
   como 200 é recusado); `Network.loadingFinished` (não `loadingFailed`); alvo do tipo `page` sem subtipo de
   pré-renderização desde a criação; status 200. 304, 206, 103 e os demais status nunca viram captura. Restauração
   de página sem troca nova (bfcache, histórico) não gera evento de resposta e, por isso, nunca vira captura nem
   renova frescor.
2. Método `GET`; nenhum salto de rede na cadeia (§2.4, linha 8); sem `Authorization` e sem cookie fora dos nomes
   declarados no perfil (§2.7(4)); resposta sem `Cache-Control: private` e sem `Vary` que inclua `Cookie` ou
   `Authorization`.
3. **Recurso admitido pelo perfil** (§2.11): tipo (`Document` de quadro principal ou `XHR`/`Fetch`), host, caminho e
   query conforme a gramática exata do recurso; fragmento descartado; esquema só `https` (`blob:`, `data:`,
   `filesystem:` e semelhantes recusados). WebSocket, Early Hints e recursos não declarados nunca são candidatos.
4. Media type declarado para aquele recurso.
5. Todas as linhas da matriz da §2.4 aprovadas.

**Correlação** (Codex r3, achado 7; Terra r3, achado 4). Toda associação de eventos usa a chave (sessão CDP, alvo,
`requestId`, ordinal do salto). O adaptador se anexa a cada alvo antes de ele iniciar requisições
(`Target.setAutoAttach` com espera pelo depurador); requisição cujo `requestWillBeSent` não foi observado, evento
fora de ordem que não se associe sem ambiguidade, chave repetida ou perda da conexão CDP descartam a candidata.
Nenhum evento herda autorização de retenção de outro salto ou de outro alvo.

**Vínculo.** A candidata é atribuída à sua própria URL validada e aos seus próprios eventos, nunca ao alvo sugerido
nem à navegação anterior. Navegação iniciada por conteúdo (script, meta refresh, janela aberta pela página) é
navegação nova, validada por si. Recurso dependente (o binário de texto de normas.leg.br) só é candidato quando o
vínculo declarado no perfil se verifica entre capturas da mesma sessão (§2.11).

**Seleção** (decisão 4; Terra r3, achado 5; Codex r3, achado 12). Ao fechar a janela, a CLI lista as candidatas
aceitas pela porta, cada uma com a identidade pública (fonte, URN ou caminho, tipo de recurso, versão quando
houver, tamanho e hash curto), e o humano marca as que entram. As não marcadas são descartadas sem gravação.
Recurso dependente segue o documento marcado; não é marcado à parte nem entra sem ele. Sem marcação, nada entra.

**Identidade da obtenção.** Cada candidata recebe identificador opaco único; não há cache nem reutilização por
método e URL. A identidade pública sanitizada nunca reúne destinos distintos; se reunisse, recusa.

Recusas são listadas ao humano com URL sanitizada e código.

### 2.4 Matriz de validação

Exaustiva quanto às validações e controles de `freoa_verifica/transport.py` (`35dd8bc`). **Igual**: mesma função ou
mesma regra, mesmo código. **Metadados**: mesma regra sobre dado de rede do navegador. **Declarada**: regra
substituta aprovada por esta emenda. **Inaplicável**: com a razão. Dado necessário ausente, opcional não presente
ou ambíguo causa recusa, nunca inferência. Recusa da porta não impede o navegador de exibir a página: só impede a
captura.

| # | Controle automático (código) | Na sessão assistida | Dado (CDP) | Recusa |
|---|---|---|---|---|
| 1 | URL ASCII, `https`, host permitido, porta 443, caminho não ambíguo, prefixos (`validate_reference`, `_path_allowed`, 605–629, 507–530) | Igual, pela mesma função, sobre a URL da resposta, e gramática exata do recurso (§2.11) | `request.url`, `response.url` | `BlockedHost` |
| 2 | DNS pela ferramenta com prazo e concorrência próprios; só IP público unicast; conexão ao IP validado (`validate_url`, `_public_unicast`, 64, 665–719, 770–783) | Metadados: o IP efetivo da conexão que entregou os bytes passa por `_public_unicast`; porta 443. Declarada: a resolução é do navegador, lançado sem proxy (§2.2(2) e (3)); prazo e concorrência de DNS inaplicáveis porque a ferramenta não resolve; o tempo de resolução entra no prazo total (linha 12) | `remoteIPAddress`, `remotePort` | `BlockedHost` |
| 3 | TLS verificado pelo contexto padrão | Metadados: navegador sem exceção de certificado; `securityDetails` com protocolo TLS 1.2 ou 1.3 e `securityState` seguro | `securityDetails`, `securityState` | `RespostaInvalida` |
| 4 | Sintaxe estrita da linha de status e dos campos; `Transfer-Encoding` só `chunked` e único; `Content-Length` com até 20 dígitos e único; recusa de coexistência de ambos (`_campos_estritos`, `_validar_framing`, 323–378) | HTTP/1.x: **igual**, por `_campos_estritos` e `_validar_framing` aplicados a `headersText`, que é então obrigatório. HTTP/2 e HTTP/3: declarada; o framing é o do protocolo, aplicado pelo navegador, e a porta confere nos cabeçalhos com multiplicidade (duplicatas separadas por `\n`) `Content-Length` único com até 20 dígitos e ausência de `Transfer-Encoding`. Protocolo vai ao recibo | `responseReceivedExtraInfo.headersText`, `.headers`, `response.protocol` | `RespostaInvalida` |
| 5 | Gramática e término dos chunks, trailers (`_get_chunk_left`, `_ler_trailer`, 243–320) | Declarada: o navegador recusa chunk malformado ou incompleto como erro de rede (`loadingFailed`), e a porta só aceita `loadingFinished`. Trailers não são observáveis nem usados. Diferença de aceitação admitida: o navegador pode tolerar extensão de chunk ou trailer que o transporte recusaria | `loadingFinished`, `loadingFailed` | recusa de candidata |
| 6 | Content-Encoding ausente ou `identity`, em todo status (0060, 1128–1136) | Declarada (emenda): admitidos ausente, `identity`, `gzip`, `deflate`, `br`, `zstd`, decodificados pelo navegador; outra codificação é recusada. A codificação original vai ao recibo; o hash é dos bytes decodificados (§2.5) | cabeçalhos com multiplicidade | `RespostaInvalida` |
| 7 | Tamanho declarado acima do limite recusado de imediato; bytes acima do limite durante a leitura; corpo vazio (1199–1203, 1238–1267) | Metadados: `Content-Length` declarado acima de `max_bytes` recusa a candidata ao chegar `responseReceivedExtraInfo`. Dois contadores independentes por pedido, a soma de `dataReceived.encodedDataLength` e a soma de `dataReceived.dataLength`, cada um contra `max_bytes`; excedido qualquer deles, a candidata é descartada e o corpo nunca é lido. Corpo vazio, recusado. Alcance declarado: o limite garante o que a ferramenta aceita e copia, não o consumo de memória do navegador | `dataReceived`, cabeçalhos | `TooLarge`, `EmptyBody` |
| 8 | Redirecionamentos: até 3, `Location`, destino validado, 307/308 entre origens recusados, desafio no corpo do salto (1137–1166, 1293) | Declarada: **nenhum salto de rede admitido** (máximo 0), porque o corpo do salto não é obtenível e o exame de desafio nele seria impossível. Única exceção: redirecionamento interno HSTS, provado por `redirectResponse` com status 307, sem `remoteIPAddress`, cabeçalho `Non-Authoritative-Reason: HSTS`, mudança só de `http` para `https` no mesmo host, caminho e query; não conta como salto. Documento obtido por redirecionamento de rede é recusado; o humano abre a URL final | `redirectResponse` | `BlockedHost` |
| 9 | Desafio (`detect_challenge`) em todo status, amostra de 64 KiB (381–418) | Igual, sobre status, cabeçalhos e os primeiros 64 KiB do corpo decodificado, como a 0060 §2 prevê para decodificação. Página de desafio nunca é candidata | corpo da candidata | `HTTPStatusError` com desafio |
| 10 | Content-Type sintaticamente válido; media type na lista (1188–1197) | Igual, sobre o Content-Type bruto; único parâmetro admitido no valor persistido é `charset`; o `mimeType` inferido pelo navegador não é usado | cabeçalhos | `RespostaInvalida` |
| 11 | Charset e interpretação textual (conectores, `texto_resposta.py`) | Igual, sobre os bytes da §2.5, com a mesma decodificação estrita | corpo | código do conector |
| 12 | Prazo total da chamada, compartilhado pela cadeia; classificação da falha pelo progresso: antes de resposta iniciada `Timeout`, depois `RespostaInvalida` (941–983, 1063–1077, 1344–1345) | Igual em valor (30 s, padrão de `fetch`) e em classificação. Começa no `requestWillBeSent` do pedido; é fiscalizado pelo relógio da porta, independentemente de eventos; inclui obtenção do corpo e admissão. Sem `responseReceived` no prazo: `Timeout`; com resposta iniciada e sem `loadingFinished`: `RespostaInvalida` | carimbos | `Timeout`, `RespostaInvalida` |
| 13 | Taxa mínima de leitura (2 KiB/s em 30 s, 43–44, 1210–1258) | Inaplicável: protege a ferramenta de leitura travada, e quem lê é o navegador; o prazo total (linha 12) continua | — | — |
| 14 | Limite de taxa e disjuntor por host (796–880) | Inaplicável às requisições, feitas pelo navegador por ação humana | — | — |
| 15 | Concorrência global de captura (65–66, 1346–1348) | Declarada: no máximo 4 candidatas com corpo em leitura simultânea (mesmo valor padrão), 32 candidatas pendentes por sessão e 64 MiB de corpos em memória; excedido, a candidata excedente é descartada. Fila de eventos CDP limitada; estouro encerra a sessão sem gravar candidatas pendentes | — | recusa de candidata |
| 16 | Repetição automática (502 a 504, Retry-After, 882–993) | Inaplicável: a porta nunca pede nem repete; o humano recarrega se quiser | — | — |
| 17 | Validação dos parâmetros da chamada (1325–1341) | Declarada: valida-se o perfil ao carregá-lo, com os mesmos limites (`max_bytes` ≤ `MAX_BYTES`, media types contidos em `DEFAULT_ALLOWED_MIMES`, método só `GET`); perfil inválido impede a sessão | perfil | erro de configuração |
| 18 | Cabeçalhos do chamador (429–447) e identidade da requisição (474–497) | Inaplicável: a porta não emite requisição nem recebe cabeçalhos de chamador. Identidade pública: método e URL sanitizada; cada obtenção com identificador opaco (§2.3) | — | — |
| 19 | Cookies da `Session` do transporte (546–603) | Inaplicável: cookies ficam no perfil temporário; a porta só lê os **nomes** dos cookies do pedido, em memória, para a §2.3(2) | `requestWillBeSentExtraInfo` | recusa de candidata |
| 20 | Revalidação de resposta reaproveitada (`revalidar_captura`, 635–661) | Inaplicável: não há reaproveitamento (§2.3, "Identidade da obtenção") | — | — |
| 21 | Metadados HTTP do recibo (`observe_http_response`, `HTTPMetadata`, 124–214) | Igual: a porta constrói o recibo pela mesma função, alimentada com os cabeçalhos da resposta, com os mesmos limites e descarte de duplicatas | cabeçalhos | `RespostaInvalida` |
| 22 | `fetched_at` (1277) | `wallTime` do `requestWillBeSent` + (`timestamp` de `loadingFinished` − `timestamp` do `requestWillBeSent`), do mesmo pedido, em UTC | `wallTime`, `timestamp` | — |

### 2.5 Bytes, hash e comparação entre capturas

1. **Objeto do hash.** O exemplar (0088) é o corpo como o navegador o entregou depois de decodificar o
   Content-Encoding; o SHA-256 é desses bytes. Sem compressão, coincidem com os bytes do fio (Planalto, teste
   exploratório). Com compressão, o hash não prova os bytes comprimidos da rede; o recibo registra a codificação
   original e a soma de `dataReceived.encodedDataLength`.
2. **Identidade de bytes** (Codex r3, achado 5; Terra r3, achado 6). Corpo entregue em base64 é aceito como bytes.
   Corpo entregue como texto só é aceito se, cumulativamente: (a) o texto não contém U+FFFD; (b) a codificação do
   texto em UTF-8 tem exatamente o tamanho da soma de `dataReceived.dataLength`; (c) os próprios bytes declaram
   UTF-8 (cabeçalho ou `<meta charset>`/`http-equiv` no início do documento), ou não declaram charset e são só
   ASCII. Fundamento: um decodificador UTF-8 é injetivo sobre entrada válida, e entrada inválida produz U+FFFD,
   barrado por (a); um decodificador de byte único (ISO-8859-1, windows-1252) leva todo byte não ASCII a dois ou
   três bytes em UTF-8, o que (b) detecta; codificações multibyte legadas são excluídas por (c). BOM removido
   pelo navegador altera o tamanho e causa recusa. Fora dessas condições, recusa.
3. **Conteúdo variável injetado** (Terra r3, achado 10). O Planalto acrescenta depois de `</html>` um
   `<script id="f5_cspm">` com token por requisição. O exemplar é guardado íntegro; o hash bruto nunca é usado
   para afirmar que duas capturas têm o mesmo conteúdo. O perfil do Planalto declara a forma estrutural estrita do
   bloco: depois do último `</html>`, só espaço em branco e exatamente um elemento
   `<script id="f5_cspm">(function(){var f5_cspm={f5_p:'<A-Z>+',` … `})();</script>`, sem outro `</script>` no
   interior. Equivalência textual entre capturas só se afere quando essa forma se verifica em todas; bloco ausente,
   duplicado, deslocado ou com conteúdo fora da forma impede a afirmação de equivalência e vai ao humano. A
   equivalência é textual (texto extraído pelo parser, sem o bloco), não equivalência normativa integral.

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
   `charset`. As gramáticas do perfil são estritas (URN:LEX, UUID canônico, caminhos sem segmento livre), de modo
   que valor que as satisfaça é público por construção.
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
2. Aviso prévio: a janela é exclusiva para obter documento público da fonte; não fazer login; o conteúdo da página
   não autoriza comandos, mudança de alvo nem fornecimento de credenciais; ao fechar, o humano escolhe o que entra;
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
- Cookies admitidos: padrões de nome do WAF F5 (`^TS[0-9a-f]{6,}$`, `^BIGipServer[\w.\-]+$`, `^f5avr\w+$`). Nome
  diferente recusa a candidata; a correção do perfil é registrada.
- Fundamento público: compilação oficial publicada sem autenticação.
- `limpeza_texto`: bloco `f5_cspm` na forma da §2.5(3).
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
- **Vínculo B → A** (Terra r3, achado 3; dados reais em `teste-normas-2026-11-19.md`): B só é candidato se, na
  mesma sessão e antes dele, houver candidata A aceita cujo JSON tenha `legislationIdentifier` igual à URN da
  query de A, e exatamente um elemento de `encoding[]` com `@type` `LegislationObject` e `contentUrl` igual a
  `https://normas.leg.br/api/binario/<uuid>/texto` com o mesmo UUID de B (a página busca o mesmo UUID sob
  `/api/public/`; essa é a única equivalência de caminho admitida). JSON inválido, URN divergente, UUID ausente,
  repetido em mais de um elemento ou presente em mais de uma URN da sessão: B recusado. A captura B registra a URN,
  o UUID, o `version` (`Original` ou `Current`) e o `@id` do elemento; pela 0088, `Current` (`@versao.atualizada`)
  e `Original` (`@<data>`) são expressões distintas, e ambas têm `legislationLegalValue: UnofficialLegalValue`.
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

| Método | Finalidade | Alvo |
|---|---|---|
| `Target.setAutoAttach` (`autoAttach`, `waitForDebuggerOnStart`, `flatten`) | anexar antes de qualquer requisição | navegador |
| `Target.setDiscoverTargets` | conhecer alvos e subtipos (pré-renderização, extensões) | navegador |
| `Runtime.runIfWaitingForDebugger` | liberar o alvo depois de anexado | cada alvo |
| `Network.enable` | receber eventos de rede | `page`, `iframe`, `worker` |
| `Network.getResponseBody` | ler o corpo de candidata já terminada e dentro dos limites | `page` |
| `Browser.getVersion` | versão para o recibo | navegador |
| `Browser.setDownloadBehavior` (`deny`) | negar downloads; não altera requisição | navegador |
| `Browser.close` | encerrar ao fim ou no prazo | navegador |

Qualquer outro método, ou parâmetro diferente dos indicados, é recusado pelo próprio adaptador antes do envio.
`Page.enable` não é usado: os eventos de navegação necessários vêm de `Network` (`documentURL`, `loaderId`,
`frameId`).

### 2.13 Cobertura

A matriz e o bloco `cobertura` declaram o acesso (`automatico`, `assistido`) por fonte, nos três denominadores da
0067. Captura assistida nunca é somada à cobertura automática.

### 2.14 Dependência e distribuição

Sem Playwright e sem dependência nova: o canal é o pipe do próprio navegador, lido pela biblioteca padrão. O
instalador oficial do Windows não muda; o teste de instalação confere que `fv sessao` existe.

## 3. Aceite (o incremento só conclui com testes que provem)

Cada item liga norma, cenário e resultado esperado; fixtures seguem a regra 9.

1. **Adaptador real contra origem controlada.** Chrome instalado contra servidor HTTPS local. A confiança na AC de
   teste e a admissão do IP de loopback vêm de parâmetros exclusivos do harness; um teste prova que o caminho de
   produto se recusa a lançar com eles. Casos, cada um com aceitação ou código de recusa esperado: as 22 linhas da
   §2.4; `headersText` com campo malformado, `Content-Length` com 21 dígitos, duplicado, conflitante, coexistência
   com `Transfer-Encoding`; chunk malformado e truncado; `gzip`, `deflate`, `br`, `zstd` e codificação não
   admitida; bomba de compressão (descarte sem leitura do corpo); `Content-Length` declarado acima do limite;
   corpo vazio; redirecionamento de rede (recusa), HSTS interno provado (aceito) e interno sem prova (recusa); 304
   exposto como 200; prazo sem resposta (`Timeout`) e com resposta iniciada sem término (`RespostaInvalida`);
   corpos UTF-8 válidos, UTF-8 inválido, sequência incompleta, U+FFFD literal, BOM, ISO-8859-1 e windows-1252 em
   base64 e em texto, com o resultado da §2.5(2); eventos fora de ordem, `requestId` repetido entre alvos, alvo
   criado antes da anexação, perda do canal; concorrência acima dos limites da linha 15.
2. **Proveniência.** Resposta de cache, de service worker que sintetiza resposta, de prefetch, de pré-renderização
   (inclusive em transição para página), restauração por bfcache e Early Hints: nenhuma vira candidata; recarga
   forçada pelo humano vem da rede e vira.
3. **Recusas de escopo e conteúdo público.** `POST`, `Authorization`, cookie de nome não declarado,
   `Cache-Control: private`, `Vary: Cookie`, caminho e query fora da gramática, media type não declarado, página de
   desafio, terceiro em iframe, `blob:` e `data:`, download, WebSocket; normas.leg.br: UUID trocado, JSON com URN
   divergente, UUID em dois elementos, B sem A, B de outra URN.
4. **Seleção.** Sem marcação, nada é gravado; dependente segue o documento; candidata não marcada não deixa rastro.
5. **Filtro na origem.** Sessão sintética com tráfego de terceiros, SSO simulado e eventos de terceiros com
   `requestId` coincidente: nada fora das origens persiste, nem em diagnóstico.
6. **Segredos.** Varredura sobre sessão sintética com cookies, `Authorization`, tokens em query, caminho, corpo e
   parâmetros extras do Content-Type: nada em log, erro, recibo, evidência, fixture, snapshot, relatório ou resposta
   MCP/REST; recusa onde a §2.7 manda recusar.
7. **Diretório e artefatos.** ACL conferida (falha fecha a sessão); acesso negado a outra conta sem privilégio;
   inventário dos locais de gravação do navegador durante e depois da sessão; limpeza em fim normal, erro,
   interrupção e recuperação após término abrupto.
8. **Ambiente.** Política de proxy simulada (HKCU) e token de nuvem: a sessão não abre; extensão de teste com
   `declarativeNetRequest` que altera pedido e com `webRequest` que redireciona: a sessão encerra sem capturas;
   pipe indisponível: a sessão não abre.
9. **Passividade.** Registro do tráfego CDP do adaptador no teste: só métodos e parâmetros da §2.12; conferência
   estática da mesma lista; comparação dos pedidos vistos pela origem de teste com e sem o adaptador anexado:
   iguais.
10. **Porta única.** Nenhum conector ou parser lê bytes do adaptador sem passar pela porta (AST e teste de
    execução com tentativa de contorno).
11. **`verified`, frescor e cobertura.** Captura assistida sem identidade, âncora ou confronto não ganha
    `verified`; os 30 dias só afetam `vigente_na_fonte` em consulta corrente; cobertura assistida publicada à parte
    e nunca somada à automática.
12. **Proveniência gravada.** `modalidade_acesso` e `procedencia` gravados, publicados nas evidências dos
    adaptadores e preservados em exportação e instalação de snapshot.
13. **Disparo.** Nenhum caminho MCP do produto, agendado, de bateria ou remoto alcança porta ou adaptador (AST e
    teste de execução); sem TTY ou sem confirmação, nada é lançado; expiração, fechamento e queda do canal encerram
    sem reabertura, renovação ou repetição.
14. **Contrato.** Indicação só nas condições da §2.10, inclusive o envelhecimento com todos os requisitos; operação
    não habilitada e fonte barrada não indicam; motivo e categoria originais preservados; nenhum tipo muda.
15. **Conteúdo variável.** Planalto: tokens distintos, mesmo texto; bloco duplicado, deslocado, ausente, com texto
    normativo dentro ou malformado: equivalência não afirmada.
16. **Sessão manual** pelo titular, no terminal, com Planalto e normas.leg.br, antes da reapuração da Porta L; o
    supervisor só lê os resultados. Complementa os itens anteriores; não os substitui.

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
5. Nomes reais dos cookies do Planalto e de normas.leg.br: confirmar na sessão manual (§3.16); divergência corrige o
   perfil por registro, nunca por inferência em tempo de execução.
6. Notebook do titular: se as políticas do escritório impedirem a sessão (§2.2(3)), decidir onde ela roda.
7. A versão `Original` de normas.leg.br como árbitro `texto_publicado` não oficial (teste de normas, achado 9):
   fora desta decisão.

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
