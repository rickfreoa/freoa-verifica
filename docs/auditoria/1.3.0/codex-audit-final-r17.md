**F-26 corrigido nos caminhos reproduzidos. Não reproduzi novo bloqueador.** Auditei `release/1.3.0`, HEAD `b540dc5720c6e2e7d44b6aaeeb072728191e6639`, contra `239bef6`. Checkout limpo antes e depois; nenhum arquivo editado.

| ID | Severidade | Item | Arquivo:linha | Prova nesta rodada | Correção |
|---|---|---|---|---|---|
| F-26 | Alta — corrigido | Decisão obrigatória e gravação do modelo | `derivados.py:31`; `verify.py:746`; `store/repo.py:546`; `service.py:830` | Os dois negativos anteriores pela API foram recusados com `interpretacao_indisponivel`, sem alterar as contagens do banco. Estados antigos sem decisão ficaram incompatíveis, sem texto atual nem `verified`. Caminho feliz passou. Modelo e decisão legada são gravados antes do mesmo commit. | Nenhuma adicional demonstrada. |
| F-24 | Alta — corrigido nos caminhos exercitados | Releitura legada e snapshot reconstruído | `service.py:798`; `texto_resposta.py:485`; `derivados.py:26` | Reparse independente das **121 capturas Planalto**: **118 conferidas + 3 declaradas nos bytes**, sem divergência de modelo ou dos hashes de conferência. Negativos de modelo divergente e decisão ausente passaram. | Preservar a conferência obrigatória. |
| F-19 | Alta — corrigido nos casos exercitados | Validação antes de BOM, MIME e status | `texto_resposta.py:434` | Passaram charset estendido, continuações, duplicação e sintaxe inválida, inclusive com BOM/MIME binário e em 200/503. Desafio UTF-16 servido como PDF foi reconhecido. | Nenhuma adicional demonstrada. |
| F-22 | Alta — corrigido no fluxo exercitado | Persistência e reprodução da interpretação | `store/repo.py:23`; `service.py:853` | Transporte TCP local, captura, persistência em memória e parser em subprocesso preservaram **“Ação”** com header UTF-8 entre aspas e meta Latin-1 divergente. Decisão divergente foi declarada como falha. | Nenhuma adicional demonstrada. |
| F-23 | Alta — corrigido nos casos exercitados | Interrupção por fonte na ressincronização | `situacao.py:240` | CVM/BCB interromperam após CAPTCHA, 403 e falha lógica 503. Também passaram seis variantes: charset inválido em 503, UTF-8 inválido em 200 e CAPTCHA UTF-16 sob PDF, nas duas fontes. | Nenhuma adicional demonstrada. |
| F-25 | Média — persiste, sem bloqueio demonstrado | Cobertura incompleta das sentinelas AST | `tests/test_garantias_estruturais.py:347` | Reproduzi escapes nas quatro regras, conforme tabela abaixo. | Ampliar negativos e retirar a promessa de cobertura universal. |
| F-20 | Baixa — persiste | Documentação contraditória | `docs/RELEASE.md:35` | Ainda afirma que a instalação consulta a “última release”; o código consulta a release da versão instalada. | Ajustar o parágrafo à decisão 0051. |

Além dos negativos anteriores de F-26, tentei declarar o HTML cp1252 como PDF, DOCX, PNG e octet-stream: **todos foram recusados**.

As quatro regras AST retornaram **0/0/0/0** na candidata. Aplicadas ao código de `26bfb271`, retornaram **60/5/22/8**. Há sensibilidade aos defeitos antigos, mas os seguintes padrões plausíveis de manutenção escaparam dos respectivos detectores, com módulos sintéticos injetados somente em memória:

| Regra | Padrões que escaparam | Relevância |
|---|---|---|
| **1 — rede sob guarda** | `f = transport_fetch; f(url)`; `conn.resolve(ref={})` | Relevante: aliases não são resolvidos; a heurística de homônimos pode dispensar uma chamada real. |
| **2 — indisponibilidade não engolida** | Handler que apenas lê `exc.categoria` e continua; `if False: raise` | Relevante: leitura de atributo não comprova registro; presença sintática de `raise` não comprova propagação. |
| **3 — interpretação única** | `str(resp.body, "latin-1")`; `codecs.decode` importado com outro nome | Relevante: conversões equivalentes escapam. Exceções também abrangem funções inteiras. |
| **4 — parser sem bytes crus** | Helper que devolve `.body`; tupla contendo `.body`, passada como `box[0]` | Relevante: não há fluxo entre funções ou recipientes; os próprios módulos de parsers são dispensados. |

**Os mecanismos fecharam as reproduções exercitadas das classes**, sob os caminhos atuais inspecionados: estado por chamada, classificação centralizada, interpretação compartilhada, deduplicação e interrupção explícita. A AST não garante que qualquer implementação futura permanecerá dentro desses mecanismos. Também permanecem as exclusões declaradas do cache: sessão, `sink` e expulsão LRU.

| Achado B3 | Estado e reprodução |
|---|---|
| **B3-01** | **Corrigido.** Chunk parcial e somente cabeçalhos produziram `resposta_inesperada`, preservando status 200. O hook efetivo manteve `failed`, sem `wasxfail`. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte do manifesto; mudança dentro do mesmo mês gerou `data_fora_do_recorte`, exit 1. |
| **B3-03** | **Corrigido nos caminhos exercitados.** Banco, blob e destino interno novo foram recusados antes da abertura. Criação física de symlink/hardlink: **NOT RUN**; proteção por resolução e identidade de arquivo inspecionada. |
| **B3-04** | **Corrigido.** Captura sem bytes gerou `blob_ausente`; `--sem-blobs` permanece parcial. Os 2.069 blobs reais foram conferidos. |
| **B3-05** | **Resolvido pela 0048 revista.** Planalto sem exceção de identidade; falha sem resposta vira `recusa_identificado`. Nenhum UA de navegador encontrado no código pesquisado. |
| **B3-06** | **Corrigido.** O mutante com prefixo/sufixo numérico passou por indexação e `obter_decisao`, sem entregar íntegra. |
| **B3-07** | **Corrigido.** Os negativos de tipo `42` e nulidade em um único elemento foram rejeitados. |

**T1/T2:** passaram os testes específicos de 502/503/504, desafio, conexão sem resposta, POST condicionado à idempotência, `Retry-After`, orçamento e breaker contado uma vez por falha lógica. Não reproduzi resposta iniciada sendo repetida como `fonte_fora`.

**FIX4:** reproduzi separação `conteudo`/`origem`, leitura de manifesto antigo, divergência de conteúdo e recusa de `--pos-instalacao` com `sync_state`. A bateria sobre `fv-home-vinc3`, contra `snapshot2/recorte-1.3.0.json`, terminou **sem falhas**, incluindo tamanho e hash dos blobs.

O snapshot tem **665.624.795 bytes**, com SHA-256 confirmado:

```text
b6921f68289a61fb35647e51397f008bebf39b3e69329ddc1e158b762ffc7fde
```

Enumerei os **2.075 membros regulares** por `tarfile`: 2.069 caminhos `blobs/<2>/<2>/<sha256>` e:

```text
freoa-verifica-corpus-20261021.db
freoa-verifica-corpus-20261021.db.gz
verifica.sqlite3
MANIFEST.json
MANIFEST.sha256
SHA256SUMS
```

Sem duplicatas, links, travessia de caminho, `registro.key`, `instalacao.json` ou membros inesperados. Os dois bancos não compactados têm o mesmo hash.

Confirmei diretamente em `C:\dev\fv-home-vinc3`, com SQLite somente leitura:

```text
integrity_check = ok
derived_version = 5
compativel = True
capturas com modelo sem decisão = 0
decisões registradas no derivado = 843
```

Os quatro logs de `snapshot2`, `reconstruir2.log` e `vinc3.log` são coerentes com esses resultados. O vínculo efetivo aceitou o digest em **1.3.0** e recusou em **1.2.0/1.4.0**.

Versões de pyproject, `__version__`, instalador e CHANGELOG conferem em **1.3.0**. Workflows e instalador atendem, por inspeção e testes específicos, às decisões 0050/0051: release em rascunho, auditoria dos bytes antes da publicação, PyPI após `release: published` e attestation obrigatória, com exceção explícita registrada.

Na varredura do diff, examinei laços fora do transporte em semente, paginação dos conectores, fallbacks, confirmação/pesquisa, ressincronização e seleção de assets. **Não reproduzi outro laço que repetisse a mesma falha contrariando a política.** Não identifiquei cliente HTTP alternativo nem chamada a modelo de linguagem no caminho de execução. Os sete controles selecionados do manifesto de fixtures passaram.

**Validação final:** três seleções terminaram com **674, 95 e 7 testes aprovados**, todas com exit 0, além das reproduções descritas. As tentativas preliminares tiveram falhas de preparação do harness em memória e operações dependentes de disco; foram corrigidas ou excluídas, sem tratá-las como defeitos do produto.

Suíte completa, fontes oficiais ao vivo, reconstrução física integral independente, wheel isolada, attestation real e futuros bytes da CI: **NOT RUN**.

PARECER: SEM BLOQUEADOR