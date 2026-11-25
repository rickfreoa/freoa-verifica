**Veredito: BLOQUEADOR**, por regressão no encerramento diante de protocolo malformado. Os três achados da r2 estão fechados nas variações examinadas.

Conferência sobre `5f5a58530e4b1cd3cff37fe982e2d486a2f523b0`, ramo `feat/0089-sessao-assistida`. Somente leitura; arquivos rastreados permaneceram limpos.

1. **MÉDIO — campo ausente pode mascarar malformação estrutural e preservar a sessão.**

   **Local:** [cdp.py:713](/C:/dev/fv14-0089i/freoa_verifica/assistida/cdp.py:713) e [cdp.py:752](/C:/dev/fv14-0089i/freoa_verifica/assistida/cdp.py:752).

   **Cenário reproduzido:** após `request(ad, rid="bad")`, entregar um destes eventos, com `sessionId="cdp"` e `requestId="bad"`:

   | Evento | Demais campos de `params` |
   |---|---|
   | `Network.requestWillBeSentExtraInfo` | `{"associatedCookies": [null]}` |
   | `Network.responseReceivedExtraInfo` | `{"statusCode": "bad", "blockedCookies": []}` |

   Em ambos falta `headers`, mas também existe malformação efetiva: elemento de cookie nulo ou status textual.

   O primeiro acesso a `dados["headers"]` lança `KeyError`. O tratamento verifica a ausência e recusa somente a candidata, sem examinar os campos malformados presentes.

   **Resultado comparativo**, executando também o método anterior extraído por AST de `16d4c7e`:

   | Implementação | Resultado nos dois casos |
   |---|---|
   | `16d4c7e` | `EVENTO_CDP_INVALIDO`; adaptador fechado e sessão encerrada |
   | HEAD | `METADADOS_SEGURANCA_ASSISTIDOS_AUSENTES`; sessão aberta; captura posterior válida admitida |

   **Critério:** a exigência do item 2 desta conferência — malformação real continuar encerrando a sessão — não foi preservada. Contradiz também o comportamento declarado em [implementacao-trilha-b.md:1506](/C:/dev/fv14-0089i/docs/auditoria/0089/implementacao-trilha-b.md:1506).

   **Correção:** validar os tipos e estruturas dos campos presentes antes de classificar o evento como simples ausência de metadados. Acrescentar regressões combinando ausência com malformação, preservando a recusa apenas da candidata quando houver exclusivamente falta de prova.

   Não houve admissão da candidata malformada nem demonstração de `verified` indevido.

A conferência dos três achados da r2 resultou em:

| Achado | Resultado |
|---|---|
| **Vínculo B→A incompleto ou IDs ausentes/nulos** | **Fechado nas variantes examinadas.** Foram recusadas 88 mutações de recibos. A mesclagem real em SQLite em memória recusou vínculo ausente, igualdade entre IDs nulos/vazios/listas, sessão de A ausente e referência a A automática. Doze mesclagens positivas cobriram `Current`, `Original`, colisões naturais de A/B e reinstalação. A e legado legitimamente sem vínculo permaneceram aceitos. |
| **Passividade com `q` nunca observado** | **Fechado.** Em 55 casos independentes, valores observados passaram e valores inéditos foram recusados, preservando ocorrência, combinação e multiplicidade. Não encontrei permissividade ou restrição adicional nos casos exercitados contra a 0090 §3.3. |
| **Evento zero anterior à resposta do streaming** | **Fechado.** Foram admitidos 48 fluxos válidos, variando quantidade de eventos zero, bytes anteriores e `Document`/XHR/Fetch. Seis controles negativos mantiveram recusas por divergência, dados anteriores, término prematuro, contador negativo, excesso e tamanho posterior incorreto, conforme a 0090 §3.2. |

A mudança para respostas de service worker **não reabriu o achado 1 da r1 nas variantes examinadas**: a matriz independente de 108 mutações não mostrou admissão por metadados ausentes ou inválidos. Resposta SW sem TLS foi recusada com `ORIGEM_ASSISTIDA_SEM_PROVA`, preservando a sessão. A falha remanescente é a classificação dos eventos com defeitos combinados descrita acima.

No diff `16d4c7e..HEAD`, não demonstrei outra regressão. Contra `87b43f7`, **77 definições preexistentes do transporte estão presentes e inalteradas por AST**; os 106 nós preexistentes do módulo permanecem na mesma ordem.

Execução própria: **638 passed, 1 skipped, 190 deselected**, sem `conftest`, cache ou fixtures temporárias. Conferi separadamente os logs finais de **1562 passed** na bateria afetada e **619 passed** em `repositorio`; os **12 hashes** registrados correspondem ao checkout atual.

**Não verifiquei:** suíte offline global, CI remota, nova execução em navegador real, instalador público de snapshots com blobs em disco, instalação Windows, gestos humanos ou sessão manual. As mesclagens exercitaram o código real com abertura e anexação SQLite direcionadas à memória.

Os adiamentos ambientais estão fielmente enumerados no payload documental e não fundamentam este bloqueio. Sua aplicação ao manifesto de aceite e ao registro da release permanece pendente; os gestos humanos continuam exigidos antes da sessão manual.