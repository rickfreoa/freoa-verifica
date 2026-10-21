Auditei `release/1.3.0`, HEAD **`90ab3b38defdc8c02a39e52eff29f1a91052f029`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado.

**F-19, F-22 e F-23 passaram nas reproduções originais e nas variantes exercitadas. Há um novo bloqueador de release: o snapshot congelado não pode ser reconstruído pela candidata atual, embora continue marcado como compatível.**

| ID | Severidade | Item | Arquivo:linha | Prova | Correção |
|---|---|---|---|---|---|
| F-19 | Alta — corrigido nos casos exercitados | Validação antes de BOM/MIME/status | [texto_resposta.py:441](C:/dev/wt/INT/freoa_verifica/texto_resposta.py:441) | BOM com `charset*`, continuação, charset divergente e PDF com CAPTCHA UTF-16 agora são recusados ou classificados como desafio. Em 503 inválido, não houve repetição interna. O hook efetivo manteve `failed`, sem `wasxfail`. | Nenhuma adicional demonstrada nesses casos. |
| F-22 | Alta — corrigido para novas capturas | Persistência e reprodução da interpretação | [service.py:802](C:/dev/wt/INT/freoa_verifica/service.py:802), [repo.py:21](C:/dev/wt/INT/freoa_verifica/store/repo.py:21) | Transporte e subprocesso de parse reais, SQLite/blobs em memória: header UTF-8 entre aspas venceu meta Latin-1; reprocessamento preservou **“Ação”**, com `reprocessados:1`, `falhas:[]`. Também passaram UTF-8 por meta e cp1252 pelo header. | O artefato legado continua pendente em F-24. |
| F-23 | Alta — corrigido nos casos exercitados | Ressincronização CVM/BCB | [situacao.py:240](C:/dev/wt/INT/freoa_verifica/situacao.py:240) | Duas obras por fonte: CAPTCHA/403 fizeram **um pedido**; 503 fez **três tentativas da mesma URL**. Segunda obra não consultada; retorno `indisponivel`, com categoria/evidência. Charset inválido e UTF-8 inválido também interromperam ambas as fontes. | Nenhuma adicional demonstrada nesses casos. |
| **F-24** | **Alta — bloqueador** | Snapshot incompatível com a releitura atual, aceito como compatível | [service.py:812](C:/dev/wt/INT/freoa_verifica/service.py:812), [derivados.py:24](C:/dev/wt/INT/freoa_verifica/derivados.py:24), [snapshot.py:1035](C:/dev/wt/INT/freoa_verifica/snapshot.py:1035) | No banco real do tar: **423 capturas BCB + 299 CVM + 121 Planalto**, com modelo e `headers_json={}`, sem as colunas da migração 014. Após migração em memória, o reprocessamento efetivo retornou **0 reprocessados e 843 falhas `interpretacao_indisponivel`**. Entretanto, `derivados.compativel` retornou **True**, versão 4/4; a instalação pode dispensar a reconstrução. | Requalificar o snapshot sob este HEAD, usando metadados autênticos ou novas capturas; reconstruir, exportar e atualizar digest/vínculo. Ajustar o critério de compatibilidade para não certificar estes derivados como atuais. Não inventar Content-Type legado. |
| F-25 | Média — lacuna de teste | AST não demonstra fechamento universal das classes | [test_garantias_estruturais.py:175](C:/dev/wt/INT/tests/test_garantias_estruturais.py:175), [378](C:/dev/wt/INT/tests/test_garantias_estruturais.py:378), [470](C:/dev/wt/INT/tests/test_garantias_estruturais.py:470), [503](C:/dev/wt/INT/tests/test_garantias_estruturais.py:503) | Os mutantes abaixo passaram pelos quatro detectores. Não reproduzi um novo defeito operacional atual por essas lacunas. | Acrescentar negativos para os padrões demonstrados, restringir exceções e delimitar a promessa: são sentinelas sintáticas, não prova completa de fluxo de dados/controle. |
| F-20 | Baixa — persiste | Documentação contraditória | [RELEASE.md:35](C:/dev/wt/INT/docs/RELEASE.md:35) | Ainda descreve consulta à “última release”. O código seleciona exclusivamente a versão instalada. | Corrigir esse parágrafo. |

As quatro regras AST foram avaliadas individualmente. Injetei os seguintes módulos **somente em memória**, mantendo o restante da árvore:

| Regra | Padrões que escaparam | Relevância |
|---|---|---|
| **1 — rede sob guarda** | `f = transport_fetch; f(url)`; `conn.resolve(ref=...)` é dispensado como homônimo por não ter argumento posicional. | Relevante para manutenção: o alias da primitiva pode escapar da guarda. O método público de conector ainda tem proteção dinâmica própria; essa segunda lacuna não demonstra, isoladamente, uma execução desprotegida atual. |
| **2 — não engolir indisponibilidade** | Dentro do laço: `except Unavailable as exc: ignored = exc.categoria; continue`, seguido de `return {"status":"ok"}`. | Relevante: acessar a categoria não comprova registrá-la nem propagá-la. Um `raise` em ramo inexequível também satisfaz a busca sintática. |
| **3 — interpretação única** | `str(resp.body, "latin-1")`; `from codecs import decode as read_text; read_text(resp.body, "latin-1")`. | Relevante para reintrodução de interpretação divergente. `codecs.decode(...)` escrito diretamente **foi detectado**. As permissões existentes abrangem funções inteiras, não apenas linhas justificadas. |
| **4 — parser sem bytes crus** | `raw(resp)` retorna `resp.body`, depois `parse_x(raw(resp))`; ou `box=(resp.body,); parse_x(box[0])`. | Relevante: a contaminação não atravessa funções nem recipientes. O detector também exclui todo `parsers/`, cujo código já oferece APIs para bytes. |

Na árvore atual, os quatro detectores retornaram zero violações. Aplicados ao HEAD da rodada 13, `26bfb271`, acusaram **60/5/22/8** violações, respectivamente. Isso demonstra sensibilidade aos padrões anteriores; não elimina os escapes acima.

O mecanismo compartilhado de classificação resolveu as variantes exercitadas de F-19; o recibo resolveu F-22 nas novas capturas; a interrupção explícita resolveu F-23 na ressincronização. **O fechamento de F-22 não alcançou o snapshot congelado.** A deduplicação também conserva limites declarados: sessões, downloads para `sink` e expulsão do cache LRU impedem tratá-la como garantia absoluta de “uma requisição em qualquer circunstância”.

| Achado | Estado |
|---|---|
| **B3-01** | **Corrigido.** Chunk parcial e somente cabeçalhos: `resposta_inesperada`, status 200 preservado; hook manteve falha. Passaram os testes selecionados de progresso, saltos e prazo externo. |
| **B3-02** | **Corrigido.** CLI efetiva, com banco/manifesto em memória, herdou o recorte; mudança dentro do mesmo mês produziu `data_fora_do_recorte`, exit 1. |
| **B3-03** | **Corrigido nos caminhos exercitados.** Banco, blob e novo destino interno recusados antes da abertura. Criação física de symlink/hardlink: **NOT RUN**. |
| **B3-04** | **Corrigido.** Ausência dos bytes foi detectada; `--sem-blobs` retornou `parcial`. Os 2.069 blobs do tar conferiram por hash. |
| **B3-05** | **Resolvido pela 0048 revista.** Identidade única, Planalto sem exceção, falha sem resposta classificada como `recusa_identificado`. Nenhuma string de UA de navegador encontrada no código pesquisado. |
| **B3-06** | **Corrigido.** Mutante `999<CNJ>999`, indexado e consultado pelo método de obtenção, retornou `parte_indisponivel`, texto nulo e `integra_processo_divergente`. |
| **B3-07** | **Corrigido nos negativos selecionados.** Tipo/nulidade inválidos em elemento individual foram rejeitados. |

**T1/T2:** passaram os testes específicos de teto de repetição, conexão sem resposta, POST condicionado à idempotência, `Retry-After`, orçamento e breaker por falha lógica. Não reproduzi resposta iniciada sendo repetida como `fonte_fora`.

Encontrei laços fora do transporte em captura, semente, sincronização e paginação dos conectores, confirmação/pesquisa no serviço e situação. A fila de reagendamento da semente foi removida; os fallbacks Planalto/CVM consultam alternativas conforme a classificação. Não reproduzi outro laço que refizesse a mesma falha contrariando essa política.

**FIX4:** passaram, em memória, separação `conteudo`/`origem`, manifesto antigo, comparação de conteúdo divergente e recusa de `--pos-instalacao` com `sync_state`.

O snapshot tem **665.335.352 bytes**, com SHA-256:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei os **2.075 membros regulares**: 2.069 caminhos `blobs/<2>/<2>/<sha256>` e:

```text
freoa-verifica-corpus-20261020.db
freoa-verifica-corpus-20261020.db.gz
verifica.sqlite3
MANIFEST.json
MANIFEST.sha256
SHA256SUMS
```

Sem membros inesperados, duplicatas, links, travessia de caminho, `registro.key` ou `instalacao.json`. Blobs, checksums internos e hash do manifesto conferiram; os dois bancos não comprimidos são idênticos. Os quatro logs são coerentes com esses bytes, **mas não comprovam reconstrução após FIX18**.

Versões de pyproject, `__version__`, instalador e CHANGELOG conferem em 1.3.0. O vínculo aceitou o digest em 1.3.0 e recusou em 1.2.0/1.4.0. Workflows e instalador inspecionados atendem às decisões 0050/0051: rascunho, auditoria dos bytes antes da publicação, PyPI por `release: published` e attestation obrigatória, salvo exceção explícita.

**Validação:** **973 testes específicos aprovados**, em duas seleções, exit 0, além das reproduções descritas. Usei `--noconftest`, cache/captura em disco desativados e excluí 199 casos dependentes de escrita. Na varredura do diff, não reproduzi novo `verified` indevido, vazamento, HTTP alternativo ou modelo de linguagem no caminho de execução. Suíte completa, fontes oficiais ao vivo, instalação completa, wheel isolada, attestation real e futuros bytes da CI: **NOT RUN**. A bateria sobre o home instalado não abriu o SQLite neste ambiente; sua aprovação não foi inferida dos logs.

PARECER: COM BLOQUEADOR — IDs: F-24