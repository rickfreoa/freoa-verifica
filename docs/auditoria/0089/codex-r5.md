A v5 **ainda não resolve integralmente B2 e R4**. Conferi o ramo `docs/0089-sessao-assistida`, HEAD `c83e1b65b37520047765b7b5e3a0467001481a91`, com árvore limpa. Li os dois pareceres r4, o laboratório e a tabela final da §7. Não alterei arquivos nem executei testes.

“Resolvido” abaixo significa resolvido **na especificação**, sujeito ao aceite da implementação. “Terra 1–7” corresponde aos sete achados da v4, conforme a tabela final da §7.

| Item | Situação | Motivo |
|---|---|---|
| **B1** | **Resolvido** | §2.5(2) abandona a reconstrução textual e exige bytes binários por streaming, confrontados com `dataLength`. O laboratório cobre o contraexemplo BOM UTF-16. |
| **B2** | **Parcial** | O inventário independe agora de alvo CDP, mas a leitura periódica de arquivos de preferências não prova o inventário efetivo durante toda a sessão. Persistem atualização diferida e mudanças transitórias entre conferências; detalhamento abaixo. |
| **B3** | **Resolvido** | §2.3 determina prontidão, recusa histórico incompleto e identifica o quadro principal pela raiz de `Page.getFrameTree`, sem depender da coincidência com `targetId`. |
| **R1** | **Resolvido** | Linha 17 acrescenta `application/json` exclusivamente à admissão assistida de recurso que o declare. |
| **R2** | **Resolvido** | Linha 7 exige os confrontos finais e declara expressamente a substituição por `loadingFinished` para documento comprimido sem contador codificado observável. |
| **R3** | **Resolvido** | Linha 12 declara a diferença entre primeiro byte e cabeçalhos completos observáveis; §3.1 inclui cabeçalho parcial. |
| **R4** | **Parcial** | Há limites numéricos para fila, corpos e candidatas, mas os 64 MiB contam corpos já decodificados. Não ficou determinada a reserva para a mensagem em processamento, strings JSON/base64, decodificação e cópias simultâneas. |
| **R5** | **Resolvido** | Linha 1 separa a URL HTTP interna do HSTS da candidata HTTPS; linha 8 conserva a exceção estrutural restrita. |
| **R6** | **Resolvido** | §2.12 enumera parâmetros, valores, encaminhamento por `sessionId` e objetos vazios. O `requestId` do streaming está previsto. |
| **R7** | **Resolvido** | O grafo fecha antes da seleção e gravação; conflitos posteriores invalidam dependentes; B referencia identificador e hash de A; múltiplos B divergentes são recusados. |
| **R8** | **Resolvido** | O modelo passa a ser verificável por região variável delimitada, comprimento e SHA-256 da cauda normalizada. Desvios impedem equivalência. |
| **R9** | **Resolvido** | §2.7(3) retira a implicação entre sintaxe e publicidade e declara o risco residual. Avaliação preserva a decisão 5 do titular. |
| **Terra 1** | **Parcial** | Mesma pendência de B2: independência de alvo corrigida; completude temporal do inventário ainda não demonstrada pelo mecanismo prescrito. |
| **Terra 2** | **Resolvido** | Mesma solução de B1: bytes binários, sem usar charset ou igualdade de comprimento como prova de reversibilidade textual. |
| **Terra 3** | **Resolvido** | Fechamento global do vínculo, referência probatória A→B, tratamento de duplicidades e validação de `version`/`@id` foram incorporados. |
| **Terra 4** | **Resolvido** | Publicidade passa a decorrer da declaração do perfil, com limite explicitado, conforme decisão 5. Não se exige prova universal adicional. |
| **Terra 5** | **Resolvido** | Nomes desconhecidos e indicadores definidos de personalização recusam a candidata. A confirmação dos nomes reais permanece requisito explícito, sem autorização para inferi-los em execução. |
| **Terra 6** | **Resolvido** | Mesma solução de R8: modelo integral identificado por hash, sem região intermediária livre. |
| **Terra 7** | **Resolvido** | Parâmetros e sequência foram determinados; HSTS, redirecionamento real e interno sem prova têm resultados distintos no aceite. A execução desses cenários continua obrigatória. |

A conferência específica do CDP resulta no seguinte:

- **Streaming:** `bufferedData` representa o prefixo acumulado até a habilitação; os eventos `dataReceived.data` fornecem os dados durante o streaming. Cada campo binário deve ser decodificado de base64 antes da concatenação dos bytes. O protocolo não exige chamar no `requestWillBeSent`: essa é uma restrição conservadora da v5. Recusar ativação tardia é compatível com o contrato. A implementação do Chromium entrega o buffer e os blocos como binários, sustentando a correção de B1. [Definição de Network](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Network.pdl), [implementação do streaming](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/core/inspector/inspector_network_agent.cc).
- **Quadro principal:** `Page.getFrameTree` fornece a árvore **atual**, não uma árvore histórica. Sua raiz, reconciliada com os eventos e a recusa de histórico incompleto da §2.3, fornece o mecanismo necessário. A observação laboratorial de igualdade com `targetId` não precisa virar pressuposto. [Definição de Page](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Page.pdl).
- **Lista da §2.12:** basta, quanto aos comandos CDP, para o streaming, a árvore de quadros e os eventos declarados. Não fornece prova adicional sobre extensões: esse requisito depende integralmente do inventário externo da §2.2(3).

As pendências abaixo são **continuação dos achados r4**, não achados novos:

**B2 / Terra 1 — BLOQUEADOR, alta.**

Trechos: §2.2(3), “`extensions.settings`, que lista toda extensão instalada” e “O inventário é refeito a cada 10 s e imediatamente antes da seleção”.

As preferências do Chromium são modificadas em memória e sua gravação é agendada. O gravador pode reunir alterações e persistir somente o estado mais recente. Assim, arquivo legível não significa estado atual comprovado; uma extensão instalada, atuante e removida entre conferências pode não constar dos estados examinados. Mesmo uma leitura final atualizada não reconstrói essa passagem. Isso é um contraexemplo ao mecanismo especificado, não uma afirmação de reprodução no Chrome 157. [JsonPrefStore](https://raw.githubusercontent.com/chromium/chromium/main/components/prefs/json_pref_store.cc), [ImportantFileWriter](https://raw.githubusercontent.com/chromium/chromium/main/base/files/important_file_writer.h), [remoção das preferências da extensão](https://raw.githubusercontent.com/chromium/chromium/main/extensions/browser/extension_prefs.cc).

O laboratório demonstra descoberta independente de alvo e detecção da Fortinet naquele ambiente. Não demonstra sincronização entre arquivo e estado efetivo nem cobertura das mudanças transitórias.

**Redação mínima:**

> A leitura periódica de `Secure Preferences`/`Preferences` é evidência auxiliar e não certifica, isoladamente, o inventário efetivo durante toda a sessão. Sem mecanismo determinado e validado que cubra instalação, alteração e remoção, inclusive entre conferências, a sessão permanece indisponível e nenhuma candidata é gravada.

**R4 — RESSALVA, média.**

Trecho: linha 15, “64 MiB de bytes de corpo [...] contados ao chegar cada bloco já decodificado de base64 e reservados antes da cópia”.

A reserva ocorre depois de uma alocação relevante já ter acontecido. O teto da fila não define o orçamento da mensagem retirada para processamento.

**Redação mínima:**

> Os 64 MiB abrangem todas as representações de corpo simultaneamente mantidas pelo adaptador, inclusive JSON/base64, buffers decodificados e cópias. A reserva precede cada alocação; a mensagem em processamento continua contabilizada. Impossibilidade de limitar a leitura ou reservar memória encerra a sessão sem gravação.

Não identifiquei outros achados novos admissíveis no escopo fechado. A tabela final da §7 registra corretamente as correções pretendidas, mas superestima o fechamento de B2 e R4.

BLOQUEADOR