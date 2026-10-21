Auditei **`release/1.3.0`**, HEAD **`8b7558d8bb2551ce90d042f408898ade2d1e27b3`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado. **As reproduções originais de F-19, F-22 e F-23 passaram, mas novas variantes demonstraram que as três classes permanecem abertas.**

| ID | Severidade | Item | Arquivo:linha | Prova reproduzida | Correção |
|---|---|---|---|---|---|
| **F-19** | **Alta — bloqueador persistente** | Validação de charset é pulada com BOM ou MIME binário | [texto_resposta.py:412](C:/dev/wt/INT/freoa_verifica/texto_resposta.py:412), [texto_resposta.py:417](C:/dev/wt/INT/freoa_verifica/texto_resposta.py:417) | TCP real: BOM UTF-8 com `charset*=x` ou `charset=utf-8; charset=utf-16` foi aceito em 200. Em 503, duas URLs fizeram **seis pedidos**, sem bloqueio; hook efetivo produziu **`skipped/wasxfail=fonte_fora:http_503`**. Também reproduzi com `application/pdf; charset*=x` e corpo UTF-16 com CAPTCHA: sucesso em 200 e seis pedidos em 503. | Validar os parâmetros proibidos e duplicados **antes** dos desvios por MIME/BOM. O BOM pode decidir a codificação, mas não dispensar a validação exigida pela FIX17/0063. |
| **F-22** | **Alta — bloqueador persistente** | Persistência perde a interpretação; reprocessamento corrompe o texto silenciosamente | [transport.py:180](C:/dev/wt/INT/freoa_verifica/transport.py:180), [service.py:774](C:/dev/wt/INT/freoa_verifica/service.py:774), [planalto.py:290](C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:290) | Transporte, persistência e subprocesso reais, SQLite/blobs em memória: `charset="utf-8"` com meta Latin-1 divergente produziu **“Ação”** inicialmente. O recibo descartou o Content-Type. `reprocessar_capturas` devolveu **`reprocessados:1`, `falhas:[]`**, substituindo o modelo por **“AÃ§Ã£o”**, sem issues. | Persistir os dados necessários para reproduzir a interpretação original e utilizá-los na releitura. Cobrir captura → persistência → reprocessamento → modelo, inclusive charset entre aspas. |
| **F-23** | **Alta — bloqueador persistente** | Ressincronização de situação engole indisponibilidade, continua e retorna sucesso | [situacao.py:183](C:/dev/wt/INT/freoa_verifica/situacao.py:183), [situacao.py:217](C:/dev/wt/INT/freoa_verifica/situacao.py:217), [situacao.py:238](C:/dev/wt/INT/freoa_verifica/situacao.py:238) | Entrada pública `ressincronizar_situacao`, conector/transporte reais e duas obras CVM: CAPTCHA ou 403 simples → **um pedido**, mas retorno **`status:"ok"`, `lidas:2`, `ilegiveis:2`**, sem categoria/evidência. Com 503 sem desafio → **seis pedidos**, mesmo retorno. É outro controlador que continua a fonte após falha. | Propagar a indisponibilidade estruturada, interromper os itens restantes daquela fonte e declarar resultado parcial/indisponível. Aplicar também ao caminho BCB e à reconstrução com situação. |
| F-20 | Baixa — persiste | Documentação contradiz a seleção por versão | [RELEASE.md:35](C:/dev/wt/INT/docs/RELEASE.md:35) | Ainda afirma que `snapshot install` consulta a “última release”. | Descrever a seleção exclusiva de `v<__version__>`. |

A tabela de controladores do relatório FIX17 **não comprova o fechamento anunciado**: sua linha de `ressincronizar_situacao` registra apenas a guarda, deixando propagação e declaração “sem mudança”. A reprodução acima demonstra a lacuna. O inventário de parsers também não resolve a releitura: a perda do Content-Type foi declarada como limitação pelo desenvolvedor e permanece efetiva.

| Achado | Estado nesta auditoria |
|---|---|
| **B3-01** | **Corrigido nas reproduções originais.** Chunk parcial e somente cabeçalhos produziram `resposta_inesperada`, com status 200 preservado; o hook manteve falha. Passaram regressões de progresso, protocolo, saltos e prazo externo. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte; mover a decisão dentro do mesmo mês produziu `data_fora_do_recorte`, exit **1**. |
| **B3-03** | **Corrigido nos casos exercitados.** Banco, blob e novo destino interno foram recusados antes da abertura. Aliases por realpath/inode simulados também foram recusados. Links físicos: **NOT RUN**. |
| **B3-04** | **Corrigido.** Blob ausente reprova; `--sem-blobs` retorna `parcial`. Os **2.069 blobs** instalados conferiram. |
| **B3-05** | **Resolvido pela 0048 revista.** Planalto sem exceção, identidade única, falha sem resposta → `recusa_identificado`. Nenhum UA de navegador encontrado no código pesquisado. |
| **B3-06** | **Corrigido.** Mutante `999<CNJ>999`, indexado e consultado por `obter_decisao`, retornou `parte_indisponivel`, texto nulo e `integra_processo_divergente`. |
| **B3-07** | **Corrigido.** Quinze mutantes de tipo/nulidade, nos três adaptadores congelados, foram rejeitados. |

**T1/T2:** passaram teto de repetição, conexão sem resposta, POST condicionado à idempotência, `Retry-After`, orçamento e breaker por falha lógica. A semente passou nas reproduções de 503, 429, prazo/baixa taxa e `Retry-After` longo. Principal/alteradora nas duas ordens reutilizaram a requisição; ata com três itens usou um GET. **F-15 foi corrigido:** duas chamadas reais a `run`, na mesma instância, fizeram um pedido cada. **F-17 passou** nos diagnósticos diretos dos conectores. Persistem as variantes de F-19 e o controlador de F-23.

**FIX4 e snapshot:** passaram seções `conteudo`/`origem`, manifesto antigo, divergência de conteúdo e recusa de `--pos-instalacao` com `sync_state`. A bateria estrita do instalado retornou **44.780 decisões, 826 obras, derivados 4, 2.069 blobs verificados e zero falhas**, com `origem:"nao_aplicavel_pos_instalacao"`.

Recalculei o arquivo de **665.335.352 bytes**:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

O tar contém **2.075 arquivos regulares**: 2.069 blobs, três bancos/representações e três manifestos/checksums. Sem duplicatas, links, caminhos perigosos, membros inesperados, `registro.key` ou `instalacao.json`. Os quatro logs são coerentes com o artefato. A lista embutida contém a entrada 1.3.0; o vínculo aceitou esse digest em **1.3.0** e recusou em **1.2.0 e 1.4.0**.

Versões em pyproject, `__version__`, instalador e CHANGELOG estão coerentes. Workflows e instalador atendem aos caminhos inspecionados das decisões 0050/0051: rascunho, auditoria dos bytes antes da publicação, PyPI por `release: published` e attestation obrigatória, salvo exceção explícita.

**Validação:** **1.022 testes específicos aprovados** — 225 + 700 + 97, todas as seleções com exit 0. Foram excluídos 190 casos dependentes de temporários/escrita; usei `--noconftest`, cache desativado e reproduções complementares em memória/TCP local. Na varredura do diff, não reproduzi `verified` indevido, vazamento, HTTP alternativo ou modelo de linguagem na execução. Suíte completa, fontes oficiais ao vivo, wheel isolada, bytes futuros da CI, instalação completa e attestation real: **NOT RUN**.

PARECER: COM BLOQUEADOR — IDs: F-19, F-22, F-23