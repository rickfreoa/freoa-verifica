Auditei `release/1.3.0`, HEAD **`06161a5ed30111b05a50507e27223a04c11eb3b2`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado. **As reproduções originais de F-04, F-06 e F-07 passaram, mas encontrei quatro bloqueadores, incluindo uma variante remanescente de F-06.**

| ID | Severidade | Item | Arquivo:linha | Prova nesta rodada | Correção |
|---|---|---|---|---|---|
| F-01 | Anterior — corrigido | Interrupção depois de resposta iniciada | [transport.py:953](C:/dev/wt/INT/freoa_verifica/transport.py:953) | Chunk parcial, cabeçalhos completos sem corpo e prazo externo produziram `RespostaInvalida`/`resposta_inesperada`. | Nenhuma adicional nesses casos. |
| F-02 | Anterior — corrigido | Repetição aninhada no Planalto | [planalto.py:269](C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:269) | 503 persistente: **3 pedidos, 1 incremento** no breaker. `Retry-After:3600`: **1 pedido**. | Nenhuma adicional nesse caminho. |
| F-03 | Anterior — corrigido | Pendências omitidas do manifesto | [bateria.py:269](C:/dev/wt/INT/freoa_verifica/bateria.py:269) | Manifesto preserva `origem.pendencias`; comparação estrita e separação pós-instalação passaram. | Nenhuma adicional. |
| F-04 | Anterior — corrigido na reprodução | Alterador recém-falhado retomado imediatamente | [semente.py:354](C:/dev/wt/INT/freoa_verifica/semente.py:354) | Primeira falha durante `run`: 503 persistente fez **3 pedidos/1 incremento**; Retry-After longo fez **1/1**. Caminho original também passou para 429 e baixa taxa após 200. | A proteção ainda precisa alcançar os auxiliares identificados em **F-08**. |
| F-05 | Anterior — corrigido na CVM | Representações alternativas depois de falha | [cvm_normas.py:210](C:/dev/wt/INT/freoa_verifica/connectors/cvm_normas.py:210) | Testes específicos passaram: desafio, recusa, indisponibilidade esgotada e resposta inválida interrompem; 404/410 permitem outra representação. | Nenhuma adicional nesse conector. |
| **F-06** | **BLOQUEADOR — correção parcial** | Redirecionamento apaga o progresso da resposta | [transport.py:738](C:/dev/wt/INT/freoa_verifica/transport.py:738), [transport.py:960](C:/dev/wt/INT/freoa_verifica/transport.py:960) | Cabeçalhos incompletos e status cortado agora fazem **1 pedido**, sem espera, e o hook mantém falha. Entretanto, servidor local com **302 `/start` → `/target`**, seguido de fechamento sem bytes no destino, gerou **`/start,/target` três vezes**, `fonte_fora`; o hook real converteu em **`skipped/wasxfail`**. O status recebido anteriormente desapareceu da classificação. | Preservar progresso e evidência da cadeia durante a chamada lógica; impedir que o redirecionamento reinicie a condição “nenhuma resposta recebida”. Acrescentar regressão com esse servidor. |
| F-07 | Anterior — corrigido | BCB escondia falha da busca consultando conteúdo | [bcb.py:238](C:/dev/wt/INT/freoa_verifica/connectors/bcb.py:238) | `resolve → fetch`, transporte real e servidor local: CAPTCHA, 403, 503 com Retry-After longo e JSON inválido fizeram **1 pedido**, preservando categoria. Busca vazia estruturada e 404 permitiram o fallback. | Nenhuma adicional nesse caminho. |
| **F-08** | **ALTO — bloqueador** | Outros caminhos da semente repetem a mesma falha | [semente.py:408](C:/dev/wt/INT/freoa_verifica/semente.py:408), [semente.py:599](C:/dev/wt/INT/freoa_verifica/semente.py:599), [semente.py:605](C:/dev/wt/INT/freoa_verifica/semente.py:605) | Duas reproduções em uma única execução de `run`: **(a)** duas obras principais consultam a data do mesmo alterador no Senado; **(b)** a mesma norma BCB aparece em “específicas” e “recentes”. Cada cenário, com servidor local respondendo **503 + `Retry-After:3600`**, fez **2 pedidos e 2 incrementos** no breaker. `_failed` é preenchido, mas esses caminhos não o consultam. | Aplicar a proteção por chave antes das consultas auxiliares e capturas BCB, compartilhada durante toda a execução. Testar sobreposição entre contextos/listas. |
| **F-09** | **ALTO — bloqueador de FIX7c** | Histórico das fontes desaparece em saídas de erro | [service.py:903](C:/dev/wt/INT/freoa_verifica/service.py:903), [service.py:2028](C:/dev/wt/INT/freoa_verifica/service.py:2028) | Planalto `recusa_identificado` e Senado `fonte_fora` resultaram, pela API pública, em `identity={status:"unavailable", reason_code:"planalto:http_403;senado:http_503", evidence:[]}`: **sem categorias nem `fontes_consultadas`**. TJSP com CAPTCHA seguido de `ValueError` no DataJud retornou apenas `motivo:"ValueError"`, perdendo a falha anterior. | Transportar a lista estruturada também nas exceções e respostas malsucedidas; preservar falhas anteriores quando o próximo conector apresenta erro de programação/parse. |
| **F-10** | **ALTO — bloqueador** | Confirmação CNJ baixa novamente o documento e engole desafio | [service.py:1998](C:/dev/wt/INT/freoa_verifica/service.py:1998), [service.py:2004](C:/dev/wt/INT/freoa_verifica/service.py:2004), [service.py:2634](C:/dev/wt/INT/freoa_verifica/service.py:2634) | Busca/parser controlados, transporte TJSP real e servidor local: primeiro download **200**, segundo download da **mesma URL → CAPTCHA/403**. A falha foi engolida por `_index_candidate_juris`; com um candidato, seguiu ao DataJud e retornou `nao_confirmado_no_acervo` **sem declarar o desafio**. Com dois candidatos, fez ainda um **terceiro pedido ao TJSP depois do CAPTCHA**. | Reutilizar `captured_response=response`, já suportado pelo indexador. Propagar `Unavailable` para o controlador da cadeia, interrompendo a mesma fonte e registrando a falha antes de eventual fonte distinta. |

| Achado | Estado |
|---|---|
| **B3-01** | **Parcialmente corrigido:** reproduções originais passaram; cadeia de redirecionamento mantém **F-06**. |
| **B3-02** | **Corrigido:** CLI efetiva herdou o recorte; mudança de data dentro do mês produziu `data_fora_do_recorte`, exit **1**. |
| **B3-03** | **Corrigido nas reproduções:** banco, blob e destino interno recusados antes da abertura; aliases por realpath/inode também recusados com metadados simulados. Links físicos: **NOT RUN**. |
| **B3-04** | **Corrigido:** captura sem bytes reprova; `--sem-blobs` produz `parcial`; conferência dos blobs instalados passou. |
| **B3-05** | **Resolvido pela 0048 revista:** identidade única, Planalto sem exceção, conexão sem resposta reclassificada como `recusa_identificado`; nenhum UA de navegador remanescente no código pesquisado. |
| **B3-06** | **Corrigido:** mutante `999<CNJ>999`, incluindo indexação e `obter_decisao`, retornou `parte_indisponivel`/`integra_processo_divergente`. |
| **B3-07** | **Corrigido:** negativos com `itens[0].ementa = 42` e `null` foram rejeitados. |

**A 0058 revista é compatível com as invariáveis 2 e 3:** consultar outro órgão oficial, com identidade própria e proveniência correta, não exige superar o controle da fonte anterior. A falha anterior precisa continuar declarada. Isso preserva a distinção exigida por F-05/F-07 entre outra fonte e outra rota da mesma fonte. **F-09 e F-10 demonstram que a implementação ainda não satisfaz essas condições.**

Na varredura dos caminhos de recuperação/repetição:

| Caminho examinado | Resultado |
|---|---|
| Planalto `fetch:269`; CVM Normas `fetch:210`; BCB `resolve:238`; CVM Colegiado `_sync_year:213` | Fallback condicionado à ausência explícita nos caminhos inspecionados. |
| TJSP `search:153/173`; Senado `search:156 → fetch:188` | Etapas sequenciais; falha propagada antes da próxima etapa. |
| STF, TCU, DataJud e laços de recursos STJ | Não reproduzi nova tentativa da mesma requisição falhada nesses caminhos; paginação e processamento de recursos distintos não foram tratados como repetição por si. |
| Serviço `_capture_work:860` | Fontes distintas e ordem deduplicada; preservação do histórico incompleta — **F-09**. |
| Serviço `_confirm_cnj:1997` e indexador `:2532` | Download duplicado e falha engolida — **F-10**. |
| Semente `_index_legis:237` e retomada `:354` | Proteção original funciona; auxiliares e sobreposição BCB escapam — **F-08**. |

**T1/T2 passaram nos testes específicos** de UA, 502/503/504 sem desafio, conexão sem resposta, POST condicionado à idempotência, 403/429/desafio sem repetição, Retry-After dentro do orçamento e breaker por falha lógica. A garantia global permanece quebrada pelos achados acima.

**FIX4 passou:** `conteudo`/`origem`, pendências, manifesto antigo, `--pos-instalacao`, recusa com `sync_state` presente e detecção de conteúdo divergente.

**Versão e snapshot conferem.** Pyproject, `__version__`, instalador e CHANGELOG indicam **1.3.0**. O arquivo solicitado tem **665.335.352 bytes** e SHA-256:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei os **2.075 membros** com `tarfile`: **2.069 blobs**, banco de distribuição `.db` e `.db.gz`, `verifica.sqlite3`, `MANIFEST.json`, `MANIFEST.sha256` e `SHA256SUMS`. Sem duplicatas, links, caminhos perigosos, `registro.key`, `instalacao.json` ou membros fora desse inventário.

O vínculo efetivo aceitou o digest em **1.3.0** e recusou-o em **1.2.0 e 1.4.0**. Os quatro logs do supervisor são coerentes com o artefato. Reexecutei a bateria estrita no home instalado, com SQLite somente leitura, `immutable=1` e temporários em memória: **44.780 decisões, 826 obras, 2.069 blobs íntegros, zero `sync_state`, nenhuma falha**.

**Distribuição conforme 0050/0051 por inspeção e testes específicos:** release em rascunho, auditoria dos bytes antes de publicar, PyPI após `release: published` e attestation obrigatória no instalador, salvo opção explícita `-SemAttestation`. CI remota, instalação completa e verificação real de attestation: **NOT RUN**. A auditoria dos futuros assets da CI continua pertencendo ao passo 6.

As duas seleções pytest tiveram **120 testes aprovados**. Cinco testes do instalador não chegaram à execução por exigirem temporários graváveis. As demais reproduções usaram SQLite/blobs em memória e servidores locais; os 13 casos existentes de FIX7c também passaram com preparação em memória. Suíte completa e fontes oficiais ao vivo: **NOT RUN**. Na varredura do diff, não reproduzi `verified` indevido ou vazamento; isso não elimina os bloqueadores demonstrados.

PARECER: COM BLOQUEADOR — IDs: F-06, F-08, F-09, F-10