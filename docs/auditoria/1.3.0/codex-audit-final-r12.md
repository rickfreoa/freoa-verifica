Auditei `release/1.3.0`, HEAD **`437505ec6d3a02c7f80cd83e50ee15b219fe8c50`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado. **F-19 foi parcialmente corrigido, mas a classe permanece aberta. Há três bloqueadores.**

| ID | Severidade | Item | Arquivo:linha | Prova reproduzida | Correção |
|---|---|---|---|---|---|
| **F-19** | **Alta — bloqueador persistente** | Declaração falsa de charset oculta desafio | [texto_resposta.py:22](/C:/dev/wt/INT/freoa_verifica/texto_resposta.py:22), [texto_resposta.py:23](/C:/dev/wt/INT/freoa_verifica/texto_resposta.py:23) | TCP real: `<meta data-charset="utf-16le"><p>CAPTCHA</p>` é interpretado como UTF-16. **200 retorna sucesso**; **503 faz três pedidos**, termina `fonte_fora` e o hook produz `skipped/wasxfail`. Duas URLs na mesma guarda: **seis pedidos, nenhum bloqueio**. Reproduzi também com comentário HTML, `charset=` dentro de outro atributo e parâmetro HTTP `x-charset`. | Reconhecer o parâmetro `charset` e os atributos HTML efetivos, respeitando seus limites e comentários. Cobrir declarações falsas pela matriz de transporte, guarda e hook. |
| **F-21** | **Alta — bloqueador novo** | Redirecionamento ignora desafio recebido | [transport.py:1133](/C:/dev/wt/INT/freoa_verifica/transport.py:1133) | **Dez variantes TCP reais:** `{301,302,303,307,308}` × `{CAPTCHA no corpo, cf-mitigated: challenge}`. Todas seguiram `/a → /b`, fizeram **dois GETs**, retornaram **200** e deixaram a guarda sem bloqueio. | Detectar desafio também nos saltos intermediários, antes de seguir `Location`; propagar a categoria e bloquear o host efetivamente desafiador. |
| **F-22** | **Alta — bloqueador novo** | Leitura de sucesso continua divergente e produz zero falso | [cvm_colegiado.py:218](/C:/dev/wt/INT/freoa_verifica/connectors/cvm_colegiado.py:218), [cvm_colegiado.py:221](/C:/dev/wt/INT/freoa_verifica/connectors/cvm_colegiado.py:221), [cvm_colegiado.py:231](/C:/dev/wt/INT/freoa_verifica/connectors/cvm_colegiado.py:231) | HTML UTF-8 com cabeçalho correto e link intitulado **“Ação”**: a função única interpreta corretamente, mas o parser recebe novamente os bytes e produz mojibake. Busca vazia encontra um candidato; busca por “Ação” encontra **zero**. Pela API pública, reproduzi **`status:"ok"`, `itens:[]`, fonte `ok`, `indisponivel:null`**. | Alimentar o parser e o filtro com o texto da interpretação única. Acrescentar regressão pela API pública com título acentuado e charset no cabeçalho. |
| F-15 | Média — persiste | Guarda atravessa execuções | [semente.py:164](/C:/dev/wt/INT/freoa_verifica/semente.py:164), [semente.py:195](/C:/dev/wt/INT/freoa_verifica/semente.py:195) | Mesma instância, duas chamadas reais a `run`: **um pedido na primeira, zero na segunda**, conservando o bloqueio. | Renovar a guarda na entrada da execução externa e compartilhá-la somente com suas chamadas aninhadas. |
| F-17 | Média — persiste; família ampliada | Diagnóstico continua após desafio, fora do transporte | [planalto.py:173](/C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:173) | Contra 403/CAPTCHA: Planalto fez **três pedidos e três incrementos** no breaker; BCB fez **três pedidos**, CVM Normas **dois**, TJDFT **dois**. | Compartilhar guarda durante o diagnóstico ou interromper as sondas após desafio/recusa. |
| F-20 | Baixa — persiste | Instrução documental contradiz 0051 | [RELEASE.md:35](/C:/dev/wt/INT/docs/RELEASE.md:35) | Ainda afirma que `snapshot install` consulta a “última release”. | Descrever a seleção exclusiva de `v<__version__>`. |

O caso mínimo de F-19, com corpo ASCII de comprimento par, é:

```html
<meta data-charset="utf-16le"><p>CAPTCHA</p>
```

Os casos originais de F-19 passaram: **135 testes**, mais verificações diretas do hook para charset desconhecido/bytes inválidos e nove variantes adicionais de BOM, status e normalização. Isso comprova a correção desses casos, mas não elimina as variantes acima.

| Achado | Estado nesta auditoria |
|---|---|
| **B3-01** | **Corrigido nas reproduções originais e variantes de progresso.** Chunk parcial, somente cabeçalhos, prazo externo, saltos e falhas de protocolo preservaram `resposta_inesperada`; o hook manteve falha. F-19/F-21 impedem aprovar globalmente a detecção de desafio. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte; mover a decisão para outro dia do mesmo mês produziu `data_fora_do_recorte`, exit **1**. |
| **B3-03** | **Corrigido nos casos exercitados.** Banco, blob e destino interno recusados antes da abertura; aliases por realpath/inode também recusados com metadados simulados. Links físicos: **NOT RUN**. |
| **B3-04** | **Corrigido.** Blob ausente reprova; `--sem-blobs` produz `parcial`. Conferência dos 2.069 blobs instalados passou. |
| **B3-05** | **Resolvido pela 0048 revista.** Planalto sem exceção; falha anterior à resposta recebe `recusa_identificado`. Nenhum UA de navegador encontrado no código pesquisado. |
| **B3-06** | **Corrigido.** Mutante `999<CNJ>999`, com indexação e `obter_decisao`, retornou `parte_indisponivel`, texto nulo e `integra_processo_divergente`. |
| **B3-07** | **Corrigido.** Quinze mutantes de tipo/nulidade, nos três adaptadores congelados, foram rejeitados. |

**T1/T2:** passaram identidade única, limites de repetição, POST condicionado à idempotência, `Retry-After`, orçamento e breaker por falha lógica. As regressões de framing, chunks, cache, entrada atual e `Content-Encoding` passaram. Principal/alteradora nas duas ordens passaram; uma ata CVM com três itens fez **um GET** e indexou as três decisões corretamente. A classe continua aberta pelos bloqueadores acima. O diagnóstico permanece um caminho de repetição fora do transporte, conforme F-17.

**FIX4:** passaram separação `conteudo`/`origem`, manifesto antigo, rejeição de `--pos-instalacao` com `sync_state`, comparação após instalação e detecção de conteúdo divergente. A bateria estrita do instalado, com SQLite `mode=ro&immutable=1`, encontrou **44.780 decisões, 826 obras, derivados 4, zero `sync_state` e nenhuma falha**.

O snapshot tem **665.335.352 bytes** e SHA-256 recalculado:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei com `tarfile` os **2.075 membros**: 2.069 blobs, os bancos/representações esperados, `MANIFEST.json`, `MANIFEST.sha256` e `SHA256SUMS`. Sem membros inesperados, duplicatas, links, caminhos perigosos, `registro.key` ou `instalacao.json`. Os quatro logs do supervisor são coerentes com o artefato. O vínculo aceitou o digest em **1.3.0** e recusou em **1.2.0 e 1.4.0**.

Pyproject, `__version__`, instalador e CHANGELOG indicam **1.3.0**. Workflows e instalador atendem aos caminhos inspecionados das decisões 0050/0051: rascunho, auditoria dos bytes antes da publicação, PyPI por `release: published` e attestation obrigatória, salvo `-SemAttestation` explícito. Assets futuros da CI e attestation real: **NOT RUN**.

A varredura das decodificações residuais encontrou:

| Ocorrências | Avaliação |
|---|---|
| `bcb.py:171,293`; `datajud.py:156,192`; `senado.py:166,213,293`; `stf.py:197,288`; `stj.py:195,230,392,401,549`; `tcu.py:186,266`; `tjdft.py:368` | Leitura de JSON, com contrato UTF-8 próprio. |
| `stj.py:697` | CSV explicitamente UTF-8 com BOM. |
| `cvm_colegiado.py:270,309,315`; `cvm_normas.py:334,336`; `stf.py:368` | Parsers mantêm interpretações independentes. A exceção registrada na 0061 não comprova equivalência; **F-22 demonstra a consequência na leitura de sucesso**. |
| `service.py:2895` | Exibição de captura já armazenada, com fallback UTF-8/Latin-1; continua fora da função única e não preserva necessariamente a interpretação original. |

Na varredura de `239bef6..HEAD`, não reproduzi promoção indevida a `verified`, vazamento, transporte HTTP alternativo ou modelo de linguagem no caminho de execução. Reproduzi o zero falso de F-22. `git diff --check` apontou 440 ocorrências de whitespace em `FIXTURES.json`, sem bloqueador funcional adicional demonstrado.

As quatro seleções específicas concluídas tiveram **794 aprovados** — `135 + 482 + 100 + 77`, todas com exit **0**. Tentativas anteriores tiveram erros de preparação por temporários negados ou fixtures indisponíveis; não foram contabilizadas como aprovação. As adaptações somente leitura usaram preparação em memória e estão delimitadas acima. Suíte completa, fontes oficiais ao vivo, instalação completa e CI remota: **NOT RUN**, conforme o escopo solicitado.

PARECER: COM BLOQUEADOR — IDs: F-19, F-21, F-22