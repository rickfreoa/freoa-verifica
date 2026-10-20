Auditei `release/1.3.0`, HEAD **`c6d5ab5b56cb9c19089682f27eec7eb73f749d37`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado.

**F-18 está corrigido. Há um novo bloqueador, F-19: a interpretação do charset ainda permite repetir uma resposta que contém desafio.**

| ID | Severidade | Item | Arquivo:linha | Prova | Correção |
|---|---|---|---|---|---|
| **F-19** | **ALTA — bloqueador novo** | Charset ignorado na detecção de desafio | [challenge.py:162](C:/dev/wt/INT/freoa_verifica/connectors/challenge.py:162), [transport.py:406](C:/dev/wt/INT/freoa_verifica/transport.py:406), [httputil.py:195](C:/dev/wt/INT/freoa_verifica/connectors/httputil.py:195) | Servidor TCP real: HTML com `charset=utf-16` e **CAPTCHA**, ou `iso-8859-1`/`windows-1252` e **“verificação de segurança”**, em **502/503/504**, fez **3 pedidos** e terminou como `fonte_fora`. O detector sempre decodifica como UTF-8. Duas URLs UTF-16 sob a mesma guarda fizeram **6 pedidos**, sem bloquear o host; hook efetivo produziu `skipped/wasxfail=fonte_fora:http_503`. Em **200**, o HTML UTF-16 com CAPTCHA foi devolvido como sucesso pelo conector. | Unificar a interpretação textual para sucesso e erro, respeitando charset/BOM. Charset não suportado ou corpo não interpretável deve causar `RespostaInvalida`, sem repetição. Cobrir charset × status × marcador, hook e guarda. |
| F-18 | Alta anterior — **corrigido** | `Content-Encoding` antes do desvio por status | [transport.py:1117](C:/dev/wt/INT/freoa_verifica/transport.py:1117) | **98 testes aprovados**, mais **104 combinações adicionais**, incluindo redirecionamentos, encoding vazio, composto e duplicado. Codificações recusadas: `resposta_inesperada`, **1 pedido**, hook mantém falha. Sem encoding/`identity`, CAPTCHA bloqueia o host. | Nenhuma adicional para `Content-Encoding`; F-19 impede considerar encerrada a classe mais ampla de interpretação do corpo. |
| F-13 | Alta anterior — corrigido nos casos exercitados | Framing, sintaxe e extensões de chunk | [transport.py:352](C:/dev/wt/INT/freoa_verifica/transport.py:352) | Regressões específicas de cabeçalhos, chunks, trailers, amostra fragmentada e corpo incompleto passaram. | Nenhuma adicional nos casos exercitados. Persiste o limite declarado de exame de **64 KiB** em respostas de erro. |
| F-16 | Alta anterior — corrigido nos casos exercitados | Identidade e política do cache | [transport.py:463](C:/dev/wt/INT/freoa_verifica/transport.py:463), [httputil.py:65](C:/dev/wt/INT/freoa_verifica/connectors/httputil.py:65) | Passaram regressões de query exata, cabeçalhos, método/corpo, validação da entrada atual e revalidação da política. | Nenhuma adicional nos casos exercitados. |
| F-15 | **MÉDIA — persiste** | Guarda sobrevive entre execuções | [semente.py:195](C:/dev/wt/INT/freoa_verifica/semente.py:195), [semente.py:1011](C:/dev/wt/INT/freoa_verifica/semente.py:1011) | Mesma instância, duas chamadas reais a `run`: **1 pedido** na primeira; **zero** na segunda, conservando o bloqueio. | Renovar a guarda na entrada de cada execução externa, compartilhando-a com as chamadas aninhadas. |
| F-17 | **MÉDIA — persiste** | Diagnóstico continua depois de desafio | [planalto.py:173](C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:173) | `health()` contra 403/CAPTCHA fez **3 GETs e 3 incrementos** no breaker, repetindo inclusive a URL positiva. É repetição fora do transporte. | Interromper as sondas após desafio/recusa ou compartilhar guarda durante o diagnóstico. |
| F-20 | BAIXA — documental | Instrução residual contradiz a 0051 | [RELEASE.md:35](C:/dev/wt/INT/docs/RELEASE.md:35) | Ainda afirma que `snapshot install` consulta a “última release”; implementação e decisão exigem a release da versão instalada. | Atualizar esse parágrafo para `v<__version__>`. |

| Achado | Estado nesta rodada |
|---|---|
| **B3-01** | **Corrigido nas reproduções de progresso, leitura parcial, saltos e prazo externo.** A ressalva de execução dos testes consta abaixo. F-19 bloqueia a aprovação global da detecção/repetição. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte; mudança de data dentro do mesmo mês produziu `data_fora_do_recorte`, exit **1**. |
| **B3-03** | **Corrigido nos destinos reproduzidos.** Banco, blob e arquivo novo internos foram recusados antes de abrir o banco. Proteções realpath/inode presentes; symlink/hardlink físicos: **NOT RUN**. |
| **B3-04** | **Corrigido.** Blob ausente falha; `--sem-blobs` retorna `parcial`. Os **2.069 blobs** instalados conferem. |
| **B3-05** | **Resolvido pela 0048 revista.** Planalto sem exceção; falha anterior à resposta recebe `recusa_identificado`. Nenhum UA de navegador encontrado no código pesquisado. |
| **B3-06** | **Corrigido.** Mutante `999<CNJ>999`, com indexação e `obter_decisao`, retornou `parte_indisponivel`, texto nulo e `integra_processo_divergente`. |
| **B3-07** | **Corrigido.** Alterar somente `itens[0].ementa` para `42` ou `null` reprova; variantes booleano, objeto e lista também reprovaram. |

**T1/T2:** passaram os testes específicos de identidade única, conexão sem resposta, POST condicionado à idempotência, `Retry-After`, teto de repetição e breaker por falha lógica. Reproduzi também principal/alteradora nas duas ordens, ata CVM com três itens compartilhando uma captura e interrupção da lista após CAPTCHA. **F-19 demonstra que os mecanismos ainda não fecham toda a classe.**

**FIX4 e snapshot:** passaram separação `conteudo`/`origem`, manifesto antigo, divergência de conteúdo e recusa de `--pos-instalacao` com `sync_state`. A bateria estrita do instalado, aberta com SQLite `mode=ro&immutable=1`, retornou **zero falhas**: **44.780 decisões, 826 obras, derivados 4, 2.069 blobs íntegros e zero `sync_state`**.

Recalculei o snapshot de **665.335.352 bytes**:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei os **2.075 membros** com `tarfile`: 2.069 blobs, três bancos/representações e três manifestos/checksums. Sem membros inesperados, duplicatas, links, caminhos perigosos, `registro.key` ou `instalacao.json`. Os quatro logs conferidos são coerentes com o artefato. O vínculo aceitou esse digest em **1.3.0** e recusou em **1.2.0 e 1.4.0**.

**Versão e distribuição:** pyproject, `__version__`, instalador e CHANGELOG indicam **1.3.0**. Inspeção e testes confirmam release em rascunho, auditoria dos bytes antes de publicar, PyPI por `release: published` e attestation obrigatória no instalador, com exceção explícita `-SemAttestation`.

**Execução e limites:** FIX14: **98 aprovados**; seleção maior: **503 aprovados, 9 falhas, 75 excluídos** por dependerem de escrita. A matriz afetada foi repetida isoladamente: **36 aprovados**. Contrato/TJDFT: **14 aprovados**. Portanto, não apresento a seleção inicial como verde. As reproduções adicionais usaram TCP local e armazenamento em memória.

Na varredura do diff, não demonstrei promoção indevida a `verified`, vazamento, HTTP alternativo ou modelo de linguagem no caminho de execução. Suíte completa, fontes oficiais ao vivo, wheel isolada, CI remota, instalação completa e attestation real: **NOT RUN**.

PARECER: COM BLOQUEADOR — IDs: F-19