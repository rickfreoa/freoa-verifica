**BLOQUEADOR**

Auditoria somente leitura sobre `docs/0089-sessao-assistida`, HEAD e `origin/main` em `35dd8bc1513e146ad2965d2c3e688dd88e91ebca`. A 0089 está não rastreada. Não alterei arquivos nem executei testes: o objeto é a especificação.

1. **ALTA — A exceção de `Content-Encoding` contradiz expressamente a 0067.**

   A [0089:49–51](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:49) dispensa a validação porque o navegador entrega corpo decodificado. A `0067-sessao-assistida-e-modelos-de-ranqueamento.md:25–29` exige as mesmas validações, nomeia `Content-Encoding` e manda recusar o que não passaria no fluxo automático. A `0060-content-encoding-antes-do-desvio-por-status.md:13–18` e `freoa_verifica/transport.py:1128–1136` recusam codificação diferente de ausente ou `identity`, em qualquer status.

   Portanto, aceitar um GET 200 originalmente gzip seria uma diferença de aceitação, não apenas de recibo. O marcador `corpo_decodificado_pelo_navegador` não elimina essa contradição.

   **Redação mínima:** “Aplica-se a validação de Content-Encoding da 0060 aos cabeçalhos originais, antes de qualquer desvio por status. Resposta com codificação diferente de ausente ou identity é recusada, ainda que o navegador disponibilize o corpo decodificado.” Se a intenção for aceitar compressão, exige-se revisão expressa da 0067, com limites e provas próprios.

2. **ALTA — A §2.3 não enumera todas as diferenças nem fornece dados suficientes para a equivalência prometida.**

   A promessa está na [0089:43–54](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:43); o protocolo oferece apenas os campos das linhas 22–26. Permanecem sem regra suficiente:

   | Validação automática | Evidência no código | Lacuna da especificação |
   |---|---|---|
   | Framing estrito, Content-Length duplicado/inválido, conflito com Transfer-Encoding | `transport.py:355–378` | Não define preservação de multiplicidade dos cabeçalhos nem prova equivalente de framing. |
   | Tamanho declarado e confronto entre Content-Length e bytes recebidos | `transport.py:1199–1203`, `1260–1264` | Omitir o cabeçalho do recibo não declara se esses controles permanecem ou desaparecem. |
   | Redirecionamentos: desafio no salto, Location, máximo de saltos e recusa de 307/308 entre origens | `transport.py:1137–1166`, `1293` | “Cadeia” não tem esquema com status, cabeçalhos e corpo de cada salto; validar suas URLs não reproduz esses controles. |
   | DNS seguro e conexão ao IP validado | `transport.py:680–719`, `769–783` | Resolver a URL depois do evento não comprova qual destino serviu os bytes. |
   | Prazo total e taxa mínima de leitura | `transport.py:1063–1077`, `1210–1258` | Os 20 minutos da sessão não definem prazo e progresso de cada captura. |
   | Identidade com método, URL, query exata, corpo e cabeçalhos do chamador | `transport.py:474–497`; `connectors/httputil.py:58–68` | “URL canônica da fonte” não define identidade da representação, isolamento por sessão nem tratamento dos cabeçalhos variáveis. |

   Também falta separar os cabeçalhos usados para validação dos selecionados para recibo: `Response.content_type` conserva o valor cru (`transport.py:158`), enquanto `observe_http_response` filtra valores e duplicatas (`transport.py:186–214`). Um único `headers` sem tipo definido não estabelece essa distinção.

   **Redação mínima:** “A §2.3 contém matriz exaustiva por validação automática, indicando dados exigidos, ordem, código de recusa e eventual diferença expressamente aprovada. O evento preserva os dados necessários de cada salto e os cabeçalhos com multiplicidade. Validação sem prova suficiente causa recusa; não se presume equivalência por normalização do navegador.” A matriz precisa ser preenchida antes da implementação.

3. **ALTA — A abertura automática da página contradiz a declaração de ausência de requisição pela ferramenta.**

   A [0089:78–83](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:78) manda a ferramenta abrir a página inicial ou `--alvo`, mas afirma que ela “não faz requisição pelo navegador” e atribui toda a rede ao humano.

   A 0067 permite abrir o contexto dedicado (`0067…md:22`), mas condiciona a leitura da regra 4 ao navegador “só usado pelo humano” (`0067…md:25–29`). A navegação inicial disparada pela ferramenta precisa de disciplina explícita; o comando humano de início não transforma esse GET em navegação manual.

   **Redação mínima:** “A ferramenta abre o contexto dedicado em página sem acesso à rede e apresenta o alvo validado. A navegação ao alvo é realizada pelo humano.” A porta única permanece obrigatória para todas as capturas. Assim se resolve a abertura inicial sem ampliar a exceção da 0067.

4. **ALTA — O aditivo proposto altera o tipo de `fontes_indisponiveis`.**

   A [0089:94–98](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:94) trata `fontes[<id>]`, `falhas[]` e `fontes_indisponiveis` como recipientes equivalentes para `motivo` e objeto `sessao_assistida`.

   No código, `fontes_indisponiveis` é **mapa de fonte para string**, produzido por `service.py:471–483`. Seus valores não recebem campos. Convertê-los em objetos viola `docs/CONTRATO.md:18–19`, mesmo mantendo todos os literais de `status`.

   **Redação mínima:** “`fontes_indisponiveis` mantém o tipo mapa de fonte para string. Os detalhes de sessão entram em campo irmão experimental `sessoes_assistidas`, indexado por fonte, ou em objetos já existentes de fonte/falha. Nenhum campo existente muda de tipo.”

   O novo código de `motivo`, isoladamente, é permitido pelo conjunto aberto (`docs/CONTRATO.md:242`). `procedencia: sessao_assistida` também já existe: `store/repo.py:62`, `verify.py:248–266` e `docs/CONTRATO.md:78`.

5. **ALTA — A §2.8 produz falsos acionamentos e omissões; categoria não prova que a sessão resolverá.**

   A [0089:92–97](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:92) faz o disparo apenas pela categoria e afirma que sessão nunca resolve `fonte_fora` ou `resposta_inesperada`.

   **Dispara sem solução assegurada:** `recusa_identificado` inclui todo 401/403 sem assinatura (`connectors/challenge.py:157–158`), inclusive recusa de autorização. A 0067 não autoriza obter autos autenticados (`0067…md:42–44`). Perfil da fonte também não prova capacidade para a operação: TJSP entra na §2.9, mas sua pesquisa POST está adiada pela própria 0089:144.

   **Deixa de disparar onde pode haver solução:** compressão recusada é `resposta_inesperada` (`0060…md:23–24`; `challenge.py:164–170`), embora a própria §2.3 pretenda aceitá-la pelo navegador. Falha de conexão/TLS sem resposta pode ser `fonte_fora` (`challenge.py:171–177`); essa classificação não prova inacessibilidade humana. O Planalto tem justamente uma reclassificação específica desse cenário (`connectors/planalto.py:38–45`).

   **Redação mínima:** “A indicação exige capacidade assistida habilitada para a operação e o alvo, fonte não barrada e evidência de barreira pública resolúvel pelo humano. Categoria isolada não comprova resolubilidade. Preservam-se motivo, categoria e evidência originais; a orientação de sessão é aditiva. Exceções por fonte são declaradas em tabela versionada.”

   É necessário definir ainda como se comprova “fonte só acessível por sessão”. Hoje essa condição deixa uma regra ao implementador.

6. **ALTA — A elegibilidade a `verified` usa uma premissa de origem ainda não demonstrada e amplia indevidamente a 0083.**

   A [0089:62–64](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:62) afirma que os bytes são oficiais porque vieram da sessão e invoca a exclusão de adulteração do home.

   Contudo, o protocolo das linhas 22–26 não exige prova que distinga resposta de rede de conteúdo sintetizado, substituído ou reaproveitado; tampouco vincula o destino efetivo à validação posterior da URL. Excluir DOM não basta para estabelecer essa fronteira.

   A `0083-modelo-de-ameaca-do-recibo-gravado.md:23–30` trata da **conferência de recibo gravado da Câmara** e exclui adulteração deliberada do banco local. Não exclui falhas normais de aquisição, adaptação ou atribuição de origem. Seus limites continuam bloqueando confirmação indevida (`0083…md:42–44`).

   **Redação mínima:** “A modalidade assistida não reduz os requisitos de verified. A aquisição deve comprovar a origem oficial e a correspondência entre resposta, URL, instante e bytes completos; origem não demonstrada causa recusa. Continuam exigidos identidade, âncora reproduzível e confronto efetivo. A exclusão da 0083 limita-se à adulteração deliberada do banco local, sem dispensar controles de aquisição.”

   **Conclusão específica:** captura assistida pode ser elegível; a justificativa atual não demonstra essa elegibilidade. Não há código nesta auditoria que permita afirmar exploração ou `verified` indevido já produzido.

7. **ALTA — O envelhecimento foi formulado como regra geral da captura, contrariando a separação temporal.**

   A [0089:65–66](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:65) diz que “a captura envelhece para unknown”. A janela de 30 dias da `0002-estados-temporais.md:5–6` condiciona `vigente_na_fonte`; não expira genericamente identidade, confronto textual ou prova histórica. A 0075 preserva essa distinção (`0075…md:17–22`).

   **Redação mínima:** “Ultrapassar 30 dias impede a afirmação corrente vigente_na_fonte nas condições da 0002. Não invalida automaticamente identidade, confronto textual ou fundamento histórico. A indicação de nova sessão refere-se à atualização necessária para a consulta corrente.”

8. **ALTA — O aceite não prova integralmente as exigências da 0067.**

   A [0089:120–133](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:120) contém controles úteis, mas insuficientes:

   - A fábrica de eventos pode provar a porta; não prova que o adaptador real entrega bytes completos, cabeçalhos e cadeia sem perda. A equivalência dos itens 4–5 precisa incluir a matriz do achado 2.
   - Ausência de importação direta não prova ausência de chamada indireta, repetição, renovação ou navegação automática.
   - A 0067 exige `modalidade_acesso: sessao_assistida` (`0067…md:23–24`); a 0089 exige apenas procedência/rótulo. Não fixa preservação dessa modalidade no snapshot, cuja procedência pública passa a `snapshot` (`0075…md:47`).
   - A política de segredos não resolve o caso de segredo presente no próprio corpo ou em URL/cabeçalho persistido. Guardar bytes integralmente e assegurar ausência de segredos exige uma regra de admissão; não se pode simplesmente redigir o corpo e manter sua identidade de captura.

   **Redação mínima:** “O aceite inclui testes do adaptador real contra origem controlada, matriz completa de validação, chamadas indiretas, ausência de repetição/renovação, descarte de segredos e exportação/instalação de snapshot. Persiste e publica modalidade_acesso: sessao_assistida separadamente da procedência. Resposta que contenha segredo incompatível com a persistência é recusada, sem alteração dos bytes para torná-la admissível.”

   Fixtures desses testes devem seguir `AGENTS.md:26`. O teste manual do Planalto complementa essas provas; não as substitui.

Não identifiquei alteração expressa de literal fechado de estado ou das categorias de `connectors/base.py:16–22`. Também não encontrei conflito específico com a 0088 ou com D6. A §6 prevê revisão independente, mas a implementação de `capturar_assistida` continua sujeita à auditoria própria de `transport` exigida por `docs/PLANO-1.4.0.md:63`.

**A especificação ainda deixa decisões de regra ao implementador e não atende aos seis critérios obrigatórios.**