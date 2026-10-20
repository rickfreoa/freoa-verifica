Auditei `release/1.3.0`, HEAD **`818ecbf32916bca5c85e21347dc068b3b2dbb0b9`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado.

**F-13 e F-16 passaram nas reproduções do FIX13. Há um novo bloqueador: F-18.**

| ID | Severidade | Item | Arquivo:linha | Prova nesta rodada | Correção |
|---|---|---|---|---|---|
| **F-18** | **ALTA — bloqueador novo** | Resposta comprimida impede examinar desafio, mas autoriza repetição | [transport.py:1158](C:/dev/wt/INT/freoa_verifica/transport.py:1158), [transport.py:1164](C:/dev/wt/INT/freoa_verifica/transport.py:1164) | Servidor TCP real: corpo `<html>captcha</html>` comprimido com **gzip ou deflate**, em **502/503/504**, provocou **3 pedidos** e terminou como `fonte_fora`. Em 200, a mesma codificação produziu `resposta_inesperada`, com 1 pedido. O hook efetivo gerou `skipped/wasxfail=fonte_fora:http_503`. Duas URLs sob a mesma guarda fizeram **6 pedidos**, sem bloquear o host. | Validar `Content-Encoding` antes do desvio por status. Codificação não suportada deve produzir `RespostaInvalida`, sem repetição. Cobrir a matriz de codificações/status e o bloqueio da guarda. |
| F-13 | Anterior alta — corrigido no FIX13 | Gramática de extensões de chunk | [transport.py:231](C:/dev/wt/INT/freoa_verifica/transport.py:231) | As três reproduções da r9 e os casos parametrizados passaram. Variantes adicionais: NUL no último chunk, DEL em quoted-string/quoted-pair e `/` em token foram recusados em 200 e 503, sempre com **1 pedido**. BWS, escapes e obs-text válidos continuaram aceitos. | Nenhuma adicional para a gramática exercitada. Ressalva do limite de amostragem abaixo. |
| F-16 | Anterior alta — corrigido nas reproduções | Identidade e política do cache | [transport.py:463](C:/dev/wt/INT/freoa_verifica/transport.py:463), [httputil.py:65](C:/dev/wt/INT/freoa_verifica/connectors/httputil.py:65) | Passaram ordem e codificação exatas da query, `X-Representation`, `Accept`, método, corpo, repetição idêntica, política atual e validação da URL antes do cache. As combinações com servidor local preservaram os resultados obtidos sem cache. | Nenhuma adicional nos casos exercitados. |
| F-15 | MÉDIA — persiste | Guarda sobrevive entre execuções | [semente.py:195](C:/dev/wt/INT/freoa_verifica/semente.py:195), [semente.py:1011](C:/dev/wt/INT/freoa_verifica/semente.py:1011) | Mesma instância, duas chamadas reais a `run`: primeira fez **1 pedido/CAPTCHA**; segunda fez **zero**, conservando a falha, embora houvesse resposta 200 preparada. | Renovar a guarda na entrada de cada execução externa; compartilhar somente com chamadas aninhadas daquela execução. |
| F-17 | MÉDIA — persiste | Diagnóstico continua após desafio | [planalto.py:173](C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:173) | `health()` contra 403/CAPTCHA fez **3 GETs e 3 incrementos** no breaker; repetiu inclusive a URL positiva. | Interromper as sondas após desafio/recusa ou compartilhar guarda no diagnóstico, declarando as demais não executadas. |

A tabela de correspondência gramatical está presente no docstring. Comparei as produções relevantes com [RFC 9112 §7.1.1](https://www.rfc-editor.org/rfc/rfc9112.html#section-7.1.1) e [RFC 9110 §5.6.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.6.4). O exame das respostas de erro continua limitado a **64 KiB**, conforme FIX10: malformações colocadas depois desse limite não são detectadas. Reproduzi essa limitação; não a contabilizei como novo defeito contra o escopo expressamente especificado.

| Achado | Estado nesta rodada |
|---|---|
| **B3-01** | **Corrigido nas reproduções originais e variantes de progresso, saltos e prazo externo.** F-18 impede aprovar globalmente a classificação/repetição. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte; alteração de data dentro do mesmo mês produziu `data_fora_do_recorte`, exit **1**. |
| **B3-03** | **Corrigido nos destinos internos reproduzidos.** Banco, blob e novo arquivo dentro do home foram recusados antes de abrir o banco. Proteções realpath/inode presentes; symlink/hardlink físicos: **NOT RUN**. |
| **B3-04** | **Corrigido.** Blobs ausentes são detectados; `--sem-blobs` retorna `parcial`. Os **2.069 blobs** instalados conferem. |
| **B3-05** | **Resolvido pela 0048 revista.** Planalto sem exceção; falha anterior à resposta recebe `recusa_identificado`. Testes de identidade única passaram; nenhum UA de navegador encontrado no código pesquisado. |
| **B3-06** | **Corrigido.** Reproduzi o mutante `999<CNJ>999` com indexação e `obter_decisao`: `parte_indisponivel`, texto nulo e `integra_processo_divergente`. |
| **B3-07** | **Corrigido.** Passaram os negativos que alteram somente `itens[0].ementa` para `42` ou `null`. |

**T1/T2:** passaram os testes específicos de 502/503/504 sem desafio, conexão sem resposta, POST condicionado à idempotência, `Retry-After` dentro do orçamento, 403/429 e breaker uma vez por falha lógica. F-18 demonstra que “sem marcador detectado” ainda pode significar **corpo não interpretável**. Fora do transporte, persiste a repetição de diagnóstico em F-17; os fallbacks BCB/CVM exercitados propagaram as falhas previstas.

**FIX4:** reproduzi separação `conteudo`/`origem`, compatibilidade com manifesto antigo e recusa de `--pos-instalacao` quando existe `sync_state`. A bateria estrita do acervo instalado, aberto com SQLite `mode=ro&immutable=1`, retornou **zero falhas**: **44.780 decisões, 826 obras, derivados versão 4, 2.069 blobs íntegros e zero `sync_state`**.

**Versão e snapshot:** pyproject, `__version__`, instalador e CHANGELOG indicam **1.3.0**. Recalculei o arquivo de **665.335.352 bytes**:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei os **2.075 membros** com `tarfile`: 2.069 blobs, três bancos/representações e três manifestos/checksums. Nenhum membro inesperado, duplicata, link, caminho perigoso, `registro.key` ou `instalacao.json`. Os quatro logs são coerentes com o artefato. `_vincular` aceitou o digest em **1.3.0** e recusou em **1.2.0 e 1.4.0**.

**Distribuição:** inspeção e testes específicos confirmam rascunho em `release.yml`, auditoria dos bytes prevista antes da publicação, `pypi.yml` por `release: published` e attestation obrigatória no instalador, com exceção explícita `-SemAttestation`. Execução remota, wheel isolada, instalação completa e attestation real: **NOT RUN**, pertencentes à verificação posterior dos assets.

Foram **554 testes específicos aprovados**, além das reproduções dirigidas. **145 casos dependentes de escrita foram excluídos**; as reproduções necessárias usaram armazenamento em memória. As tentativas iniciais pararam por temporários negados pelo sandbox. Suíte completa e fontes oficiais ao vivo: **NOT RUN**. Na varredura do diff, não demonstrei promoção indevida a `verified`, vazamento, HTTP alternativo ou modelo de linguagem no caminho de execução.

PARECER: COM BLOQUEADOR — IDs: F-18

