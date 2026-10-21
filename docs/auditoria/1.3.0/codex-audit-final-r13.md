Auditei **`release/1.3.0`**, HEAD **`26bfb271adedb4a73db06989bba823a71ec9de9f`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado. **Persistem F-19 e F-22; reproduzi um novo bloqueador, F-23.**

| ID | Severidade | Item | Arquivo:linha | Prova | Correção |
|---|---|---|---|---|---|
| **F-19** | **Alta — bloqueador persistente** | Parser MIME transforma parâmetros distintos em `charset` | [texto_resposta.py:305](C:/dev/wt/INT/freoa_verifica/texto_resposta.py:305) | TCP real: `charset*=us-ascii''utf-16le`, `charset*0=utf-16; charset*1=le` e continuação codificada ocultaram `<p>CAPTCHA</p>`. Cada variante: **200 retornou sucesso; 503 fez três pedidos e terminou `fonte_fora`; duas URLs sob a mesma guarda fizeram seis pedidos, sem bloqueio**. Hook efetivo: `skipped/wasxfail=fonte_fora:http_503`. | Extrair somente o parâmetro HTTP chamado exatamente `charset`, preservando os nomes anteriores à transformação RFC 2231. Cobrir parâmetros estendidos e continuações no transporte, guarda e hook. |
| **F-22** | **Alta — bloqueador persistente** | Planalto ainda interpreta novamente os bytes | [planalto.py:285](C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:285), [html_devices.py:153](C:/dev/wt/INT/freoa_verifica/parsers/html_devices.py:153) | `Content-Type: text/html; charset=utf-8`, bytes UTF-8 e `<meta charset="iso-8859-1">`: a interpretação única contém **“Ação”**; `PlanaltoConnector.parse`, usando o subprocesso real, devolve **“AÃ§Ã£o”**, dispositivo `art1` e **nenhuma issue**. | Entregar ao parser o texto produzido com o Content-Type do `Response`. Preservar os bytes originais separadamente para captura e hash. |
| **F-23** | **Alta — bloqueador novo** | Busca legislativa continua após desafio e declara fonte saudável | [service.py:1063](C:/dev/wt/INT/freoa_verifica/service.py:1063), [service.py:1149](C:/dev/wt/INT/freoa_verifica/service.py:1149), [service.py:2821](C:/dev/wt/INT/freoa_verifica/service.py:2821) | Busca controlada com dois candidatos CVM, conector/transporte reais e TCP local: `buscar_legislacao` fez **dois pedidos e dois incrementos** após CAPTCHA; respondeu `parcial`, mas **`fontes.cvm_normas.status="ok"`**, motivo nulo. `_index_candidate_legis` engole a indisponibilidade. `buscar_normas_cvm` também fez dois pedidos e perdeu categoria/evidência nas falhas. `StjConnector.sync`, com estado e índice em memória, continuou para outro pacote após CAPTCHA: **dois pedidos**. | Propagar `Unavailable` estruturada; aplicar guarda por execução nos controladores restantes; interromper a fonte após desafio/recusa e declarar a falha. Cobrir buscas legislativas e sincronização comum, além da semente. |
| F-17 | Média — correção parcial | `doctor` protegido; `health()` direto continua repetindo | [service.py:3069](C:/dev/wt/INT/freoa_verifica/service.py:3069), [planalto.py:174](C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:174) | `doctor`: **um pedido por fonte** após CAPTCHA. Chamadas diretas a `health()`: Planalto **três**, BCB **três**, CVM Normas **dois**, TJDFT **dois**. | Fazer a entrada de `health()` compartilhar a guarda ou interromper as sondas após desafio/recusa. |
| F-15 | Média — persiste | Guarda atravessa execuções da semente | [semente.py:195](C:/dev/wt/INT/freoa_verifica/semente.py:195), [semente.py:1011](C:/dev/wt/INT/freoa_verifica/semente.py:1011) | Mesma instância, duas chamadas reais a `run`, SQLite em memória: **um pedido na primeira, zero na segunda**, conservando o bloqueio. | Renovar a guarda na entrada de cada execução externa; compartilhar somente com chamadas aninhadas. |
| F-20 | Baixa — persiste | Instrução documental contradiz 0051 | [RELEASE.md:35](C:/dev/wt/INT/docs/RELEASE.md:35) | Ainda afirma que `snapshot install` consulta a “última release”. | Descrever a seleção exclusiva de `v<__version__>`. |
| F-21 | Alta anterior — corrigido nos casos exercitados | Desafio em redirecionamentos | [transport.py:1133](C:/dev/wt/INT/freoa_verifica/transport.py:1133), [guarda.py:73](C:/dev/wt/INT/freoa_verifica/connectors/guarda.py:73) | Passaram os dez originais: cinco status × CAPTCHA/cabeçalho de borda. Variante adicional: desafio no **segundo host**, em 307, interrompeu a cadeia e bloqueou esse host; consulta posterior não chegou à rede. | Nenhuma adicional para o mecanismo de saltos exercitado. A interpretação do corpo continua vulnerável por F-19. |

O caso mínimo de F-19 é:

```http
Content-Type: text/html; charset*=us-ascii''utf-16le

<p>CAPTCHA</p>
```

O corpo tem **14 bytes**. `email.message.Message` transforma o parâmetro estendido em `charset`, contrariando a exigência da FIX16 de considerar somente esse nome exato. A gramática HTTP distingue os nomes dos parâmetros. [RFC 9110, §5.6.6](https://www.rfc-editor.org/rfc/rfc9110.html#section-5.6.6).

| Achado | Estado nesta auditoria |
|---|---|
| **B3-01** | **Corrigido nas reproduções originais e variantes exercitadas.** Chunk parcial, somente cabeçalhos, prazo externo, falhas de protocolo e saltos mantiveram `resposta_inesperada`; o hook manteve falha. F-19 impede aprovar globalmente a detecção/repetição. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte; mover a decisão para outro dia do mesmo mês produziu `data_fora_do_recorte`, exit **1**. Banco e manifesto em memória. |
| **B3-03** | **Corrigido nos casos exercitados.** Banco, blob e destino novo internos recusados antes de abrir o banco. Aliases por realpath/inode simulados também recusados. Links físicos: **NOT RUN**. |
| **B3-04** | **Corrigido.** Blob ausente reprova; `--sem-blobs` retorna `parcial`. Os **2.069 blobs** instalados conferiram. |
| **B3-05** | **Resolvido pela 0048 revista.** Planalto sem exceção; falha anterior à resposta recebe `recusa_identificado`; respostas HTTP seguem a classificação geral. Nenhum UA de navegador encontrado no código pesquisado. |
| **B3-06** | **Corrigido.** Mutante `999<CNJ>999`, indexado e consultado por `obter_decisao`: `parte_indisponivel`, texto nulo e `integra_processo_divergente`. |
| **B3-07** | **Corrigido.** Quinze mutantes de tipo/nulidade, nos três adaptadores congelados, foram rejeitados. |

**T1/T2:** passaram identidade única, teto de repetição, conexão sem resposta, POST condicionado à idempotência, `Retry-After`, orçamento e breaker por falha lógica. Passaram também principal/alteradora nas duas ordens, ata CVM com três itens usando **um GET** e interrupção da lista após desafio. **Os mecanismos não fecham as classes**, pelas variantes de F-19 e pelos controladores descobertos em F-23.

**FIX16/F-22:** a reprodução original pela API pública da CVM foi corrigida: busca por “Ação” encontrou **um item**, com fonte disponível. CVM Colegiado, CVM Normas, STF e TJSP passaram a fornecer texto aos respectivos parsers HTML/XML. O caminho do Planalto permanece divergente. JSON, CSV do STJ e exibição de captura armazenada continuam com os contratos ou limites documentados na 0062.

**FIX4:** passaram separação `conteudo`/`origem`, manifesto antigo, comparação pós-instalação, divergência de conteúdo e rejeição de `--pos-instalacao` com `sync_state`. A bateria estrita do instalado, com SQLite `mode=ro&immutable=1` e temporários em memória, retornou:

- **44.780 decisões; 826 obras; derivados 4**.
- **2.069 blobs conferidos; zero falhas; zero `sync_state`**.
- `origem: "nao_aplicavel_pos_instalacao"`.

Recalculei o snapshot de **665.335.352 bytes**:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei com `tarfile` os **2.075 membros**: 2.069 blobs, três bancos/representações e três manifestos/checksums. Sem duplicatas, links, caminhos perigosos, membros inesperados, `registro.key` ou `instalacao.json`. Os quatro logs do supervisor são coerentes com o artefato. O vínculo aceitou esse digest em **1.3.0** e recusou em **1.2.0 e 1.4.0**.

Pyproject, `__version__`, instalador e CHANGELOG indicam **1.3.0**. Workflows e instalador atendem aos caminhos inspecionados das decisões 0050/0051: rascunho, auditoria dos bytes antes da publicação, PyPI por `release: published` e attestation obrigatória, salvo `-SemAttestation` explícito.

As duas seleções específicas terminaram com **855 aprovados — 687 + 168, ambas exit 0**; **140 casos foram excluídos** por dependerem de temporários/escrita. Reproduções complementares usaram TCP local, armazenamento em memória e o hook efetivo. Tentativas com preparação inadequada não foram contabilizadas como aprovação.

Na varredura de `239bef6..HEAD`, não reproduzi `verified` indevido, vazamento, HTTP alternativo ou modelo de linguagem no caminho de execução. Reproduzi os três bloqueadores acima. Suíte completa, fontes oficiais ao vivo, wheel isolada, assets futuros da CI, instalação completa e attestation real: **NOT RUN**.

PARECER: COM BLOQUEADOR — IDs: F-19, F-22, F-23