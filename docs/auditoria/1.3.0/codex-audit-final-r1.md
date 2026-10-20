Auditei `release/1.3.0`, HEAD **`a02e60593ebdcdbc0bfab4bedc095dcc7f0564cf`**, incluindo o diff `239bef6..HEAD`. Árvore limpa antes e depois; nenhum arquivo editado. **Persistem dois bloqueadores.**

| ID | Severidade | Item | Arquivo:linha | Prova | Correção |
|---|---|---|---|---|---|
| **F-01** | **BLOQUEADOR** | FIX3/T1: resposta iniciada ainda pode virar ambiental e ser repetida | [transport.py:811](/C:/dev/wt/INT/freoa_verifica/transport.py:811), [challenge.py:151](/C:/dev/wt/INT/freoa_verifica/connectors/challenge.py:151), [planalto.py:282](/C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:282) | Servidor local real enviou **HTTP 200 e chunk parcial**. A interrupção por baixa taxa produziu `transporte_TransporteLento`, categoria **`fonte_fora`**, evidência `status:200`; o hook real converteu em **`skipped/wasxfail`**. Na composição simulada com o Planalto, essa falha foi repetida **três vezes**. | Aplicar a distinção anterior/posterior à resposta também a `TransporteLento`; após resposta iniciada, usar `RespostaInvalida` → `resposta_inesperada`, sem repetição. Cobrir transporte → conector → hook. |
| **F-02** | **BLOQUEADOR** | T1: repetição aninhada contorna teto, orçamento e breaker | [planalto.py:271](/C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:271), [transport.py:600](/C:/dev/wt/INT/freoa_verifica/transport.py:600) | Conector e controlador reais, com respostas de rede simuladas: 503 persistente gerou **nove tentativas**, três prazos distintos e **três incrementos** no breaker. Com `Retry-After:3600`, o transporte recusou repetir, mas o conector fez novos pedidos após **2 e 4 segundos**. | Centralizar a política de repetição no transporte; eliminar o laço externo para essas falhas, preservando um único orçamento e uma contabilização lógica no breaker. |
| **F-03** | MÉDIO — divergência de especificação | FIX4 pede pendências em `origem`; decisão e implementação as excluem | [bateria.py:262](/C:/dev/wt/INT/freoa_verifica/bateria.py:262), [0057:31](/C:/dev/wt/INT/docs/decisoes/0057-bateria-do-snapshot.md:31) | Uma pendência sintética foi coletada, mas desapareceu do manifesto canônico: `origem` continha somente `recursos_ckan`. A exclusão está expressamente registrada na emenda 0057, contrariando FIX4. | Harmonizar FIX4 com a decisão adotada ou incluir e comparar as pendências em `origem`. Não bloqueia esta candidata: a conferência estrita não encontrou pendências. |

Estado dos achados anteriores:

| Achado | Estado e evidência |
|---|---|
| **B3-01** | **Parcialmente corrigido.** Timeout após chunk parcial e após somente cabeçalhos agora produz `resposta_inesperada`; o hook mantém falha. A variante por baixa taxa permanece — **F-01**. |
| **B3-02** | **Corrigido.** CLI efetiva herdou o recorte congelado; mover a data dentro do mesmo mês produziu `data_fora_do_recorte`, exit **1**. SQLite e manifesto em memória. |
| **B3-03** | **Corrigido nas reproduções.** Banco, blob e novo destino interno recusados antes da abertura do banco. Aliases symlink/hardlink também recusados com resolução/metadados simulados; criação física de links **NOT RUN**. |
| **B3-04** | **Corrigido.** Captura sem blob falhou; `--sem-blobs` retornou `parcial`. A conferência do acervo instalado autenticou os 2.069 blobs. |
| **B3-05** | **Resolvido pela nova 0048 e implementação.** Todos os conectores usam identidade única; nenhuma string de UA de navegador encontrada no código. Planalto sem resposta recebe `recusa_identificado`; 503 segue `fonte_fora`. A repetição remanescente está em **F-02**. |
| **B3-06** | **Corrigido.** O mutante `999<CNJ>999` foi rejeitado; após indexação, a resposta pública foi `parte_indisponivel`, motivo `integra_processo_divergente`. Armazenamento em memória. |
| **B3-07** | **Corrigido.** Alterar somente `itens[0].ementa` para `42` ou `null` agora reprova, identificando o elemento 0. |

**FIX4 funciona nos caminhos exercitados:** manifesto com `conteudo`/`origem`, leitura do formato antigo, origem não aplicável após instalação, rejeição de `--pos-instalacao` com `sync_state` e detecção de divergência de conteúdo. Ressalva documental em F-03.

**Versão e snapshot conferem.** `pyproject.toml`, `__version__`, instalador e CHANGELOG indicam 1.3.0. O arquivo de **665.335.352 bytes** tem exatamente:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

Esse digest consta da entrada 1.3.0; a função efetiva de vínculo aceitou-o em 1.3.0 e recusou-o em 1.2.0 e 1.4.0.

Enumerei os **2.075 membros** do tar: 2.069 blobs, `freoa-verifica-corpus-20261020.db`, sua versão `.db.gz`, `verifica.sqlite3`, `MANIFEST.json`, `MANIFEST.sha256` e `SHA256SUMS`. Sem duplicatas, links, caminhos perigosos, `registro.key`, `instalacao.json` ou arquivos fora do inventário. Todos os hashes inventariados conferiram.

Os quatro logs do supervisor são coerentes com esses bytes. Reexecutei a bateria estrita sobre `C:\dev\fv-home-vinc`: **`ok`**, 44.780 decisões, 826 obras, 2.069 blobs íntegros e zero `sync_state`. A abertura padrão foi recusada no sandbox; a repetição usou SQLite somente leitura com `immutable=1` e temporários em memória.

**Distribuição:** por inspeção e testes específicos, a release nasce em rascunho, a sequência exige auditoria dos bytes antes da publicação, `pypi.yml` depende de `release: published`, e o instalador exige attestation, salvo `-SemAttestation` explícito. Execução remota e instalação completa: **NOT RUN**; a auditoria dos futuros assets da CI continua pertencendo ao passo 6.

A seleção final terminou com **168 passed, 122 deselected**. Casos dependentes de temporários/conftests indisponíveis foram excluídos após erros de preparação, sem tratá-los como defeitos do produto. Suíte completa e fontes reais: **NOT RUN**. Na varredura do diff, não reproduzi `verified` indevido, falha convertida em zero ou contorno de controle; os desvios demonstrados estão acima.

PARECER: COM BLOQUEADOR — IDs: F-01, F-02