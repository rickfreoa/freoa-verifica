A v4 ainda contém **bloqueadores**: a prova de identidade dos bytes admite contraexemplo, e o controle de extensões não assegura a aplicação da decisão 3 do titular. A lista CDP também não determina como comprovar que um `Document` pertence ao quadro principal.

Conferi o ramo `docs/0089-sessao-assistida` e o HEAD `9bbe2e0e709d6031c037a2c329da1d633fd2d226`. A árvore está limpa; os seis arquivos de código indicados permanecem iguais aos de `35dd8bc`. Não alterei arquivos, executei testes nem abri navegador. As seis decisões do titular foram tratadas como premissas, sem reabertura.

**Situação de todos os achados da rodada 3**

“Resolvido” significa resolvido na especificação, sujeito ao aceite da implementação.

| Parecer | Achado r3 | Situação na v4 |
|---|---|---|
| Codex 1 | Leitura da regra 4 | **Resolvido.** §2.1 e remissões em AGENTS/0001 explicitam a exceção. |
| Codex 2 | Cache e service worker | **Resolvido.** Comandos retirados; observação pura expressamente adotada. |
| Codex 3 | Matriz incompleta | **Parcial.** Cobertura ampliada, mas persistem diferenças e indeterminações descritas abaixo. |
| Codex 4 | Contenção e recursos | **Parcial.** Alcance limitado à admissão foi esclarecido; fila e contabilização global ainda precisam de determinação. |
| Codex 5 | Identidade após charset | **Parcial.** U+FFFD foi barrado, mas o contraexemplo B1 permanece possível. |
| Codex 6 | Redirecionamentos/HSTS | **Parcial.** Saltos de rede foram recusados; falta conciliar expressamente o salto HTTP interno com a validação de URL. |
| Codex 7 | Correlação | **Parcial.** Chave composta e descarte de ambiguidade resolvem o núcleo; quadro principal e anexação permanecem incompletos. |
| Codex 8 | Status, cabeçalhos e completude | **Parcial.** `statusCode`, `headersText` e opcionais foram corrigidos; faltam confrontos finais explícitos. |
| Codex 9 | Prazo e classificação | **Parcial.** Valor e fiscalização definidos; “resposta iniciada” continua diferente do transporte. |
| Codex 10 | Proxy e políticas | **Parcial.** Conexão direta e pipe definidos; inventário de extensões insuficiente, B2. |
| Codex 11 | Conteúdo público/segredos | **Parcial.** Decisão 5 aplicada; a promessa de publicidade “por construção” e o aceite de segredos ainda conflitam. |
| Codex 12 | Identidade e autorização | **Resolvido.** Obtenção opaca e seleção final com dependentes vinculados. |
| Codex 13 | Perfis/envelhecimento | **Parcial.** Gates cumulativos corrigidos; perfil JSON contradiz a linha 17. |
| Codex 14 | Lista CDP | **Parcial.** Lista enumerada, mas insuficiente para quadro principal e incompleta nos parâmetros. |
| Codex 15 | Alcance do filtro | **Resolvido.** Separação expressa entre registros da ferramenta e artefatos do navegador. |
| Codex 16 | Aceite | **Parcial.** Ampliação substancial; lacunas de rastreabilidade e resultados esperados abaixo. |
| Terra 1 | Extensões forçadas | **Aberto.** A detecção depende de alvo CDP; B2. |
| Terra 2 | Canal DevTools | **Resolvido no modelo declarado.** TCP eliminado, pipe restrito e adversário da mesma conta expressamente excluído. |
| Terra 3 | JSON–binário | **Parcial.** Vínculo concreto definido; falta fechar conflitos posteriores e referência probatória entre capturas. |
| Terra 4 | Origem/associação | **Parcial.** Melhorou, mas subsiste B3. |
| Terra 5 | Seleção humana | **Resolvido.** Decisão 4 aplicada. |
| Terra 6 | Identidade dos bytes | **Parcial.** Subsiste B1. |
| Terra 7 | Bomba/completude | **Parcial.** Garantia de contenção reformulada; completude e contabilidade precisam de complemento. |
| Terra 8 | Captura privada | **Resolvido no âmbito da decisão 5.** Não exijo prova universal adicional de publicidade. |
| Terra 9 | Segredos/artefatos | **Parcial.** Artefatos receberam requisito verificável; publicidade sintática continua excessivamente afirmada. |
| Terra 10 | `f5_cspm` | **Parcial.** Estrutura delimitada, mas o miolo está representado por reticências. |
| Terra 11 | Tráfego não controlado | **Resolvido quanto ao alcance declarado.** Não se promete confinamento do tráfego do navegador. |
| Terra 12 | Página inicial | **Resolvido.** Texto escapado, sem scripts/recursos externos e CSP restritiva. |

**Achados bloqueadores**

**B1 — BLOQUEADOR, alta: §2.5(2) ainda não prova identidade de bytes.**

Trecho: [§2.5(2)](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:175), especialmente “BOM removido pelo navegador altera o tamanho e causa recusa”.

Há um contraexemplo concreto à prova matemática:

```text
Content-Type: text/html; charset=utf-8

Bytes anteriores à interpretação:
FF FE 00 08 00 08                 — 6 bytes

Interpretação por BOM UTF-16LE:
U+0800 U+0800

Reencodificação UTF-8:
E0 A0 80 E0 A0 80                 — 6 bytes diferentes
```

As três condições enunciadas passam: não há U+FFFD; os comprimentos coincidem; o cabeçalho declara UTF-8. A retirada dos dois bytes do BOM é compensada pela expansão dos dois caracteres.

Isso não depende de um decodificador hipotético: o decodificador do Blink admite que BOM UTF-16 prevaleça sobre outra codificação e remove esse BOM. O inspetor possui caminho textual que usa `TextResourceDecoder`. Não executei o exemplo no Chrome instalado; trata-se de refutação da suficiência da regra, apoiada no código primário. [Decodificador do Blink](https://raw.githubusercontent.com/chromium/chromium/main/third_party/blink/renderer/core/html/parser/text_resource_decoder.cc), [decodificação no inspetor](https://chromium.googlesource.com/chromium/src/+/267dbb8b5f6604eb9b76efea2764794e90ffdd5c/third_party/blink/renderer/core/inspector/inspector_page_agent.cc).

A classe inteira compreende transformações cuja redução e expansão se compensam, inclusive conflitos entre declaração e codificação efetiva. Pode-se construir HTML completo com o mesmo fenômeno, compensando cada caractere ASCII com caracteres que expandem na passagem UTF-16→UTF-8.

`repo.save_capture` não corrige isso: confere o hash contra o corpo recebido do adaptador, já transformado, em [repo.py:82](/C:/dev/fv14-0089/freoa_verifica/store/repo.py:82).

**Redação mínima:** “Texto retornado pelo CDP não constitui prova de identidade dos bytes por ausência de U+FFFD, declaração de charset e igualdade de comprimento. Sem obtenção comprovadamente preservadora dos bytes anteriores à interpretação de charset, a candidata é recusada.”

Isso preserva as decisões do titular e reduz a compatibilidade onde a prova faltar.

**B2 — BLOQUEADOR, crítica: extensões sem alvo CDP escapam ao controle da decisão 3.**

Trecho: [§2.2(3)](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:65): “a cada extensão que apareça como alvo”.

Uma extensão Manifest V3 pode conter somente regras estáticas `declarativeNetRequest`, sem página de fundo nem service worker. Essas regras são executadas pelo navegador e podem modificar cabeçalhos ou redirecionar pedidos; sua execução não depende de surgir um alvo de extensão inspecionável. A documentação oficial descreve regras estáticas empacotadas e ações de modificação de pedidos e respostas. [API declarativeNetRequest](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest).

Assim, uma extensão instalada por política pode interferir e nunca alcançar a condição que dispara a leitura do manifesto. Ler o Registro sem recusar ou resolver integralmente a instalação forçada também não estabelece um inventário completo. Os eventos finais podem continuar mostrando resposta 200, TLS seguro e IP público.

A classe compreende extensões declarativas sem contexto executável, contextos inativos e instalação/ativação posterior à conferência.

**Redação mínima:** “A conferência abrange todas as extensões habilitadas ou cuja instalação seja imposta por política, independentemente de aparecerem como alvos CDP. Inventário incompleto, manifesto indisponível ou impossibilidade de excluir permissões vedadas impede a sessão; instalação ou ativação posterior encerra-a sem capturas.”

É aplicação da decisão 3 já tomada, não proposta de rever sua exigência.

**B3 — BLOQUEADOR, alta: a lista fechada não fornece prova determinada do quadro principal.**

Trechos: §2.3(3), “`Document` de quadro principal”; [§2.12](/C:/dev/fv14-0089/docs/decisoes/0089-sessao-assistida-especificacao.md:309), especialmente a dispensa de `Page.enable` porque `Network` fornece `documentURL`, `loaderId` e `frameId`.

Esses identificadores não fornecem, por si, a relação pai–filho dos quadros. Um iframe no mesmo processo pode emitir `Document` na mesma sessão `page`; `frameId` identifica o quadro, mas não declara que ele é a raiz. Comparar `frameId` com `targetId` sem contrato técnico expresso acrescentaria uma suposição de implementação. [Definição de Network](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json).

A classe abrange iframes no mesmo processo, navegações concorrentes e mudanças de processo. A especificação deixa ao implementador escolher entre aceitar documento fora do escopo, inventar uma inferência ou ampliar a lista proibida.

Também falta a sequência de prontidão: `setAutoAttach` alcança alvos relacionados, pode anexar alvos já existentes e admite uso recursivo; não retroage para observar requisições anteriores à configuração. [Definição de Target](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Target.pdl).

**Redação mínima:** “A lista enumera um mecanismo somente leitura para obter e acompanhar a árvore de quadros, com identificação inequívoca da raiz. Antes da prontidão confirmada de anexação e `Network.enable`, nenhum pedido é elegível; alvo existente ou histórico incompleto é recusado. A sequência de anexação, habilitação e liberação é normativa.”

Se a lista permanecer exatamente como está, deve-se retirar a promessa de admitir `Document` de quadro principal sem essa prova.

**Ressalvas e correções determinadas**

| ID e gravidade | Trecho e classe inteira | Redação mínima |
|---|---|---|
| **R1 — RESSALVA, média** | §2.4, linha 17 exige MIME contido em `DEFAULT_ALLOWED_MIMES`, mas §2.11 exige `application/json`, ausente daquele conjunto em `transport.py:48`. Todo perfil `normas_leg` fica inválido pela própria regra. | “A lista assistida acrescenta exclusivamente `application/json` para o recurso A; não altera os padrões do fluxo automático.” |
| **R2 — RESSALVA, média** | Linhas 4–7 não enunciam o confronto final de CL com corpo codificado nem de corpo obtido com a contagem decodificada. O transporte faz confronto efetivo em `transport.py:1260`; limitar tamanho e esperar `loadingFinished` não descreve a mesma validação. | Exigir confronto final quando houver contagem apropriada; declarar expressamente a substituição pelo navegador onde não houver. Para base64, conferir também o comprimento dos bytes obtidos contra a contagem decodificada. |
| **R3 — RESSALVA, média** | Linha 12 chama de “Igual” uma regra baseada em `responseReceived`. Em `_classificar`, qualquer byte de resposta iniciado basta, inclusive cabeçalho incompleto. Toda resposta que trava antes de completar os cabeçalhos expõe a diferença. | Declarar a diferença observacional e a classificação assistida correspondente, sem chamá-la de equivalência ao primeiro byte. Incluir o caso no aceite. |
| **R4 — RESSALVA, média** | Linha 15: “Fila de eventos CDP limitada” não informa limite; “64 MiB de corpos” não define reserva antes de receber strings JSON/base64 e cópias. Abrange filas cheias e corpos simultâneos. | Fixar limite da fila e unidade, contabilização/reserva dos buffers do adaptador e ação ao exceder; manter expressa a exclusão da memória interna do navegador. |
| **R5 — RESSALVA, média** | Linha 8 admite HSTS `http→https`, mas linha 1 manda validar `request.url` pela função que recusa HTTP. Abrange todo HSTS admitido. | “A URL HTTP exclusivamente interna desse salto não é candidata e recebe apenas a validação estrutural da exceção; a URL HTTPS efetiva passa integralmente pela linha 1.” |
| **R6 — RESSALVA, média** | §2.12 proíbe parâmetros não indicados, mas omite `discover:true` e o `requestId` obrigatório de `Network.getResponseBody`. | Enumerar os parâmetros exatos de cada chamada e o `sessionId` de encaminhamento; métodos sem parâmetros usam objeto vazio. |
| **R7 — RESSALVA, média** | §2.11 verifica B após A, mas não determina revalidação quando outra A posterior torna o UUID ambíguo; tampouco exige referência identificável à captura A. Abrange conflitos surgidos depois da primeira admissão. | Fechar o grafo da sessão antes da seleção/persistência; invalidar dependentes conflitantes e gravar em B a referência e o hash da A que fundamenta o vínculo. |
| **R8 — RESSALVA, média** | §2.5(3) apresenta uma “forma estrutural estrita” cujo miolo é `…`. Abrange qualquer conteúdo colocado nessa região. | Substituir as reticências por padrão integral verificável, com trechos fixos e regiões variáveis enumeradas. |
| **R9 — RESSALVA, média** | §2.7(3) afirma que conformidade à gramática torna o valor público “por construção”; §3.6 promete ausência de tokens no corpo. A decisão 5 autoriza declaração do perfil, não essa implicação matemática nem detector universal de segredo. | Vincular a publicidade à declaração do perfil e aos indicadores de recusa definidos; separar dados pessoais publicamente publicados de segredos sintéticos recusáveis. Retirar a equivalência entre sintaxe e publicidade. |

**Conferência dos elementos CDP solicitados**

| Elemento | Resultado |
|---|---|
| `responseReceivedExtraInfo.headersText` | Existe, opcional, com texto bruto; pode faltar, especialmente em HTTP/2/QUIC. Exigi-lo em HTTP/1 é conservador. |
| `statusCode` no mesmo evento | Existe e resolve corretamente o caso 304 apresentado como 200. |
| `requestWillBeSentExtraInfo` | Existe; pode faltar ou anteceder o evento comum. `associatedCookies` inclui cookies enviados e bloqueados; é preciso distingui-los. |
| `dataReceived.dataLength/encodedDataLength` | Existem. São comprimentos reportados; não provam identidade textual nem contenção anterior ao evento. |
| `redirectResponse` | Existe como `Response`; não contém corpo. `Non-Authoritative-Reason` é um valor no mapa de cabeçalhos, não um campo tipado de prova HSTS. |
| `TargetInfo.subtype` | Existe, opcional, com exemplo `prerender`. Guardar o histórico desde a criação é a exigência adequada. |
| `Browser.setDownloadBehavior` | Existe, experimental; a chamada usa `behavior:"deny"`. Sem `browserContextId`, alcança o contexto padrão. |
| `Network.getResponseBody` | Serve para XHR/Fetch da sessão `page`; não exige `Fetch.enable`, replay ou execução de script. Pode falhar por indisponibilidade/expulsão do corpo, impondo recusa. |

As semânticas acima constam das definições oficiais de [Network](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Network.pdl), [Target](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Target.pdl) e [Browser](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Browser.pdl).

A lista fechada, portanto, **basta para obter corpos XHR**, mas **não basta para todas as provas prometidas**. A matriz tampouco está determinada integralmente a ponto de dispensar escolhas normativas ou pressupostos adicionais.

**Contrato, estados e procedência**

O desenho da §2.10 é aditivo e compatível com `docs/CONTRATO.md`: mantém strings em `fontes_indisponiveis`, acrescenta objetos em campos novos e preserva motivo/categoria. Isso também respeita `_falhas_de_fonte` e `_status_com_falhas`, em [service.py:471](/C:/dev/fv14-0089/freoa_verifica/service.py:471). A indicação não deve substituir a indisponibilidade original.

As §§2.6 e 2.13 preservam corretamente:

- requisitos de identidade, âncora e confronto para `verified`, conforme 0001;
- janela de 30 dias da 0002, sem transformar captura recente em prova histórica;
- abstenções históricas da 0075;
- `procedencia:sessao_assistida` na obtenção e `procedencia:snapshot` após instalação, conservando `modalidade_acesso`;
- separação de cobertura assistida e automática;
- distinção da 0088 entre obra, expressão e exemplar, sem equiparar `Current` a vigência.

A 0083 não sana B1: seu recorte trata de recibo gravado adulterado, enquanto o problema aqui nasce da aquisição permitida pelo adaptador. A própria v4 corretamente não a invoca como dispensa.

A emenda à 0060 também precisa conservar a distinção “não examinado” versus “sem desafio”: respostas não candidatas podem ser simplesmente recusadas, mas não classificadas como livres de desafio por ausência de exame.

**Suficiência do aceite da §3**

Não há prova executada nesta auditoria. Avalio abaixo se os critérios propostos bastam para produzir essa prova.

| Item | Avaliação |
|---|---|
| 1 | **Parcial.** Acrescentar B1, corpo indisponível, confronto final de comprimentos, cabeçalho parcial e limites completos de fila/memória. |
| 2 | **Adequado no escopo**, após fechar B3. Separar resposta final após 103 de recurso iniciado por Early Hints; não exigir recusa indiscriminada da primeira. |
| 3 | **Parcial.** Acrescentar conflitos do vínculo surgidos depois de B e identificação do quadro principal. |
| 4 | **Adequado**, incluindo descarte dos dependentes de documento não selecionado. |
| 5 | **Adequado no enunciado**, devendo exercitar extras antes/depois e mudança de origem na cadeia. |
| 6 | **Parcial.** Resolver R9 e definir, por cenário, qual conteúdo é recusado e qual é documento público preservado. |
| 7 | **Adequado**, condicionado a Chrome/Edge e versões efetivamente suportados. |
| 8 | **Insuficiente para B2.** Incluir extensão declarativa sem background/service worker e instalação tardia. |
| 9 | **Parcial.** Conferir sequência de prontidão, parâmetros efetivos e liberação dos alvos, além dos nomes dos métodos. |
| 10 | **Adequado.** |
| 11 | **Parcial.** Exigir regressões nos caminhos finais da 0075, inclusive `verificar_texto` e `obter_dispositivo`, com histórico e juízo pendente. |
| 12 | **Adequado.** Conferir que snapshot muda procedência para `snapshot` e preserva modalidade. |
| 13 | **Parcial.** Acrescentar prova de ausência de leitura do perfil pessoal, exigência expressa da 0067. |
| 14 | **Adequado.** Incluir ausência de barreira registrada, barreira expirada e 401. |
| 15 | **Parcial.** Depende de substituir as reticências por padrão integral. |
| 16 | **Complementar.** Os testes existentes não provaram pipe, inventário de extensões nem identidade dos bytes textuais. |

Falta ainda exigir expressamente o teste de instalação anunciado na §2.14, verificando a disponibilidade de `fv sessao`.

A exceção ao teto está registrada e foi respeitada. Pelas condições da própria v4, os bloqueadores desta rodada encerram a especificação na forma atual e devolvem a questão ao titular; este parecer não propõe rodada 5.

BLOQUEADOR