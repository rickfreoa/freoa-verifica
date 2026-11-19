A v3 ainda contém **bloqueadores de especificação**. A escolha da opção A resolve a bifurcação arquitetural, mas não torna exaustiva a matriz nem demonstra todas as garantias atribuídas ao CDP.

Conferi o ramo `docs/0089-sessao-assistida`, HEAD `d1079f0d8047ee2369ea1db69cba61800d56ecac`. A árvore permaneceu limpa. Não alterei arquivos, não executei testes e não abri sessão assistida. Os arquivos de código indicados permanecem iguais aos de `35dd8bc`. Os cenários abaixo atacam a especificação; não constituem demonstração de vulnerabilidade em implementação existente.

Nas classificações abaixo, **decisão** significa definição normativa que o implementador não pode tomar; **redação** significa completar ou corrigir a especificação dentro das escolhas já autorizadas.

**1. ALTA — A exceção à regra 4 ainda não está conciliada expressamente com seu enunciado invariável. Natureza: decisão normativa de escopo.**

Trechos: [0089:41](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:41), §§2.1–2.2; `AGENTS.md:21`; `0001:11`.

A opção A prevê requisições feitas pela conexão do navegador e entrega posterior de respostas à porta. Isso estabelece uma **porta única de admissão da captura**, mas não faz cada requisição passar pelo transporte. A própria §2.2(5) admite tráfego de terceiros observado e descartado.

A 0067 já vinculava a sessão assistida à porta única; a v3 precisa resolver expressamente a relação entre essa disciplina e o texto absoluto “Toda requisição passa por `freoa_verifica.transport`”. A afirmação das linhas 10–11 e da §4 de que nenhuma regra invariável muda deixa duas leituras incompatíveis disponíveis ao implementador.

A classe envolve todo o tráfego do navegador dedicado: documentos, subrecursos, desafios, terceiros e requisições iniciadas por conteúdo.

**Redação mínima:** “Exclusivamente na sessão assistida, a regra 4 exige que toda admissão de resposta como captura passe por `transport.capturar_assistida`; as requisições do navegador dedicado não são emitidas nem encaminhadas pelo transporte. A exceção não alcança requisições da ferramenta nem o fluxo automático.”

Essa formulação precisa ser incorporada à disciplina normativa correspondente, inclusive à leitura da 0001. **Não é necessário repetir a escolha de A; é necessário explicitar o alcance normativo dessa escolha.**

**2. ALTA — Os comandos de cache e service worker contradizem a proibição absoluta de alterar requisições. Natureza: decisão.**

Trechos: §2.1, linhas 47–48; §2.2(4), linhas 71–75; §4, linhas 282–284.

A lista admite `Network.setCacheDisabled(true)` e `Network.setBypassServiceWorker(true)`, mas simultaneamente afirma que a ferramenta apenas observa e não altera requisições.

No Chromium consultado, esses controles modificam o modo de cache e o indicador de desvio de service worker do objeto de requisição. O agente também força preflight em determinada condição quando o cache está desativado. Portanto, a ausência de `setExtraHTTPHeaders` não demonstra ausência de intervenção na requisição. [Implementação oficial do agente Network](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/core/inspector/inspector_network_agent.cc).

Há duas soluções normativas possíveis:

- Manter a proibição absoluta: retirar esses comandos e recusar respostas cuja origem de rede não seja demonstrada.
- Autorizar expressamente esses dois controles como exceções limitadas, abandonando a afirmação absoluta de passividade.

**Redação mínima compatível com a proibição solicitada:** “O adaptador não configura cache nem desvio de service worker; observa os eventos e recusa respostas provenientes desses mecanismos ou com procedência indeterminada.”

A opção A, isoladamente, não decide essa exceção adicional.

**3. ALTA — A matriz não é exaustiva e a linha 4 não determina integralmente sua própria substituição. Natureza: redação; as dispensas adicionais exigem decisão.**

Trechos: [0089:110](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:110), linhas 120–135; [transport.py:247](/C:/dev/fv14-0089/freoa_verifica/transport.py:247).

Estas são as validações omitidas, ou nomeadas apenas na descrição do fluxo automático sem regra operacional assistida suficiente:

| Validação efetivamente existente | Código | Lacuna da v3 |
|---|---|---|
| Gramática e término dos chunks: tamanho hexadecimal limitado, extensões, CRLF após dados e término completo | `transport.py:243–244`, `286–305` | A linha 4 fala de cabeçalhos e framing de HTTP/2/3; não estabelece a substituição dessas verificações em HTTP/1. |
| Gramática, término, comprimento e quantidade dos trailers | `307–320` | Não aparecem na matriz. |
| `Content-Length` com no máximo 20 dígitos | `374–375` | “Único e numérico” não conserva esse limite. |
| Um único `Transfer-Encoding` e proibição de coexistência com `Content-Length` | `372–377` | A regra assistida não manda expressamente recusar a coexistência; aceitar separadamente CL válido e TE `chunked` não basta. |
| Recusa imediata de tamanho declarado superior ao limite | `1199–1203` | Consta da coluna automática, mas a regra assistida só descreve contagem de eventos. |
| Concorrência global de captura | `65–66`, `1346–1348`, `1430` | Não há equivalente nem dispensa expressa. `max_capturas` limita quantidade, não simultaneidade. |
| Concorrência e prazo próprios da resolução DNS | `64`, `691–712` | A resolução pelo navegador é declarada, mas a matriz não explicita o destino desses controles de recursos. |
| Validação dos parâmetros de captura: limites de bytes, redirecionamentos, métodos, lista de MIME, taxa e repetição | `1325–1341` | O perfil introduz novos parâmetros sem declarar suas restrições ou quais controles se tornam inaplicáveis. |
| Validação dos cabeçalhos fornecidos pelo chamador: tipos, nomes vazios, reservados e duplicados | `429–447`, `1342` | A linha 16 trata da identidade; não declara que essa interface deixa de existir na porta assistida. |
| Classificação da falha segundo o progresso de toda a cadeia, inclusive resposta parcial em salto anterior | `906–938`, `941–983`, `995–1023` | Ausente; a linha 12 prescreve `Timeout` indistintamente. |
| Revalidação de resposta reaproveitada contra a política da chamada atual | `635–661` | Não há regra assistida de revalidação nem proibição inequívoca de reaproveitamento. |

A linha 18, marcada “Igual”, pode remeter legitimamente ao código existente, mas isso deve significar **reutilização efetiva de `observe_http_response`/`HTTPMetadata`**, incluindo limites, descarte de duplicatas e validação dos valores (`124–214`), não apenas seleção de nomes de `HEADER_NAMES`.

**Redação mínima:** acrescentar linhas explícitas para os controles acima, com uma destas respostas: aplicação do código existente; substituição determinada; inaplicabilidade justificada e expressa. Para framing: “Recusar CL com mais de 20 dígitos, TE múltiplo e qualquer coexistência CL/TE; declarar separadamente a política de chunks e trailers.”

Delegar framing não observável ao navegador pode ser uma decisão válida, mas precisa abranger **a classe completa de verificações**, sem continuar prometendo equivalência onde ela foi dispensada.

**4. ALTA — A linha 6 promete contenção antes e durante a expansão sem mecanismo suficiente. Natureza: decisão sobre a garantia; redação dos limites.**

Trechos: §2.4, linha 122; §3.1, linhas 248–250.

Há quatro problemas distintos:

1. `dataReceived` comunica progresso já ocorrido. Receber seus comprimentos não demonstra que a ferramenta consegue impedir consumo anterior de memória ou expansão no navegador.
2. A interrupção da carga não tem mecanismo definido na lista permitida. Descartar a candidata, interromper uma página e encerrar o navegador são ações diferentes.
3. Não está determinado se devem ser confrontados **dois acumuladores independentes** ou a soma entre bytes codificados e decodificados. Somá-los entre si contaria duas representações do mesmo conteúdo.
4. `max_bytes` por resposta e `max_capturas` não limitam eventos pendentes, corpos simultâneos, memória total ou tráfego de respostas recusadas.

A classe inclui bombas de compressão, muitas respostas pequenas simultâneas, respostas que nunca terminam e eventos produzidos mais rapidamente do que o adaptador os processa.

**Redação mínima:** “Manter contadores independentes de corpo codificado e decodificado, validar o tamanho declarado antes de obter o corpo e definir limites globais de memória, candidatas e filas. Especificar a ação de interrupção e seu alcance.”

Se a opção A só permite limitar o que a ferramenta **aceita e copia**, isso deve ser declarado como tal. Substituir a promessa de contenção da expansão por uma garantia de admissão é decisão de escopo, não escolha de implementação. O teste “interrupção antes de ler o corpo” não prova contenção anterior no navegador.

**5. ALTA — A exceção para corpo textual não prova identidade de bytes e pode eliminar recusas de charset. Natureza: redação, com redução explícita de compatibilidade se necessário.**

Trechos: [0089:146](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:146), §2.5(2); linha 127 da matriz.

UTF-8 efetivo e igualdade de tamanho são condições insuficientes para demonstrar que a reencodificação reproduz os bytes originais.

Como contraexemplo lógico, um decodificador com substituição pode converter uma sequência UTF-8 incompleta de três bytes, como `F0 9F 92`, em U+FFFD, cuja codificação UTF-8 também tem três bytes: `EF BF BD`. O tamanho permanece; os bytes mudam. Não executei esse cenário no navegador instalado.

Isso afeta também a alegação “mesmo parser”: o parser local recebe bytes já reparados e deixa de enxergar a sequência inválida que deveria recusar. O código atual usa decodificação estrita e levanta `RespostaInvalida` nesses casos (`texto_resposta.py:448–461`). O armazenamento apenas confere o hash contra o corpo entregue, não contra os bytes anteriores à transformação (`repo.py:82–85`).

O Chromium mantém caminhos distintos de conteúdo textual e binário no armazenamento do inspetor; a API não deve ser tratada como promessa universal de bytes originais. [Armazenamento oficial de recursos do inspetor](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/core/inspector/network_resources_data.cc).

**Redação mínima:** “Corpo retornado como texto não é aceito apenas por igualdade de tamanho. Exige-se obtenção dos bytes anteriores à interpretação de charset por mecanismo comprovadamente sem perda; sem esse mecanismo, recusa.”

O aceite deve incluir UTF-8 inválido, sequências incompletas, substituições e BOM, além dos três charsets válidos. Se ISO-8859-1/windows-1252 só puderem ser obtidos como texto transformado, o resultado esperado é recusa; não se pode exigir simultaneamente aceitação e identidade de bytes.

**6. ALTA — Redirecionamentos e desafio em todo status continuam sem dados suficientes. Natureza: redação; eventual dispensa exige decisão.**

Trechos: §2.4, linhas 124–125; §2.3, linha 105; §3.1.

`redirectResponse` fornece metadados da resposta anterior; não fornece seu corpo. A v3 exige exame dos primeiros 64 KiB de cada salto, mas não estabelece como obter essa amostra antes de perder o acesso à resposta intermediária. A classe inclui desafio presente apenas no corpo de 301/302/303/307/308 e corpos intermediários comprimidos.

Além disso:

- A §2.3 diz que as demais respostas nunca são persistidas, mas não distingue descarte definitivo de inspeção transitória obrigatória de erros e saltos.
- A exceção HSTS não define como comprovar que o redirecionamento interno é realmente HSTS.
- HSTS normalmente envolve mudança de esquema; exigir `https` em cada URL e simultaneamente admitir esse salto interno deixa indeterminado o tratamento da URL inicial.
- O “Igual” não distingue recusar uma **captura final** de impedir que o navegador siga o salto. A arquitetura passiva só promete a primeira coisa.

**Redação mínima:** “Cada cadeia tem estado próprio. Todo salto exige os metadados e a amostra necessários; indisponibilidade da amostra impede aceitar a captura final. A inspeção transitória de respostas recusadas não as torna capturas. A política HSTS define prova, contagem e exceção de esquema; sem prova, recusa.”

O aceite precisa distinguir três saltos admissíveis de cadeias recusadas por falta de prova. Uma cadeia válida no navegador não é necessariamente admissível pelo protocolo especificado.

**7. ALTA — A correlação por `requestId` isolado é insuficiente, inclusive para o filtro de terceiros. Natureza: redação.**

Trechos: §2.2(5), linhas 76–79; §2.3, “Vínculo”; §2.4, linhas 120, 124 e 135.

A especificação observa múltiplos alvos, mas associa cabeçalhos sem URL apenas por `requestId`. Falta definir namespace da sessão CDP, alvo, navegação e posição do salto.

A classe de falhas inclui:

- Identificadores iguais em sessões de depuração distintas.
- Reutilização do identificador na cadeia de redirecionamento.
- Cabeçalhos extras chegando antes ou depois dos demais eventos.
- Salto de origem permitida para terceiro, ou retorno de terceiro para origem permitida.
- Navegação, troca de processo, perda de conexão ou evento inicial não observado.

Assim, associar o identificador a uma URL permitida em algum momento não basta para autorizar a retenção de todos os eventos posteriores.

**Redação mínima:** “Correlacionar por sessão CDP/alvo, `requestId` e ordinal do salto, com vínculo à navegação/quadro. Associar cada evento extra ao salto correspondente; nunca herdar autorização de retenção de outro salto. Histórico incompleto ou associação ambígua causa descarte.”

Isso precisa preceder qualquer gravação, inclusive de cabeçalhos brutos e diagnóstico.

**8. ALTA — A matriz confunde cabeçalhos expostos, status efetivo e dados de completude. Natureza: redação.**

Trechos: §2.3(1); §2.4, linhas 120, 123 e 126.

Os campos CDP citados **existem**, mas não têm todos a suficiência presumida:

| Campo | Resultado da conferência |
|---|---|
| `fromDiskCache`, `fromServiceWorker`, `fromPrefetchCache` | Existem, opcionais; ausência não prova `false`. |
| `requestServedFromCache` | Existe como evento; exige observação completa. |
| `remoteIPAddress`, `remotePort` | Existem, opcionais; descrevem o par remoto. |
| `securityDetails`, `securityState` | Existem na resposta; não autenticam o corpo isoladamente. |
| `responseReceivedExtraInfo.headers` | Existe; duplicatas são concatenadas por `\n`. |
| `dataReceived.dataLength/encodedDataLength` | Existem; são comprimentos dos dados reportados. |
| `loadingFinished.encodedDataLength` | Existe; não é tamanho exclusivo do corpo comprimido. |
| `redirectResponse` | Existe; não contém corpo. |
| `wallTime` | Existe em `requestWillBeSent`; exige conversão com relógio monotônico. |

O protocolo também oferece `headersText` opcional para HTTP/1 e `statusCode` em `responseReceivedExtraInfo`; este pode revelar 304 quando `responseReceived` mostra 200. Logo, a afirmação de que a sintaxe dos cabeçalhos nunca é observável é excessiva, e a recusa de 304 precisa usar o status de rede correspondente. [Definição oficial de Network](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Network.pdl).

**Redação mínima:** “Exigir os eventos extras necessários; validar multiplicidade sem escolher um valor; recusar divergência ou ambiguidade entre os metadados. Conferir o status de rede de cada salto, inclusive 304. Quando houver texto bruto de HTTP/1, declarar sua utilização; quando não houver, aplicar a substituição expressamente aprovada.”

A linha 7 já admite completude delegada ao navegador quando falta tamanho codificado adequado. Essa diferença está declarada; não deve ser descrita como confronto independente de CL. O teste exploratório, que registra tamanho de fio com cabeçalhos, não sustenta usar esse total como tamanho do corpo.

**9. ALTA — O prazo não tem valor, fiscalização nem classificação completos. Natureza: redação.**

Trechos: §2.4, linhas 128 e 135; §2.11, linhas 217–219.

“Medido entre eventos” não define:

- O prazo máximo da captura.
- Se começa no primeiro pedido da cadeia.
- Como encerrar candidata sem `loadingFinished`.
- Se inclui obtenção do corpo pelo CDP e admissão pela porta.
- Como tratar desconexão do observador e perda de eventos.
- Qual par de timestamps usar após redirecionamentos.

O fluxo atual usa prazo compartilhado pela chamada inteira (`transport.py:1035–1077`, `1344–1345`, `1439–1455`). Depois de resposta iniciada, o esgotamento vira `RespostaInvalida`, não `Timeout` (`941–969`, `1231–1235`, `1255–1259`). A linha 12, marcada “Igual”, produz outra classificação; isso muda `resposta_inesperada` para `fonte_fora` em `challenge.py:164–177`.

**Redação mínima:** “Fixar o prazo e seu início no primeiro pedido da cadeia, fiscalizá-lo independentemente de eventos finais e incluir a obtenção/admissão do corpo. Preservar a classificação por progresso da chamada. Calcular `fetched_at = wallTime_inicial + timestamp_final − timestamp_inicial`, usando um par correspondente e validado.”

Não identifiquei defeito na escolha do instante final em si; o defeito está na determinação incompleta e na classificação anunciada como equivalente.

**10. ALTA — Política de proxy não cobre o caminho efetivo, e a política corporativa continua uma questão normativa aberta. Natureza: decisão.**

Trechos: §2.2(3), linhas 65–70; §2.4, linhas 118–119; §5.5, linhas 295–297.

A sessão recusa **política que fixe proxy**, mas a garantia anunciada exige conexão que não seja intermediada por proxy. A regra não contempla configurações efetivas de sistema, descoberta automática ou outros mecanismos fora daquela política.

Um IP público e porta 443, por si, não demonstram que o par é a fonte. A própria §2.2(3) reconhece essa distinção.

Também não está decidido se extensões e páginas corporativas forçadas são admissíveis em produção: §2.2 permite, enquanto §5.5 manda conferir depois se isso “basta”. Registrar identificador de extensão não prova compatibilidade com isolamento, natureza pública e passividade.

**Redação mínima:** “A condição de ausência de proxy refere-se à configuração e ao caminho efetivos, não apenas a uma política específica; impossibilidade de demonstrá-la recusa a captura. Definir antes da implementação quais políticas/extensões são admitidas e quais garantias devem provar.”

A leitura de `chrome://policy` também precisa de procedimento compatível com a proibição de navegação e injeção de script do adaptador. Chrome e Edge precisam ter procedimentos suportados e determinados.

**11. ALTA — Corpo público e ausência de segredos continuam sem critério de admissão suficiente. Natureza: redação da exigência já adotada; eventual aceitação de conteúdo personalizado exigiria decisão.**

Trechos: §2.3(2–3); §2.7(3–4); §3.5.

O problema apontado em Codex r2/6 e Terra r2/8 permanece: URL pública e ausência de `Authorization` não excluem autenticação por cookie, personalização, SSO ou segredo embutido no corpo.

A classe inclui:

- Documento público com identificação pessoal ou token de sessão.
- Corpo retornado de maneira diferente conforme cookie.
- Segredo em parâmetro adicional do `Content-Type` cru.
- Tokens que satisfaçam uma expressão regular permissiva de caminho ou query.
- Conteúdo sigiloso que passe pelos filtros de host, MIME e método.

A v3 diz que bytes nunca são alterados para torná-los admissíveis, mas não determina como recusar essas respostas. `repo.py:87–110` grava o corpo integral e o Content-Type cru; filtrar `HEADER_NAMES` não protege esses dois canais.

**Redação mínima:** “O perfil declara como demonstra que o recurso é público e não personalizado. Autenticação, personalização, segredo no corpo ou em metadados persistidos, ou dúvida sobre sua admissibilidade, impedem gravação, sem alteração dos bytes. O aceite inclui esses negativos.”

Não se exige um detector universal de dados pessoais. Exige-se restringir a admissão aos recursos cuja natureza pública possa ser demonstrada e definir falha fechada no restante.

**12. ALTA — Identidade assistida e autorização de capturas subsequentes continuam incompletas. Natureza: redação quanto à identidade; decisão quanto ao alcance da autorização humana.**

Trechos: §2.2(1); §2.3, linhas 100–103; §2.4, linha 132; §2.6(1).

Atribuir cada resposta à própria URL corrige a associação indevida ao alvo anterior. Isso **não** resolve dois outros problemas:

- Método e URL sanitizada ainda podem colapsar representações distintas. `sessao_id` não substitui identidade de cada obtenção nem define a proibição de cache/reuso por essa chave.
- A confirmação é para “aquela sessão e aquele alvo”, mas script, meta refresh ou pop-up podem gerar capturas de outros documentos admitidos. Dizer que são novas navegações não estabelece sua autorização.

Prefetch, prerender e navegação iniciada por conteúdo são classes distintas; excluir os dois primeiros não resolve a terceira. O CDP possui informação de subtipo para identificar alvos de prerender, mas a especificação precisa conservar esse estado durante a obtenção, inclusive em transições. [Definição oficial de Target](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Target.pdl).

**Redação mínima sobre identidade:** “Cada obtenção recebe identificador opaco único; não há reutilização por método/URL sanitizada. Sanitização não reúne destinos distintos; identidade pública insuficiente causa recusa.”

**Decisão necessária sobre autorização:** escolher entre confirmação de cada documento efetivamente selecionado ou autorização explícita, na abertura, de um escopo de capturas públicas da fonte. A captura de XHR dependente de uma seleção humana precisa de vínculo determinado, sem exigir artificialmente gesto humano em cada requisição auxiliar.

**13. MÉDIA — Perfis iniciais e indicação por envelhecimento ainda deixam escolhas de regra ao implementador. Natureza: redação.**

Trechos: §2.10(1–2), linhas 202–207; §2.11, linhas 217–230.

A estrutura de `PerfilSessaoAssistida` está definida, mas os perfis iniciais não estão completos: faltam valores de limites, operações, media types por recurso, gramáticas completas de caminhos/valores e a tabela concreta de barreiras com validade e escopo.

Também persiste a ambiguidade de r2: “Também indica sessão” não manda herdar **todos** os requisitos do item 1. A leitura permissiva pode indicar sessão para operação não habilitada ou fonte barrada quando existe captura antiga.

**Redação mínima:** “O item 2 exige cumulativamente todos os requisitos do item 1. Os perfis iniciais completos e a tabela versionada de barreiras integram esta especificação, com vínculo a fonte, operação, alvo e critério de validade.”

A reclassificação do Planalto (`planalto.py:38–45`) é evidência específica; não transforma toda falha de conexão em barreira resolúvel. A exclusão de 401 foi corretamente incorporada.

**14. MÉDIA — A lista CDP anunciada como fechada não está realmente enumerada. Natureza: redação.**

Trechos: §2.2(4); §3.8.

“Domínios Network, Page e Target” mais três comandos de configuração não é lista fechada dos métodos usados pelo adaptador. Faltam métodos de descoberta/anexação, obtenção do corpo, identificação do navegador, leitura das políticas e encerramento/interrupção.

Sem essa lista, o teste que verifica “só métodos da lista fechada” deixa ao implementador a definição do próprio critério.

**Redação mínima:** “Enumerar cada método permitido, seus parâmetros, tipos de alvo e finalidade. Método ou parâmetro fora da lista é recusado. Distinguir observação, leitura de corpo, configuração e encerramento.”

A lista precisa ser compatível com as correções dos achados 2, 4 e 10. Ativar genericamente um domínio não autoriza todos os seus comandos.

**15. ALTA — O filtro do observador não sustenta a promessa de nenhuma persistência de terceiros pelo navegador. Natureza: redação do alcance; decisão se a promessa absoluta for mantida.**

Trechos: §2.2(5); §2.7(1–3); §3.4–7.

O filtro pode impedir a gravação pelo **adaptador**, mas atua depois de o navegador receber os eventos e não controla, por si, histórico, cache, armazenamento de sites ou artefatos de extensões. O teste exploratório demonstrou tráfego corporativo no perfil dedicado.

A v3 admite cookies no perfil temporário e seu descarte posterior. Isso é compatível com a 0067, que exige descarte ao fim, mas precisa ser distinguido da frase “Nada de terceiros [...] é persistido”.

A classe abrange todos os artefatos temporários, enquanto a sessão está ativa e após falha abrupta. Conferir a ACL de um diretório não prova automaticamente que todos os produtores gravam apenas nele.

**Redação mínima:** “O filtro impede persistência de terceiros nos registros da ferramenta e nos entregáveis. Artefatos temporários do navegador ficam exclusivamente no diretório protegido e são descartados conforme §2.7; o aceite verifica os locais efetivos de gravação e o acesso por outra conta sem privilégio.”

Se a intenção for impedir **qualquer** persistência de terceiros, inclusive temporária pelo navegador, o mecanismo correspondente continua ausente. A tolerância a extensões corporativas torna essa promessa especialmente relevante.

**16. ALTA — O aceite não prova integralmente a v3 nem a 0067 emendada. Natureza: redação; depende das decisões anteriores.**

Trechos: [0089:244](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:244), §3.

O navegador real contra origem controlada é um avanço importante. Contudo, “cada linha da §2.4” não cobre normas fora da matriz nem corrige linhas indeterminadas.

| Item do aceite | Cobertura ou resíduo |
|---|---|
| 1 — Adaptador real | Acrescentar framing completo, UTF-8 inválido, eventos ausentes, corpo indisponível, prazo sem término e contenção global. Definir resultados esperados de aceitação e recusa. |
| 2 — Proveniência | Acrescentar prefetch, revalidação 304 exposta como 200, observação iniciada tarde e transição de prerender. |
| 3 — Escopo | Acrescentar cadeia que atravessa terceiro, personalização por cookie e vínculo de XHR com a seleção correspondente. |
| 4 — Filtro | Testar eventos extras fora de ordem, múltiplas sessões CDP e mudança de origem dentro da cadeia. |
| 5 — Segredos | Acrescentar corpo, Content-Type cru e valores secretos que satisfaçam padrões permissivos. |
| 6 — Diretório | Provar acesso negado a outra conta e inventariar artefatos efetivos durante e após a sessão. |
| 7 — Políticas | Testar configuração efetiva de proxy além da política e os critérios aprovados para extensões. |
| 8 — Passividade | Lista precisa existir; verificar efeitos nas requisições, não apenas nomes dos métodos. |
| 9 — Proveniência gravada | A preservação em snapshot está prevista; falta exigir também publicação correta nas evidências dos adaptadores. |
| 10 — Disparo | Acrescentar expiração, fechamento, desconexão e ausência de reabertura/renovação/replay automático. |
| 11 — Contrato | Testar envelhecimento com todos os gates, motivo/categoria originais, operações não habilitadas e fontes barradas. |
| 12 — Conteúdo variável | Adequado para o bloco identificado; não prova as demais garantias de aquisição. |
| 13 — Sessão manual | Complementa; não substitui negativos controlados. Definir o recorte para a proibição de chamadas “pelo MCP”, pois o próprio aceite menciona supervisão via WMI. |

Faltam ainda provas expressas de três exigências transversais:

- **Porta única:** nenhum conector/parser admite bytes do navegador por outro caminho; teste de contorno da porta, exigido pela 0067.
- **Sem redução de `verified` e frescor:** documento capturado sem identidade, âncora ou confronto não ganha `verified`; os 30 dias só afetam a afirmação corrente pertinente, preservadas as abstenções históricas da 0075.
- **Cobertura separada:** captura assistida nunca incrementa cobertura automática e é publicada separadamente nos três denominadores da 0067.

**Redação mínima:** incorporar esses casos com ligação explícita entre norma, cenário e resultado esperado. A auditoria D5 e a sessão manual não suprem requisitos ausentes do aceite.

A afirmação “nenhum caminho MCP [...] alcança porta ou adaptador” também precisa distinguir o produto MCP de uma ferramenta administrativa que apenas opera a CLI por ação humana autorizada. Não se deve deixar essa exceção implícita no item 13.

**Quanto aos seis critérios obrigatórios, o resultado é:**

| Critério | Conclusão |
|---|---|
| 1 — Matriz exaustiva e determinada | **Não atende.** Achados 3–9 e 12–14. |
| 2 — Emenda coerente e restrita | **Parcial.** A restrição ao assistido está escrita; regra 4 e passividade exigem conciliação expressa. Não há autorização para usar identidade do navegador em requisição própria. |
| 3 — Existência e suficiência do CDP | **Não atende integralmente.** Os campos nomeados existem; suas limitações, correlação e suficiência não sustentam todas as promessas. |
| 4 — Contrato, `verified`, frescor e procedência | **Atende quanto ao desenho normativo principal**, com lacunas de aquisição, publicação e aceite. |
| 5 — Aceite integral | **Não atende.** Achado 16. |
| 6 — Resolução das rodadas anteriores | **Não atende.** A §7 dá como respondidas classes ainda parcialmente abertas. |

O contrato aditivo está corretamente encaminhado: `fontes_indisponiveis` continua mapa para string, conforme `service.py:471–483`, e os novos detalhes entram em campos irmãos ou objetos existentes. A §2.6 também corrige o envelhecimento genérico, preserva a distinção entre procedência e modalidade e não reduz expressamente `verified`.

Não identifiquei conflito conceitual específico com a 0088: captura continua exemplar; texto extraído e equivalência textual permanecem separados. A limitação da 0083 deixou de ser usada para dispensar aquisição, embora seja mais preciso manter expressamente seu contexto de **conferência de recibo gravado da Câmara**, sem convertê-la em modelo geral da sessão.

**A correspondência da §7 precisa ser corrigida assim:**

| Parecer/achados | Situação na v3 |
|---|---|
| Codex r1/1 — Content-Encoding | **Resolvido quanto à contradição expressa**, pela emenda restrita; limites e exame de erros continuam pendentes. |
| Codex r1/2 — Matriz | **Não resolvido integralmente.** Há matriz, mas persistem omissões e substituições indeterminadas. |
| Codex r1/3 e /4 — Abertura inicial e tipo do mapa | **Resolvidos no texto.** |
| Codex r1/5 — Indicação | **Parcial.** Faltam perfis/tabela completos e herança expressa dos requisitos no envelhecimento. |
| Codex r1/6 — Origem e 0083 | **Formulação corrigida; demonstração de origem ainda parcial.** |
| Codex r1/7 — Frescor | **Resolvido no texto.** |
| Codex r1/8 — Aceite | **Parcial.** |
| Terra r1/1 — Cache/service worker/304 | **Parcial.** Há requisitos; permanecem conciliação da passividade e status/correlação efetivos. |
| Terra r1/2 — Vínculo | **Parcial.** Atribuição à própria URL foi corrigida; autorização e correlação completas ainda não. |
| Terra r1/3 — Downloads | **Resolvido como regra de escopo**, sujeito à prova do adaptador. |
| Terra r1/4 e /5 — Conteúdo privado e segredos em URL | **Parciais.** |
| Terra r1/6 — Expansão e hash | **Hash definido; contenção e identidade de bytes ainda abertas.** |
| Terra r1/7 — ACL e descarte | **Parcial.** Ciclo de vida melhorou; falta prova abrangente dos artefatos e acesso. |
| Terra r1/8 e /9 — Página hostil e confirmação inicial | **Resolvidos quanto ao aviso e à confirmação inicial**, sem resolver capturas subsequentes. |
| Terra r1/10 — Cabeçalhos e terceiros | **Parcial.** |
| Codex r2/1 — SPKI/AC | **Superado pela retirada do mecanismo.** |
| Codex r2/2 — `fetch` como retransmissor | **Superado arquiteturalmente.** A inspeção de erros/saltos permanece questão própria da opção A. |
| Codex r2/3 — Cadeia e vínculo | **Parcial.** |
| Codex r2/4 — Repetição, concorrência e guardas | **Parcial.** Replay pela porta foi vedado; concorrência, fiscalização e aceite não estão completos. |
| Codex r2/5 — Identidade | **Não resolvido integralmente.** |
| Codex r2/6 — Conteúdo público/segredos | **Não resolvido integralmente.** |
| Codex r2/7 — CONNECT irrestrito | **Mecanismo retirado.** A fronteira do tráfego direto precisa ser declarada sob a regra 4. |
| Codex r2/8 — Aceite | **Parcial.** |
| Codex r2/9 — Ambiguidades | **Parcial.** Bytes do navegador resolvem a bifurcação; indicação e perfis continuam incompletos. |
| Terra r2/1–4 — Túnel, credencial, AC e autoridades | **Superados quanto ao proxy retirado.** Não equivalem a aprovação automática da nova fronteira. |
| Terra r2/5–6 — Intenção e tráfego automático | **Parciais.** |
| Terra r2/7 — Protocolos/saída alternativa | **Proxy retirado; política de admissão declarada parcialmente.** Não há mais promessa de confinamento por proxy. |
| Terra r2/8 — Cookies/personalização | **Não resolvido integralmente.** |
| Terra r2/9 — Página local hostil | **Não resolvido expressamente.** Exigir dados escapados como texto, sem script/recursos externos, com teste de alvo hostil. **MÉDIA; redação.** |
| Terra r2/10 — Recursos globais | **Não resolvido integralmente.** `max_capturas` não limita tráfego, memória ou simultaneidade. |
| Terra r2/11 — Aceite | **Parcial.** |

O teste exploratório é evidência útil de viabilidade em um navegador, três portais e um ato. Suas próprias limitações — especialmente não ter capturado o corpo XHR de normas.leg.br nem exercitado desafios ativos — impedem usá-lo como prova global das garantias normativas restantes.

BLOQUEADOR