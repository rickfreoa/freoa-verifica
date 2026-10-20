Auditei `release/1.3.0`, HEAD **`2e4f4d600844295ab6903d994f1cef65f7ae9991`**, contra `239bef6`. Árvore limpa antes e depois; nenhum arquivo editado. **As reproduções originais de F-01, F-02 e F-03 passaram, mas há três bloqueadores adicionais.**

| ID | Severidade | Item | Arquivo:linha | Prova | Correção |
|---|---|---|---|---|---|
| F-01 | Bloqueador anterior — corrigido | Interrupção por baixa taxa após resposta iniciada | [transport.py:96](/C:/dev/wt/INT/freoa_verifica/transport.py:96) | Servidor local real com HTTP 200, byte parcial e pausa: Planalto e TJDFT fizeram **uma tentativa**, retornaram `resposta_inesperada` e permaneceram falha no hook real. | Correção efetiva nos casos originais. A repetição pela semente está em F-04. |
| F-02 | Bloqueador anterior — corrigido no Planalto | Repetição aninhada no conector | [planalto.py:269](/C:/dev/wt/INT/freoa_verifica/connectors/planalto.py:269) | Conector e transporte reais contra servidor local: 503 persistente → **3 pedidos, 1 incremento** no breaker; `Retry-After:3600` → **1 pedido, nenhuma espera**. | Laço original removido. Persistem outros caminhos abaixo. |
| F-03 | Médio anterior — corrigido | Pendências ausentes do manifesto | [bateria.py:267](/C:/dev/wt/INT/freoa_verifica/bateria.py:267) | Pendência inserida exclusivamente em SQLite em memória apareceu em `origem.pendencias`. Divergência passou sem `--estrito` e falhou com ele. Decisão 0057 harmonizada. | Nenhuma adicional para a reprodução original. |
| **F-04** | **BLOQUEADOR** | Semente mantém repetição fora do transporte | [semente.py:958](/C:/dev/wt/INT/freoa_verifica/semente.py:958), [semente.py:980](/C:/dev/wt/INT/freoa_verifica/semente.py:980) | `SementeSync.run` e Planalto reais, checkpoint em memória e servidor local: 503 persistente → **9 pedidos e 3 incrementos** no breaker; `Retry-After:3600` → **3 pedidos**. Com falhas de rede simuladas, **429 e `TransporteLento` após HTTP 200 também geraram 3 tentativas**, com três prazos distintos. `_transient` decide pelo texto, perdendo a categoria estruturada. | Remover o reagendamento automático dessas falhas na semente; centralizar a repetição no transporte. Cobrir o percurso completo `run → conector → transporte`, inclusive 429, resposta iniciada e `Retry-After`. |
| **F-05** | **BLOQUEADOR** | CVM Normas continua por outros anexos após desafio | [cvm_normas.py:210](/C:/dev/wt/INT/freoa_verifica/connectors/cvm_normas.py:210) | Com transporte simulado, um candidato com quatro representações provocou **4 chamadas após CAPTCHA/403**; também quatro após 503 com `Retry-After:3600`. Quando a segunda representação respondeu 200, `fetch` devolveu sucesso apesar do desafio anterior. **Não houve tentativa contra a CVM real.** | Propagar imediatamente desafio, recusa, falha transitória esgotada e resposta inválida. Limitar a seleção de representação alternativa a ausências explicitamente permitidas, como 404. |
| **F-06** | **BLOQUEADOR** | Erro ao ler cabeçalhos ainda vira ambiental e é repetido | [transport.py:724](/C:/dev/wt/INT/freoa_verifica/transport.py:724), [transport.py:889](/C:/dev/wt/INT/freoa_verifica/transport.py:889) | Servidor local real enviou `HTTP/1.1 200 OK` e cabeçalho com mais de 65.536 bytes. `getresponse()` levantou `LineTooLong` antes de atribuir `response`: resultado **3 pedidos**, `transporte_TransportError`, categoria **`fonte_fora`**. O hook real converteu em **`skipped/wasxfail`**. `HTTP/9.9 200 OK` reproduziu o mesmo desvio. | Distinguir erros de protocolo/cabeçalho de encerramento sem resposta. Classificá-los como `RespostaInvalida`, sem repetição, e corrigir a tabela de exceções com regressão até o hook. |

F-04 e F-05 são caminhos herdados, abrangidos pela varredura solicitada; a remoção do laço do Planalto não os alcançou.

| Achado | Estado |
|---|---|
| **B3-01** | **Casos originais corrigidos:** timeout após chunk parcial, somente cabeçalhos e vencimento na thread externa mantêm falha. A garantia geral contra falso ambiental continua incompleta por **F-06**. |
| **B3-02** | **Corrigido:** CLI efetiva herdou o recorte; mover a data dentro do mesmo mês produziu `data_fora_do_recorte`, exit 1. Banco e manifesto em memória. |
| **B3-03** | **Corrigido nas reproduções:** banco, blob e novo destino interno recusados antes da abertura. Aliases recusados com resolução/metadados simulados; criação física de links **NOT RUN**. |
| **B3-04** | **Corrigido:** ausência de bytes reprova; `--sem-blobs` produz `parcial`. Conferência real autenticou os 2.069 blobs instalados. |
| **B3-05** | **Resolvido pela nova 0048:** identidade única, sem UA de navegador no código. Planalto sem resposta → `recusa_identificado`; 503 → classificação geral. |
| **B3-06** | **Corrigido:** mutante `999<CNJ>999` rejeitado; após indexação, serviço público devolveu `parte_indisponivel` com `integra_processo_divergente`. SQLite e blobs em memória. |
| **B3-07** | **Corrigido:** os negativos `itens[0].ementa = 42` e `null` reprovam por elemento. |

FIX4 passou nos caminhos exercitados: `conteudo`/`origem`, formato antigo, comparação após instalação, rejeição de `--pos-instalacao` com `sync_state` e detecção de conteúdo divergente.

**Versão e snapshot conferem.** `pyproject.toml`, `__version__`, instalador e CHANGELOG indicam 1.3.0. O arquivo auditado tem **665.335.352 bytes** e SHA-256:

```text
995401482be861371a6bb11eb9a0c7d283e11b979c4ca5b23cb6f95bd76332fe
```

O vínculo efetivo aceitou esse digest em 1.3.0 e recusou-o em 1.2.0 e 1.4.0. Enumerei os **2.075 membros**: 2.069 blobs, dois bancos de distribuição — `.db` e `.db.gz` —, `verifica.sqlite3`, `MANIFEST.json`, `MANIFEST.sha256` e `SHA256SUMS`. Sem duplicatas, links, caminhos perigosos, `registro.key`, `instalacao.json` ou arquivos fora desse inventário. Os **2.073 hashes de `SHA256SUMS`** conferiram.

Os quatro logs do supervisor são coerentes com o snapshot. Reexecutei a bateria estrita sobre o acervo instalado: **`ok`**, 44.780 decisões, 826 obras, 2.069 blobs íntegros e zero `sync_state`, usando SQLite somente leitura com `immutable=1` e temporários em memória.

**Distribuição:** por inspeção e testes específicos, a release nasce em rascunho; a sequência exige auditoria dos bytes antes de publicar; `pypi.yml` depende de `release: published`; o instalador exige attestation, salvo `-SemAttestation` explícito. CI remota, instalação completa e verificação real de attestation: **NOT RUN**. A auditoria dos futuros assets permanece no passo 6.

A seleção final terminou com **166 passed, 117 deselected**, além das reproduções diretas descritas acima. Uma seleção intermediária teve 84 erros de preparação por fixtures/temporários indisponíveis; não foram contabilizados como defeitos do produto. Suíte completa e fontes oficiais ao vivo: **NOT RUN**. Na varredura do diff, não reproduzi `verified` indevido nem falha convertida em zero nos caminhos exercitados; reproduzi os desvios de repetição, desafio e classificação acima.

PARECER: COM BLOQUEADOR — IDs: F-04, F-05, F-06