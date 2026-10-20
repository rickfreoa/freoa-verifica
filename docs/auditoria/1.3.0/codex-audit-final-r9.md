Auditei `release/1.3.0`, HEAD **`1bde2e131fcccf04892698ed6de996820917bb97`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado.

**F-13 e F-16 tiveram as reproduções anteriores corrigidas, mas os mecanismos ainda não fecham as classes de defeito.**

| ID | Severidade | Item | Arquivo:linha | Prova reproduzida nesta rodada | Correção |
|---|---|---|---|---|---|
| **F-13** | **ALTO — bloqueador; correção parcial** | Extensões de chunk continuam sem gramática estrita | [transport.py:232](/C:/dev/wt/INT/freoa_verifica/transport.py:232) | As quatro variantes da r8 agora dão `resposta_inesperada`, com **1 pedido**, em 200 e 503. Porém, chunks iniciados por `5;\x00`, `5;x="unfinished` ou `5;=x` foram aceitos em **200**. Em **503**, cada variante fez **3 pedidos** e terminou em `fonte_fora`. O hook efetivo produziu **`skipped/wasxfail=fonte_fora:http_503`**. | Validar também a gramática das extensões, substituindo `;[^\r\n]*`. Sintaxe inválida deve produzir `RespostaInvalida`, sem repetição, em qualquer status. |
| **F-16** | **ALTO — bloqueador; correção parcial** | Cache ainda confunde requisições com respostas diferentes | [transport.py:444](/C:/dev/wt/INT/freoa_verifica/transport.py:444), [httputil.py:69](/C:/dev/wt/INT/freoa_verifica/connectors/httputil.py:69), [guarda.py:107](/C:/dev/wt/INT/freoa_verifica/connectors/guarda.py:107) | Passaram as variantes anteriores de URL e política. Novas provas com servidor local: **sem cache**, `/x?a=1&a=2` e `/x?a=2&a=1` devolveram corpos distintos; **com cache**, a segunda recebeu o corpo da primeira. O mesmo ocorreu ao trocar `X-Representation: one` por `two`. | Preservar a ordem da query, salvo equivalência comprovada por fonte. Incorporar à identidade os cabeçalhos efetivos relevantes ou desabilitar o reaproveitamento quando variam. Revalidar a URL não resolve colisões de identidade. |
| F-15 | MÉDIO — persiste | Guarda sobrevive entre execuções | [semente.py:195](/C:/dev/wt/INT/freoa_verifica/semente.py:195), [semente.py:1011](/C:/dev/wt/INT/freoa_verifica/semente.py:1011) | Mesma instância, duas chamadas reais a `run`: primeira fez **1 pedido/CAPTCHA**; segunda fez **zero pedidos**, conservando o bloqueio, embora a próxima resposta preparada fosse 200. | Renovar a guarda na entrada de cada execução externa; compartilhar somente com chamadas aninhadas daquela execução. |
| F-17 | MÉDIO — persiste | Diagnóstico continua após desafio | [planalto.py:173](/C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:173) | `health()` contra 403/CAPTCHA fez **3 GETs**, incluindo duas consultas à mesma URL positiva, e **3 incrementos** no breaker. | Compartilhar guarda no diagnóstico ou interromper as sondas da fonte após desafio/recusa, declarando as restantes não executadas. |

As extensões usadas em F-13 violam a gramática `token`/`quoted-string` da [RFC 9112, §7.1.1](https://www.rfc-editor.org/rfc/rfc9112.html#section-7.1.1). **Não demonstrei promoção indevida a `verified` nem vazamento de dados; demonstrei repetição/classificação indevida e entrega de captura diferente daquela obtida sem cache.**

| Achado | Estado nesta rodada |
|---|---|
| **B3-01** | **Parcialmente corrigido.** Reproduzi chunk parcial e somente cabeçalhos: `resposta_inesperada`, status 200 preservado. Passaram os testes de progresso, saltos e controlador externo. Persiste a variante de F-13. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte do manifesto; mudança de data dentro do mesmo mês produziu `data_fora_do_recorte`, exit **1**. Banco e manifesto em memória. |
| **B3-03** | **Corrigido nas reproduções.** Banco, blob e destino interno recusados antes de abrir o banco. Aliases por realpath/inode simulados também recusados. Links físicos: **NOT RUN**. |
| **B3-04** | **Corrigido.** Blob ausente reprova; `--sem-blobs` retorna `parcial`. Conferi novamente os **2.069 blobs** instalados. |
| **B3-05** | **Resolvido pela 0048 revista.** Planalto sem exceção; falha sem resposta recebe `recusa_identificado`. Identidade única; nenhum UA de navegador encontrado no código pesquisado. |
| **B3-06** | **Corrigido.** Reproduzi `999<CNJ>999` com indexação e `obter_decisao`: `parte_indisponivel`, motivo `integra_processo_divergente`. |
| **B3-07** | **Corrigido.** Os negativos que alteram somente `itens[0].ementa` para `42` ou `null` reprovaram. |

**Fragmentos:** não identifiquei regressão nos chamadores examinados. A recusa já existia no transporte em `239bef6`; o FIX12 elimina a aceitação indevida pelo cache. O CVM Colegiado remove o fragmento antes da rede e o reaplica para selecionar o item. Reproduzi **três itens distintos com um único GET**, selecionando os três processos corretos.

**T1/T2 e repetição:** passaram os testes específicos de 502/503/504 válidos sem desafio, conexão sem resposta, POST condicionado à idempotência, `Retry-After` no orçamento e breaker por falha lógica. F-13 impede declarar fechamento global. Os fallbacks BCB/CVM examinados interrompem as falhas previstas. Fora do transporte, permanece a continuação das sondas em **F-17**. F-11 passou; a reprodução pública de F-14 fez **1 GET**, declarou CAPTCHA na cobertura e retornou `indisponivel`.

**FIX4:** passaram separação `conteudo`/`origem`, manifesto antigo, divergência de conteúdo e recusa de `--pos-instalacao` com `sync_state`. A bateria estrita do acervo instalado, aberta com SQLite `mode=ro&immutable=1` e temporários em memória, retornou **`ok`**, sem falhas: **44.780 decisões, 826 obras, 2.069 blobs íntegros e zero `sync_state`**.

**Versão e snapshot:** pyproject, `__version__`, instalador e CHANGELOG indicam **1.3.0**. Recalculei o digest do arquivo de **665.335.352 bytes**:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei os **2.075 membros**: 2.069 blobs, três bancos/representações e três manifestos/checksums. Sem duplicatas, links, caminhos perigosos, `registro.key`, `instalacao.json` ou membros inesperados. Os quatro logs conferem com o artefato. O vínculo efetivo aceitou o digest em **1.3.0** e recusou em **1.2.0 e 1.4.0**.

**Distribuição:** por inspeção e testes específicos, os workflows seguem 0050/0051: release em rascunho, auditoria dos bytes antes da publicação, PyPI por `release: published` e instalador exigindo attestation, com exceção explícita `-SemAttestation`. Execução remota, instalação completa, wheel isolada e attestation real: **NOT RUN**; continuam dependentes da auditoria dos assets do passo 6.

Foram **378 testes específicos aprovados**, além das reproduções dirigidas. Na segunda seleção, **132 casos dependentes de escrita foram excluídos**; reproduções necessárias foram feitas em memória. Suíte completa e fontes oficiais ao vivo: **NOT RUN**. Na varredura do diff, não demonstrado HTTP alternativo, modelo de linguagem no caminho de execução ou vazamento.

PARECER: COM BLOQUEADOR — IDs: F-13, F-16