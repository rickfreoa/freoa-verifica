Auditei `release/1.3.0`, HEAD **`17cc21deabc585a88d1af9f358d9d40fbfe72b66`**, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado.

**O novo snapshot corrige a ocorrência original de F-24. Contudo, reproduzi outra variante do mesmo problema de compatibilidade: F-26, bloqueador.**

| ID | Severidade | Item | Arquivo:linha | Prova | Correção |
|---|---|---|---|---|---|
| **F-26** | **Alta — bloqueador** | Content-Type presente dispensa decisão de interpretação | [derivados.py:32](/C:/dev/wt/INT/freoa_verifica/derivados.py:32), [repo.py:21](/C:/dev/wt/INT/freoa_verifica/store/repo.py:21) | Dois negativos pela API `indexar_obra`, sem adulteração manual do banco: recibo com Content-Type, mas codec/origem nulos; releitura falha; `compativel=True` permanece; consulta entrega texto e verificação retorna `identity=verified`, `text=verified`. | Exigir decisão registrada independentemente da presença de Content-Type. Acrescentar regressões para ambos os negativos abaixo e impedir sua certificação/consulta como derivados atuais. |
| F-24 | Alta — ocorrência original corrigida | Snapshot legado e reconstrução | [service.py:798](/C:/dev/wt/INT/freoa_verifica/service.py:798), [texto_resposta.py:485](/C:/dev/wt/INT/freoa_verifica/texto_resposta.py:485) | Tar novo íntegro, derivados v5, decisões legadas registradas. Reparse independente das 121 capturas Planalto: **118 conferidas + 3 declaradas nos bytes**, sem divergência de hash de modelo. | O artefato passou; o fechamento geral do critério de compatibilidade permanece pendente em F-26. |
| F-19 | Alta — corrigido nos casos exercitados | Validação antes de BOM/MIME/status | [texto_resposta.py:441](/C:/dev/wt/INT/freoa_verifica/texto_resposta.py:441) | Passaram os negativos de charset estendido, continuações, duplicação, BOM e MIME binário, em 200/503. Desafio HTML UTF-16 sob PDF foi reconhecido. | Nenhuma adicional demonstrada nesses caminhos. |
| F-22 | Alta — corrigido no fluxo de captura exercitado | Recibo e releitura preservam interpretação | [service.py:813](/C:/dev/wt/INT/freoa_verifica/service.py:813) | Transporte TCP, persistência e subprocesso reais, com SQLite/blobs em memória: header `charset="utf-8"` venceu meta Latin-1; releitura preservou **“Ação”**, com uma captura reprocessada e nenhuma falha. | Preservar esse fluxo; fechar a admissão de derivados sem decisão em F-26. |
| F-23 | Alta — corrigido nos casos exercitados | Interrupção da ressincronização por fonte | [situacao.py:240](/C:/dev/wt/INT/freoa_verifica/situacao.py:240) | CVM e BCB, duas obras: CAPTCHA/403 interromperam após um pedido; 503 limitou-se às tentativas da primeira URL. Também passaram charset inválido em 503, UTF-8 inválido em 200 e desafio UTF-16 sob PDF. Retorno indisponível, com categoria/evidência. | Nenhuma adicional demonstrada nesses caminhos. |
| F-25 | Média — lacuna de teste persiste | AST não garante fechamento universal | [test_garantias_estruturais.py:347](/C:/dev/wt/INT/tests/test_garantias_estruturais.py:347) | Os escapes descritos abaixo continuam passando pelos respectivos detectores. | Ampliar os negativos e delimitar a promessa das sentinelas sintáticas. |
| F-20 | Baixa — persiste | Documentação contraditória | [RELEASE.md:35](/C:/dev/wt/INT/docs/RELEASE.md:35) | Ainda diz que a instalação consulta a “última release”; o código exige a versão instalada. | Corrigir o parágrafo. |

**Prova de F-26.** Usei o método real `indexar_obra`, um modelo Planalto sintético produzido pelo parser e armazenamento em memória. Não modifiquei recibos nem modelos por SQL. Exercitei:

1. Corpo cp1252 contendo “Ação”, declarado como `text/html; charset=utf-8`.
2. Corpo UTF-8 com `text/html; charset*=x`.

Resultado nos dois casos:

```text
recibo: content_type preenchido; codificacao=None; origem_da_codificacao=None
derived_version: 5
compativel: True
reprocessamento: falha
compativel após a falha: True
obter_dispositivo: encontrada
verificar_citacao: identity=verified; text=verified
```

As falhas foram, respectivamente, `Corpo inválido para o charset utf-8` e recusa do charset estendido. O predicado `_SEM_DECISAO` só procura ausência de decisão quando **também** `c.content_type IS NULL`.

**Limite da reprodução:** depende de um produtor chamar a API de indexação com modelo e bytes inconsistentes. Não reproduzi essa admissão pelo transporte HTTP validado, que recusa essas respostas antes do parser. Ainda assim, a candidata certifica um estado produzido pela própria API que viola expressamente a compatibilidade exigida pela 0065.

As quatro regras AST apresentaram os seguintes limites, reproduzidos com módulos injetados somente em memória:

| Regra | Padrões que escaparam do detector correspondente | Relevância |
|---|---|---|
| **1 — rede sob guarda** | `f = transport_fetch; f(url)`; `conn.resolve(ref={})`, dispensado como homônimo sem argumento posicional | Relevante para manutenção: a análise não resolve aliases nem prova a identidade do receptor. |
| **2 — indisponibilidade não engolida** | `except Unavailable as exc: ignored = exc.categoria; continue`; `if False: raise` dentro do handler | Relevante: ler a categoria ou encontrar um `raise` sintaticamente não comprova registro ou propagação. |
| **3 — interpretação única** | `str(resp.body, "latin-1")`; `from codecs import decode as read_text` seguido de `read_text(...)` | Relevante: conversões equivalentes escapam. As exceções também abrangem funções inteiras. |
| **4 — parser sem bytes crus** | Helper `raw(resp)` devolvendo `.body`; recipiente `box=(resp.body,)` seguido de `parse_x(box[0])` | Relevante: não há propagação entre funções/recipientes; todo `parsers/` é dispensado. |

Na árvore atual, os detectores retornaram **0/0/0/0**. Aplicados ao commit da rodada 13, `26bfb271`, retornaram **60/5/22/8**. Isso demonstra sensibilidade aos padrões antigos, não cobertura universal.

O estado por chamada, a classificação compartilhada e a interrupção explícita resolveram as reproduções de transporte e sincronização exercitadas. A garantia global continua limitada pelos escapes AST, pelas exclusões declaradas do cache — sessão, `sink`, expulsão LRU — e por F-26.

| Achado | Estado |
|---|---|
| **B3-01** | **Corrigido.** Chunk parcial e somente cabeçalhos: `resposta_inesperada`, status 200 preservado; hook efetivo manteve `failed`, sem `wasxfail`. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte; alteração dentro do mesmo mês gerou `data_fora_do_recorte`, exit 1. |
| **B3-03** | **Corrigido nos caminhos exercitados.** Banco, blob e novo destino interno recusados antes da abertura. Criação física de symlink/hardlink: **NOT RUN**. |
| **B3-04** | **Corrigido.** Bytes ausentes detectados; `--sem-blobs` retornou `parcial`; 2.069 blobs do tar conferidos. |
| **B3-05** | **Resolvido pela 0048 revista.** Identidade única, Planalto sem exceção, falha sem resposta como `recusa_identificado`; nenhum UA de navegador encontrado no código pesquisado. |
| **B3-06** | **Corrigido.** Mutante `999<CNJ>999`, indexado e consultado, retornou `parte_indisponivel`, texto nulo e `integra_processo_divergente`. |
| **B3-07** | **Corrigido nos negativos exercitados.** Tipo `42` e nulidade em um único elemento foram rejeitados. |

**T1/T2:** passaram os testes específicos de teto, conexão sem resposta, POST condicionado à idempotência, `Retry-After`, orçamento e breaker por falha lógica. Não reproduzi resposta iniciada sendo repetida como `fonte_fora`.

**FIX4:** passaram separação `conteudo`/`origem`, manifesto antigo, divergência de conteúdo e recusa de `--pos-instalacao` com `sync_state`. A bateria sobre o banco do próprio tar, carregado em memória e confrontado com `snapshot2/recorte-1.3.0.json`, retornou **nenhuma falha**; os blobs foram autenticados separadamente.

**Snapshot:** **665.624.795 bytes**, SHA-256 confirmado:

```text
b6921f68289a61fb35647e51397f008bebf39b3e69329ddc1e158b762ffc7fde
```

Enumerei os **2.075 membros regulares**: 2.069 caminhos `blobs/<2>/<2>/<sha256>` e:

```text
freoa-verifica-corpus-20261021.db
freoa-verifica-corpus-20261021.db.gz
verifica.sqlite3
MANIFEST.json
MANIFEST.sha256
SHA256SUMS
```

Sem duplicatas, links, travessia de caminho, `registro.key`, `instalacao.json` ou membros inesperados. Conferiram os checksums internos, os tamanhos/hashes dos blobs e a igualdade dos três bancos, após descompressão. Integridade SQLite: `ok`.

O banco contém derivados **5** e as **843 decisões de interpretação** abrangidas pela reconstrução. Os quatro logs e `reconstruir2.log` são coerentes com o artefato; `vinc.log` registra instalação vinculada. O vínculo efetivo aceitou esse digest em **1.3.0** e recusou em **1.2.0/1.4.0**.

Versões de pyproject, `__version__`, instalador e CHANGELOG conferem em 1.3.0. Workflows e instalador inspecionados atendem às decisões 0050/0051: rascunho, auditoria dos bytes antes da publicação, PyPI após `release: published` e attestation obrigatória, salvo exceção explícita registrada.

Encontrei laços fora do transporte em semente, paginação/varredura dos conectores, fallbacks, confirmação/pesquisa e ressincronização. Não reproduzi outro laço que refizesse a mesma falha contrariando a política. Na varredura estática do diff, não identifiquei cliente HTTP alternativo ou chamada a modelo de linguagem no caminho de execução. O novo falso positivo demonstrado é F-26.

**Validação e limites:** a seleção principal teve **1.043 aprovados e sete falhas de importação nos subprocessos**. Corrigido o ambiente com `PYTHONPATH`, uma seleção de **89 testes passou, exit 0**, incluindo os sete. Uma seleção intermediária teve 81 erros de preparação por fixtures indisponíveis com `--noconftest`; foi corrigida e não foi tratada como evidência do produto. Testes dependentes de escrita foram excluídos; reproduções adicionais usaram memória. Suíte completa, fontes ao vivo, reconstrução física integral independente, wheel isolada, attestation real e futuros bytes da CI: **NOT RUN**.

PARECER: COM BLOQUEADOR — IDs: F-26