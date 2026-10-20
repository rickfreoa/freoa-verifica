Auditei `release/1.3.0`, HEAD **`cf66c09ef94a6c0ec404a2d0d35892ccbc8a44c6`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado. **F-11 foi corrigido nas reproduções; F-13 e F-16 continuam bloqueadores por novas variantes das mesmas classes.**

| ID | Severidade | Item | Arquivo:linha | Prova nesta rodada | Correção |
|---|---|---|---|---|---|
| F-11 | Corrigido nos casos exercitados | Guarda registra o desfecho final | [httputil.py:43](C:/dev/wt/INT/freoa_verifica/connectors/httputil.py:43), [guarda.py:121](C:/dev/wt/INT/freoa_verifica/connectors/guarda.py:121) | Servidor TCP encerrando sem resposta: primeira lei fez **3 pedidos**, terminou em `recusa_identificado_planalto` e bloqueou o host. Duas leis seguintes fizeram **zero pedidos adicionais**; breaker permaneceu em **1**. Passaram também bloqueio do host redirecionado, ata CVM compartilhada entre três itens e interrupção após CAPTCHA. | Nenhuma adicional nesses casos. |
| **F-13** | **ALTO — bloqueador; correção parcial** | Parser tolerante ainda transforma resposta malformada em falha ambiental repetível | [transport.py:279](C:/dev/wt/INT/freoa_verifica/transport.py:279), [transport.py:266](C:/dev/wt/INT/freoa_verifica/transport.py:266) | Os framings anteriores foram corrigidos. Novas variantes TCP reais: `Content-Length : 100`, `Transfer-Encoding : chunked`, cabeçalho sem `:` antes do comprimento e trailer sem `:`. Em **200**, foram aceitas; em **503**, cada uma fez **3 pedidos** e terminou em `fonte_fora`. O hook efetivo converteu a reprodução em **`skipped/wasxfail=fonte_fora:http_503`**. | Rejeitar defeitos de parsing dos cabeçalhos e validar a sintaxe dos trailers. Cabeçalhos descartados pelo parser não podem equivaler a cabeçalhos ausentes válidos. Propagar como `RespostaInvalida`, sem repetição. |
| **F-16** | **ALTO — bloqueador; correção parcial** | Cache valida a URL armazenada, dispensando a URL atual | [httputil.py:82](C:/dev/wt/INT/freoa_verifica/connectors/httputil.py:82), [transport.py:559](C:/dev/wt/INT/freoa_verifica/transport.py:559) | Os controles originais de host, caminho, MIME e tamanho passaram. Contudo, após capturar `https://example.com/x`, o cache aceitou `/x#fragment`, `https://user:secret@example.com/x`, `https://example.com:bad/x` e `/%78` sob prefixo restrito a `/x`. **Sem cache, as quatro chamadas foram recusadas por `BlockedHost`**. Com cache, receberam a captura, sem novo pedido. | Validar a **URL solicitada nesta chamada** antes do reaproveitamento, além da cadeia armazenada. A canonicalização da chave não substitui a validação da entrada. |
| F-15 | MÉDIO — persiste | Guarda permanece entre execuções | [semente.py:195](C:/dev/wt/INT/freoa_verifica/semente.py:195), [semente.py:1013](C:/dev/wt/INT/freoa_verifica/semente.py:1013) | Mesma instância, duas chamadas reais a `run`: primeira fez **1 pedido/CAPTCHA**; segunda fez **zero pedidos**, embora o servidor estivesse preparado para 200. O bloqueio anterior permaneceu. | Renovar a guarda na entrada de cada execução externa, compartilhando-a somente com suas chamadas aninhadas. |
| F-17 | MÉDIO — novo, fora da sincronização | Diagnóstico repete pedidos após desafio | [planalto.py:173](C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:173) | `PlanaltoConnector.health()` contra servidor com 403/CAPTCHA fez **3 GETs**, incluindo a mesma URL positiva duas vezes, e **3 incrementos** no breaker. As três sondas continuam após o primeiro desafio. | Compartilhar guarda durante o diagnóstico ou interromper as sondas da fonte após desafio/recusa, declarando as restantes não executadas. |

F-16 demonstra dispensa indevida de controles de aceitação. **Não foi demonstrada promoção indevida a `verified`.**

| Achado | Estado |
|---|---|
| **B3-01** | **Parcialmente corrigido.** Passaram timeout após chunk parcial, cabeçalhos recebidos, progresso entre saltos e controlador externo. Persiste a classificação ambiental indevida de **F-13**. |
| **B3-02** | **Corrigido.** CLI efetiva herdou `2026-02-05..2026-02-20`; mover a decisão para `2026-02-01` produziu `data_fora_do_recorte`, exit **1**, preservando a contagem mensal. |
| **B3-03** | **Corrigido nas reproduções.** Banco, blob e destino interno recusados antes da abertura; aliases simulados por realpath e inode também recusados. Criação física de links: **NOT RUN**. |
| **B3-04** | **Corrigido.** Blob ausente reprova; `--sem-blobs` retorna `parcial`; os **2.069 blobs** do acervo instalado conferiram. |
| **B3-05** | **Resolvido pela 0048 revista.** Planalto sem exceção; falha sem resposta vira `recusa_identificado`. UA identificado de fonte única; nenhum UA de navegador encontrado no código pesquisado. |
| **B3-06** | **Corrigido.** Mutante `999<CNJ>999`, passando pela indexação e por `obter_decisao`, retornou `parte_indisponivel`/`integra_processo_divergente`. |
| **B3-07** | **Corrigido.** Alterar somente `itens[0].ementa` para `42` ou `null` produziu incompatibilidade de tipo por elemento. |

**T1/T2:** passaram os testes específicos de 502/503/504, conexão sem resposta, POST condicionado à idempotência, `Retry-After` dentro do orçamento, 403/429/desafio sem repetição e breaker por falha lógica. **F-13 impede afirmar fechamento global da classificação.**

Na varredura dos demais caminhos, passaram fallback BCB e representações alternativas da CVM Normas. As reproduções da pesquisa textual também passaram: desafio declarado, captura compartilhada e guarda renovada entre pesquisas. O diagnóstico de saúde revelou **F-17**.

**FIX4 passou:** separação `conteudo`/`origem`, manifesto antigo, divergência de conteúdo e recusa de `--pos-instalacao` quando há `sync_state`. Reexecutei a bateria estrita em `C:\dev\fv-home-vinc`, com SQLite somente leitura e `immutable=1`: **44.780 decisões, 826 obras, 2.069 blobs íntegros, zero `sync_state`, nenhuma falha**.

**Versão e snapshot conferem.** Pyproject, `__version__`, instalador e CHANGELOG indicam **1.3.0**. Recalculei o SHA-256 do arquivo de **665.335.352 bytes**:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei os **2.075 membros**: 2.069 blobs, os bancos `.db`, `.db.gz` e `verifica.sqlite3`, `MANIFEST.json`, `MANIFEST.sha256` e `SHA256SUMS`. Sem duplicatas, links, caminhos perigosos, `registro.key`, `instalacao.json` ou membros inesperados. Os quatro logs são coerentes com o artefato. O vínculo efetivo aceitou o digest em **1.3.0** e recusou em **1.2.0 e 1.4.0**.

**Distribuição conforme 0050/0051 por inspeção e testes específicos:** release em rascunho, auditoria dos bytes antes de publicar, PyPI por `release: published` e attestation obrigatória no instalador, salvo `-SemAttestation` explícito. Execução remota, instalação completa e verificação real da attestation: **NOT RUN**; os futuros assets continuam sujeitos ao passo 6.

Foram **310 testes específicos aprovados**, além das reproduções dirigidas com servidores locais e armazenamento em memória. Na seleção principal, 39 casos dependentes de escrita foram excluídos. Suíte completa, wheel isolada e fontes oficiais ao vivo: **NOT RUN**. Na varredura do diff, não demonstrado vazamento, HTTP alternativo ou modelo de linguagem no caminho de execução.

PARECER: COM BLOQUEADOR — IDs: F-13, F-16