Auditei `release/1.3.0`, HEAD **`d2e55fcadfc8fe880ee63cad226dbd851dcc921f`**, contra `239bef6`. Árvore limpa antes e depois; nenhum arquivo editado. **As reproduções originais de FIX6 passaram, mas F-04 e F-06 permanecem incompletos. Encontrei também F-07.**

| ID | Severidade | Item | Arquivo:linha | Prova | Correção |
|---|---|---|---|---|---|
| F-01 | Bloqueador anterior — corrigido | Interrupção após resposta iniciada | [transport.py:895](C:/dev/wt/INT/freoa_verifica/transport.py:895) | Chunk parcial, cabeçalhos completos sem corpo e vencimento na thread externa produziram `resposta_inesperada`. Hook manteve falha. Baixa taxa após 200 fez um pedido. | Nenhuma adicional nos casos originais; permanece a variante F-06 abaixo. |
| F-02 | Bloqueador anterior — corrigido | Repetição aninhada no Planalto | [planalto.py:269](C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:269) | Transporte e conector reais: 503 persistente → **3 pedidos, 1 incremento** no breaker; Retry-After longo → **1 pedido**. | Nenhuma adicional no caminho original. |
| F-03 | Médio anterior — corrigido | Pendências no manifesto | [bateria.py:267](C:/dev/wt/INT/freoa_verifica/bateria.py:267) | `manifesto_canonico` inclui `origem.pendencias`; comparação e reprovação estrita preservadas. | Nenhuma adicional. |
| **F-04** | **BLOQUEADOR — correção parcial** | Alterador recém-falhado é repetido na mesma sincronização | [semente.py:342](C:/dev/wt/INT/freoa_verifica/semente.py:342), [semente.py:408](C:/dev/wt/INT/freoa_verifica/semente.py:408) | O caminho original passou: **3/1/1/1 pedidos** para 503 persistente, Retry-After longo, 429 e baixa taxa após 200. Porém, `_resolve_alteradores` grava uma falha nova que a consulta posterior de pendências recolhe imediatamente. Uma única execução de `run` gerou **6 pedidos e 2 incrementos** para 503; com `Retry-After:3600`, **2 pedidos e 2 incrementos**. SQLite em memória e servidor local real; persistência do documento principal interceptada. | Retomar somente pendências existentes na entrada da execução e impedir novas tentativas da mesma chave durante essa execução, inclusive entre contextos de obras principais. Acrescentar regressão com alterador que falha pela primeira vez durante `run`. |
| F-05 | Bloqueador anterior — corrigido na CVM | Representações alternativas | [cvm_normas.py:210](C:/dev/wt/INT/freoa_verifica/connectors/cvm_normas.py:210) | CAPTCHA, 403, 503 esgotado e resposta inválida interrompem na primeira chamada; 404/410 permitem a segunda representação; quatro ausências propagam a última. | Nenhuma adicional nesse conector. A varredura da família encontrou F-07. |
| **F-06** | **BLOQUEADOR — correção parcial** | Status recebido antes de completar os cabeçalhos ainda vira ambiental | [transport.py:730](C:/dev/wt/INT/freoa_verifica/transport.py:730), [transport.py:897](C:/dev/wt/INT/freoa_verifica/transport.py:897), [transport.py:1062](C:/dev/wt/INT/freoa_verifica/transport.py:1062) | Cabeçalho de 70.000 bytes, HTTP/9.9 e excesso de cabeçalhos agora fazem **1 pedido**, sem espera, com `resposta_inesperada`. Entretanto, servidor local enviando `HTTP/1.1 200 OK` e cabeçalhos incompletos produz `transporte_Timeout` → **`fonte_fora`**. Observei o cliente efetivamente interpretar o status 200. O hook real converteu a falha em **`skipped/wasxfail`**. | Registrar progresso durante a leitura da linha de status/cabeçalhos, antes de `getresponse()` retornar. Compartilhar esse estado com o controlador externo e classificar a interrupção posterior como `RespostaInvalida`. |
| **F-07** | **ALTO — bloqueador de FIX6** | BCB engole falha da busca e continua por outro endpoint | [bcb.py:227](C:/dev/wt/INT/freoa_verifica/connectors/bcb.py:227), [bcb.py:237](C:/dev/wt/INT/freoa_verifica/connectors/bcb.py:237) | Com transporte real e servidor local, a busca respondeu, separadamente, CAPTCHA/403, 403 sem desafio e 503 com `Retry-After:3600`. Confirmei as categorias `ambiental_desafio`, `recusa_identificado` e `fonte_fora`. Em todos, `resolve → fetch` fez **2 pedidos** e retornou HTTP 200 pelo endpoint de conteúdo, ocultando a falha inicial. Não houve tentativa contra o BCB real. | Propagar essas falhas. Limitar o fallback às ausências explicitamente admitidas, conforme a disciplina exigida em FIX6, com regressão sobre `resolve → fetch`. |

| Achado | Estado |
|---|---|
| **B3-01** | **Parcialmente corrigido.** Casos originais passaram; cabeçalhos incompletos após status interpretado ainda produzem falso ambiental — **F-06**. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte; mudar a data dentro do mesmo mês produziu `data_fora_do_recorte`, exit **1**. |
| **B3-03** | **Corrigido nas reproduções.** Banco, blob e novo destino interno recusados antes da abertura. Aliases por resolução e inode também recusados com metadados simulados. Criação física de links: **NOT RUN**. |
| **B3-04** | **Corrigido.** Captura sem bytes reprova; `--sem-blobs` produz `parcial`. Os 2.069 blobs instalados foram autenticados. |
| **B3-05** | **Resolvido pela nova 0048.** Identidade única; nenhum UA de navegador remanescente no código examinado. Planalto sem resposta recebe `recusa_identificado`; HTTP 503 segue a classificação geral. |
| **B3-06** | **Corrigido.** Reexecutei o mutante `999<CNJ>999`, incluindo indexação e resposta pública: `parte_indisponivel`, motivo `integra_processo_divergente`. |
| **B3-07** | **Corrigido.** Negativos com `itens[0].ementa = 42` e `null` reprovam por elemento. |

**T1/T2 passaram nos casos específicos** de identidade, POST condicionado à idempotência, 502/503/504 sem desafio, 403/429 sem repetição, Retry-After dentro do orçamento e contabilização lógica do breaker. A garantia global continua violada por F-04, F-06 e F-07.

**FIX4 passou:** seções `conteudo`/`origem`, manifesto antigo, comparação após instalação, rejeição de `--pos-instalacao` com `sync_state` e detecção de conteúdo divergente.

**Versão e snapshot conferem.** Pyproject, `__version__`, instalador e CHANGELOG indicam 1.3.0. O arquivo solicitado tem **665.335.352 bytes** e SHA-256:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei os **2.075 membros** com `tarfile`: 2.069 blobs, banco de distribuição `.db` e `.db.gz`, `verifica.sqlite3`, `MANIFEST.json`, `MANIFEST.sha256` e `SHA256SUMS`. Sem duplicatas, links, caminhos perigosos, `registro.key`, `instalacao.json` ou membros fora desse inventário.

O vínculo efetivo aceitou o digest em **1.3.0** e recusou-o em **1.2.0 e 1.4.0**. Os quatro logs do supervisor são coerentes com o artefato. A bateria estrita sobre o acervo instalado, usando SQLite somente leitura com `immutable=1`, passou: **44.780 decisões, 826 obras, 2.069 blobs íntegros e zero `sync_state`**.

**Distribuição conforme 0050/0051 nos caminhos inspecionados e testes específicos:** release em rascunho; auditoria dos bytes antes de publicar; PyPI após `release: published`; instalador exige attestation, salvo `-SemAttestation` explícito. Execução remota, instalação completa e verificação real de attestation: **NOT RUN**. Os futuros assets da CI ainda exigem a auditoria do passo 6.

A seleção específica terminou com **171 passed, 129 deselected**, adaptando somente a preparação em memória ao regime de leitura. As reproduções diretas estão descritas acima. Suíte completa e fontes oficiais ao vivo: **NOT RUN**. Na varredura de `239bef6..HEAD`, não reproduzi `verified` indevido ou vazamento; os bloqueadores demonstrados impedem encerrar a candidata sem correção.

PARECER: COM BLOQUEADOR — IDs: F-04, F-06, F-07