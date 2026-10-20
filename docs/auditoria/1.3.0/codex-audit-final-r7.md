Auditei `release/1.3.0`, HEAD **`e5314adb4d6cb681c742f3511c8608fc4579bc15`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado. **Persistem dois bloqueadores anteriores e há um bloqueador novo.**

| ID | Severidade | Item | Arquivo:linha | Prova nesta rodada | Correção |
|---|---|---|---|---|---|
| F-08 | Corrigido nas reproduções | Deduplicação por identidade | [guarda.py:87](C:/dev/wt/INT/freoa_verifica/connectors/guarda.py:87) | Passaram principal/alteradora nas duas ordens, data compartilhada no Senado, sobreposição BCB e variantes de host, porta, caixa, fragmento e percent-encoding. | Nenhuma adicional para essas reproduções. A segurança do reaproveitamento apresenta **F-16**. |
| **F-11** | **ALTO — bloqueador; correção parcial** | Recusa do Planalto não bloqueia a fonte | [planalto.py:39](C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:39), [guarda.py:97](C:/dev/wt/INT/freoa_verifica/connectors/guarda.py:97) | Redirecionamento para host desafiador agora bloqueia corretamente. Porém, servidor local encerrando sem resposta: lei 7000 fez **3 pedidos**, retornou `recusa_identificado_planalto`, mas deixou `bloqueios={}`. Lei 7001, na mesma guarda, fez **mais 3 pedidos**; breaker passou de 1 para 2. A reclassificação ocorre depois do registro pela guarda. | Fazer a guarda registrar o desfecho final, incluindo a reclassificação da 0048, antes de permitir outra consulta ao host. |
| F-12 | Corrigido | README corrente | [README.md:53](C:/dev/wt/INT/README.md:53) | Instalação, MCP, estado atual, attestation obrigatória e seleção exclusiva do snapshot da versão instalada conferem. | Nenhuma adicional. |
| **F-13** | **ALTO — bloqueador; correção parcial** | Framing inválido ainda autoriza repetição ambiental | [transport.py:235](C:/dev/wt/INT/freoa_verifica/transport.py:235), [transport.py:972](C:/dev/wt/INT/freoa_verifica/transport.py:972) | Os originais passaram: `hello` seguido de `ZZ`, corpo incompleto e CAPTCHA entre chunks. Novas variantes com **503 + `Content-Length: xyz`**, comprimento negativo, CL conflitante com chunked, CL duplicado ou chunk `5\r\nhelloXX0\r\n\r\n` fizeram **3 pedidos e 2 esperas**, terminando em `fonte_fora`. O hook efetivo converteu os casos exercitados em **`skipped/wasxfail=fonte_fora:http_503`**. | Validar framing também nas respostas de erro, compartilhando as verificações aplicáveis ao 200. Não depender da tolerância de `http.client` para declarar resposta válida e repetível. |
| F-14 | Corrigido nas reproduções | Indexador e pesquisa textual | [service.py:2313](C:/dev/wt/INT/freoa_verifica/service.py:2313), [service.py:2656](C:/dev/wt/INT/freoa_verifica/service.py:2656) | Python, MCP e REST: dois candidatos da mesma ata com CAPTCHA fizeram **1 GET/1 incremento**, declararam categoria na cobertura e saíram de `ok`. Sucesso compartilhou captura; pesquisas distintas renovaram a guarda. | Nenhuma adicional nesses caminhos. |
| F-15 | MÉDIO — persiste | Guarda sobrevive entre execuções | [semente.py:164](C:/dev/wt/INT/freoa_verifica/semente.py:164), [semente.py:1013](C:/dev/wt/INT/freoa_verifica/semente.py:1013) | Mesma instância, duas chamadas reais a `run`: primeira fez **1 pedido/CAPTCHA**; segunda fez **0 pedidos**, conservando o bloqueio anterior, embora o servidor estivesse preparado para responder 200. | Renovar a guarda na entrada da execução externa; compartilhá-la somente com chamadas aninhadas daquela execução. |
| **F-16** | **ALTO — bloqueador novo** | Cache dispensa a política da chamada seguinte | [guarda.py:91](C:/dev/wt/INT/freoa_verifica/connectors/guarda.py:91), [httputil.py:38](C:/dev/wt/INT/freoa_verifica/connectors/httputil.py:38) | Após armazenar HTML 200 de 28 bytes, chamadas à mesma URL retornaram essa resposta mesmo com **host proibido**, **caminho proibido**, **MIME restrito a PDF** ou **`max_bytes=1`**. Sem cache, os quatro controles recusaram corretamente. | Revalidar a política da chamada atual antes de entregar a captura armazenada, sem novo pedido. Acrescentar regressões entre contextos com políticas distintas. |

F-16 demonstra violação dos controles de aceitação; **não foi demonstrada promoção indevida a `verified`**.

| Achado | Estado |
|---|---|
| **B3-01** | **Parcialmente corrigido.** Chunk parcial e somente cabeçalhos produziram `resposta_inesperada`, com hook mantendo falha. Redirecionamentos, DNS e controlador externo passaram; persiste **F-13**. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte; alteração de data dentro do mesmo mês produziu `data_fora_do_recorte`, exit **1**. |
| **B3-03** | **Corrigido nas reproduções.** Banco, blob e destino interno recusados antes da abertura; aliases por realpath/inode simulados recusados. Links físicos: **NOT RUN**. |
| **B3-04** | **Corrigido.** Blob ausente reprova; `--sem-blobs` retorna `parcial`; os 2.069 blobs instalados conferiram. |
| **B3-05** | **Resolvido pela 0048 revista.** Planalto sem exceção, UA identificado único e falha sem resposta reclassificada como `recusa_identificado`. Nenhum UA de navegador encontrado no código. A interação com a guarda permanece defeituosa em **F-11**. |
| **B3-06** | **Corrigido.** Mutante `999<CNJ>999`, passando por indexação e `obter_decisao`, resultou em `parte_indisponivel`/`integra_processo_divergente`. |
| **B3-07** | **Corrigido.** Alterar apenas `itens[0].ementa` para `42` ou `null` foi rejeitado. |

**T1/T2:** passaram os testes específicos de UA, 502/503/504, conexão sem resposta, POST condicionado à idempotência, `Retry-After` no orçamento, 403/429/desafio sem repetição e breaker por falha lógica. **F-13 impede afirmar fechamento da classificação global.**

Conferi todos os chamadores do indexador:

| Chamador | Tratamento da indisponibilidade |
|---|---|
| `service.py:1973` e `:1978` | Captura reutilizada; exceção sobe ao controlador, que declara motivo e classificação. |
| `service.py:2012` | Interrompe TJSP e preserva histórico antes do DataJud. |
| `service.py:2131` | Interrompe candidatos da fonte; declara indisponibilidade na cobertura. |
| `service.py:2421` | Interrompe a fonte; pesquisa textual usa guarda por pesquisa. |
| `semente.py:787` | Registra pendência STJ com categoria. |
| `semente.py:888` | Captura comum de jurisprudência registra pendência com categoria. |
| `semente.py:995` | Registra pendência STF com categoria. |

Na varredura dos demais laços, os casos de retomada da semente, fallback BCB e representações alternativas da CVM passaram. A repetição posterior à recusa do Planalto permanece demonstrada em **F-11**.

**FIX4 passou:** seções `conteudo`/`origem`, formato antigo, divergência de conteúdo e recusa de `--pos-instalacao` com `sync_state`. A bateria estrita no acervo instalado, usando SQLite somente leitura com `immutable=1`, retornou **`ok`**, com **44.780 decisões, 826 obras, 2.069 blobs íntegros, zero `sync_state` e nenhuma falha**.

**Versão e snapshot conferem.** Pyproject, `__version__`, instalador e CHANGELOG indicam **1.3.0**. Recalculei o arquivo de **665.335.352 bytes**:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Enumerei os **2.075 membros**: 2.069 blobs e os seis arquivos esperados de banco/manifestos/checksums. Sem duplicatas, links, caminhos perigosos, `registro.key`, `instalacao.json` ou membros inesperados. Os quatro logs são coerentes com o artefato, inclusive o hash do manifesto. O vínculo aceitou o digest em **1.3.0** e recusou em **1.2.0 e 1.4.0**.

**Distribuição conforme 0050/0051 por inspeção e testes específicos:** release em rascunho, auditoria dos bytes antes da publicação, PyPI por `release: published` e instalador exigindo attestation, salvo `-SemAttestation` explícito. Execução remota, instalação completa e verificação real de attestation: **NOT RUN**. Os futuros assets da CI continuam sujeitos ao passo 6.

Na seleção com a `.venv`, **213 testes específicos passaram**, além de **24 reproduções de testes existentes com armazenamento em memória**. Dez casos foram desselecionados; outros 17 dependentes de temporários não foram validados porque o harness sem escrita falhou com `KeyError: tmp_path`. Isso não foi contado como defeito do produto. Suíte completa, wheel isolada e fontes oficiais ao vivo: **NOT RUN**. O inventário de fixtures retornou zero problemas; a varredura do diff não demonstrou vazamento ou HTTP alternativo.

**PARECER: COM BLOQUEADOR — IDs: F-11, F-13, F-16**

